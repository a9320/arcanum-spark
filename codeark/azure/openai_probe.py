"""Azure OpenAI 端点探针（IC27 v1 待验点：v1 端点的 Bearer vs api-key）。

背景：`codeark/models/factory.py` 走 OpenAI SDK（`Authorization: Bearer`）；
Azure OpenAI 经典路径惯用 `api-key` 头，v1 端点文档示例用 OpenAI SDK + api_key。
本探针发一条最小 chat 请求，按「v1×Bearer → v1×api-key → classic×api-key →
classic×Bearer」顺序实测，报告哪种鉴权被接受——把"待验点"变成可重跑证据。

边界：
- 只做连通性/鉴权探针，不进生产路径；
- 零密钥落盘：结果与 detail 均脱敏，脚本只打印 endpoint host；
- 200 才算成功；400/404 只说明路径或部署名问题，不代表鉴权通过。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_API_VERSION = "2024-10-21"
DEFAULT_TIMEOUT = 30.0
DEFAULT_PROMPT = "Reply with the single word: pong"
_REASON_LIMIT = 300


@dataclass(frozen=True)
class ProbeAttempt:
    path: str      # "v1" / "classic"
    auth: str      # "bearer" / "api-key"
    status: int | None
    ok: bool
    detail: str


@dataclass(frozen=True)
class ChatProbeResult:
    endpoint: str
    deployment: str
    attempts: tuple[ProbeAttempt, ...]
    content: str = ""
    usage: dict[str, Any] | None = None
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return any(a.ok for a in self.attempts)

    @property
    def auth_mode(self) -> str | None:
        for attempt in self.attempts:
            if attempt.ok:
                return attempt.auth
        return None

    @property
    def path(self) -> str | None:
        for attempt in self.attempts:
            if attempt.ok:
                return attempt.path
        return None


def _root_endpoint(endpoint: str) -> str:
    root = (endpoint or "").strip().rstrip("/")
    if not root:
        raise ValueError("Azure OpenAI endpoint 为空")
    if not root.startswith(("https://", "http://")):
        raise ValueError("Azure OpenAI endpoint 必须以 https:// 或 http:// 开头")
    suffix = "/openai/v1"
    if root.endswith(suffix):
        root = root[: -len(suffix)].rstrip("/")
    return root


def _scrub(text: object, key: str) -> str:
    t = str(text)
    if key:
        t = t.replace(key, "***")
    t = " ".join(t.split())
    return t[:_REASON_LIMIT] + ("…" if len(t) > _REASON_LIMIT else "")


def _parse_success(data: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    content = ""
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            value = message.get("content")
            if isinstance(value, str):
                content = value
            elif value is not None:
                content = str(value)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
    return content, usage


def probe_chat_completion(
    *,
    endpoint: str,
    key: str,
    deployment: str,
    prompt: str = DEFAULT_PROMPT,
    api_version: str = DEFAULT_API_VERSION,
    timeout: float = DEFAULT_TIMEOUT,
    transport: httpx.BaseTransport | None = None,
) -> ChatProbeResult:
    """按 v1/classic × Bearer/api-key 顺序探测；返回全部尝试与首个成功结果。"""
    key = (key or "").strip()
    deployment = (deployment or "").strip()
    if not key:
        raise ValueError("Azure OpenAI key 为空")
    if not deployment:
        raise ValueError("Azure OpenAI deployment 为空")
    root = _root_endpoint(endpoint)
    v1_url = f"{root}/openai/v1/chat/completions"
    classic_url = (
        f"{root}/openai/deployments/{quote(deployment)}/chat/completions"
        f"?api-version={quote(api_version)}"
    )
    payload = {"model": deployment, "messages": [{"role": "user", "content": prompt}]}
    plan = (
        ("v1", "bearer", v1_url),
        ("v1", "api-key", v1_url),
        ("classic", "api-key", classic_url),
        ("classic", "bearer", classic_url),
    )

    attempts: list[ProbeAttempt] = []
    content = ""
    usage: dict[str, Any] | None = None
    started = time.perf_counter()
    with httpx.Client(timeout=timeout, transport=transport) as client:
        for path, auth, url in plan:
            headers = {"Content-Type": "application/json"}
            if auth == "bearer":
                headers["Authorization"] = f"Bearer {key}"
            else:
                headers["api-key"] = key
            try:
                resp = client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                attempts.append(ProbeAttempt(
                    path, auth, None, False, _scrub(f"{type(exc).__name__}: {exc}", key)
                ))
                continue
            if 200 <= resp.status_code < 300:
                try:
                    data = resp.json()
                except ValueError:
                    attempts.append(ProbeAttempt(path, auth, resp.status_code, False,
                                                 "200 但响应不是 JSON"))
                    continue
                if not isinstance(data, dict):
                    attempts.append(ProbeAttempt(path, auth, resp.status_code, False,
                                                 "200 但响应顶层不是对象"))
                    continue
                content, usage = _parse_success(data)
                attempts.append(ProbeAttempt(path, auth, resp.status_code, True, "ok"))
                break
            attempts.append(ProbeAttempt(
                path, auth, resp.status_code, False,
                _scrub(f"HTTP {resp.status_code}: {resp.text}", key),
            ))
    return ChatProbeResult(
        endpoint=root,
        deployment=deployment,
        attempts=tuple(attempts),
        content=content,
        usage=usage,
        elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
    )
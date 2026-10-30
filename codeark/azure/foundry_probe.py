"""Azure AI Foundry 模型推理探针（非 OpenAI 模型：Phi-4 等）。

与 `openai_probe` 的区别：Foundry 的 serverless 模型不挂在 `*.openai.azure.com`，而是
`https://<resource>.services.ai.azure.com` 下的 `/models/chat/completions`，鉴权用
`api-key` 头（或 Entra Bearer），请求体里带 `model` 字段。三种形状都试一遍，200 即停。

env 契约：
  ARCA_FOUNDRY_ENDPOINT      必需  形如 https://<res>.services.ai.azure.com（可带 /models）
  ARCA_FOUNDRY_KEY           必需  资源密钥；repr/原因中脱敏
  ARCA_FOUNDRY_DEPLOYMENT    必需  部署名（门户里那个名字，不是模型名）
  ARCA_FOUNDRY_API_VERSION   可选  默认 2024-05-01-preview
  ARCA_FOUNDRY_TIMEOUT       可选  秒，默认 20

零联网保证：构造不发请求；测试全 MockTransport。
"""
from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

ENDPOINT_ENV = "ARCA_FOUNDRY_ENDPOINT"
KEY_ENV = "ARCA_FOUNDRY_KEY"
DEPLOYMENT_ENV = "ARCA_FOUNDRY_DEPLOYMENT"
API_VERSION_ENV = "ARCA_FOUNDRY_API_VERSION"
TIMEOUT_ENV = "ARCA_FOUNDRY_TIMEOUT"

DEFAULT_API_VERSION = "2024-05-01-preview"
DEFAULT_TIMEOUT = 20.0
_REQUIRED_ENVS = (ENDPOINT_ENV, KEY_ENV, DEPLOYMENT_ENV)
_REASON_LIMIT = 240
_PROMPT = "Reply with the single word: ok"


class _CallFailed(Exception):
    """内部：一次调用失败（已脱敏）。"""


@dataclass(frozen=True)
class FoundryAttempt:
    path: str
    auth: str
    status: int | None
    ok: bool
    elapsed_ms: float
    detail: str = ""


@dataclass(frozen=True)
class FoundryProbeResult:
    ok: bool
    path: str = ""
    auth: str = ""
    reply: str = ""
    attempts: tuple[FoundryAttempt, ...] = ()
    degraded: bool = True
    reason: str = ""


@dataclass(frozen=True)
class FoundryStatus:
    configured: bool
    missing: tuple[str, ...]
    endpoint_host: str
    deployment: str
    api_version: str


def status_from_env(env: Mapping[str, str] | None = None) -> FoundryStatus:
    e = os.environ if env is None else env
    missing = tuple(name for name in _REQUIRED_ENVS if not (e.get(name) or "").strip())
    endpoint = (e.get(ENDPOINT_ENV) or "").strip()
    host = ""
    if endpoint:
        try:
            host = urlsplit(endpoint).netloc
        except ValueError:
            host = ""
    return FoundryStatus(
        configured=not missing,
        missing=missing,
        endpoint_host=host,
        deployment=(e.get(DEPLOYMENT_ENV) or "").strip(),
        api_version=(e.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION,
    )


class FoundryClient:
    def __init__(
        self,
        *,
        endpoint: str,
        key: str,
        deployment: str,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        endpoint = (endpoint or "").strip().rstrip("/")
        key = (key or "").strip()
        deployment = (deployment or "").strip()
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("Foundry endpoint 必须以 https:// 或 http:// 开头")
        if not key or not deployment:
            raise ValueError("Foundry key/deployment 不能为空")
        self.endpoint = endpoint
        self.deployment = deployment
        self.api_version = (api_version or "").strip() or DEFAULT_API_VERSION
        self._key = key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def __repr__(self) -> str:
        return (
            f"FoundryClient(endpoint={self.endpoint!r}, deployment={self.deployment!r}, "
            f"api_version={self.api_version!r})"
        )

    def __enter__(self) -> FoundryClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> FoundryClient | None:
        e = os.environ if env is None else env
        if status_from_env(e).missing:
            return None
        try:
            timeout = float(e.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        return cls(
            endpoint=(e.get(ENDPOINT_ENV) or "").strip(),
            key=(e.get(KEY_ENV) or "").strip(),
            deployment=(e.get(DEPLOYMENT_ENV) or "").strip(),
            api_version=(e.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION,
            timeout=timeout if timeout > 0 else DEFAULT_TIMEOUT,
            transport=transport,
        )

    def _scrub(self, text: object) -> str:
        t = str(text).replace(self._key, "***") if self._key else str(text)
        t = " ".join(t.split())
        return t[: _REASON_LIMIT] + ("…" if len(t) > _REASON_LIMIT else "")

    def _base(self) -> str:
        # 允许用户把 /models 直接写进 endpoint，避免拼成 /models/models
        return self.endpoint[: -len("/models")] if self.endpoint.endswith("/models") else self.endpoint

    def _shapes(self) -> Sequence[tuple[str, str, dict[str, str], dict[str, Any]]]:
        base = self._base()
        body = {
            "messages": [{"role": "user", "content": _PROMPT}],
            "model": self.deployment,
            "max_tokens": 16,
        }
        return (
            ("models", f"{base}/models/chat/completions",
             {"api-key": self._key}, body),
            ("models-bearer", f"{base}/models/chat/completions",
             {"Authorization": f"Bearer {self._key}"}, body),
            ("openai-v1", f"{base}/openai/v1/chat/completions",
             {"Authorization": f"Bearer {self._key}"},
             {"messages": [{"role": "user", "content": _PROMPT}], "max_tokens": 16}),
        )

    def probe(self, *, stop_on_first: bool = True) -> FoundryProbeResult:
        """按 models/api-key → models/bearer → openai-v1/bearer 顺序试；200 即停。"""
        attempts: list[FoundryAttempt] = []
        for name, url, headers, body in self._shapes():
            t0 = time.perf_counter()
            status: int | None = None
            detail = ""
            reply = ""
            try:
                resp = self._client.post(
                    url,
                    params={"api-version": self.api_version},
                    headers={**headers, "Content-Type": "application/json"},
                    json=body,
                )
                status = resp.status_code
                if status // 100 == 2:
                    data = resp.json()
                    reply = _first_text(data)
                    attempts.append(FoundryAttempt(name, "api-key" if "api-key" in headers else "bearer",
                                                   status, True, _ms(t0), ""))
                    return FoundryProbeResult(
                        ok=True, path=name,
                        auth="api-key" if "api-key" in headers else "bearer",
                        reply=reply[:200], attempts=tuple(attempts),
                        degraded=False, reason="",
                    )
                detail = self._scrub(f"HTTP {status}: {resp.text}")
            except httpx.HTTPError as exc:
                detail = self._scrub(f"{type(exc).__name__}: {exc}")
            except ValueError:
                detail = "响应不是合法 JSON"
            attempts.append(FoundryAttempt(name, "api-key" if "api-key" in headers else "bearer",
                                           status, False, _ms(t0), detail))
            if not stop_on_first and status is None:
                continue
        last = attempts[-1].detail if attempts else "no attempt"
        return FoundryProbeResult(ok=False, attempts=tuple(attempts), degraded=True,
                                  reason=f"三种形状均失败；最后一条：{last}")


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _first_text(data: Any) -> str:
    try:
        choices = data["choices"]
        message = choices[0]["message"]["content"]
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            return " ".join(str(part.get("text", "")) for part in message if isinstance(part, dict))
    except (KeyError, IndexError, TypeError):
        return ""
    return ""
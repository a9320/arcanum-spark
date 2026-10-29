"""Azure AI Language v0 客户端（IC27 P0：双服务的第二件——证据 PII 脱敏门）。

定位：同一引擎的 Azure 云版/生态门的第二个承重件。模型面证据（被扫描仓的代码与
报告摘录，可能含客户 PII）在离开本机前先经 Language 的 PII 实体识别脱敏。
与 Content Safety 同构：窄客户端 + env 门控 + fail-closed，构造零联网。

失败语义（fail-closed）：
- 未配置 → from_env() 返回 None；status_from_env() 提供机读状态入报告。
- HTTP/协议失败、响应缺字段、单文档超长 → 该文档 degraded=True 且
  redacted_text=None（**未知 ≠ 已脱敏**）；调用方不得把未脱敏原文当成脱敏结果。

env 契约：
  ARCA_AZURE_LANGUAGE_ENDPOINT     必需  https://<res>.cognitiveservices.azure.com
  ARCA_AZURE_LANGUAGE_KEY          必需  资源密钥；repr/异常/降级原因均脱敏
  ARCA_AZURE_LANGUAGE_API_VERSION  可选  默认 2024-11-01
  ARCA_AZURE_LANGUAGE_TIMEOUT      可选  秒，默认 10

接口：POST {endpoint}/language/:analyze-text?api-version=...
      body.kind=PiiEntityRecognition，文档按 ≤5 篇/请求分批。
stringIndexType 固定 UnicodeCodePoint：offset/length 可直接用于 Python 切片
（本地回退脱敏只靠 offset/length，且**不保存实体原文**，避免 PII 二次落盘）。
"""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

ENDPOINT_ENV = "ARCA_AZURE_LANGUAGE_ENDPOINT"
KEY_ENV = "ARCA_AZURE_LANGUAGE_KEY"
API_VERSION_ENV = "ARCA_AZURE_LANGUAGE_API_VERSION"
TIMEOUT_ENV = "ARCA_AZURE_LANGUAGE_TIMEOUT"

DEFAULT_API_VERSION = "2024-11-01"
DEFAULT_TIMEOUT = 10.0
DEFAULT_LANGUAGE = "en"
MAX_DOCS_PER_REQUEST = 5
MAX_DOC_CHARS = 5000  # 服务端单文档上限 5,120 字符，留余量
_REQUIRED_ENVS = (ENDPOINT_ENV, KEY_ENV)
_REASON_LIMIT = 240
_MASK = "[REDACTED:{}]"


class _CallFailed(Exception):
    """内部：一次 HTTP 调用失败（已脱敏）。对外只体现为 degraded 结果。"""


@dataclass(frozen=True)
class PiiEntity:
    """PII 实体（**不含原文**：category/位置/置信度足以脱敏且可安全入报告）。"""

    category: str
    sub_category: str = ""
    offset: int = 0
    length: int = 0
    confidence: float = 0.0


@dataclass(frozen=True)
class RedactedDocument:
    """单文档脱敏结果。redacted_text=None 表示未知（降级），**不等于原文干净**。"""

    doc_id: str
    redacted_text: str | None = None
    entities: tuple[PiiEntity, ...] = ()
    degraded: bool = False
    reason: str = ""


@dataclass(frozen=True)
class RedactionResult:
    """批级结果。degraded=True 时至少一篇 redacted_text=None。"""

    documents: tuple[RedactedDocument, ...] = ()
    degraded: bool = False
    reason: str = ""
    batches: int = 0

    @property
    def entity_counts(self) -> dict[str, int]:
        """category→计数（只含类别，不含原文；报告元数据用）。"""
        counts: dict[str, int] = {}
        for doc in self.documents:
            for ent in doc.entities:
                counts[ent.category] = counts.get(ent.category, 0) + 1
        return dict(sorted(counts.items()))

    def redacted_map(self) -> dict[str, str]:
        """仅成功脱敏的文档；调用方必须另行检查 degraded_ids() 并扣留它们。"""
        return {
            doc.doc_id: doc.redacted_text
            for doc in self.documents
            if doc.redacted_text is not None
        }

    def degraded_ids(self) -> tuple[str, ...]:
        return tuple(
            doc.doc_id for doc in self.documents if doc.degraded or doc.redacted_text is None
        )


@dataclass(frozen=True)
class LanguageStatus:
    """机读配置状态：报告元数据用它显式记录「未配置」，避免静默跳过。"""

    configured: bool
    missing: tuple[str, ...]
    endpoint_host: str
    api_version: str


def status_from_env(env: Mapping[str, str] | None = None) -> LanguageStatus:
    """读取 env 契约并给出可入报告的配置状态（不构造客户端、零联网）。"""
    e = os.environ if env is None else env
    missing = tuple(name for name in _REQUIRED_ENVS if not (e.get(name) or "").strip())
    endpoint = (e.get(ENDPOINT_ENV) or "").strip()
    host = ""
    if endpoint:
        try:
            host = urlsplit(endpoint).netloc
        except ValueError:
            host = ""
    return LanguageStatus(
        configured=not missing,
        missing=missing,
        endpoint_host=host,
        api_version=(e.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION,
    )


class LanguageClient:
    """Azure AI Language 窄客户端（v0：PII 实体识别 + 脱敏文本）。"""

    def __init__(
        self,
        *,
        endpoint: str,
        key: str,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        endpoint = (endpoint or "").strip().rstrip("/")
        key = (key or "").strip()
        if not endpoint:
            raise ValueError("Language endpoint 为空")
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("Language endpoint 必须以 https:// 或 http:// 开头")
        if not key:
            raise ValueError("Language key 为空")
        self.endpoint = endpoint
        self.api_version = (api_version or "").strip() or DEFAULT_API_VERSION
        self._key = key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    # 密钥绝不进 repr / 日志
    def __repr__(self) -> str:
        return (
            f"LanguageClient(endpoint={self.endpoint!r}, "
            f"api_version={self.api_version!r})"
        )

    def __enter__(self) -> LanguageClient:
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
    ) -> LanguageClient | None:
        """两个必需条件齐全才返回客户端；缺项返回 None（调用方用 status_from_env 记账）。"""
        e = os.environ if env is None else env
        endpoint = (e.get(ENDPOINT_ENV) or "").strip()
        key = (e.get(KEY_ENV) or "").strip()
        if not endpoint or not key:
            return None
        try:
            timeout = float(e.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT
        if timeout <= 0:
            timeout = DEFAULT_TIMEOUT
        api_version = (e.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION
        return cls(
            endpoint=endpoint,
            key=key,
            api_version=api_version,
            timeout=timeout,
            transport=transport,
        )

    # ── 公开接口 ──

    def redact_texts(
        self,
        texts: Mapping[str, str],
        *,
        language: str = DEFAULT_LANGUAGE,
    ) -> RedactionResult:
        """批量 PII 脱敏。doc_id 用调用方键名（文件路径等），顺序确定。"""
        docs: list[RedactedDocument] = []
        reasons: list[str] = []
        degraded = False
        batches = 0
        pending: list[tuple[str, str]] = []
        for doc_id, text in texts.items():
            if len(text) > MAX_DOC_CHARS:
                docs.append(
                    RedactedDocument(
                        doc_id=doc_id,
                        degraded=True,
                        reason=f"超长文档（>{MAX_DOC_CHARS} 字符），未送服务",
                    )
                )
                degraded = True
                reasons.append(f"{doc_id}: 超长")
            else:
                pending.append((doc_id, text))

        for start in range(0, len(pending), MAX_DOCS_PER_REQUEST):
            chunk = pending[start : start + MAX_DOCS_PER_REQUEST]
            batches += 1
            try:
                payload = self._post_analyze(chunk, language)
            except _CallFailed as exc:
                for doc_id, _ in chunk:
                    docs.append(RedactedDocument(doc_id=doc_id, degraded=True, reason=str(exc)))
                degraded = True
                reasons.append(str(exc))
                continue
            parsed, chunk_degraded, chunk_reason = self._parse_chunk(payload, chunk)
            docs.extend(parsed)
            degraded = degraded or chunk_degraded
            if chunk_degraded:
                reasons.append(chunk_reason)

        order = {doc_id: i for i, doc_id in enumerate(texts)}
        docs.sort(key=lambda d: order.get(d.doc_id, len(order)))
        return RedactionResult(
            documents=tuple(docs),
            degraded=degraded,
            reason="; ".join(dict.fromkeys(r for r in reasons if r))[: _REASON_LIMIT * 2],
            batches=batches,
        )

    # ── 内部 ──

    def _scrub(self, text: object) -> str:
        """脱敏 + 压平 + 截断：降级原因会进报告，密钥与超长响应体不得外泄。"""
        t = str(text)
        if self._key:
            t = t.replace(self._key, "***")
        t = " ".join(t.split())
        return t[: _REASON_LIMIT] + ("…" if len(t) > _REASON_LIMIT else "")

    def _post_analyze(
        self, chunk: Sequence[tuple[str, str]], language: str
    ) -> dict[str, Any]:
        url = f"{self.endpoint}/language/:analyze-text"
        payload = {
            "kind": "PiiEntityRecognition",
            "analysisInput": {
                "documents": [
                    {"id": doc_id, "language": language or DEFAULT_LANGUAGE, "text": text}
                    for doc_id, text in chunk
                ]
            },
            "parameters": {"stringIndexType": "UnicodeCodePoint"},
        }
        try:
            resp = self._client.post(
                url,
                params={"api-version": self.api_version},
                headers={
                    "Ocp-Apim-Subscription-Key": self._key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise _CallFailed(self._scrub(f"{type(exc).__name__}: {exc}")) from None
        if resp.status_code // 100 != 2:
            raise _CallFailed(self._scrub(f"HTTP {resp.status_code}: {resp.text}"))
        try:
            data = resp.json()
        except ValueError:
            raise _CallFailed("响应不是合法 JSON") from None
        if not isinstance(data, dict):
            raise _CallFailed("响应 JSON 顶层不是对象")
        return data

    def _parse_chunk(
        self, data: dict[str, Any], chunk: Sequence[tuple[str, str]]
    ) -> tuple[list[RedactedDocument], bool, str]:
        results = data.get("results")
        if not isinstance(results, dict):
            return (
                [RedactedDocument(doc_id=d, degraded=True, reason="响应缺 results") for d, _ in chunk],
                True,
                "响应缺 results",
            )
        entries = results.get("documents")
        entries = entries if isinstance(entries, list) else []
        errors = results.get("errors")
        error_ids: set[str] = set()
        if isinstance(errors, list):
            for err in errors:
                if isinstance(err, dict) and isinstance(err.get("id"), str):
                    error_ids.add(err["id"])
        by_id = {
            entry.get("id"): entry
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        }

        parsed: list[RedactedDocument] = []
        degraded = False
        reason = ""
        for doc_id, original in chunk:
            if doc_id in error_ids:
                parsed.append(RedactedDocument(doc_id=doc_id, degraded=True, reason="服务端逐文档错误"))
                degraded, reason = True, "服务端逐文档错误"
                continue
            entry = by_id.get(doc_id)
            if entry is None:
                parsed.append(RedactedDocument(doc_id=doc_id, degraded=True, reason="响应缺该文档结果"))
                degraded, reason = True, "响应缺文档结果"
                continue
            entities = self._parse_entities(entry.get("entities"))
            if entities is None:
                parsed.append(
                    RedactedDocument(doc_id=doc_id, degraded=True, reason="entities 字段类型不符")
                )
                degraded, reason = True, "entities 字段类型不符"
                continue
            redacted = entry.get("redactedText")
            if not isinstance(redacted, str):
                # 服务端没给脱敏文本时，用 offset/length 本地回退（仍是真的脱敏）
                redacted = _mask_by_offsets(original, entities) if entities else None
                if redacted is None:
                    parsed.append(
                        RedactedDocument(
                            doc_id=doc_id,
                            entities=entities,
                            degraded=True,
                            reason="响应缺 redactedText 且无实体可用",
                        )
                    )
                    degraded, reason = True, "缺 redactedText"
                    continue
            parsed.append(
                RedactedDocument(doc_id=doc_id, redacted_text=redacted, entities=entities)
            )
        return parsed, degraded, reason

    @staticmethod
    def _parse_entities(raw: Any) -> tuple[PiiEntity, ...] | None:
        if raw is None:
            return ()
        if not isinstance(raw, list):
            return None
        out: list[PiiEntity] = []
        for item in raw:
            if not isinstance(item, dict):
                return None
            category = item.get("category")
            offset = item.get("offset", 0)
            length = item.get("length", 0)
            confidence = item.get("confidenceScore", 0.0)
            if not isinstance(category, str) or not isinstance(offset, int) or not isinstance(
                length, int
            ):
                return None
            if isinstance(offset, bool) or isinstance(length, bool):
                return None
            try:
                score = float(confidence)
            except (TypeError, ValueError):
                score = 0.0
            sub = item.get("subcategory")
            out.append(
                PiiEntity(
                    category=category,
                    sub_category=sub if isinstance(sub, str) else "",
                    offset=offset,
                    length=length,
                    confidence=score,
                )
            )
        return tuple(out)


def _mask_by_offsets(text: str, entities: Sequence[PiiEntity]) -> str | None:
    """按 offset/length 原地打码（只用于服务端未返回 redactedText 的回退）。"""
    spans = sorted(
        {
            (e.offset, e.length, e.category)
            for e in entities
            if 0 <= e.offset < len(text)
            and e.length > 0
            and e.offset + e.length <= len(text)
        },
        reverse=True,
    )
    if not spans:
        return None
    out = text
    for offset, length, category in spans:
        out = out[:offset] + _MASK.format(category) + out[offset + length :]
    return out
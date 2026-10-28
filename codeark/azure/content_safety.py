"""Azure AI Content Safety v0 客户端（IC27 P0：Azure 双服务接线的通用基线侧）。

定位：一个引擎多扇门里 Azure 云版/生态门共用件，也是「双路裁决」的通用基线——
Content Safety（Prompt Shields + 文本危害）对比代码场景确定性规则（PITAX）。

v0 边界：只做**窄客户端 + 显式降级**，任何主链路（verify/scout）接线留 v1，
须真实凭据端到端验证后才进生产路径。设计见 docs/AZURE-INTEGRATION.md。

接口：
- shield_prompt(user_prompt, documents) → Prompt Shields（越狱/注入，双路裁决通用基线）
- analyze_text(text, categories)        → 四类危害严重度（0-7）

失败语义（fail-closed）：
- 未配置 → from_env() 返回 None；调用方必须把「未配置」写进报告元数据，
  不得静默跳过（status_from_env() 提供机读状态）。
- HTTP/协议失败 → degraded=True 且判定值为 None（**不是 False**）。
  None 绝不等于 clean，聚合层不得把未知当清白。

env 契约：
  ARCA_AZURE_CONTENT_SAFETY_ENDPOINT     必需  例 https://<res>.cognitiveservices.azure.com
  ARCA_AZURE_CONTENT_SAFETY_KEY          必需  资源密钥；repr/异常/降级原因均脱敏
  ARCA_AZURE_CONTENT_SAFETY_API_VERSION  可选  默认 2024-09-01
  ARCA_AZURE_CONTENT_SAFETY_TIMEOUT      可选  秒，默认 10

鉴权：v0 用资源密钥头 Ocp-Apim-Subscription-Key（最通用、可离线自测）。
AAD/Managed Identity + Key Vault 是 v1 的 Azure 底盘形态，不影响本模块接口。

零联网保证：构造零网络；只有显式调用两个方法才发请求，且 CI 用
httpx.MockTransport 全量替身（tests/test_azure_content_safety.py）。
"""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

ENDPOINT_ENV = "ARCA_AZURE_CONTENT_SAFETY_ENDPOINT"
KEY_ENV = "ARCA_AZURE_CONTENT_SAFETY_KEY"
API_VERSION_ENV = "ARCA_AZURE_CONTENT_SAFETY_API_VERSION"
TIMEOUT_ENV = "ARCA_AZURE_CONTENT_SAFETY_TIMEOUT"

DEFAULT_API_VERSION = "2024-09-01"
DEFAULT_TIMEOUT = 10.0
_REQUIRED_ENVS = (ENDPOINT_ENV, KEY_ENV)
_REASON_LIMIT = 240


class _CallFailed(Exception):
    """内部：一次 HTTP 调用失败（已脱敏）。对外只体现为 degraded 结果。"""


@dataclass(frozen=True)
class ShieldPromptResult:
    """Prompt Shields 结果。None = 未知（降级），**不等于 clean**。"""

    user_prompt_attack: bool | None
    documents_attack: tuple[bool | None, ...] = ()
    degraded: bool = False
    reason: str = ""

    @property
    def attack_detected(self) -> bool | None:
        """任一输入命中 → True；全部为 False → False；存在未知 → None。"""
        values = (self.user_prompt_attack, *self.documents_attack)
        if any(v is True for v in values):
            return True
        if any(v is None for v in values):
            return None
        return False


@dataclass(frozen=True)
class CategorySeverity:
    category: str
    severity: int


@dataclass(frozen=True)
class TextAnalysisResult:
    """文本危害分析结果。degraded=True 时 max_severity 为 None（未知非零）。"""

    categories: tuple[CategorySeverity, ...] = ()
    degraded: bool = False
    reason: str = ""

    @property
    def max_severity(self) -> int | None:
        if self.degraded:
            return None
        return max((c.severity for c in self.categories), default=0)


@dataclass(frozen=True)
class ContentSafetyStatus:
    """机读配置状态：报告元数据用它显式记录「未配置」，避免静默跳过。"""

    configured: bool
    missing: tuple[str, ...]
    endpoint_host: str
    api_version: str


def status_from_env(env: Mapping[str, str] | None = None) -> ContentSafetyStatus:
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
    return ContentSafetyStatus(
        configured=not missing,
        missing=missing,
        endpoint_host=host,
        api_version=(e.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION,
    )


class ContentSafetyClient:
    """Azure AI Content Safety 窄客户端（v0：shieldPrompt + text:analyze）。"""

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
            raise ValueError("Content Safety endpoint 为空")
        if not endpoint.startswith(("https://", "http://")):
            raise ValueError("Content Safety endpoint 必须以 https:// 或 http:// 开头")
        if not key:
            raise ValueError("Content Safety key 为空")
        self.endpoint = endpoint
        self.api_version = (api_version or "").strip() or DEFAULT_API_VERSION
        self._key = key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    # 密钥绝不进 repr / 日志
    def __repr__(self) -> str:
        return (
            f"ContentSafetyClient(endpoint={self.endpoint!r}, "
            f"api_version={self.api_version!r})"
        )

    def __enter__(self) -> ContentSafetyClient:
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
    ) -> ContentSafetyClient | None:
        """三个必需条件齐全才返回客户端；缺项返回 None（调用方用 status_from_env 记账）。"""
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

    def shield_prompt(
        self,
        user_prompt: str,
        documents: Sequence[str] = (),
    ) -> ShieldPromptResult:
        """Prompt Shields：检测用户提示与文档中的越狱/注入攻击。"""
        docs = list(documents or ())
        payload: dict[str, Any] = {"userPrompt": user_prompt or "", "documents": docs}
        try:
            data = self._post_json("text:shieldPrompt", payload)
        except _CallFailed as exc:
            return ShieldPromptResult(None, tuple(None for _ in docs), True, str(exc))

        analysis = data.get("userPromptAnalysis")
        if not isinstance(analysis, dict) or not isinstance(
            analysis.get("attackDetected"), bool
        ):
            return ShieldPromptResult(
                None, tuple(None for _ in docs), True,
                "响应缺 userPromptAnalysis.attackDetected",
            )
        entries = data.get("documentsAnalysis")
        entries = entries if isinstance(entries, list) else []
        flags: list[bool | None] = []
        for i in range(len(docs)):
            entry = entries[i] if i < len(entries) else None
            flag = entry.get("attackDetected") if isinstance(entry, dict) else None
            flags.append(flag if isinstance(flag, bool) else None)
        degraded = any(flag is None for flag in flags)
        return ShieldPromptResult(
            analysis["attackDetected"],
            tuple(flags),
            degraded,
            "文档分析结果缺失或类型不符" if degraded else "",
        )

    def analyze_text(
        self,
        text: str,
        categories: Sequence[str] | None = None,
    ) -> TextAnalysisResult:
        """文本危害分析：返回各 category 的严重度（0-7）。"""
        payload: dict[str, Any] = {"text": text or ""}
        if categories:
            payload["categories"] = list(categories)
        try:
            data = self._post_json("text:analyze", payload)
        except _CallFailed as exc:
            return TextAnalysisResult((), True, str(exc))

        entries = data.get("categoriesAnalysis")
        if not isinstance(entries, list) or not entries:
            return TextAnalysisResult((), True, "响应缺 categoriesAnalysis")
        parsed: list[CategorySeverity] = []
        for entry in entries:
            if not isinstance(entry, dict):
                return TextAnalysisResult(tuple(parsed), True, "categoriesAnalysis 条目类型不符")
            category = entry.get("category")
            severity = entry.get("severity")
            if not isinstance(category, str) or not isinstance(severity, int) or isinstance(
                severity, bool
            ):
                return TextAnalysisResult(tuple(parsed), True, "category/severity 字段缺失或类型不符")
            parsed.append(CategorySeverity(category, severity))
        return TextAnalysisResult(tuple(parsed))

    # ── 内部 ──

    def _scrub(self, text: object) -> str:
        """脱敏 + 压平 + 截断：降级原因会进报告，密钥与超长响应体不得外泄。"""
        t = str(text)
        if self._key:
            t = t.replace(self._key, "***")
        t = " ".join(t.split())
        return t[: _REASON_LIMIT] + ("…" if len(t) > _REASON_LIMIT else "")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.endpoint}/contentsafety/{path}"
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
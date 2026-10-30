"""Azure 集成层（IC27 P0）：同一引擎的 Azure 云版/生态门共用件。

v0：Content Safety 与 Azure AI Language 两个窄客户端（env 门控 / fail-closed）、
Azure OpenAI 鉴权探针、主链路前哨 gate（默认关）；
Azure OpenAI 生产调用走既有四岗 env 路由（codeark/models/factory.py 的
ARCA_<STAGE>_* 覆盖），不在此重复实现。
设计依据与 v0/v1 边界见 docs/AZURE-INTEGRATION.md。
"""
from .content_safety import (
    CategorySeverity,
    ContentSafetyClient,
    ContentSafetyStatus,
    ShieldPromptResult,
    TextAnalysisResult,
    status_from_env,
)
from .language import (
    LanguageClient,
    LanguageStatus,
    PiiEntity,
    RedactedDocument,
    RedactionResult,
)
from .language import status_from_env as language_status_from_env
from .foundry_probe import (
    FoundryAttempt,
    FoundryClient,
    FoundryProbeResult,
    FoundryStatus,
)
from .foundry_probe import status_from_env as foundry_status_from_env
from .openai_probe import ChatProbeResult, ProbeAttempt, probe_chat_completion
from .preflight import GateOutcome, run_azure_gate

__all__ = [
    "CategorySeverity",
    "ChatProbeResult",
    "ContentSafetyClient",
    "ContentSafetyStatus",
    "FoundryAttempt",
    "FoundryClient",
    "FoundryProbeResult",
    "FoundryStatus",
    "GateOutcome",
    "LanguageClient",
    "LanguageStatus",
    "PiiEntity",
    "ProbeAttempt",
    "RedactedDocument",
    "RedactionResult",
    "ShieldPromptResult",
    "TextAnalysisResult",
    "foundry_status_from_env",
    "language_status_from_env",
    "probe_chat_completion",
    "run_azure_gate",
    "status_from_env",
]
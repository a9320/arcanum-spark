"""Azure 集成层（IC27 P0）：同一引擎的 Azure 云版/生态门共用件。

v0 只有 Content Safety 窄客户端；Azure OpenAI 走既有四岗 env 路由
（codeark/models/factory.py 的 ARCA_<STAGE>_* 覆盖），不在此重复实现。
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

__all__ = [
    "CategorySeverity",
    "ContentSafetyClient",
    "ContentSafetyStatus",
    "ShieldPromptResult",
    "TextAnalysisResult",
    "status_from_env",
]
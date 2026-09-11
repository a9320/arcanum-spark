"""Pydantic 数据模型 — Agent A（侦察）的结构化输出契约。

设计原则（整合版蓝图 §7）：
- 用 Literal 枚举约束 confidence（high/medium/low），杜绝模型乱填越界；
- coverage_notes 强迫模型汇报扫描盲区，避免静默漏目录；
- 每个假设必须携带 suggested_verification，为验证 Agent 提供明确工具方向。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "VulnHypothesis",
    "HypothesisSet",
    "VerificationResult",
    "VerificationSet",
    "AttackChain",
    "FinalReport",
    "AgentHandoff",
]


# ────────────────────────── Agent A 输出 ──────────────────────────
class VulnHypothesis(BaseModel):
    """侦察 Agent 提出的单条漏洞假设（尚未验证，仅候选）。"""

    title: str = Field(description="假设的简要标题")
    vuln_type: str = Field(
        description="漏洞类型，如 SQL_INJECTION / COMMAND_INJECTION / PATH_TRAVERSAL"
    )
    file_path: str = Field(description="可疑文件路径（仓库相对路径）")
    line_start: int = Field(description="起始行号")
    line_end: int = Field(description="结束行号")
    code_snippet: str = Field(description="相关代码片段")
    attack_path: str = Field(description="推测的攻击路径说明")
    confidence: Literal["high", "medium", "low"] = Field(
        description="模型对假设的置信度：high/medium/low"
    )
    suggested_verification: str = Field(
        description="建议的验证方式（给验证 Agent 的工具方向）"
    )


class HypothesisSet(BaseModel):
    """侦察 Agent 对仓库的整体扫描输出。"""

    hypotheses: list[VulnHypothesis] = Field(
        default_factory=list, description="全部漏洞假设"
    )
    coverage_notes: str = Field(
        description="扫描覆盖情况说明，包括未覆盖/未检查的区域，避免静默漏目录"
    )


# ────────────────────────── 验证 Agent 输出（预留）──────────────────────
class VerificationResult(BaseModel):
    """验证 Agent 对单条假设的裁决结果。"""

    hypothesis_title: str
    verdict: Literal["CONFIRMED", "REFUTED", "UNCERTAIN"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(description="工具验证证据原文")
    verification_method: str = Field(description="实际使用的验证方法")


class VerificationSet(BaseModel):
    """验证 Agent 的整体输出：对全部假设的裁决列表。"""

    results: list[VerificationResult] = Field(
        default_factory=list, description="全部假设的验证裁决"
    )
    summary: str = Field(
        default_factory="", description="验证阶段总结：哪些确认/证伪/待复核，及共性原因"
    )


# ────────────────────────── 深挖 Agent 输出（预留）──────────────────────
class AttackChain(BaseModel):
    """深挖 Agent 对 confirmed 漏洞的攻击链推演。"""

    preconditions: list[str] = Field(default_factory=list)
    lateral_moves: list[str] = Field(default_factory=list)
    impact: str
    remediation: str


# ────────────────────────── 裁判官输出（FinalReport）──────────────────────
class FinalReportFinding(BaseModel):
    """裁判官定稿里的单条漏洞条目（CONFIRMED 且攻击链完整）。"""

    title: str
    vuln_type: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    code_snippet: str = ""
    severity: str = "high"
    confidence: str = "high"
    evidence: str = ""
    attack_path: str = ""
    remediation: str = ""


class FinalReport(BaseModel):
    """裁判官的多源合议定稿（供报告 Agent 排版，非成品文档）。"""

    findings: list[FinalReportFinding] = Field(
        default_factory=list, description="CONFIRMED 且攻击链完整的漏洞条目"
    )
    conclusion: str = Field(
        default_factory="", description="整体结论：风险概况、主要威胁、建议"
    )


# ────────────────────────── Agent 间交接契约（预留）────────────────────
class AgentHandoff(BaseModel):
    """Agent 间交接的标准格式：传摘要与结构化数据，不传全对话。"""

    from_agent: str
    to_agent: str
    context_summary: str
    structured_data: dict
    instructions: str
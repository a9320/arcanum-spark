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
    "assign_hypothesis_ids",
    "confidence_to_float",
]


# ── confidence 枚举↔float 转换规则（写死，消费方一律走这里，禁止各写各的）──
_CONFEnum_TO_FLOAT = {"high": 0.9, "medium": 0.6, "low": 0.3}


def confidence_to_float(value: "str | float | int") -> float:
    """high/medium/low 枚举或数值 → [0,1] float。

    枚举口径：high=0.9 / medium=0.6 / low=0.3；数值直接夹到 [0,1]。
    """
    if isinstance(value, str):
        v = _CONFEnum_TO_FLOAT.get(value.strip().lower())
        if v is None:
            raise ValueError(f"未知 confidence 枚举: {value!r}")
        return v
    f = float(value)
    return max(0.0, min(1.0, f))


# ────────────────────────── Agent A 输出 ──────────────────────────
class VulnHypothesis(BaseModel):
    """侦察 Agent 提出的单条漏洞假设（尚未验证，仅候选）。"""

    id: str = Field(
        default="", description="假设 ID（H1/H2/...，由 pipeline 确定性分配，验证按 id 对齐）"
    )
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

    hypothesis_id: str = Field(
        default="", description="对应 VulnHypothesis.id（结构化对齐，替代 title 字符串匹配）"
    )
    hypothesis_title: str
    verdict: Literal["CONFIRMED", "REFUTED", "UNCERTAIN"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(description="工具验证证据原文")
    verification_method: str = Field(description="实际使用的验证方法")


# ── id 对齐（确定性，替代 title 字符串匹配）──
def assign_hypothesis_ids(hypothesis_set: "HypothesisSet") -> None:
    """就地给假设集编号 H1..Hn（按列表顺序，幂等：已有 id 不覆盖）。"""
    for i, h in enumerate(getattr(hypothesis_set, "hypotheses", []) or [], start=1):
        if not getattr(h, "id", ""):
            h.id = f"H{i}"


class VerificationSet(BaseModel):
    """验证 Agent 的整体输出：对全部假设的裁决列表。"""

    results: list[VerificationResult] = Field(
        default_factory=list, description="全部假设的验证裁决"
    )
    summary: str = Field(
        default="", description="验证阶段总结：哪些确认/证伪/待复核，及共性原因"
    )


# ────────────────────────── 深挖 Agent 输出（预留）──────────────────────
class AttackChain(BaseModel):
    """深挖 Agent 对 confirmed 漏洞的攻击链推演。"""

    title: str = Field(default="", description="攻击链标题（缺省由渲染层补'攻击链 N'）")
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
        default="", description="整体结论：风险概况、主要威胁、建议"
    )


# ────────────────────────── Agent 间交接契约（预留）────────────────────
class AgentHandoff(BaseModel):
    """Agent 间交接的标准格式：传摘要与结构化数据，不传全对话。"""

    from_agent: str
    to_agent: str
    context_summary: str
    structured_data: dict
    instructions: str
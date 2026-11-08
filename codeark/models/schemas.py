"""Pydantic 数据模型 — Agent A（侦察）的结构化输出契约。

设计原则（整合版蓝图 §7）：
- 用 Literal 枚举约束 confidence（high/medium/low），杜绝模型乱填越界；
- coverage_notes 强迫模型汇报扫描盲区，避免静默漏目录；
- 每个假设必须携带 suggested_verification，为验证 Agent 提供明确工具方向。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

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
    evidence_source: str | None = Field(
        default=None,
        description="最主要证据来源（方差治理 D2 溯源，2026-10-25）：repo_file/"
        "tool_result/library_knowledge/reasoning_only；自由字符串入库，"
        "归一化层清洗非法值（junk→None，不用 Literal 防旧输出炸校验）",
    )
    partial_grounding: bool = Field(
        default=False,
        description="派生字段（模型不得产出）：CONFIRMED 且 evidence_source="
        "library_knowledge（证实面含非仓内知识）→ True；方差治理 D2 打标",
    )
    degraded: bool = Field(
        default=False,
        description="True=invoke/输出契约失败后的降级记录；verdict 的 UNCERTAIN "
        "不代表模型真实判断，聚合与判分不得与真实 UNCERTAIN 混同",
    )
    starving: bool = Field(
        default=False,
        description="方差治理 D3（我方计算，模型不得产出）：证据包饥饿判定——"
        "点名覆盖率 < ARCA_VERIFY_STARVING_COVERAGE（默认 1.0）或包宽率 < "
        "ARCA_VERIFY_STARVING_MIN_FRACTION（默认 0.5，0=关闸）；归一化层清零，"
        "verify_agent pack 侧回填；判分器据此把'证据不足卷'与采样方差分开计数",
    )
    pack_tokens: int = Field(
        default=0,
        description="D3 统计：证据包内容 token 粗估（_est_tokens 口径）",
    )
    pack_coverage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="D3 统计：假设点名文件（file_path + attack_path/"
        "suggested_verification 点名的仓内路径）进包覆盖率 0~1",
    )
    pack_fraction: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="D3 统计：包宽率=pack_tokens/全仓 tokens——minpack 类极小包"
        "（4c 饥饿机理）下点名文件被 force 进包、点名覆盖率恒 1.0 的盲区补刀",
    )
    degraded_reason: str = Field(
        default="",
        description="方差治理 D5 降级分类学（台账契约类 #4 设计输入）："
        "contract（id 契约失败）/ parse（PEG/JSON 解析拒绝）/ tool-fail（invoke "
        "异常、超时）/ context（上下文溢出）；非降级记录为空串；判分器按类计数"
        "（契约/解析类可重跑，tool-fail 看基建，context 查证据包）",
    )


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
def _coerce_confidence_number(value: object) -> float:
    """D5（台账契约类 #2）：FinalReport confidence 强制数字型——历史双形态
    （0.9 vs "0.9" vs "high"）在解析口一次性收敛，schema 重试自愈路径退役。
    映射 high→0.9 / medium→0.6 / low→0.3（与 D1 三档兜底枚举同表）；数字串直转；
    非法值保守落 0.5（不炸校验，同 D2 junk 容忍口径）；越界夹取 [0,1]。"""
    try:
        if isinstance(value, bool):
            return 0.5
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        s = str(value).strip().lower()
        tiers = {"high": 0.9, "medium": 0.6, "low": 0.3}
        if s in tiers:
            return tiers[s]
        return max(0.0, min(1.0, float(s)))
    except (TypeError, ValueError):
        return 0.5


class FinalReportFinding(BaseModel):
    """裁判官定稿里的单条漏洞条目（CONFIRMED 且攻击链完整）。"""

    title: str
    vuln_type: str
    file_path: str
    line_start: int = 0
    line_end: int = 0
    code_snippet: str = ""
    severity: str = "high"
    confidence: float = Field(
        default=0.9,
        description="D5 强制数字型（0~1；历史 'high'/'0.9' 双形态在解析口收敛）",
    )
    evidence: str = ""
    attack_path: str = ""
    remediation: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf_number(cls, v: object) -> float:
        return _coerce_confidence_number(v)


class FinalReportRefuted(BaseModel):
    """D5（台账语义类 #6）：已证伪假设的透传条目——驳判理由进最终报告，
    arbiter 禁把已证伪假设定性当事实写进 conclusion。"""

    hypothesis_id: str = ""
    title: str = ""
    reason: str = Field(default="", description="驳判理由（=verify evidence 原文）")
    confidence: float = Field(default=0.9, description="驳判置信（0~1）")

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf_number(cls, v: object) -> float:
        return _coerce_confidence_number(v)


class FinalReport(BaseModel):
    """裁判官的多源合议定稿（供报告 Agent 排版，非成品文档）。"""

    findings: list[FinalReportFinding] = Field(
        default_factory=list, description="CONFIRMED 且攻击链完整的漏洞条目"
    )
    refuted_on_intended: list[FinalReportRefuted] = Field(
        default_factory=list,
        description="D5 透传：REFUTED 裁决及其理由（理由不透传=报告层盲区，台账 #6）",
    )
    conclusion: str = Field(
        default="", description="整体结论：风险概况、主要威胁、建议"
    )

    @field_validator("findings", "refuted_on_intended", mode="before")
    @classmethod
    def _none_to_empty_list(cls, v: object) -> object:
        # D5 打磨（2026-11-08 DSW 块 4 实测）：模型首调传 null 被 schema 拒→
        # 多花一次重试；None 就地收敛空列表，该重试路径退役
        return [] if v is None else v


# ────────────────────────── Agent 间交接契约（预留）────────────────────
class AgentHandoff(BaseModel):
    """Agent 间交接的标准格式：传摘要与结构化数据，不传全对话。"""

    from_agent: str
    to_agent: str
    context_summary: str
    structured_data: dict
    instructions: str
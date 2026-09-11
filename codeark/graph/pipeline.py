"""Graph 编排 — 6 节点流水线串联（无卡阶段骨架）。

把 6 个节点按蓝图顺序串成确定性流水线：
    agent0(PITAX规则) → scout(侦察) → verify(验证) → deepen(深挖)
        → arbiter(裁判合议) → report(报告渲染)

设计原则（对照蓝图 §5 工程机制）：
- **权威计算确定性**：风险评分/汇总值由代码算（compute_risk_score），不让 LLM 算；
- **证据可追溯**：每个阶段的结果都保留原始证据字段，传递的是结构化数据而非闲聊；
- **生成≠发布**：report 只产出格式文件，不发送任何外部渠道；
- **可验证性**：每节点可单独跑/可注入 mock，端到端可在离线数据上重演。

当前无卡阶段：默认用免费模型（DeepSeek）驱动 LLM 节点；
卡批后仅需替换 make_model("bedrock") 即可切 Claude，Graph 编排本身不动。
"""
from __future__ import annotations

from typing import Any, Callable

from codeark.agents.agent0_pitax import run_agent0
from codeark.agents.scout_agent import run_scout
from codeark.agents.verify_agent import run_verify
from codeark.agents.deepen_agent import run_deepen
from codeark.agents.arbiter_agent import run_arbiter
from codeark.agents.report_agent import render_report
from codeark.graph.quarantine import quarantine_files

__all__ = [
    "GraphResult",
    "compute_risk_score",
    "CodeRiskGraph",
]


# ────────────────────────── 权威计算（确定性）─────────────────────────
_SEV_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}
# 注：之前缺少 "critical" 键，导致 rules.py 中 severity=critical 的规则
# （PIT-T-46 / PIT-E-57）被 .get(sev, 1) 静默当成 low 计 1 分（2026-09-11 修复）。


def _field(f: Any, key: str, default: str = "") -> str:
    """兼容 dict 与 pydantic 模型两种 finding 形态(实弹修复)"""
    if isinstance(f, dict):
        return str(f.get(key) or default)
    return str(getattr(f, key, None) or default)


def compute_risk_score(findings: list[Any]) -> int:
    """由确定性代码计算风险总分，绝不让 LLM 算分（蓝图 §5.2）。

    规则：每个高危 +3 / 中危 +2 / 低危 +1，取总和（封顶 100）。
    """
    total = 0
    for f in findings:
        sev = _field(f, "severity", "") or _field(f, "confidence", "") or "low"
        total += _SEV_WEIGHT.get(sev.lower(), 1)
    return min(total, 100)


# ────────────────────────── 图执行结果 ──────────────────────────
class GraphResult:
    """整条流水线的可追溯结果（含每节点输出 + 汇总）。"""

    def __init__(self) -> None:
        self.agent0_findings: list[dict] = []
        self.hypothesis_set: Any = None
        self.verifications: list[Any] = []
        self.attack_chains: list[Any] = []
        self.final_report: Any = None
        self.reports: dict[str, Any] = {}
        self.risk_score: int = 0
        # 隔离层统计（§11-B）：多少文件被消毒、中和了多少注入触发词
        self.quarantine_stats: dict[str, Any] = {}
        # Deepen 解析降级计数（治本可观测性：坏链不再静默消失）
        self.deepen_failures: int = 0
        # 节点级故障披露（invoke 级容错：失败节点降级为确定性路径并记录）
        self.node_errors: dict[str, str] = {}

    def to_dict(self) -> dict:
        def _dump(x: Any) -> Any:
            if hasattr(x, "model_dump"):
                return x.model_dump()
            if isinstance(x, list):
                return [_dump(i) for i in x]
            return x

        return {
            "agent0_findings": self.agent0_findings,
            "hypothesis_set": _dump(self.hypothesis_set),
            "verifications": _dump(self.verifications),
            "attack_chains": _dump(self.attack_chains),
            "final_report": _dump(self.final_report),
            "reports": self.reports,
            "risk_score": self.risk_score,
            "quarantine_stats": self.quarantine_stats,
            "deepen_failures": self.deepen_failures,
            "node_errors": self.node_errors,
        }


# ────────────────────────── 图（6 节点串联）──────────────────────────
class CodeRiskGraph:
    """6 节点流水线编排器。

    用法：
        g = CodeRiskGraph()
        result = await g.run(files)          # 真实 LLM 跑通
        result = await g.run(files, dry=True)  # 离线 dry-run，不烧模型
    """

    def __init__(self, model=None, dry: bool = False) -> None:
        self.model = model  # None → 各节点用默认免费模型
        self.dry = dry

    # ── dry-run：离线确定性路径（用 agent0 + 简单结构化占位，不调 LLM）──
    def _dry_scout(self, files: dict[str, str], baseline: list[dict]) -> Any:
        from codeark.models.schemas import HypothesisSet, VulnHypothesis
        hyps = []
        for f in baseline:
            hyps.append(VulnHypothesis(
                title=f.get("title", f.get("type", "PITAX finding")),
                vuln_type=f.get("type", "PITAX"),
                file_path=f.get("file", ""),
                line_start=int(f.get("line", 0)),
                line_end=int(f.get("line", 0)),
                code_snippet=f.get("code_snippet", ""),
                attack_path="PITAX 规则确定性命中（dry-run 占位）",
                confidence="high",
                suggested_verification="static_scan / taint_flow 交叉验证",
            ))
        return HypothesisSet(hypotheses=hyps, coverage_notes="dry-run：仅 agent0 PITAX 基线，未做模型补充扫描")

    # ── dry/降级共用：规则基线验证（CONFIRMED=规则命中即证实，dry 语义）──
    @staticmethod
    def _dry_verify(hypothesis_set: Any) -> list:
        from codeark.models.schemas import VerificationResult
        out = []
        for h in hypothesis_set.hypotheses:
            out.append(VerificationResult(
                hypothesis_title=h.title,
                verdict="CONFIRMED",
                confidence=0.9,
                evidence="PITAX 规则确定性命中即视为已证实（确定性降级路径）",
                verification_method="pitax_scan(deterministic)",
            ))
        return out

    @staticmethod
    def _dry_chains(confirmed: list) -> list:
        from codeark.models.schemas import AttackChain
        return [AttackChain(
            preconditions=["攻击者可接触被扫描的提示注入内容（确定性降级占位）"],
            lateral_moves=[],
            impact="PITAX 命中可能导致 AI 助手被劫持执行非授权指令",
            remediation="修复对应 PITAX 规则命中的代码/配置",
        ) for _ in confirmed]

    # ── 主入口 ──
    async def run(self, files: dict[str, str]) -> GraphResult:
        res = GraphResult()

        # 1. Agent0：PITAX 规则层（无 LLM，确定性基线）——永远跑**原始**文件
        res.agent0_findings = run_agent0(files)

        # 1.5 隔离层（§11-B）：LLM prompt 只看消毒版；工具/Agent0 看原始版。
        safe_files = files
        if not self.dry:
            safe_files, res.quarantine_stats = quarantine_files(files)

        # 2. 侦察：提出漏洞假设（失败 → 降级为规则基线假设，不中断流水线）
        if self.dry:
            res.hypothesis_set = self._dry_scout(files, res.agent0_findings)
        else:
            try:
                res.hypothesis_set = await run_scout(
                    files, self.model, prompt_files=safe_files
                )
            except Exception as exc:
                res.node_errors["scout"] = f"{type(exc).__name__}: {exc}"
                print(f"[Pipeline] ⚠ Scout 失败，降级为规则基线假设: {exc}")
                res.hypothesis_set = self._dry_scout(files, res.agent0_findings)

        # 3. 验证：逐条证实/证伪（失败 → 降级为规则证实口径）
        if self.dry:
            res.verifications = self._dry_verify(res.hypothesis_set)
        else:
            try:
                res.verifications = await run_verify(
                    res.hypothesis_set, files, self.model, prompt_files=safe_files
                )
            except Exception as exc:
                res.node_errors["verify"] = f"{type(exc).__name__}: {exc}"
                print(f"[Pipeline] ⚠ Verify 失败，降级为规则证实口径: {exc}")
                res.verifications = self._dry_verify(res.hypothesis_set)

        # 4. 深挖：对 CONFIRMED 推演攻击链（失败 → 占位链 + 降级计数披露）
        confirmed = [v for v in res.verifications if getattr(v, "verdict", "") == "CONFIRMED"]
        if self.dry:
            res.attack_chains = self._dry_chains(confirmed)
        else:
            try:
                res.attack_chains = await run_deepen(
                    confirmed, files, self.model, prompt_files=safe_files
                )
            except Exception as exc:
                res.node_errors["deepen"] = f"{type(exc).__name__}: {exc}"
                print(f"[Pipeline] ⚠ Deepen 失败，输出占位链并记降级: {exc}")
                res.attack_chains = self._dry_chains(confirmed)
                res.deepen_failures = len(confirmed)
            else:
                res.deepen_failures = getattr(res.attack_chains, "failures", 0)

        # 5. 裁判官：多源合议定稿（内部已含重试+确定性兜底；此处再保一层不崩）
        if self.dry:
            res.final_report = {
                "findings": res.agent0_findings,
                "conclusion": "dry-run：基线扫描完成，待真实模型合议",
            }
        else:
            try:
                res.final_report = await run_arbiter(
                    res.hypothesis_set, res.verifications, res.attack_chains, self.model
                )
            except Exception as exc:
                res.node_errors["arbiter"] = f"{type(exc).__name__}: {exc}"
                print(f"[Pipeline] ⚠ Arbiter 异常，切换确定性兜底定稿: {exc}")
                from codeark.agents.arbiter_agent import _deterministic_fallback_report
                res.final_report = _deterministic_fallback_report(
                    res.verifications, res.attack_chains, res.hypothesis_set,
                    reason=f"arbiter 异常 {type(exc).__name__}: {exc}",
                )

        # 6. 报告：确定性渲染（JSON/SARIF/Markdown），生成≠发布
        # 攻击链与隔离层统计一并进报告（§11：链曾只存不渲）
        res.reports = render_report(
            res.final_report,
            ["json", "sarif", "markdown"],
            attack_chains=res.attack_chains,
            meta={
                "quarantine_stats": res.quarantine_stats,
                "deepen_failures": res.deepen_failures,
                "node_errors": res.node_errors,
            },
        )

        # 权威计算：风险分（确定性代码）
        # 优先级：合议定稿 findings（LLM 层产出）→ Agent0 规则层兜底。
        # 修复 §11-A：原写法 `res.agent0_findings or ...` 因 or 短路，
        # 导致 LLM 层产出对风险分零影响（两次端到端均恒为 22）。
        final_findings = None
        if isinstance(res.final_report, dict):
            final_findings = res.final_report.get("findings")
        elif res.final_report is not None:
            final_findings = getattr(res.final_report, "findings", None)
        res.risk_score = compute_risk_score(
            final_findings or res.agent0_findings
        )
        return res


# ── 便捷入口 ──
async def run_pipeline(
    files: dict[str, str],
    model=None,
    dry: bool = False,
) -> GraphResult:
    """一次性跑完整 6 节点流水线。"""
    graph = CodeRiskGraph(model=model, dry=dry)
    return await graph.run(files)
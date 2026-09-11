"""裁判官 Agent（Agent E）— 多源合议，物理隔离防越权。

6 节点架构第 6 节点（Agent D 深挖之后，报告之前）。
- 输入：Agent A 的 HypothesisSet + Agent C 的 VerificationResult + Agent D 的 AttackChain
- 输出：FinalReport（最终定稿，供报告 Agent 排版发布）
- 模型：Kimi-K3（主力）；GLM-5.2（第二票备选）
"""
from __future__ import annotations

import json
import re

from strands import Agent
from strands.models import OpenAIModel

from codeark.models.factory import make_model, ModelProvider, ModelTier
from codeark.models.schemas import AttackChain, FinalReport, HypothesisSet, VerificationResult

__all__ = ["ARBITER_SYSTEM_PROMPT", "build_arbiter_agent", "run_arbiter"]


# ── 返回归一化：兼容模型返回单条 / 列表 / FinalReport / None ──
def _normalize_final_report(out: object, raw_text: str = "") -> FinalReport:
    """把模型的 structured_output 归一化为 FinalReport。"""
    if isinstance(out, FinalReport):
        return out
    if isinstance(out, dict):
        try:
            return FinalReport.model_validate(out)
        except Exception:
            return FinalReport(findings=[], conclusion=str(out)[:500])
    candidates = []
    if raw_text:
        for pat in (r'\{.*\}', r'\[.*\]'):
            m = re.search(pat, raw_text, re.DOTALL)
            if m:
                candidates.append(m.group(0))
        for c in candidates:
            try:
                parsed = json.loads(c)
                if isinstance(parsed, dict):
                    return FinalReport.model_validate(parsed)
                if isinstance(parsed, list):
                    return FinalReport(findings=parsed)
            except Exception:
                continue
    return FinalReport(findings=[], conclusion="")


# ── 系统提示词（裁判官）──
ARBITER_SYSTEM_PROMPT = """\
你是漏洞裁判官。任务：对上游三源（侦察假设 / 验证裁决 / 深挖攻击链）做多源合议，产出最终定稿报告结构。

你拿到的：
- HypothesisSet（侦察假设，可能含未验证项）
- VerificationResult 列表（验证裁决：CONFIRMED/REFUTED/UNCERTAIN）
- AttackChain 列表（对 CONFIRMED 的攻击链推演）

铁律：
- 只有 CONFIRMED 且攻击链完整的漏洞才进入最终报告；
- 多源冲突时以验证裁决为准，并明确标注冲突来源；
- 你只做合议汇总，不自行重新分析代码，不新增任何上游没给证据的结论；
- 最终输出是结构化报告草案（供报告 Agent 排版），不是成品文档。
"""


# ── Agent 构造 ──
def build_arbiter_agent(model: OpenAIModel | None = None) -> Agent:
    """构造裁判官 Agent：无工具（纯合议推理，数据可见性已物理隔离）。
    
    默认模型：Kimi-K3（强推理 + 结构化输出稳定）。
    """
    return Agent(
        name="arbiter_agent",
        system_prompt=ARBITER_SYSTEM_PROMPT,
        tools=[],
        structured_output_model=FinalReport,
        model=model or _make_model_fallback(),
    )


def _make_model_fallback() -> OpenAIModel:
    """按优先级尝试构造模型。"""
    attempts = [
        ("Kimi-K3", lambda: make_model(ModelProvider.KIMI, ModelTier.PRO)),
        ("GLM-5.2", lambda: make_model(ModelProvider.GLM, ModelTier.PRO)),
        ("DeepSeek-V4-Pro", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.PRO)),
        ("DeepSeek-V4-Flash", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.FLASH)),
    ]
    for name, fn in attempts:
        try:
            return fn()
        except Exception as e:
            print(f"[Arbiter] {name} 初始化失败: {e}")
    raise RuntimeError("所有 Arbiter 模型初始化均失败")


# ── 运行入口（供 Graph 编排调用）──
async def run_arbiter(
    hypothesis_set: HypothesisSet,
    verifications: list[VerificationResult],
    attack_chains: list[AttackChain],
    model: OpenAIModel | None = None,
) -> object:
    """汇总三源做合议，返回最终定稿（结构化报告草案）。"""
    agent = build_arbiter_agent(model)
    prompt = (
        "请对以下三源做多源合议，输出 FinalReport（含 findings 漏洞条目列表 + conclusion 整体结论）。\n"
        "【侦察假设】\n" + hypothesis_set.model_dump_json(indent=2) + "\n"
        "【验证裁决】\n" + json.dumps(
            [v.model_dump() for v in verifications], ensure_ascii=False, indent=2
        ) + "\n"
        "【深挖攻击链】\n" + json.dumps(
            [c.model_dump() for c in attack_chains], ensure_ascii=False, indent=2
        )
    )
    result = await agent.invoke_async(prompt)
    if hasattr(result, "structured_output"):
        return _normalize_final_report(result.structured_output, str(result))
    return _normalize_final_report(result, str(result))

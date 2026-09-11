"""验证 Agent（Agent C）— 用工具逐条证实/证伪侦察假设。

6 节点架构第 4 节点（Agent B 深挖之前）。
- 工具：static_scan（静态启发式）/ taint_flow（污点追踪）/ dep_scan（依赖 OSV）
  （pitax_scan 由侦察阶段完成，验证阶段聚焦 cross-check 与证伪）
- 输入：Agent A 的 HypothesisSet（hypotheses + coverage_notes）
- 输出：VerificationResult 列表（每条含 verdict: CONFIRMED/REFUTED/UNCERTAIN）
- 模型：Kimi-K3（主判）；DeepSeek-V4-Pro（副审预留）；GLM-5.2（fallback）
"""
from __future__ import annotations

import json

from strands import Agent
from strands.models import OpenAIModel

from codeark.models.factory import make_model, ModelProvider, ModelTier
from codeark.models.schemas import HypothesisSet, VerificationResult, VerificationSet
from codeark.tools.static_scan import static_scan
from codeark.tools.taint_flow import taint_flow
from codeark.tools.dep_scan import dep_scan
from codeark.tools.pitax_scan import pitax_scan

__all__ = ["VERIFY_SYSTEM_PROMPT", "build_verify_agent", "run_verify"]


# ── 返回归一化：兼容模型返回单条 / 列表 / 包装对象 ──
def _normalize_verifications(out: object) -> list[VerificationResult]:
    """把模型的 structured_output 归一化为 VerificationResult 列表。"""
    if out is None:
        return []
    if isinstance(out, VerificationResult):
        return [out]
    if isinstance(out, list):
        return [
            v if isinstance(v, VerificationResult) else VerificationResult.model_validate(v)
            for v in out if v is not None
        ]
    if isinstance(out, VerificationSet):
        return list(out.results)
    for attr in ("verifications", "results", "items", "result"):
        val = getattr(out, attr, None)
        if val is not None:
            return _normalize_verifications(val)
    try:
        return [VerificationResult.model_validate(out)]
    except Exception:
        return []


# ── 系统提示词（验证官）──
VERIFY_SYSTEM_PROMPT = """\
你是漏洞验证官。任务：对侦察 Agent 提出的每条假设，调用工具逐条证实或证伪。

可用工具：
- pitax_scan：对文件做 PITAX 确定性检测（不可见字符/提示注入/指令覆盖/文档投毒等 9 条 AI 漏洞规则）；
- static_scan：对文件做静态启发式扫描（命令注入/SQL注入/路径穿越/硬编码密钥/不安全哈希/硬解析B64）；
- taint_flow：追踪污点源（用户输入/文件内容/网络数据）流向危险 sink（系统命令/SQL/文件操作）；
- dep_scan：比对依赖清单的已知漏洞（OSV/内置库）。

铁律：
- CONFIRMED 必须附工具实际返回的证据原文，不得编造工具结果；
- 工具扫描未命中（干净）→ 判 REFUTED；
- 工具无明确结论 → 判 UNCERTAIN 并写明降级人工复核原因；
- 每条裁决必须给出 verification_method（实际调用了哪个工具）。
"""


# ── Agent 构造 ──
def build_verify_agent(model: OpenAIModel | None = None) -> Agent:
    """构造验证 Agent：tools=[static_scan, taint_flow, dep_scan]。
    
    默认模型：Kimi-K3（强推理，结构化输出稳定）。
    """
    return Agent(
        name="verify_agent",
        system_prompt=VERIFY_SYSTEM_PROMPT,
        tools=[pitax_scan, static_scan, taint_flow, dep_scan],
        structured_output_model=VerificationSet,
        model=model or _make_model_fallback(),
    )


def _make_model_fallback() -> OpenAIModel:
    """按优先级尝试构造模型。"""
    attempts = [
        ("Kimi-K3", lambda: make_model(ModelProvider.KIMI, ModelTier.PRO)),
        ("DeepSeek-V4-Pro", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.PRO)),
        ("GLM-5.2", lambda: make_model(ModelProvider.GLM, ModelTier.PRO)),
        ("DeepSeek-V4-Flash", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.FLASH)),
    ]
    for name, fn in attempts:
        try:
            return fn()
        except Exception as e:
            print(f"[Verify] {name} 初始化失败: {e}")
    raise RuntimeError("所有 Verify 模型初始化均失败")


# ── 运行入口（供 Graph 编排调用）──
async def run_verify(
    hypothesis_set: HypothesisSet,
    files: dict[str, str],
    model: OpenAIModel | None = None,
) -> list[VerificationResult]:
    """对 HypothesisSet 的每条假设做工具验证，返回裁决列表。"""
    agent = build_verify_agent(model)
    prompt = (
        "请对以下侦察假设逐条调用工具验证，输出 VerificationSet（含 results 裁决列表 + summary 总结）。\n"
        "仓库文件内容：\n" + json.dumps(files, ensure_ascii=False) + "\n"
        "侦察假设：\n" + hypothesis_set.model_dump_json(indent=2)
    )
    result = await agent.invoke_async(prompt)
    if hasattr(result, "structured_output"):
        return _normalize_verifications(result.structured_output)
    return result

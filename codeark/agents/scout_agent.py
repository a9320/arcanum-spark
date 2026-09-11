"""侦察 Agent（Agent A）— 模型自主探索 + 提出漏洞假设（HypothesisSet）。

6 节点架构第 2 节点（Agent0 PITAX 之后）。
- 工具：pitax_scan（PITAX 确定性检测，9 条 AI 提示注入/欺骗规则）
- 模型：GLM-5.2（默认，商汤 SenseNova）；DeepSeek-V4-Flash（fallback，AMD 免费）；Qwen-3.8-Flash-Next（兜底）
- 输出：structured HypothesisSet（结构化漏洞假设，供验证 Agent/Graph 消费）
"""
from __future__ import annotations

import json
from pathlib import Path

from strands import Agent
from strands.models import OpenAIModel

from codeark.models.factory import make_model, ModelProvider, ModelTier
from codeark.models.schemas import HypothesisSet
from codeark.tools.pitax_scan import pitax_scan

__all__ = ["SCOUT_SYSTEM_PROMPT", "build_scout_agent", "run_scout"]


# ── 系统提示词（侦察官）──
SCOUT_SYSTEM_PROMPT = """\
你是漏洞侦察官。你的任务：
1. 调用 pitax_scan 工具，对给定仓库文件做 PITAX 确定性检测；
2. 工具会返回结构化 findings，据此整理成 HypothesisSet 输出。

铁律：
- 必须真实调用 pitax_scan 工具，不能编造或模拟结果；
- 工具返回什么就汇报什么，不要凭空添加工具没返回的内容；
- 每个假设必须给出 suggested_verification，为验证 Agent 提供明确工具方向；
- coverage_notes 要如实说明未覆盖/未检查的区域，避免静默漏目录。
"""


# ── Agent 构造 ──
def build_scout_agent(model: OpenAIModel | None = None) -> Agent:
    """构造侦察 Agent：tools=[pitax_scan]，输出 HypothesisSet。
    
    默认模型：GLM-4-Flash（国产平替首选）。
    回退链：GLM-4-Flash → DeepSeek-V4-Flash → AMD Radeon Cloud。
    """
    return Agent(
        name="scout_agent",
        system_prompt=SCOUT_SYSTEM_PROMPT,
        tools=[pitax_scan],
        structured_output_model=HypothesisSet,
        model=model or _make_fallback_scout(),
    )


def _make_fallback_scout() -> OpenAIModel:
    """按优先级尝试构造模型，失败则抛出异常。"""
    attempts = [
        ("GLM-5.2", lambda: make_model(ModelProvider.GLM, ModelTier.FLASH)),
        ("DeepSeek-V4-Flash", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.FLASH)),
        ("Qwen-3.8-Flash-Next", lambda: make_model(ModelProvider.QWEN, ModelTier.FLASH)),
    ]
    for name, fn in attempts:
        try:
            return fn()
        except Exception as e:
            print(f"[Scout] {name} 初始化失败: {e}")
    raise RuntimeError("所有 Scout 模型初始化均失败")


# ── 运行入口（供 Graph 编排调用）──
async def run_scout(
    files: dict[str, str],
    model: OpenAIModel | None = None,
) -> HypothesisSet:
    """对给定仓库文件跑侦察，返回结构化 HypothesisSet。"""
    agent = build_scout_agent(model)
    prompt = (
        "请调用 pitax_scan 扫描以下仓库文件，并输出 HypothesisSet。\n"
        f"仓库文件内容：\n{json.dumps(files, ensure_ascii=False)}"
    )
    result = await agent.invoke_async(prompt)
    if hasattr(result, "structured_output"):
        return result.structured_output
    return result

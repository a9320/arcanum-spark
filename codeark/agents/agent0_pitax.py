"""Agent 0：PITAX 前置扫描（规则层，无需 LLM）。

6 节点架构第 1 节点（侦察 Agent 之前）。
- 纯确定性规则层：直接调用 pitax_scan 对仓库文件跑 9 条 PITAX AI 漏洞规则
- 不涉及任何 LLM，结果即最终事实（ground truth baseline），供下游 Agent 引用
- 迁移自 app/pitax —— 9 条确定性 AI 提示注入/欺骗规则

设计要点：
- 它是流水线的"种子"：先跑出确定性的 PITAX 命中，再交给侦察 Agent 做假设与补充；
- 零成本、零幻觉：规则层输出天然可信，是铁律"结论有工具背书"的最强实现；
- 与 scout_agent 的 pitax_scan 工具共享同一底层规则，但此处是独立前置通道。
"""
from __future__ import annotations

from codeark.tools.pitax_scan import scan_repo as _scan_repo

__all__ = ["PITAX_RULES_COUNT", "run_agent0"]


PITAX_RULES_COUNT = 9  # 9 条 PITAX 规则（提示注入/指令覆盖/欺骗/数据泄漏等）


def run_agent0(files: dict[str, str]) -> list[dict]:
    """对仓库文件跑 PITAX 确定性规则扫描（无 LLM）。

    Args:
        files: 文件路径 → 文件内容映射。

    Returns:
        findings 列表（与 pitax_scan 工具返回同构：rule/severity/confidence/
        file/line/code_snippet/evidence 等）。此结果即确定性基线事实。
    """
    return _scan_repo(files)
"""Laya 假设排序运行时（System One 决策模型）—— score_laya 的唯一实现。

2026-11-05 自 eval/replay.py 提升（单一事实源纪律：实现只在本文件；
replay.py 与 codeark/graph/gate_factory.py 均转发到这里）。

调用面：
- ``eval/replay.py cmd_score``（评测 CLI，`--backend laya`）
- ``codeark/graph/gate_factory.py::make_laya_gate``（生产 gate 挂载）
- arcanum-mcp ``rank_hypotheses`` 工具（stdio MCP，[laya] extra 形态）

设计事实（迁自 replay，口径不变）：
- 考题契约（2026-09-26 定稿）：2-option choice（A=KEEP/B=PRUNE）——noul 有
  标签偏置坑（issue #156）、score 原语最弱（SST-5 0.372）均不用；
  act_probability 官方已废弃（AUROC 0.30）禁用。每假设一次 system_one 调用
  （state 是文件域压缩格式，全量拼接塞不下 token 预算）。
- **防标签泄漏**：_laya_state 只喂 Scout 阶段信息；Verify 裁决入 state=作弊。
- order-only 契约：本层只产分数，**排序不删除**（gate v1 语义；prune 姿态在
  gate.py，且结构性剪枝逐条记录 gate meta）。

依赖口径：本文件顶层**纯标准库**——torch/transformers 只在 vendor
rl_agent_api.py（随模型目录自带）exec 时引入。Windows CPU safetensors mmap
已知坑：特定环境段错误（EVAL-LEDGER 2026-10-07 laya-r6 Windows 行记录，
绕法=fp32 物化副本，该补丁当时未入仓）；本层不做未验证的加载补丁，
遇到崩溃按 LAYA_RUNTIME_NOTE 提示处置。

checkpoint 分发：GitHub Release `laya-checkpoints`（三资产，sha256 见
EVAL-LEDGER）；MCP 侧用户手动下载 + ARCA_LAYA_PATH 指路（零网络红线）。
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["score_laya", "LAYA_RUNTIME_NOTE"]

# Windows CPU 用户提示（MCP 工具输出与文档共用同一段文字，避免两处口径漂移）
LAYA_RUNTIME_NOTE = (
    "Laya ranks hypotheses offline (a ~421M decision model, ~0.4s/item on CPU). "
    "Known caveat: on some Windows CPU environments safetensors mmap crashes at "
    "load (observed 2026-10-07, EVAL-LEDGER); workaround there was a materialized "
    "fp32 copy of the checkpoint. If loading crashes on Windows, re-run on "
    "Linux/WSL or a GPU host."
)


def _norm_path(p: str) -> str:
    # 与 eval/replay.py::norm_path 同一语义（文件域回显判定用），此处内联避免跨包耦合
    return str(p or "").replace("\\", "/").strip().lower()


def _load_laya_agent(model_path: str):
    """vendor 加载：模型目录自带 rl_agent_api.py（RLAgent），零额外依赖。

    非 transformers pipeline（2026-09-26 官方源码级研读纠偏）；sibling 导入
    （rl_common 等）依赖 sys.path，插入模型目录后不回收（CLI 一次性进程无害）。
    """
    if not model_path:
        raise ValueError("laya 后端需要 --model <模型目录>（DSW: /mnt/workspace/models/laya）")
    import importlib.util
    import sys

    root = Path(model_path)
    api = root / "rl_agent_api.py"
    if not api.exists():
        raise FileNotFoundError(
            f"未找到 {api}——rl_agent_api.py/rl_common.py 应随模型目录自带"
            "（多 checkpoint 布局：单检查点子目录才含 API 脚本）")
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("laya_rl_agent_api", api)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RLAgent(str(root))


def _laya_state(item: dict, baseline_rows: list[dict]) -> str:
    """单假设压缩 state——**Scout 阶段信息 ONLY**。

    裁决/验证方法是 Verify 后信息，入 state = 标签泄漏（zero-shot 分数即作弊，
    违反防泄漏口径）；基线上下文只给同文件行——回显判定是文件域的，token 预算
    也只装得下这个（英文根 ~320 / typed-decisions ~768）。
    """
    fp = str(item.get("file_path") or "")
    lines = [
        f"vuln_type: {item.get('vuln_type', '')}",
        f"file: {fp}",
        f"title: {str(item.get('title') or '')[:160]}",
        f"attack_path: {str(item.get('attack_path') or '')[:400]}",
    ]
    same = [b for b in baseline_rows if _norm_path(str(b.get("file") or "")) == _norm_path(fp)]
    lines.append("baseline rows on this file:")
    if same:
        for b in same[:6]:
            lines.append(f"- [{b.get('rule', '')}] {str(b.get('title') or '')[:80]}")
    else:
        lines.append("- none")
    return "\n".join(lines)


_SCORE_LAYA_INSTRUCTIONS = (
    "Decide whether this vulnerability hypothesis deserves a Verify-stage budget. "
    "A = keep, B = prune."
)
_SCORE_LAYA_CRITERIA = {
    "A": "KEEP: semantic increment beyond the rule baseline, or backed by tool evidence",
    "B": "PRUNE: echoes a baseline row (same file+type), duplicates another hypothesis, "
         "degenerate repetition, or no semantic increment",
}


def score_laya(
    items: list[dict], baseline: list[dict], model_path: str
) -> tuple[list[float], list[float]]:
    """Laya（System One 决策模型）后端：逐假设 P(KEEP) + confidence。

    返回 (P(KEEP) 列表, confidence 列表)；Brier/ECE 在 cmd_score 接线。
    items 字段：title/vuln_type/file_path/attack_path（code_snippet 允许缺席）；
    baseline 行字段：file/rule/title（agent0 findings 转行形态，
    见 gate_factory.baseline_rows_from_agent0）。
    """
    agent = _load_laya_agent(model_path)
    probs: list[float] = []
    confs: list[float] = []
    for i, it in enumerate(items):
        out = agent.system_one(
            _laya_state(it, baseline),
            {f"q{i}": {"type": "choice", "instructions": _SCORE_LAYA_INSTRUCTIONS,
                       "criteria": dict(_SCORE_LAYA_CRITERIA)}},
        )
        # 官方契约（rl_agent_api.py system_one 尾行）：{"model", "answers": {qid: {...}}, "usage"}，
        # answers[qid] = {"choice", "probabilities": {选项: 概率}, "confidence", "rl_agent"}
        a = ((out or {}).get("answers") or {}).get(f"q{i}") or {}
        p = float((a.get("probabilities") or {}).get("A") or 0.0)
        probs.append(min(max(p, 0.0), 1.0))
        confs.append(float(a.get("confidence") or 0.0))
    return probs, confs

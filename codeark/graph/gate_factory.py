"""Hypothesis gate 工厂 —— 验收与生产挂载的单一数据源。

gate v1.1/v1.2 验收（eval/run_gate_e2e.py）与生产挂载（codeark/dashboard.py）
共用同一套工厂与旋钮语义，防止两处漂移：
- make_laya_gate / make_deterministic_gate：gate callable 构造（含 prune_mode/min_keep 转发）；
- resolve_backend：ARCA_GATE_BACKEND 旋钮解析（缺省 laya，非法值显式报错）；
- resolve_prune：ARCA_GATE_PRUNE 旋钮解析（缺省 off；threshold/cap 已按
  GATE-V2-DESIGN §6 v1.1 搁置，显式报错；ARCA_GATE_PRUNE_TAU/_MAX 设置即报错）；
- build_gate_from_env：生产挂载策略——模型缺失/配置非法时返回 (None, reason)
  由调用方告警后无 gate 继续，生产扫描不因 checkpoint 缺席而失败。

gate 运行时异常由 pipeline 兜底（fallback=True 回退原序）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from codeark.graph.gate import PRUNE_MODES, GateResult, rerank_hypotheses
from codeark.models.schemas import HypothesisSet

__all__ = [
    "baseline_rows_from_agent0",
    "build_gate_from_env",
    "make_deterministic_gate",
    "make_laya_gate",
    "resolve_backend",
    "resolve_prune",
]

GateCallable = Callable[[HypothesisSet, list[dict]], GateResult]


def baseline_rows_from_agent0(agent0_findings: list[dict] | None) -> list[dict]:
    """agent0 findings → replay 基线行形态（_laya_state 读 file/rule/title）。"""
    rows: list[dict] = []
    for f in agent0_findings or []:
        if not isinstance(f, dict):
            continue
        rows.append({
            "file": str(f.get("file") or f.get("file_path") or ""),
            "rule": str(f.get("type") or f.get("rule") or f.get("vuln_type") or ""),
            "title": str(f.get("title") or ""),
        })
    return rows


def make_deterministic_gate(prune_mode: str = "off", min_keep: int = 1) -> GateCallable:
    """纯确定性排序 gate（零模型）：保护/echo-first/去重/复读/triage≤6 健康加成。

    prune_mode="structural" 时叠加结构性剪枝（echo ∪ duplicate ∪ degenerate），
    其余姿态按 GATE-V2-DESIGN §6 v1.1 显式拒绝。
    """

    def gate(hypothesis_set, agent0_findings):
        return rerank_hypotheses(
            hypothesis_set, agent0_findings, backend="deterministic",
            prune_mode=prune_mode, min_keep=min_keep,
        )

    gate.__name__ = "deterministic_gate"
    return gate


def _import_replay():
    """eval/replay.py 运行时懒导入（score_laya 单一数据源）。

    eval/ 不是包，按脚本态目录导入；codeark 不产生对 eval 的导入期依赖。
    """
    eval_dir = Path(__file__).resolve().parents[2] / "eval"
    if str(eval_dir) not in sys.path:
        sys.path.insert(0, str(eval_dir))
    import replay
    return replay


def make_laya_gate(model_path: str, prune_mode: str = "off", min_keep: int = 1) -> GateCallable:
    """laya 评分 gate：live HypothesisSet → items → score_laya → scores map → 重排。

    只喂 Scout 阶段信息（_laya_state 契约），Verify 裁决不进 gate——防标签泄漏。
    prune_mode="structural" 时叠加结构性剪枝（剪枝面与打分独立，I3 仍只认精确键）。
    """
    if not model_path:
        raise ValueError("laya gate 需要 --model <模型目录>")
    replay = _import_replay()  # 构造期导入：eval/ 缺席在挂载时暴露，不拖到扫描中途

    def gate(hypothesis_set, agent0_findings):
        items = [
            {
                "id": str(getattr(h, "id", "") or ""),
                "title": str(getattr(h, "title", "") or ""),
                "vuln_type": str(getattr(h, "vuln_type", "") or ""),
                "file_path": str(getattr(h, "file_path", "") or ""),
                "attack_path": str(getattr(h, "attack_path", "") or ""),
                "code_snippet": str(getattr(h, "code_snippet", "") or ""),
            }
            for h in hypothesis_set.hypotheses
        ]
        baseline = baseline_rows_from_agent0(agent0_findings)
        probs, _confs = replay.score_laya(items, baseline, model_path)
        scores = {item["id"]: float(p) for item, p in zip(items, probs)}
        return rerank_hypotheses(
            hypothesis_set, agent0_findings, scores=scores, backend="laya",
            prune_mode=prune_mode, min_keep=min_keep,
        )

    gate.__name__ = "laya_gate"
    return gate


def resolve_backend(explicit: str | None, env_value: str | None) -> str:
    """--backend 显式值优先；否则 ARCA_GATE_BACKEND（缺省 laya=挂默认）。

    支持的值：laya（默认）/ deterministic / det；其他值报错——挂载旋钮
    必须显式可判，静默回落会掩盖配置错误。
    """
    if explicit:
        return explicit
    value = (env_value or "").strip().lower()
    if value in ("", "laya"):
        return "laya"
    if value in ("deterministic", "det"):
        return "deterministic"
    raise ValueError(f"unsupported ARCA_GATE_BACKEND value: {env_value!r}")


def resolve_prune(explicit: str | None, env_value: str | None) -> str:
    """--prune 显式值优先；否则 ARCA_GATE_PRUNE（缺省 off）。

    支持 off / structural（GATE-V2-DESIGN §6 v1.1 收缩后的全部姿态）。
    threshold/cap 已依 τ 双负结果搁置——设置即显式报错，不静默降级为 off
    （否则会掩盖"以为预算帽生效"的配置错误）。
    """
    raw = explicit if explicit is not None else env_value
    value = (raw or "").strip().lower()
    if value in ("", "off"):
        return "off"
    if value in PRUNE_MODES:
        return value
    if value in ("threshold", "cap"):
        raise ValueError(
            f"prune_mode {value!r} 已按 GATE-V2-DESIGN §6 v1.1 搁置（τ 双负结果）；"
            f"仅支持 {PRUNE_MODES}"
        )
    raise ValueError(f"unsupported prune mode: {raw!r}（仅支持 {PRUNE_MODES}）")


def _resolve_min_keep(env_value: str | None) -> int:
    raw = (env_value or "").strip()
    if not raw:
        return 1
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"ARCA_GATE_PRUNE_MIN_KEEP 非法: {raw!r}") from None
    if value < 1:
        raise ValueError(f"ARCA_GATE_PRUNE_MIN_KEEP 必须是 >=1 的整数: {raw!r}")
    return value


def build_gate_from_env(
    backend: str | None = None, model: str | None = None
) -> tuple[GateCallable | None, str]:
    """生产挂载策略：env 旋钮 → (gate, meta) 或 (None, 降级原因)。

    - ARCA_GATE_BACKEND 缺省 laya；deterministic/det 全环境可用；
    - ARCA_GATE_PRUNE 缺省 off（off/structural）；threshold/cap 或设置了
      ARCA_GATE_PRUNE_TAU/_MAX（已搁置）→ (None, reason)，显式失败不静默回落；
    - ARCA_GATE_PRUNE_MIN_KEEP 缺省 1，非法值同上；
    - laya 需 ARCA_GATE_MODEL（或显式 model）指向模型目录：未设置/目录不存在/
      构造失败 → (None, reason)，调用方告警后无 gate 继续扫（不失败）；
    - 非法 backend 值不静默回落 → (None, reason)（resolve_backend 的报错在此收口）。
    """
    try:
        resolved = resolve_backend(backend, os.environ.get("ARCA_GATE_BACKEND"))
        prune_mode = resolve_prune(None, os.environ.get("ARCA_GATE_PRUNE"))
        min_keep = _resolve_min_keep(os.environ.get("ARCA_GATE_PRUNE_MIN_KEEP"))
        for knob in ("ARCA_GATE_PRUNE_TAU", "ARCA_GATE_PRUNE_MAX"):
            if (os.environ.get(knob) or "").strip():
                raise ValueError(
                    f"{knob} 已按 §6 v1.1 搁置（threshold/cap 未实施），不得设置"
                )
    except ValueError as exc:
        return None, str(exc)
    if resolved == "deterministic":
        return make_deterministic_gate(prune_mode=prune_mode, min_keep=min_keep), "deterministic"
    model_path = model or os.environ.get("ARCA_GATE_MODEL") or ""
    if not model_path:
        return None, "ARCA_GATE_MODEL 未设置（laya checkpoint 缺席，无 gate 降级）"
    if not Path(model_path).is_dir():
        return None, f"ARCA_GATE_MODEL 目录不存在: {model_path}"
    try:
        return make_laya_gate(model_path, prune_mode=prune_mode, min_keep=min_keep), f"laya:{model_path}"
    except Exception as exc:
        return None, f"laya gate 构造失败: {type(exc).__name__}: {exc}"

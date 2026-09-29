#!/usr/bin/env python
"""Gate v1 e2e acceptance runner — M4 门 3 验收工具（本地编码，DSW 执行）。

在 Scout→Verify 之间注入 gate 跑完整六节点管线。gate 只重排序不删除：
原始 Scout 集与 gated 副本都随报告归档（meta.hypothesis_set / meta.gated_hypothesis_set），
eval/replay.py build 可直接消费。

两个后端：
- laya（默认）：eval/replay.score_laya 逐假设 P(KEEP) → rerank_hypotheses(scores=...)，
  确定性保护（非 echo 证据 KEEP 优先 / echo·重复·复读沉底）叠加在模型分之上；
- deterministic：纯确定性排序对照臂（零模型），用于隔离"模型分 vs 结构规则"的贡献。

治理约束（WORK_LOG 2026-09-28 22:58 M4）：M1 v2 裁定通过前**不启用**——本工具入库
不等于 gate 上线。验收对照指标 = Verify 请求数 / 总耗时 / 裁决分布 / findings 数。

用法（DSW，四服务就绪后）：
    ARCA_DEPLOYMENT=local python eval/run_gate_e2e.py /mnt/workspace/repos/variant-20 \
        --model /mnt/workspace/models/laya-r3
    ARCA_DEPLOYMENT=local python eval/run_gate_e2e.py <repo> --backend deterministic
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_EVAL_DIR = str(Path(__file__).resolve().parent)
if _EVAL_DIR not in sys.path:
    sys.path.insert(0, _EVAL_DIR)

import replay  # noqa: E402  # eval/replay.py（同目录脚本态导入，build_hard_exam 同款）

from codeark.cli import _read_repo  # noqa: E402
from codeark.graph.gate import GateResult, rerank_hypotheses  # noqa: E402
from codeark.graph.pipeline import CodeRiskGraph  # noqa: E402
from codeark.models.factory import make_stage_models_from_env  # noqa: E402
from codeark.models.routing import redact_error  # noqa: E402
from codeark.models.schemas import HypothesisSet  # noqa: E402

__all__ = ["baseline_rows_from_agent0", "make_deterministic_gate", "make_laya_gate", "main"]


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


def make_deterministic_gate() -> Callable[[HypothesisSet, list[dict]], GateResult]:
    """纯确定性排序 gate（零模型）：保护/echo-first/去重/复读/triage≤6 健康加成。"""

    def gate(hypothesis_set, agent0_findings):
        return rerank_hypotheses(hypothesis_set, agent0_findings, backend="deterministic")

    gate.__name__ = "deterministic_gate"
    return gate


def make_laya_gate(model_path: str) -> Callable[[HypothesisSet, list[dict]], GateResult]:
    """laya 评分 gate：live HypothesisSet → items → score_laya → scores map → 重排。

    只喂 Scout 阶段信息（_laya_state 契约），Verify 裁决不进 gate——防标签泄漏。
    """
    if not model_path:
        raise ValueError("laya gate 需要 --model <模型目录>")

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
        return rerank_hypotheses(hypothesis_set, agent0_findings, scores=scores, backend="laya")

    gate.__name__ = "laya_gate"
    return gate


async def _main(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"repo directory not found: {repo}")
        return 2
    files = _read_repo(repo)
    if not files:
        print(f"no readable source files: {repo}")
        return 2

    if args.backend == "laya":
        try:
            gate = make_laya_gate(args.model or "")
        except ValueError as exc:
            print(f"gate e2e failed: {exc}")
            return 2
    else:
        gate = make_deterministic_gate()

    routes = make_stage_models_from_env()
    started = time.perf_counter()
    try:
        result = await CodeRiskGraph(stage_models=routes, hypothesis_gate=gate).run(files)
    except Exception as exc:
        print(f"gate e2e failed: {type(exc).__name__}: {redact_error(exc)}")
        return 1
    elapsed = time.perf_counter() - started

    verdicts: dict[str, int] = {}
    for v in result.verifications:
        label = str(getattr(v, "verdict", "?"))
        verdicts[label] = verdicts.get(label, 0) + 1

    out_dir = Path(args.out) if args.out else ROOT / "reports" / f"{repo.name}_gate"
    out_dir.mkdir(parents=True, exist_ok=True)
    for fmt, content in result.reports.items():
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
        (out_dir / f"e2e_report.{fmt}").write_text(text, encoding="utf-8")

    final_report = result.final_report
    if hasattr(final_report, "findings"):
        final_findings = getattr(final_report, "findings", None) or []
    elif isinstance(final_report, dict):
        final_findings = final_report.get("findings") or []
    else:
        final_findings = []
    summary = {
        "repo": str(repo),
        "backend": args.backend,
        "gate": result.gate,
        "elapsed_seconds": round(elapsed, 3),
        "files": len(files),
        "hypotheses": len(getattr(result.hypothesis_set, "hypotheses", []) or []),
        "verify_requests": len(result.verifications),
        "verdicts": verdicts,
        "final_findings": len(final_findings),
        "risk_score": result.risk_score,
        "node_errors": result.node_errors,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[gate-e2e] backend={args.backend} files={len(files)} elapsed={elapsed:.1f}s")
    print(f"  hypotheses={summary['hypotheses']} verify_requests={summary['verify_requests']} verdicts={verdicts}")
    print(f"  gate: backend={result.gate.get('backend')} protected={result.gate.get('protected_ids')}"
          f" fallback={result.gate.get('fallback', False)}")
    print(f"  final_findings={summary['final_findings']} risk_score={result.risk_score}"
          f" node_errors={result.node_errors}")
    print(f"  reports -> {out_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate v1 e2e acceptance runner (reorder-only)")
    parser.add_argument("repo", help="repository directory to scan")
    parser.add_argument("--backend", default="laya", choices=["laya", "deterministic"],
                        help="laya=模型分+确定性保护；deterministic=纯确定性对照臂")
    parser.add_argument("--model", help="laya 模型目录（DSW: /mnt/workspace/models/laya-r3）")
    parser.add_argument("--out", help="报告输出目录（默认 reports/<repo>_gate）")
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())

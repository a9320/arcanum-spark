#!/usr/bin/env python
"""Gate v1 e2e 扩仓验收对照器 — M4 判读工具（本地编码，DSW/本地两用）。

输入：无 gate 基线报告（pipeline archive report.json）+ 一个或多个 gate 臂目录
（run_gate_e2e.py 产物：summary.json + e2e_report.json）。产出验收表（JSON+MD）。

判据（M4 扩仓验收，WORK_LOG 2026-09-30 定稿；门 3 variant-20 单仓证据的加固口径）：
  P1 reorder-only   gated 副本与原始假设集同 id 同数（结构级"只重排不删"）
  P2 no-fallback    臂 gate.fallback == False
  P3 quality-floor  confirmed 与 final_findings 均不低于无 gate 基线
  P4 confirmed-coverage  基线 CONFIRMED 假设逐键 ⊆ 臂 CONFIRMED（外审整改
      2026-10-02：数量判据对"假设集漂移丢真威胁"失明——gate11 v27 基线 CONFIRMED
      的 H6 不在 laya 臂宇宙即为实例）。未钉假设集的数据上 id 是位置级键，
      P4 失败=宇宙漂移或真损失，从严 REJECT；任一侧 verifications 缺失→null
      不猜，记入 missing_evidence。
观测项（不作硬判据）：verify_requests、protected_ids、elapsed、node_errors、语义增量。

用法：
    python eval/compare_gate_e2e.py --baseline <report.json> \
        --arm reports/variant-23_gate_laya --arm reports/variant-23_gate_deterministic \
        --out reports/gate-e2e/acceptance-variant-23.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_EVAL_DIR = str(Path(__file__).resolve().parent)
for _p in (str(ROOT), _EVAL_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import summarize_ablation  # noqa: E402  # eval/ 同目录脚本态导入（run_gate_e2e 同款）

__all__ = ["accept_arm", "compare_arms", "render_markdown", "main"]


def _hyp_ids(meta: dict[str, Any], key: str) -> list[str]:
    rows = (meta.get(key) or {}).get("hypotheses") or []
    return [str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")]


def _confirmed_ids(report: dict[str, Any]) -> set[str] | None:
    """报告的 CONFIRMED 假设 id 集；verifications 缺失 → None（不猜）。"""
    vers = (report.get("meta") or {}).get("verifications")
    if not isinstance(vers, list):
        return None
    return {
        str(row.get("hypothesis_id"))
        for row in vers
        if isinstance(row, dict) and row.get("hypothesis_id")
        and str(row.get("verdict") or "").upper() == "CONFIRMED"
    }


def _load_arm(arm_dir: Path) -> dict[str, Any]:
    summary_path = arm_dir / "summary.json"
    report_path = arm_dir / "e2e_report.json"
    missing = [str(p) for p in (summary_path, report_path) if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"arm 目录缺产物: {missing}（须为 run_gate_e2e.py 输出目录）")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"summary": summary, "report": report}


def accept_arm(
    baseline_row: dict[str, Any],
    baseline_keys: set[tuple[str, str]],
    arm_dir: Path,
    baseline_confirmed: set[str] | None = None,
) -> dict[str, Any]:
    """对照基线行评一个 gate 臂：硬判据 P1-P4 + 观测项，缺失=null 不猜。"""
    arm_dir = Path(arm_dir)
    loaded = _load_arm(arm_dir)
    summary, report = loaded["summary"], loaded["report"]
    meta = report.get("meta") or {}
    row = summarize_ablation.summarize_report(
        arm_dir / "e2e_report.json", arm=arm_dir.name, baseline_keys=baseline_keys
    )

    original_ids = _hyp_ids(meta, "hypothesis_set")
    gated_ids = _hyp_ids(meta, "gated_hypothesis_set")
    reorder_only = bool(gated_ids) and sorted(original_ids) == sorted(gated_ids)

    gate_info = meta.get("gate") if isinstance(meta.get("gate"), dict) else {}
    fallback = gate_info.get("fallback", summary.get("gate", {}).get("fallback"))
    protected = gate_info.get("protected_ids", summary.get("gate", {}).get("protected_ids"))

    arm_confirmed = _confirmed_ids(report)
    coverage_missing = baseline_confirmed is None or arm_confirmed is None
    confirmed_coverage = None if coverage_missing else baseline_confirmed <= arm_confirmed
    missing_confirmed = (
        sorted(baseline_confirmed - arm_confirmed)
        if not coverage_missing else None
    )

    criteria = {
        "P1_reorder_only": reorder_only,
        "P2_no_fallback": fallback is False,
        "P3_quality_floor": (
            row["confirmed"] >= baseline_row["confirmed"]
            and row["final_findings"] >= baseline_row["final_findings"]
        ),
        "P4_confirmed_coverage": confirmed_coverage,
    }
    core_ok = all(
        criteria[key] is True
        for key in ("P1_reorder_only", "P2_no_fallback", "P3_quality_floor")
    )
    return {
        "arm": arm_dir.name,
        "backend": summary.get("backend") or gate_info.get("backend"),
        "criteria": criteria,
        "passed": core_ok and confirmed_coverage is not False,
        "observations": {
            "hypotheses": row["baseline_findings"],
            "verify_requests": summary.get("verify_requests"),
            "confirmed_vs_baseline": [row["confirmed"], baseline_row["confirmed"]],
            "final_findings_vs_baseline": [row["final_findings"], baseline_row["final_findings"]],
            "baseline_confirmed_missing_in_arm": missing_confirmed,
            "semantic_increment_confirmed": row["semantic_increment_confirmed"],
            "refuted": row["refuted"],
            "uncertain": row["uncertain"],
            "protected_ids": protected,
            "elapsed_seconds": summary.get("elapsed_seconds") or row["elapsed_seconds"],
            "node_errors": summary.get("node_errors"),
        },
        "missing_evidence": [
            key
            for key, value in (
                ("fallback", fallback),
                ("verify_requests", summary.get("verify_requests")),
                ("confirmed_coverage", None if coverage_missing else "present"),
            )
            if value is None
        ],
    }


def compare_arms(baseline_path: str | Path, arm_dirs: list[str | Path]) -> dict[str, Any]:
    baseline_path = Path(baseline_path)
    baseline_json = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_row = summarize_ablation.summarize_report(baseline_path, arm="baseline_no_gate")
    baseline_keys = {
        summarize_ablation._finding_key(row)  # noqa: SLF001  # 共享基线键集，与消融器同源
        for row in (baseline_json.get("meta") or {}).get("agent0_findings") or []
        if isinstance(row, dict)
    }
    baseline_confirmed = _confirmed_ids(baseline_json)
    arms = [
        accept_arm(baseline_row, baseline_keys, Path(d), baseline_confirmed)
        for d in arm_dirs
    ]
    overall = all(arm["passed"] for arm in arms) and bool(arms)
    return {
        "schema": "gate-e2e-acceptance/2",
        "baseline": str(baseline_path),
        "verdict": "ACCEPT" if overall else "REJECT",
        "arms": arms,
    }


def render_markdown(acceptance: dict[str, Any]) -> str:
    lines = [
        "# Gate e2e Acceptance",
        "",
        f"> baseline=`{acceptance['baseline']}` — verdict: **{acceptance['verdict']}** "
        "(P1 reorder-only / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage; "
        "REFUTED is a model verdict, not an FP rate)",
        "",
        "| Arm | Backend | P1 | P2 | P3 | P4 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in acceptance["arms"]:
        obs = arm["observations"]
        conf, final = arm["criteria"], obs
        p4 = conf["P4_confirmed_coverage"]
        p4_cell = "✅" if p4 is True else ("❌" if p4 is False else "–")
        lines.append(
            f"| {arm['arm']} | {arm.get('backend') or 'null'} "
            f"| {'✅' if conf['P1_reorder_only'] else '❌'} "
            f"| {'✅' if conf['P2_no_fallback'] else '❌'} "
            f"| {'✅' if conf['P3_quality_floor'] else '❌'} "
            f"| {p4_cell} "
            f"| {obs['confirmed_vs_baseline'][0]}({obs['confirmed_vs_baseline'][1]}) "
            f"| {obs['final_findings_vs_baseline'][0]}({obs['final_findings_vs_baseline'][1]}) "
            f"| {obs['verify_requests'] if obs['verify_requests'] is not None else 'null'} "
            f"| {len(obs['protected_ids'] or [])} "
            f"| {obs['elapsed_seconds'] if obs['elapsed_seconds'] is not None else 'null'} "
            f"| {'PASS' if arm['passed'] else 'FAIL'} |"
        )
    for arm in acceptance["arms"]:
        missing = arm["observations"].get("baseline_confirmed_missing_in_arm")
        if missing:
            lines.append(f"> {arm['arm']}: 基线 CONFIRMED 未覆盖键: {', '.join(missing)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare gate e2e arms against the no-gate baseline")
    parser.add_argument("--baseline", required=True, help="无 gate 基线报告 report.json（e2e archive）")
    parser.add_argument("--arm", action="append", required=True,
                        help="gate 臂目录（run_gate_e2e.py 输出，含 summary.json+e2e_report.json），可多次")
    parser.add_argument("--out", required=True, help="输出 JSON 路径（旁边同写 .md）")
    args = parser.parse_args()
    try:
        acceptance = compare_arms(args.baseline, args.arm)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(acceptance, ensure_ascii=False, indent=2), encoding="utf-8")
        out.with_suffix(".md").write_text(render_markdown(acceptance), encoding="utf-8")
    except Exception as exc:
        print(f"gate e2e compare failed: {type(exc).__name__}: {exc}")
        return 1
    print(render_markdown(acceptance))
    print(f"wrote {args.out} and {out.with_suffix('.md')}")
    return 0 if acceptance["verdict"] == "ACCEPT" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Summarize rules/single-agent/six-agent ablation reports.

The script reports observable model verdicts, not independent truth labels.
Missing elapsed time or provider usage remains ``null`` instead of being
inferred from log fragments.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

__all__ = ["summarize_report", "summarize_reports", "render_markdown"]


def _norm_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def _norm_type(value: Any) -> str:
    return str(value or "").strip().upper()


def _finding_key(row: dict[str, Any]) -> tuple[str, str]:
    return (
        _norm_path(row.get("file") or row.get("file_path")),
        _norm_type(row.get("rule") or row.get("type") or row.get("vuln_type")),
    )


def _usage(meta: dict[str, Any]) -> dict[str, int] | None:
    value = meta.get("usage")
    if not isinstance(value, dict):
        return None
    out = {
        key: int(value[key])
        for key in ("input_tokens", "output_tokens", "total_tokens")
        if isinstance(value.get(key), (int, float))
    }
    return out or None


def summarize_report(path: str | Path, arm: str) -> dict[str, Any]:
    """Return one normalized ablation row from a report JSON file."""
    report_path = Path(path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    meta = report.get("meta") or {}
    ablation = meta.get("ablation") or {}
    baseline = meta.get("agent0_findings") or []
    baseline_keys = {_finding_key(row) for row in baseline if isinstance(row, dict)}
    hypothesis_set = meta.get("hypothesis_set") or {}
    hypotheses = {
        str(row.get("id")): row
        for row in hypothesis_set.get("hypotheses", [])
        if isinstance(row, dict) and row.get("id")
    }
    verdicts = meta.get("verifications") or []
    counts = {"CONFIRMED": 0, "REFUTED": 0, "UNCERTAIN": 0}
    increments: set[tuple[str, str]] = set()
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        label = str(verdict.get("verdict") or "").upper()
        if label in counts:
            counts[label] += 1
        if label != "CONFIRMED":
            continue
        hyp = hypotheses.get(str(verdict.get("hypothesis_id") or ""))
        if hyp is None:
            continue
        key = _finding_key(hyp)
        if key not in baseline_keys:
            increments.add(key)

    if arm == "rules":
        semantic_increment: int | None = 0
    elif verdicts:
        semantic_increment = len(increments)
    else:
        semantic_increment = None

    elapsed = ablation.get("elapsed_seconds")
    if elapsed is None:
        elapsed = meta.get("elapsed_seconds")
    usage = _usage(ablation) or _usage(meta)
    return {
        "arm": arm,
        "path": str(report_path),
        "agent": ablation.get("agent") or ("agent0" if arm == "rules" else arm),
        "baseline_findings": len(baseline),
        "final_findings": len(report.get("findings") or []),
        "confirmed": counts["CONFIRMED"],
        "refuted": counts["REFUTED"],
        "uncertain": counts["UNCERTAIN"],
        "semantic_increment_confirmed": semantic_increment,
        "elapsed_seconds": elapsed if isinstance(elapsed, (int, float)) else None,
        "usage": usage,
        "notes": (
            "REFUTED is an observable model verdict, not an independently labeled FP rate; "
            "semantic increment requires hypothesis/verdict archive."
        ),
    }


def summarize_reports(paths: dict[str, str | Path]) -> dict[str, Any]:
    rows = [summarize_report(path, arm) for arm, path in paths.items()]
    return {"schema": "ablation-summary/1", "arms": rows}


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Ablation Summary",
        "",
        "> REFUTED counts are model verdicts, not independently labeled false-positive rates. "
        "Missing usage or timing stays `null`.",
        "",
        "| Arm | Agent | Baseline | Final | Confirmed | Semantic increment | Refuted | Uncertain | Seconds | Tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.get("arms", []):
        usage = row.get("usage") or {}
        tokens = usage.get("total_tokens", "null")
        lines.append(
            f"| {row['arm']} | {row.get('agent') or 'null'} | {row['baseline_findings']} | "
            f"{row['final_findings']} | {row['confirmed']} | "
            f"{row['semantic_increment_confirmed'] if row['semantic_increment_confirmed'] is not None else 'null'} | "
            f"{row['refuted']} | {row['uncertain']} | "
            f"{row['elapsed_seconds'] if row['elapsed_seconds'] is not None else 'null'} | {tokens} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize three ablation report arms")
    parser.add_argument("--rules", required=True, help="rules-only report JSON")
    parser.add_argument("--single", required=True, help="single-agent report JSON")
    parser.add_argument("--multi", required=True, help="six-agent report JSON")
    parser.add_argument("--out", required=True, help="output JSON path")
    args = parser.parse_args()
    try:
        summary = summarize_reports({
            "rules": args.rules,
            "single_agent": args.single,
            "six_agent": args.multi,
        })
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        out.with_suffix(".md").write_text(render_markdown(summary), encoding="utf-8")
    except Exception as exc:
        print(f"ablation summary failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"wrote {args.out} and {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

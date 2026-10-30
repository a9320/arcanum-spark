"""PITAX rule benchmark runner — deterministic, zero network, zero model.

For each labeled case: run `run_agent0` twice (determinism check), compare the detected
rule ids with the expected ones, and report per-rule recall plus negative-case false
positives. Severity is checked against the rule table too.

Usage:
    python eval/pitax_bench/run.py            # report only (exit 0)
    python eval/pitax_bench/run.py --strict   # gate: exit 1 unless recall 100% and FP 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codeark.tools.pitax_scan import scan_repo  # noqa: E402  (run_agent0 的薄封装，同一条产品路径)
from codeark.pitax.rules import PITAX_RULES  # noqa: E402


def _scan(path: str, text: str) -> list[tuple[str, str, int]]:
    # strict=True：检测器异常必须炸出来，不能被"按 clean 返回"吞成漏报
    findings = scan_repo({path: text}, strict=True)
    return [
        (str(f.get("type")), str(f.get("severity")), int(f.get("line") or 0))
        for f in findings
    ]


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PITAX rule benchmark")
    ap.add_argument("--cases", default=str(HERE / "cases.jsonl"))
    ap.add_argument("--out", default=str(HERE / "score-latest.json"))
    ap.add_argument("--strict", action="store_true", help="exit 1 unless recall=100%% and FP=0")
    args = ap.parse_args(argv)

    cases = _load(Path(args.cases))
    rows: list[dict] = []
    expected_severity = {code: str(rule.get("severity")) for code, rule in PITAX_RULES.items()}

    for case in cases:
        first = _scan(case["path"], case["text"])
        second = _scan(case["path"], case["text"])
        detected = sorted({rule for rule, _, _ in first})
        expected = set(case["expect"])
        missing = sorted(expected - set(detected))
        extra = sorted(set(detected) - expected)
        severity_bad = [
            rule for rule, sev, _ in first
            if expected_severity.get(rule) and sev != expected_severity[rule]
        ]
        rows.append({
            "id": case["id"],
            "kind": case["kind"],
            "note": case.get("note", ""),
            "expected": sorted(expected),
            "detected": detected,
            "missing": missing,
            "extra": extra,
            "false_positive": case["kind"] == "neg" and bool(detected),
            "deterministic": first == second,
            "severity_mismatch": severity_bad,
        })

    pos = [r for r in rows if r["kind"] == "pos"]
    neg = [r for r in rows if r["kind"] == "neg"]
    hit = [r for r in pos if not r["missing"]]
    recall = len(hit) / len(pos) if pos else 0.0
    fp = [r for r in neg if r["false_positive"]]
    nondet = [r for r in rows if not r["deterministic"]]
    sev_bad = [r for r in rows if r["severity_mismatch"]]

    per_rule: dict[str, dict[str, int]] = {}
    for r in pos:
        for rule in r["expected"]:
            bucket = per_rule.setdefault(rule, {"expected": 0, "hit": 0})
            bucket["expected"] += 1
            if rule in r["detected"]:
                bucket["hit"] += 1

    summary = {
        "cases": len(rows),
        "positive": len(pos),
        "recall": round(recall, 4),
        "negative": len(neg),
        "false_positives": len(fp),
        "unexpected_rules": sum(len(r["extra"]) for r in pos),
        "nondeterministic": len(nondet),
        "severity_mismatches": len(sev_bad),
        "per_rule": per_rule,
    }

    print(f"{'case':7} {'kind':4} {'expected':12} {'detected':22} status")
    for r in rows:
        if r["kind"] == "pos":
            status = "MISS " + ",".join(r["missing"]) if r["missing"] else "hit"
            if r["extra"]:
                status += " +extra:" + ",".join(r["extra"])
        else:
            status = "FP " + ",".join(r["detected"]) if r["false_positive"] else "clean"
        if not r["deterministic"]:
            status += " NONDET"
        if r["severity_mismatch"]:
            status += " SEV=" + ",".join(r["severity_mismatch"])
        print(f"{r['id']:7} {r['kind']:4} {','.join(r['expected']) or '-':12} "
              f"{','.join(r['detected']) or '-':22} {status}")

    print("\nper-rule recall:")
    for rule in sorted(per_rule):
        b = per_rule[rule]
        print(f"  {rule:10} {b['hit']}/{b['expected']}")

    print(
        f"\nsummary: recall={summary['recall']:.0%} ({len(hit)}/{len(pos)})  "
        f"neg_FP={summary['false_positives']}/{len(neg)}  "
        f"extra_rules={summary['unexpected_rules']}  "
        f"nondet={summary['nondeterministic']}  sev_mismatch={summary['severity_mismatches']}"
    )

    payload = {"summary": summary, "rows": rows}
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")

    ok = recall == 1.0 and not fp and not nondet and not sev_bad
    if args.strict and not ok:
        print("GATE FAIL (recall 100% and FP 0 required)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
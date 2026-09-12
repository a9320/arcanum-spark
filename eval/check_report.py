#!/usr/bin/env python
"""eval 回归校验器（确定性，零 LLM 调用）——蓝图 §8 预期检出表的机器判定。

用法：
    python eval/check_report.py --report reports/e2e_report.json
    python eval/check_report.py --report reports/clean_report.json --clean

校验内容：
1. agent0 层：meta.agent0_findings 覆盖 expected.agent0_required 的每条 (file, rule) 及最小 count；
2. 定稿层：findings 覆盖 expected.final_required 的每条 (file, vuln_type)，
   且 severity 不低于 min_severity（规则底线，§11-H 只许升级不许降级）；
   Scout 语义增量的额外条目仅提示、不判失败；
3. --clean 模式：干净仓报告 findings 必须为 0（FP=0 验收）。

退出码 0=全部通过，1=有失败项。配套 report 由 python -m codeark.cli 生成。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _norm(p: str) -> str:
    return str(p or "").replace("\\", "/").strip().lower()


def check_main(report_path: Path, expected_path: Path) -> int:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    # 1. agent0 层
    agent0 = report.get("meta", {}).get("agent0_findings") or []
    counts: dict[tuple[str, str], int] = {}
    for f in agent0:
        key = (_norm(f.get("file") or f.get("file_path") or ""),
               str(f.get("rule") or f.get("type") or f.get("vuln_type") or ""))
        counts[key] = counts.get(key, 0) + 1
    for req in expected.get("agent0_required", []):
        key = (_norm(req["file_path"]), req["rule"])
        got = counts.get(key, 0)
        if got < req.get("count", 1):
            failures.append(
                f"agent0 缺口: {req['file_path']} [{req['rule']}] 期望≥{req.get('count', 1)} 实得 {got}"
            )

    # 2. 定稿层（severity 底线）
    findings = report.get("findings") or []
    fmap: dict[tuple[str, str], str] = {}
    for f in findings:
        key = (_norm(f.get("file_path") or f.get("file") or ""),
               str(f.get("vuln_type") or f.get("rule") or f.get("type") or ""))
        sev = str(f.get("severity") or "low").lower()
        if key not in fmap or _SEV_ORDER.get(sev, 9) < _SEV_ORDER.get(fmap[key], 9):
            fmap[key] = sev
    for req in expected.get("final_required", []):
        key = (_norm(req["file_path"]), req["vuln_type"])
        sev = fmap.get(key)
        if sev is None:
            failures.append(f"final finding missing: {req['file_path']} [{req['vuln_type']}]")
        elif _SEV_ORDER.get(sev, 9) > _SEV_ORDER.get(req["min_severity"], 9):
            failures.append(
                f"final downgrade: {req['file_path']} [{req['vuln_type']}] floor {req['min_severity']} got {sev}"
            )
    # 额外条目（Scout 语义增量）：提示不判失败
    expected_keys = {(_norm(r["file_path"]), r["vuln_type"]) for r in expected.get("final_required", [])}
    extras = sorted(k for k in fmap if k not in expected_keys)
    for e in extras:
        print(f"  [info] extra confirmed finding (semantic increment, allowed): {e[0]} [{e[1]}] sev={fmap[e]}")

    print(f"agent0: {len(agent0)} hits / confirmed: {len(findings)} findings")
    if failures:
        for x in failures:
            print(f"  [FAIL] {x}")
        return 1
    print("  [PASS] all expected detections covered, no severity downgrade")
    return 0


def check_clean(report_path: Path) -> int:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    findings = report.get("findings") or []
    if findings:
        for f in findings:
            print(f"  [FAIL] clean-repo false positive: {f.get('file_path') or f.get('file')} "
                  f"[{f.get('vuln_type') or f.get('rule') or f.get('type')}]")
        return 1
    print("  [PASS] clean repo FP=0")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic eval checker (zero LLM)")
    ap.add_argument("--report", required=True, help="path to report.json")
    ap.add_argument("--expected", default=str(Path(__file__).parent / "expected.json"))
    ap.add_argument("--clean", action="store_true", help="clean-repo FP=0 check mode")
    args = ap.parse_args()
    report_path = Path(args.report)
    if not report_path.exists():
        print(f"[FAIL] report not found: {report_path}")
        return 1
    if args.clean:
        return check_clean(report_path)
    return check_main(report_path, Path(args.expected))


if __name__ == "__main__":
    sys.exit(main())

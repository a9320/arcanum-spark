#!/usr/bin/env python
"""T6 验收判据检查器 — 固定假设集重跑卷的 verify 契约验收。

判据（WORK_LOG 10-18 16:41 块 T6）：
1. 官方链假设（默认 H2）必须有裁决记录，hypothesis_id 非空；
2. 不得是降级记录（degraded=True / verification_method=none(degraded) /
   evidence 含"降级人工复核"）；
3. evidence 不得含 peg-native（llama.cpp×gpt-oss 整轮解析失败）；
4. 允许 UNCERTAIN，但 evidence 必须能引用裁定依据（默认 ≥40 字符；
   --require-confirmed 则只收 CONFIRMED/REFUTED）；
5. meta.verify_degraded（若有）必须为 0。

用法：
    python eval/check_verify_acceptance.py <report.json> --target H2
退出码：0=通过，1=不通过，2=输入错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_MIN_EVIDENCE = 40


def check_report(
    report: object, target_id: str = "H2", require_confirmed: bool = False
) -> list[str]:
    """返回问题列表；空列表=通过。纯函数，单测直接喂 dict。"""
    problems: list[str] = []
    if not isinstance(report, dict):
        return ["report 不是 JSON 对象"]
    meta = report.get("meta")
    if not isinstance(meta, dict):
        return ["report.meta 缺失"]
    verifications = meta.get("verifications")
    if not isinstance(verifications, list) or not verifications:
        return ["meta.verifications 缺失或为空"]

    by_id: dict[str, dict] = {}
    for v in verifications:
        if not isinstance(v, dict):
            problems.append(f"裁决记录不是对象: {v!r}")
            continue
        hid = str(v.get("hypothesis_id") or "")
        if not hid:
            problems.append("存在 hypothesis_id 为空的裁决（违反 id 必填契约）")
        else:
            by_id.setdefault(hid, v)
        if v.get("degraded"):
            problems.append(f"{hid or '?'} 是降级记录（degraded=True）")

    target = by_id.get(target_id)
    if target is None:
        problems.append(f"缺少目标假设 {target_id} 的裁决")
    else:
        verdict = str(target.get("verdict") or "").upper()
        method = str(target.get("verification_method") or "")
        evidence = str(target.get("evidence") or "")
        if verdict not in {"CONFIRMED", "REFUTED", "UNCERTAIN"}:
            problems.append(f"{target_id} verdict 非法: {verdict!r}")
        if method == "none(degraded)" or "降级人工复核" in evidence:
            problems.append(f"{target_id} 仍是降级裁决（method={method!r}）")
        if "peg-native" in evidence:
            problems.append(f"{target_id} 证据含 peg-native 解析失败")
        if require_confirmed and verdict == "UNCERTAIN":
            problems.append(f"{target_id} 仍为 UNCERTAIN（--require-confirmed）")
        if verdict == "UNCERTAIN" and len(evidence.strip()) < _MIN_EVIDENCE:
            problems.append(
                f"{target_id} UNCERTAIN 证据过短（{len(evidence.strip())} "
                f"< {_MIN_EVIDENCE}），无法引用裁定依据"
            )

    degraded_count = meta.get("verify_degraded", 0)
    if degraded_count:
        problems.append(f"meta.verify_degraded={degraded_count}（应 0）")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T6 verify 契约验收检查器")
    parser.add_argument("report", help="重跑卷 report.json / e2e_report.json")
    parser.add_argument("--target", default="H2", help="官方链假设 id（默认 H2）")
    parser.add_argument(
        "--require-confirmed", action="store_true",
        help="只接受 CONFIRMED/REFUTED（默认允许有据可引的 UNCERTAIN）",
    )
    args = parser.parse_args(argv)

    path = Path(args.report)
    if not path.is_file():
        print(f"FAIL: 报告不存在: {path}")
        return 2
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: 报告不可读: {exc}")
        return 2

    problems = check_report(report, args.target, args.require_confirmed)
    if problems:
        print(f"FAIL: {len(problems)} 项不达标")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"PASS: {args.target} 获得真实裁决（无降级/无 peg-native/id 契约完整）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

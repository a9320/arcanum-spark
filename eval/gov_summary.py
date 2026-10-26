#!/usr/bin/env python3
"""方差治理 P1 DSW 验收汇总——预注册判据（docs/VERDICT-VARIANCE-GOVERNANCE.md §四）机读判读。

卷目录 = run_gate_e2e.py 输出（含 e2e_report.json，verifications 在顶层或 meta 归档）。

用法:
  python3 eval/gov_summary.py -m a   <ExpA卷目录...>    # 档位一致率（判据 ≥4/5）
  python3 eval/gov_summary.py -m b   <ExpB卷目录...>    # evidence_source 随臂分布（H1 漂移/H2 零效应）
  python3 eval/gov_summary.py -m ref <全部卷目录...>    # conf_ref 零误报闸（命中即 exit 1）

Exp A 判据口径：按假设聚合各卷 (verdict, confidence, degraded) 单元格，一致率=档位
（confidence）跨卷完全相同的假设占比；判决翻转在明细行可见，供人工复核。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# judge v0.7 同口径：REFUTED 高置信=错驳风险样本（台账"自信错驳"判据）
CONF_REF_THRESHOLD = 0.9
# 预注册 §四.1：同假设档位一致率 ≥ 4/5
ANCHOR_PASS_RATE = 0.8


def _load_verifications(vol: Path) -> list[dict]:
    path = vol / "e2e_report.json"
    if not path.is_file():
        print(f"!! 卷缺 e2e_report.json（跳过）: {vol}")
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    verifs = data.get("verifications")
    if verifs is None:  # 兼容 meta 归档形（pipeline meta 同时归档 verifications）
        verifs = (data.get("meta") or {}).get("verifications") or []
    return verifs


def _cell(v: dict) -> str:
    conf = v.get("confidence")
    conf_s = "?" if conf is None else f"{float(conf):.2f}"
    deg = "/deg" if v.get("degraded") else ""
    return f"{v.get('verdict') or '?'}/{conf_s}{deg}"


def _hyp(v: dict) -> str:
    return str(v.get("hypothesis_id") or "(null)")


def mode_a(vols: list[Path]) -> int:
    """Exp A：同假设 confidence 档位跨卷一致率（D1 五档锚）。"""
    by_hyp: dict[str, list[tuple[str, str, float | None]]] = defaultdict(list)
    for vol in vols:
        for v in _load_verifications(vol):
            conf = v.get("confidence")
            by_hyp[_hyp(v)].append((vol.name, _cell(v), None if conf is None else float(conf)))
    total = consistent = 0
    for h in sorted(by_hyp):
        entries = sorted(by_hyp[h])
        tiers = [e[2] for e in entries]
        judged = [t for t in tiers if t is not None]
        is_cons = len(judged) >= 2 and len(set(judged)) == 1
        total += 1
        consistent += 1 if is_cons else 0
        mark = "一致" if is_cons else ("唯一卷" if len(judged) < 2 else "不一致")
        cells = " ".join(f"{e[0]}:{e[1]}" for e in entries)
        print(f"  {h} [{mark}] {cells}")
    if total == 0:
        print("ANCHOR_CONSISTENCY=NO_DATA（0 假设）")
        return 2
    rate = consistent / total
    verdict = "PASS" if rate >= ANCHOR_PASS_RATE else "FAIL"
    print(f"ANCHOR_CONSISTENCY={verdict} ({consistent}/{total} = {rate:.0%}，判据 ≥4/5)")
    return 0 if verdict == "PASS" else 1


def mode_b(vols: list[Path]) -> int:
    """Exp B：evidence_source 随臂分布（D2 溯源；H1 漂移 / H2 零效应对照）。"""
    arms: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for vol in vols:
        name = vol.name.lower()
        arm = "minpack" if "minpack" in name else "default" if "default" in name else "unknown"
        for v in _load_verifications(vol):
            arms[arm][_hyp(v)][str(v.get("evidence_source") or "None")] += 1
    if not arms:
        print("EVIDENCE_DISTRIBUTION=NO_DATA")
        return 2
    for arm in ("default", "minpack", "unknown"):
        if arm not in arms:
            continue
        print(f"== arm={arm} ==")
        for h in sorted(arms[arm]):
            dist = ", ".join(f"{k}×{n}" for k, n in arms[arm][h].most_common())
            print(f"  {h}: {dist}")
    print("判读：H1 官方链应随臂漂移（default 主 repo_file / minpack 主 library_knowledge）；"
          "H2 两臂均主 repo_file（零效应对照）。")
    return 0


def mode_ref(vols: list[Path]) -> int:
    """无误报闸：全部卷 confident_refutations（REFUTED ∧ conf≥0.9）保持 0。"""
    hits: list[tuple[str, str, object]] = []
    for vol in vols:
        for v in _load_verifications(vol):
            conf = v.get("confidence")
            if str(v.get("verdict") or "") == "REFUTED" and conf is not None \
                    and float(conf) >= CONF_REF_THRESHOLD:
                hits.append((vol.name, _hyp(v), conf))
    for vol_name, h, conf in hits:
        print(f"  HIT {vol_name} {h} REFUTED conf={conf}")
    if hits:
        print(f"CONF_REF_GATE=FAIL ({len(hits)} hits)")
        return 1
    print("CONF_REF_GATE=PASS (0)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="方差治理 P1 DSW 验收汇总")
    parser.add_argument("-m", "--mode", choices=("a", "b", "ref"), required=True,
                        help="a=档位一致率 b=溯源分布 ref=零误报闸")
    parser.add_argument("volumes", nargs="+", help="卷目录（run_gate_e2e.py 输出）")
    args = parser.parse_args()
    vols = [Path(p) for p in args.volumes]
    fn = {"a": mode_a, "b": mode_b, "ref": mode_ref}[args.mode]
    return fn(vols)


if __name__ == "__main__":
    sys.exit(main())

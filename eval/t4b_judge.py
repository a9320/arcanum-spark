#!/usr/bin/env python3
"""T4b 判读：poem-collection 证据包两臂（default vs minpack）逐卷提取与对比。

用法（DSW，六卷 ALL DONE 后）：
    python3 eval/t4b_judge.py --base /mnt/workspace/runs/20261021-t4b
判据（对齐一期 WORK_LOG 2026-10-20 22:35）：
    - 完整性：每卷 verify 数>0、node_errors 空（看 summary.json）；
    - 降级台账：degraded 计数逐卷打印（一期两臂共 6 卷为 0）；
    - 可迁移性：官方链假设（★ 行）在 default 臂 CONFIRMED 多数，
      且 minpack 臂非 CONFIRMED 多数 ⇒ 与一期同向，可迁移性成立。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OFFICIAL_KEYS = ("path traversal", "traversal", "lfi", "local file",
                 "directory traversal", "../")


def load_verifications(rep: dict) -> list:
    for holder in (rep.get("meta") or {}, rep):
        vs = holder.get("verifications") if isinstance(holder, dict) else None
        if vs:
            return vs
    return []


def load_hypotheses(rep: dict) -> list:
    hs = (rep.get("meta") or {}).get("hypothesis_set") or rep.get("hypothesis_set") or {}
    return hs.get("hypotheses") or []


def short(v: dict) -> str:
    ev = v.get("evidence") or ""
    if not isinstance(ev, str):
        ev = json.dumps(ev, ensure_ascii=False)
    return (f"{v.get('hypothesis_id', '?'):4} {str(v.get('verdict', '?')):11}"
            f" deg={str(v.get('degraded')).lower():5} ev={len(ev):4}"
            f" m={v.get('verification_method', '?')}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/mnt/workspace/runs/20261021-t4b")
    ap.add_argument("--arms", default="default,minpack")
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    base = Path(args.base)
    official: set[str] = set()
    matrices: dict[str, dict[str, list[str]]] = {}

    for arm in args.arms.split(","):
        per_hyp: dict[str, list[str]] = {}
        for r in range(1, args.runs + 1):
            d = base / f"poem-{arm}-r{r}"
            rep_p = d / "e2e_report.json"
            if not rep_p.exists():
                print(f"[{arm}-r{r}] !! 缺 e2e_report.json（该卷未跑成）")
                continue
            rep = json.loads(rep_p.read_text(encoding="utf-8"))
            vs = load_verifications(rep)
            for h in load_hypotheses(rep):
                text = f"{h.get('title', '')} {h.get('description', '')}".lower()
                if any(k in text for k in OFFICIAL_KEYS):
                    official.add(str(h.get("id", "?")))
            deg = sum(1 for v in vs if v.get("degraded"))
            summ = {}
            summ_p = d / "summary.json"
            if summ_p.exists():
                summ = json.loads(summ_p.read_text(encoding="utf-8"))
            print(f"[{arm}-r{r}] verify={len(vs)} degraded={deg}"
                  f" risk={summ.get('risk_score', '?')}"
                  f" node_errors={summ.get('node_errors', '?')}")
            for v in vs:
                print(f"    {short(v)}")
                per_hyp.setdefault(str(v.get("hypothesis_id", "?")), []).append(
                    f"{v.get('verdict', '?')}/{str(v.get('degraded')).lower()}")
        matrices[arm] = per_hyp

    print("== OFFICIAL 候选 id（title/desc 关键词匹配）==",
          sorted(official) or "(未匹配——人工看 meta.hypothesis_set)")
    print("== 两臂矩阵（verdict/degraded × N 卷）==")
    for h in sorted(set().union(*(set(m) for m in matrices.values()))):
        row = "  ".join(f"{arm}={'|'.join(matrices[arm].get(h, ['-']))}"
                        for arm in matrices)
        print(f"  {h}{' ★' if h in official else ''}: {row}")
    print("== 判据 == ★ 在 default 臂 CONFIRMED 多数 ∧ minpack 臂非 CONFIRMED 多数"
          " ⇒ 可迁移性成立（与一期同向）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""M8/K1 选题器 — 从 NYU_CTF_Bench 克隆枚举候选 challenge → 选题清单骨架。

布局无关：递归找 flag 文件（chal.flag/flag/flag.txt）定位 challenge 目录，
类目从路径段推断（web/pwn/forensics/rev/crypto/misc 任一父目录名命中）。
输出清单骨架（challenge_id/upstream_path/category/flag_present），intended_types
留 null——按协议由人工读题后在清单上补（缺失=null 不猜）。

用法：
  python eval/m8_select_web.py --upstream-root ../NYU_CTF_Bench \
      [--category web] [--limit 20] [--out data/m8_k1_manifest.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FLAG_CANDIDATES = ("chal.flag", "flag", "flag.txt")
CATEGORIES = ("web", "pwn", "forensics", "rev", "crypto", "misc")


def infer_category(rel_parts: tuple[str, ...]) -> str | None:
    lowered = [p.lower() for p in rel_parts]
    for cat in CATEGORIES:
        if cat in lowered:
            return cat
    return None


def _challenge_root(root: Path, flag_parent: Path) -> Path:
    """启发式：challenge 根 = 类目段的下一层目录（flag 常在 challenge 深处的
    src/dist 等子目录）；路径无类目段则回退 flag 原位。真实布局落地后按证据微调。"""
    try:
        rel = flag_parent.relative_to(root)
    except ValueError:
        return flag_parent
    parts = rel.parts
    cat_idx = next((i for i, p in enumerate(parts) if p.lower() in CATEGORIES), None)
    if cat_idx is None:
        return flag_parent
    return root.joinpath(*parts[: cat_idx + 2])


def select_challenges(upstream_root: Path, category: str) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for flag_name in FLAG_CANDIDATES:
        for flag_path in sorted(upstream_root.rglob(flag_name)):
            chal_dir = _challenge_root(upstream_root, flag_path.parent)
            if str(chal_dir) in seen:
                continue
            seen.add(str(chal_dir))
            rel = chal_dir.relative_to(upstream_root)
            cat = infer_category(rel.parts)
            if cat is not None and cat != category:
                continue
            rows.append({
                "challenge_id": chal_dir.name,
                "upstream_path": rel.as_posix(),
                "category": cat,
                "flag_present": True,
                "intended_types": None,
                "notes": "",
            })
    rows.sort(key=lambda r: r["upstream_path"])
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="M8/K1 web-challenge selector")
    ap.add_argument("--upstream-root", required=True, help="NYU_CTF_Bench 克隆根")
    ap.add_argument("--category", default="web", choices=list(CATEGORIES) + ["all"])
    ap.add_argument("--limit", type=int, default=None, help="截取前 N 个（骨架用，人工终选）")
    ap.add_argument("--out", default=None, help="输出 JSON（缺省 stdout）")
    args = ap.parse_args()

    root = Path(args.upstream_root)
    if not root.is_dir():
        print(f"upstream root not found: {root}", file=sys.stderr)
        return 2
    rows = select_challenges(root, args.category)
    if args.category != "all":
        uncat = [r for r in rows if r["category"] is None]
        if uncat:
            print(f"note: {len(uncat)} challenges had no category in path "
                  f"(category=null, 人工归类)", file=sys.stderr)
    if args.limit:
        rows = rows[: args.limit]
    payload = json.dumps(rows, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"wrote {len(rows)} candidates -> {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""finetune_export：gate_dataset(+_full).json → 官方 records.jsonl（R0 微调训练输入，纯 stdlib）。

官方契约（rl_common.encode_record 代码级钉死，2026-09-27，本地存档 $TEMP/rl_common.py）：
    rec = {"state": str,               # _laya_state 输出——复用 eval 侧同函数，train/eval 分布一致是命门
           "qs": [{"t": "choice",      # 内部格式：build_sequence:56 直取 q["ins"]、render_options:37 直取 q["crit"]。
                   "ins": ...,         #   ⚠ 推理侧外部 API 键名 instructions/criteria 是 RLAgent._to_internal 的
                   "crit": {...},      #   输入侧写法，训练 records 必须用内部键名 ins/crit（WORK_LOG 22:15 区块
                   "y": 0,             #   记法即此处修正）；两者混用 = KeyError。
                   "soft": [...]},     # 可选软标签（长度 k）；R0 用 one-hot（y 即可），不写 soft
                  ...],
           "src": "<run 名>",          # encode_record 原样透传到每条训练样本；train/val 按 src 整体切分防泄漏
           "meta": {...}}              # 私有追溯键：encode_record 不读额外键，训练后可回查 item id
y 映射：KEEP→0（选项 A）、PRUNE→1（选项 B）；REVIEW/未知剔除。train=True 时官方内建选项乱序
（encode_record:253），records 无需预洗。crit 用有序 dict，插入序=标签序，渲染 "A: KEEP…" / "B: PRUNE…"。

用法：
    python eval/finetune_export.py --dataset runs/20260926-healthy/gate_dataset_full.json \
        --dataset runs/20260926-healthy2/gate_dataset_full.json --out records.jsonl \
        [--val-srcs 20260926-healthy2]      # 指定 src 整体进 val → 另写 records.train.jsonl/records.val.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

try:  # 直接脚本执行（python eval/finetune_export.py，sys.path[0]=eval/）
    from replay import _SCORE_LAYA_CRITERIA, _SCORE_LAYA_INSTRUCTIONS, _laya_state
except ImportError:  # 包导入（pytest / python -m）
    from eval.replay import _SCORE_LAYA_CRITERIA, _SCORE_LAYA_INSTRUCTIONS, _laya_state

# gate 裁决 → 正确选项下标（crit 顺序 {"A": KEEP…, "B": PRUNE…}，与 score_laya 同一套常量）
GATE_TO_Y = {"KEEP": 0, "PRUNE": 1}


def derive_src(path: Path) -> str:
    """run 名推导：e2e 归档目录名（如 20260926-healthy2）优先，退回文件 stem。"""
    return path.parent.name or path.stem


def item_to_record(item: dict, baseline_rows: list[dict], src: str) -> dict | None:
    """单假设条目 → 官方 record；gate 不在 {KEEP, PRUNE}（REVIEW 等）→ None 剔除。

    state/ins/crit 全部复用 eval 侧对象（import 共享），保证训练序列与 score_laya
    考卷逐 token 同构；meta 仅作追溯，官方 encode_record 忽略额外键。
    """
    gate = str((item.get("label") or {}).get("gate") or "")
    y = GATE_TO_Y.get(gate)
    if y is None:
        return None
    return {
        "state": _laya_state(item, baseline_rows),
        "qs": [{"t": "choice", "ins": _SCORE_LAYA_INSTRUCTIONS,
                "crit": dict(_SCORE_LAYA_CRITERIA), "y": y}],
        "src": src,
        "meta": {"item_id": item.get("id", ""), "gate": gate,
                 "origin": item.get("origin", ""), "file_path": item.get("file_path", "")},
    }


def export_datasets(loaded: list[tuple[str, dict]], val_srcs: set[str]) -> tuple[list[dict], list[dict], dict]:
    """loaded = [(src, dataset_dict)] → (train_records, val_records, 统计)。

    防泄漏纪律：src 是切分原子（同一 run 的条目整体去留，绝不按条目随机切——
    同 run 同基线域的条目互为近重复，条目级切分 = val 被 train 见过）。
    """
    train: list[dict] = []
    val: list[dict] = []
    stats = {"n_items": 0, "n_kept": 0, "n_dropped": 0, "per_src": {}, "dropped_ids": []}
    for src, ds in loaded:
        baseline = ds.get("baseline_rows") or []
        per = stats["per_src"].setdefault(src, {"items": 0, "records": 0, "dropped": 0})
        for item in ds.get("items") or []:
            stats["n_items"] += 1
            per["items"] += 1
            rec = item_to_record(item, baseline, src)
            if rec is None:
                stats["n_dropped"] += 1
                per["dropped"] += 1
                stats["dropped_ids"].append(item.get("id", ""))
                continue
            stats["n_kept"] += 1
            per["records"] += 1
            (val if src in val_srcs else train).append(rec)
    return train, val, stats


def write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="gate_dataset → 官方 records.jsonl（Laya R0 微调，零 LLM/零 torch）")
    ap.add_argument("--dataset", action="append", required=True,
                    help="gate_dataset(.json/_full.json) 路径，可重复")
    ap.add_argument("--out", default="records.jsonl", help="全量输出（--val-srcs 未给时唯一产物）")
    ap.add_argument("--val-srcs", default="",
                    help="逗号分隔的 src 列表：这些 run 整体进 val，其余进 train"
                         "（写 <out>.train.jsonl / <out>.val.jsonl）")
    args = ap.parse_args()

    loaded: list[tuple[str, dict]] = []
    for p in args.dataset:
        path = Path(p)
        ds = json.loads(path.read_text(encoding="utf-8"))
        if not (ds.get("items") or ds.get("baseline_rows")):
            print(f"[finetune_export] {path} 缺 items/baseline_rows（schema 不符？）")
            return 1
        loaded.append((derive_src(path), ds))

    val_srcs = {s.strip() for s in args.val_srcs.split(",") if s.strip()}
    unknown = val_srcs - {src for src, _ in loaded}
    if unknown:
        print(f"[finetune_export] --val-srcs 含未出现 src: {sorted(unknown)}"
              f"（可用 src: {sorted({src for src, _ in loaded})}）")
        return 1

    train, val, stats = export_datasets(loaded, val_srcs)
    out = Path(args.out)
    if val_srcs:
        write_jsonl(out.with_suffix(".train.jsonl"), train)
        write_jsonl(out.with_suffix(".val.jsonl"), val)
    else:
        write_jsonl(out, train + val)

    print(f"[finetune_export] 条目 {stats['n_items']} → records {stats['n_kept']}"
          f"（剔除 {stats['n_dropped']}：REVIEW/未知 gate{stats['dropped_ids'][:6]}）")
    for src, per in stats["per_src"].items():
        lane = "VAL " if src in val_srcs else "train"
        print(f"  [{lane}] {src}: items {per['items']} → records {per['records']}"
              f"（剔除 {per['dropped']}）")
    if val_srcs:
        print(f"  → {out.with_suffix('.train.jsonl')}（{len(train)}）+ {out.with_suffix('.val.jsonl')}（{len(val)}）"
              f"  按 src 整体切分，无条目级泄漏面")
    else:
        print(f"  → {out}（{len(train) + len(val)}，未切分）")
    print("  y: KEEP→0 / PRUNE→1；train 侧选项乱序由官方 encode_record(train=True) 内建")
    return 0


if __name__ == "__main__":
    sys.exit(main())

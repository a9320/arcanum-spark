#!/usr/bin/env python
"""Laya 逐题计时+判分评测 — hard_exam 全卷逐题用时与准确性（零额外依赖）。

用途（2026-09-30 定稿）：
  ①逐题 latency（模型加载/首调冷启/稳态中位分开报告）；
  ②阈值 0.5 混淆矩阵 + 准确率 + AP(KEEP) + Brier/ECE；
  ③错题清单（预测≠标签）落盘 = 微调素材候选（经同型异实例 anti-leak 转化后入
    训练集，考卷本体保持 held-out——直接拿考卷错题训练=烧卷，禁止）。

用法：
    python eval/time_laya.py --dataset reports/hard-exam-v2/gate_dataset_hard.json \
        --model /mnt/workspace/models/laya-r3 --out reports/hard-exam-v2/timing-r3.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_EVAL_DIR = str(Path(__file__).resolve().parent)
for _p in (str(ROOT), _EVAL_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import replay  # noqa: E402  # eval/ 同目录脚本态导入（run_gate_e2e 同款）

THRESH = 0.5


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-item timing + accuracy for Laya gate scoring")
    ap.add_argument("--dataset", required=True, help="gate-dataset JSON（ds.items[].label.gate）")
    ap.add_argument("--model", required=True, help="laya 模型目录（含 rl_agent_api.py）")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    args = ap.parse_args()

    ds = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    items = ds["items"]
    baseline = ds.get("baseline_rows") or []
    if not items:
        print("[time-laya] 数据集无条目")
        return 1

    t0 = time.perf_counter()
    agent = replay._load_laya_agent(args.model)  # noqa: SLF001  # 计时包装复用同一加载器
    load_s = time.perf_counter() - t0

    rows: list[dict] = []
    latencies: list[float] = []
    for i, it in enumerate(items):
        state = replay._laya_state(it, baseline)
        q = {f"q{i}": {"type": "choice", "instructions": replay._SCORE_LAYA_INSTRUCTIONS,
                       "criteria": dict(replay._SCORE_LAYA_CRITERIA)}}
        t1 = time.perf_counter()
        out = agent.system_one(state, q)
        dt_ms = (time.perf_counter() - t1) * 1000
        a = ((out or {}).get("answers") or {}).get(f"q{i}") or {}
        p = min(max(float((a.get("probabilities") or {}).get("A") or 0.0), 0.0), 1.0)
        label = it["label"]["gate"]
        pred = "KEEP" if p >= THRESH else "PRUNE"
        rows.append({
            "id": it["id"],
            "label": label,
            "p_keep": round(p, 4),
            "confidence": float(a.get("confidence") or 0.0),
            "pred": pred,
            "correct": None if label == "REVIEW" else (pred == label),
            "evidence_backed": bool(it.get("heuristics", {}).get("evidence_backed")),
            "latency_ms": round(dt_ms, 1),
            "title": str(it.get("title") or "")[:60],
        })
        latencies.append(dt_ms)

    scored = [r for r in rows if r["label"] != "REVIEW"]
    tp = sum(1 for r in scored if r["pred"] == "KEEP" and r["label"] == "KEEP")
    fp = sum(1 for r in scored if r["pred"] == "KEEP" and r["label"] == "PRUNE")
    tn = sum(1 for r in scored if r["pred"] == "PRUNE" and r["label"] == "PRUNE")
    fn = sum(1 for r in scored if r["pred"] == "PRUNE" and r["label"] == "KEEP")
    probs = [r["p_keep"] for r in scored]
    ys = [1.0 if r["label"] == "KEEP" else 0.0 for r in scored]
    ranked_labels = [r["label"] for r in sorted(rows, key=lambda r: -r["p_keep"])]
    wrong = [r for r in scored if r["correct"] is False]

    summary = {
        "schema": "laya-timing/1",
        "model": args.model,
        "dataset": args.dataset,
        "n_items": len(items),
        "model_load_seconds": round(load_s, 3),
        "latency_ms": {
            "first_call": round(latencies[0], 1),
            "median": round(statistics.median(latencies), 1),
            "min": round(min(latencies), 1),
            "max": round(max(latencies), 1),
            "total": round(sum(latencies), 1),
        },
        "accuracy@0.5": {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "accuracy": round((tp + tn) / len(scored), 4) if scored else None,
            "false_prune_rate": round(fn / (tp + fn), 4) if (tp + fn) else None,
            "false_keep_rate": round(fp / (tn + fp), 4) if (tn + fp) else None,
        },
        "AP(KEEP)": round(replay.average_precision(ranked_labels), 4),
        "Brier": round(replay.brier_score(probs, ys), 4) if scored else None,
        "ECE": round(replay.expected_calibration_error(probs, ys), 4) if scored else None,
        "wrong_items": [{"id": r["id"], "label": r["label"], "pred": r["pred"],
                         "p_keep": r["p_keep"], "title": r["title"]} for r in wrong],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "items": rows}, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print(f"[time-laya] model_load={load_s:.1f}s  n={len(items)}")
    lat = summary["latency_ms"]
    print(f"  latency(ms): first={lat['first_call']} median={lat['median']} "
          f"min={lat['min']} max={lat['max']} total={lat['total']}")
    print(f"  accuracy@0.5: {tp + tn}/{len(scored)}  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  AP(KEEP)={summary['AP(KEEP)']}  Brier={summary['Brier']}  ECE={summary['ECE']}")
    if wrong:
        print(f"  错题 {len(wrong)} 条（微调素材候选，经同型异实例转化入训）：")
        for r in wrong:
            print(f"    {r['id']}  label={r['label']} pred={r['pred']} p={r['p_keep']}  {r['title']}")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

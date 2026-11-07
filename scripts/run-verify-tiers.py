#!/usr/bin/env python
"""Verify-only 五档一致性微基准（方差治理 Exp A 前哨；单模型可跑，无需五服务共驻）。

用途（2026-11-07 W7900/gfx1100 窗）：只起一个 verify 模型（生产默认 gpt-oss :8085），
对**钉假设集**重跑 N 次逐假设裁决，统计 D1 五档锚（0.95/0.9/0.75/0.5/0.3）与
verdict 的跨 run 一致率。

判据（预注册，前哨口径）：每假设 tier 一致率 ≥4/5 = PASS；verdict 翻转只记观察不判劣。
对照 = 归档 meta.verifications（MI300X 参照）——仅观察：硬件与证据包都不同，绝对判决
可比性为零。

证据包口径：归档不含被扫仓源文件，files 由假设 code_snippet 合成（输出 meta 披露
evidence_pack=synthetic_from_snippet）——一致性测量只要求输入固定，合成即满足。

用法：
  ARCA_DEPLOYMENT=local python scripts/run-verify-tiers.py \
      --runs 5 --from reports/20261102-harden/reuse-r1/e2e_report.json --out /tmp/tiers.json
前提：ARCA_DEPLOYMENT=local + :8085 verify 模型就绪（scripts/check_endpoints.py 可核）。
self-test：--self-test 用合成记录离线自测统计逻辑，不调模型。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codeark.agents.verify_agent import run_verify_split, snap_confidence  # noqa: E402
from codeark.models.factory import make_stage_models_from_env  # noqa: E402
from codeark.models.schemas import HypothesisSet  # noqa: E402


def _synthetic_files(hs: HypothesisSet) -> dict[str, str]:
    """假设 code_snippet → files dict（证据包原料；空 snippet 用 title+attack_path 兜底）。"""
    files: dict[str, str] = {}
    for h in hs.hypotheses:
        path = (h.file_path or "").replace("\\", "/").strip() or "context.txt"
        content = (h.code_snippet or "").strip() or f"{h.title}\n{h.attack_path}"
        files[path] = (files[path] + "\n" + content) if path in files else content
    return files


def _tier(value: object) -> float | None:
    try:
        return snap_confidence(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _modal_agreement(samples: list[tuple[str, float | None]], runs: int) -> dict:
    """单假设聚合：verdict 集 + tier 众数一致率（degraded 样本剔除后计）。"""
    valid = [(v, t) for v, t in samples if t is not None]
    tier_counts = Counter(t for _, t in valid)
    top_tier, top_n = ("", 0)
    if tier_counts:
        # 平手取更靠近 0.5 的锚（与 snap_confidence 同取向）
        top_tier, top_n = min(
            tier_counts.items(), key=lambda kv: (-kv[1], abs(kv[0] - 0.5))
        )
    return {
        "verdicts": sorted({v for v, _ in valid}),
        "verdict_flip": len({v for v, _ in valid}) > 1,
        "tiers": {str(k): v for k, v in sorted(tier_counts.items(), reverse=True)},
        "modal_tier": top_tier,
        "agreement": round(top_n / len(valid), 3) if valid else 0.0,
        "valid_samples": len(valid),
        "degraded_samples": len(samples) - len(valid),
        # 判据（本微基准预注册）：tier 一致率 ≥4/5 ∧ verdict 零翻转 ∧ 有效样本 ≥4。
        # 比 Exp A 的纯档位判据更严——verdict 翻转是最强不稳信号，出现即 FAIL。
        # runs>=4 是实验设计约束，在 main() 的 CLI 层卡（统计函数保持纯函数）。
        "pass": len(valid) >= 4 and top_n >= 4 and len({v for v, _ in valid}) == 1,
    }


def _stats(per_run: list[dict[str, list[dict]]], runs: int) -> dict:
    """per_run[i] = {hyp_id: [(verdict, tier), ...]}（单 run 内逐假设）。"""
    by_hyp: dict[str, list[tuple[str, float | None]]] = {}
    order: list[str] = []
    for run in per_run:
        for hid, rec in run.items():
            if hid not in by_hyp:
                by_hyp[hid] = []
                order.append(hid)
            by_hyp[hid].extend(rec)
    hyps = {hid: _modal_agreement(samples, runs) for hid, samples in by_hyp.items()}
    return {
        "hypotheses": hyps,
        "all_pass": bool(hyps) and all(h["pass"] for h in hyps.values()),
        "verdict_flips": sorted(hid for hid, h in hyps.items() if h["verdict_flip"]),
    }


def _record(vers: list) -> dict[str, list[tuple[str, float | None]]]:
    out: dict[str, list[tuple[str, float | None]]] = {}
    for v in vers:
        vid = str(getattr(v, "hypothesis_id", "") or "")
        out.setdefault(vid, []).append(
            (str(getattr(v, "verdict", "") or ""), _tier(getattr(v, "confidence", None)))
        )
    return out


def _load_fixture(path: Path) -> tuple[HypothesisSet, dict[str, tuple[str, float]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = data.get("meta") or {}
    hs = HypothesisSet.model_validate(meta["hypothesis_set"])
    reference = {
        str(v.get("hypothesis_id")): (
            str(v.get("verdict") or ""), _tier(v.get("confidence")) or 0.0
        )
        for v in meta.get("verifications") or []
        if isinstance(v, dict) and v.get("hypothesis_id")
    }
    return hs, reference


def _self_test() -> int:
    stable = [("CONFIRMED", 0.95)] * 5
    flip = [("CONFIRMED", 0.95)] * 3 + [("UNCERTAIN", 0.5)] * 2
    drift = [("CONFIRMED", 0.95)] * 4 + [("CONFIRMED", 0.75)]
    stats = _stats(
        [{"H1": stable} for _ in range(5)],
        runs=5,
    )
    assert stats["all_pass"] and stats["hypotheses"]["H1"]["modal_tier"] == 0.95
    merged = _stats(
        [{"H2": flip[:3]}, {"H2": flip[3:]}, {"H2": [("CONFIRMED", 0.95)] * 5}],
        runs=3,
    )
    h2 = merged["hypotheses"]["H2"]
    assert h2["verdict_flip"] and not h2["pass"] and h2["agreement"] == 0.8
    drift_stats = _stats(
        [{"H3": drift[:2]}, {"H3": drift[2:]}, {"H3": [("CONFIRMED", 0.95)] * 5}],
        runs=3,
    )
    assert drift_stats["hypotheses"]["H3"]["modal_tier"] == 0.95
    assert not drift_stats["hypotheses"]["H3"]["verdict_flip"]
    assert drift_stats["hypotheses"]["H3"]["pass"]
    # tier 漂移（无 verdict 翻转）：0.9×3 + 0.5×2 → 众数 3/5 < 4 → FAIL
    tier_drift = _stats(
        [{"H4": [("CONFIRMED", 0.9)] * 3 + [("CONFIRMED", 0.5)] * 2}],
        runs=5,
    )
    assert not tier_drift["hypotheses"]["H4"]["pass"]
    assert tier_drift["hypotheses"]["H4"]["agreement"] == 0.6
    print("SELF-TEST PASS")
    return 0


async def _main(args: argparse.Namespace) -> int:
    hs, reference = _load_fixture(Path(args.frm))
    files = _synthetic_files(hs)
    print(f"[tiers] hyps={len(hs.hypotheses)} files={len(files)} runs={args.runs} "
          f"evidence_pack=synthetic_from_snippet")
    stage_models = make_stage_models_from_env()
    model = stage_models.resolve("verify", None)
    per_run: list[dict[str, list[tuple[str, float | None]]]] = []
    timings: list[float] = []
    for i in range(1, args.runs + 1):
        t0 = time.perf_counter()
        vers = await run_verify_split(
            hs, files, model, prompt_files=files,
            inter_call_delay=args.delay, max_concurrency=1,
            per_invoke_timeout=args.timeout,
        )
        elapsed = time.perf_counter() - t0
        timings.append(round(elapsed, 1))
        rec = _record(vers)
        per_run.append(rec)
        print(f"[tiers] run {i}/{args.runs} elapsed={elapsed:.1f}s "
              f"verdicts={ {k: v[-1][0] for k, v in rec.items()} }")
    stats = _stats(per_run, args.runs)
    payload = {
        "schema": "verify-tiers-microbench/1",
        "fixture": str(args.frm),
        "runs": args.runs,
        "evidence_pack": "synthetic_from_snippet",
        "elapsed_per_run": timings,
        "reference_mi300x": {k: {"verdict": v[0], "tier": v[1]} for k, v in reference.items()},
        "stats": stats,
        "verdict": "PASS" if stats["all_pass"] else "FAIL",
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[tiers] wrote {args.out}")
    print(text)
    print(f"[tiers] VERDICT: {payload['verdict']}（前哨观察口径，不替代 Exp A 预注册实验）")
    return 0 if stats["all_pass"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="verify-only tier consistency microbench")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--from", dest="frm", default="reports/20261102-harden/reuse-r1/e2e_report.json",
                    help="钉假设集来源（e2e 报告，meta.hypothesis_set）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=360.0)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return _self_test()
    if args.runs < 4:
        print("!! --runs 至少 4（预注册 N=5）；样本不足无一致性可言", file=sys.stderr)
        return 2
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())

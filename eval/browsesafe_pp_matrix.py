"""Per-attack-type coverage matrix for the PITAX static battery on BrowseSafe++.

Runs every ``codeark.pitax.detectors.detect_*`` over a local shard directory and
reports: overall confusion/F1/FPR, per-attack-type recall (malicious pages),
per-detector hits split by page arm (FP attribution), and a sample of
benign-page false positives for manual review.

Shards are processed one at a time (load -> score -> free) because materializing
all 21 shards at once exhausts memory (~59k HTML pages).

    <venv-python> eval/browsesafe_pp_matrix.py --source <shard-dir> \
        [--shards 0000,0003] [--fp-samples 60] [--output out.json]
"""
import argparse
import collections
import json
import shutil
import sys
import tempfile
from pathlib import Path

import browsesafe_pp as bs

SPARK_ROOT = Path(__file__).resolve().parents[1]
if str(SPARK_ROOT) not in sys.path:
    sys.path.insert(0, str(SPARK_ROOT))

from codeark.pitax import detectors as pitax  # noqa: E402

DETECTORS = tuple(
    getattr(pitax, name)
    for name in sorted(dir(pitax))
    if name.startswith("detect_") and callable(getattr(pitax, name))
)


def run_page(content: str):
    """Return (detector names hit, total findings, detector errors)."""
    hits, errors, total = [], 0, 0
    for fn in DETECTORS:
        try:
            found = fn(content, "page") or []
        except Exception:
            errors += 1
            found = []
        if found:
            hits.append(fn.__name__)
            total += len(found)
    return hits, total, errors


def score_bench(bench):
    """Yield (pair, m_hits, b_hits, errors) per pair."""
    for pair in bench.pairs:
        m_hits, _, e1 = run_page(pair.malicious.content)
        b_hits, _, e2 = run_page(pair.benign.content)
        yield pair, m_hits, b_hits, e1 + e2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, help="Directory with members-*.parquet shards")
    parser.add_argument("--shards", help="Comma-separated 4-digit shard suffixes to run (default: all)")
    parser.add_argument("--view", default="html", choices=("html", "markdown", "accessibility"))
    parser.add_argument("--fp-samples", type=int, default=60)
    parser.add_argument("--output", help="Write JSON report here")
    args = parser.parse_args()

    source = Path(args.source)
    shards = sorted(source.glob("members-*.parquet"))
    if args.shards:
        keep = {f"members-train-{s.strip()}.parquet" for s in args.shards.split(",")}
        shards = [p for p in shards if p.name in keep]
    if not shards:
        sys.exit(f"no shards matched under {source}")

    agg = {
        "tp": 0, "fp": 0, "tn": 0, "fn": 0, "errors": 0, "pairs": 0,
        "both": 0, "attack_only": 0, "control_only": 0, "neither": 0,
    }
    by_type = collections.defaultdict(lambda: {"mal": 0, "mal_hit": 0})
    per_detector = {fn.__name__: {"malicious_pages": 0, "benign_pages": 0} for fn in DETECTORS}
    fp_samples = []

    for idx, shard in enumerate(shards, 1):
        tmp = Path(tempfile.mkdtemp(prefix="bspp-"))
        try:
            shutil.copy(shard, tmp / shard.name)
            bench = bs.load(source=tmp, split="train", view=args.view)
            for pair, m_hits, b_hits, errs in score_bench(bench):
                mp, bp = bool(m_hits), bool(b_hits)
                attack_type = pair.metadata.get("attack_type", "?")
                agg["pairs"] += 1
                agg["errors"] += errs
                by_type[attack_type]["mal"] += 1
                if mp:
                    by_type[attack_type]["mal_hit"] += 1
                for name in m_hits:
                    per_detector[name]["malicious_pages"] += 1
                for name in b_hits:
                    per_detector[name]["benign_pages"] += 1
                agg["tp"] += mp
                agg["fn"] += not mp
                agg["fp"] += bp
                agg["tn"] += not bp
                if mp and not bp:
                    agg["both"] += 1
                elif mp and bp:
                    agg["attack_only"] += 1
                elif bp:
                    agg["control_only"] += 1
                else:
                    agg["neither"] += 1
                if bp and len(fp_samples) < args.fp_samples:
                    fp_samples.append({"pair_id": pair.pair_id, "attack_type": attack_type, "detectors": b_hits})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        tp, fp, fn = agg["tp"], agg["fp"], agg["fn"]
        print(
            f"[{idx}/{len(shards)}] {shard.name}: cum pairs={agg['pairs']} "
            f"tp={tp} fp={fp} fn={fn} recall={tp / (tp + fn) if tp + fn else 0:.3f}",
            flush=True,
        )

    tp, fp, tn, fn = agg["tp"], agg["fp"], agg["tn"], agg["fn"]
    pairs = agg["pairs"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    report = {
        "view": args.view,
        "shards": [p.name for p in shards],
        "pairs": pairs,
        "pages": 2 * pairs,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision and recall else None,
        "benign_fpr": fp / (fp + tn) if fp + tn else None,
        "pair_correctness": agg["both"] / pairs if pairs else None,
        "paired_outcomes": {
            "both_correct": agg["both"], "attack_only": agg["attack_only"],
            "control_only": agg["control_only"], "neither": agg["neither"],
        },
        "detector_errors": agg["errors"],
        "per_attack_type": {
            k: {**v, "recall": v["mal_hit"] / v["mal"] if v["mal"] else None}
            for k, v in sorted(by_type.items())
        },
        "per_detector_arms": per_detector,
        "fp_samples": fp_samples,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

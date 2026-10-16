"""Score the CodeRisk PITAX static detector battery on BrowseSafe++ pairs.

Zero-LLM, rule-based: wraps every ``codeark.pitax.detectors.detect_*`` function
as a browsesafe_pp detector and reports the benchmark's standard metrics
(f1_valid / pair_correctness), plus a per-detector hit breakdown that seeds the
PITAX-vs-24-attack-types coverage matrix.

    python -m browsesafe_pp.testing ./fixture                       # offline fixture
    <venv-python> eval/browsesafe_pp_eval.py --source ./fixture     # smoke
    <venv-python> eval/browsesafe_pp_eval.py --view html --n-pairs 500   # Hub train

Requires the dedicated benchmark venv (not the project venv):
    python -m venv <dir> && <dir>/Scripts/pip install -e <browsesafe-plus-plus-checkout> httpx
"""
import argparse
import collections
import json
import sys
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

HITS: collections.Counter = collections.Counter()


def predict(request: bs.DetectorInput) -> bs.Prediction:
    findings = []
    for fn in DETECTORS:
        try:
            found = fn(request.content, "page") or []
        except Exception:
            HITS["error:" + fn.__name__] += 1
            found = []
        if found:
            HITS[fn.__name__] += 1
        findings.extend(found)
    return bs.Prediction(injected=bool(findings), score=min(1.0, len(findings) / 2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="Local shard directory; omit to download from the Hub")
    parser.add_argument("--split", default="train")
    parser.add_argument("--view", default="html", choices=("html", "markdown", "accessibility"))
    parser.add_argument("--n-pairs", type=int, default=100)
    parser.add_argument("--output", help="Optional new directory for the report")
    args = parser.parse_args()

    print(f"pitax detectors: {[fn.__name__ for fn in DETECTORS]}")
    benchmark = bs.load(source=args.source, split=args.split, view=args.view, n_pairs=args.n_pairs)
    report = bs.evaluate(benchmark, predict)
    if args.output:
        report.save(args.output)
    print(json.dumps(report.metrics, indent=2))
    print("pitax per-detector hits:", json.dumps(dict(HITS), indent=2))


if __name__ == "__main__":
    main()

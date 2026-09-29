#!/usr/bin/env python
"""Print the explicit repository test collection count.

The paths are intentional: collecting from the repository root can discover a
sibling checkout and produce import-mismatch noise. This helper is the single
counting rule used by verification and documentation.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITES = (ROOT / "codeark" / "tests", ROOT / "tests")


def collect_count() -> int:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ROOT / "codeark" / "pyproject.toml"),
        *(str(path) for path in SUITES),
        "--collect-only",
        "-q",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    for line in reversed(completed.stdout.splitlines()):
        match = re.search(r"(\d+)\s+tests?\s+collected\b", line)
        if match:
            return int(match.group(1))
    raise RuntimeError("pytest collect-only output did not contain a collection count")


def main() -> int:
    parser = argparse.ArgumentParser(description="Count explicit repository tests")
    parser.add_argument("--check", type=int, help="fail unless the count equals N")
    args = parser.parse_args()
    count = collect_count()
    print(f"{count} tests collected (codeark/tests + tests)")
    if args.check is not None and count != args.check:
        print(f"expected {args.check}, got {count}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

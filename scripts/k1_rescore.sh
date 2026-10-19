#!/usr/bin/env bash
# ============================================================
# K1 全量重判（零模型调用）— 判分器 v0.6 + 官方 manifest + 20/20 覆盖断言
# 用法：bash scripts/k1_rescore.sh <reports-dir> [out.json]
#   reports-dir 按 <challenge_id>/report.json 组织
#   DSW: bash scripts/k1_rescore.sh /mnt/workspace/runs/20261003-k1
#   UPSTREAM_ROOT=/mnt/workspace/NYU_CTF_Bench 时附带 flag 原位读取
# 纪律：manifest SHA 不匹配或缺任一题报告，直接 exit 2，不出分。
# ============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

MANIFEST=data/m8_k1_manifest.json
EXPECTED_SHA=6501ba7c8e76464a23748e9fb7ead89050d6dbb47e0c8d5dfd64d5b21c971ec4
REPORTS=${1:?usage: bash scripts/k1_rescore.sh <reports-dir> [out.json]}
OUT=${2:-runs/k1-rescore-$(date +%Y%m%d-%H%M%S).json}

mkdir -p "$(dirname "$OUT")"
args=(
  --manifest "$MANIFEST"
  --expected-manifest-sha256 "$EXPECTED_SHA"
  --reports-dir "$REPORTS"
  --require-all
  --out "$OUT"
)
if [ -n "${UPSTREAM_ROOT:-}" ]; then
  args+=(--upstream-root "$UPSTREAM_ROOT")
fi

python eval/m8_k1_score.py "${args[@]}"
echo "score -> $OUT"
#!/usr/bin/env bash
# K1-min e2e 批 v2：20 题 web challenge × 生产管线（nogate，VERIFY temp=0）。
# v2（2026-10-04）：v1 幂等逻辑不变（已有 report.json 自动跳过=旧报告天然防覆盖），
# 新增 ①单题超时（K1_TIMEOUT 秒，默认 5400=90min，timeout 杀僵尸防整批卡死）
#      ②崩溃自动重试一次（exit≠0 且无 report 产出才重试；语义空跑交卷不重试）。
# 补跑姿势：备份旧 report 后 rm 之，本脚本幂等自动重跑该题。
set -u
cd /root/arcanum-spark || exit 1
export ARCA_DEPLOYMENT=local ARCA_VERIFY_TEMPERATURE=0
G=/mnt/workspace/runs/20261003-k1
TIMEOUT_SECS=${K1_TIMEOUT:-5400}
mkdir -p "$G/logs"
python -c "
import json
for r in json.load(open('data/m8_k1_manifest.json')):
    print(r['upstream_path']+'\t'+r['challenge_id'])
" | while IFS=$'\t' read -r REL CID; do
  OUT="$G/$CID"
  if [ -f "$OUT/report.json" ]; then echo "[k1] $CID skip(已有)"; continue; fi
  mkdir -p "$OUT"
  timeout "$TIMEOUT_SECS" python -m codeark.cli "/mnt/workspace/NYU_CTF_Bench/$REL" --out "$OUT" > "$G/logs/$CID.log" 2>&1
  RC=$?
  if [ "$RC" -ne 0 ] && [ ! -s "$OUT/report.json" ]; then
    echo "[k1] $CID exit=$RC 重试一次"
    timeout "$TIMEOUT_SECS" python -m codeark.cli "/mnt/workspace/NYU_CTF_Bench/$REL" --out "$OUT" > "$G/logs/$CID.retry.log" 2>&1
    RC=$?
  fi
  echo "[k1] $CID exit=$RC $(date +%H:%M)"
done
touch "$G/K1_BATCH_DONE.txt"
echo K1_BATCH_ALL_DONE

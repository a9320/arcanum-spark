#!/bin/bash
# ============================================================
# T4 二期：证据包可迁移性复测——第二题 poem-collection（default vs minpack）
# 配方对齐一期（WORK_LOG 2026-10-20 22:35）：固定假设集 + gpt-oss-verify +
# plain-json 验收臂 + temp=0 + 串行；单变量=证据包（default 60000 vs 1）。
# 假设集源=10-18 new2q poem-collection 卷（官方链 PT→LFI，老 4 假设）。
# 用法（五服务 UP 后）：
#   ARM=default N=3 bash scripts/run-arm-t4b.sh
#   ARM=minpack N=3 bash scripts/run-arm-t4b.sh
# 判读：每卷 run-verify-acceptance.sh 内建 == exit= 行；逐卷
#   python3 -c ".../e2e_report.json 提取 verdict/degraded"（会话内给命令）。
# ============================================================
set -u
cd "$(dirname "$0")/.." || exit 1
source scripts/dsw-env.sh
export ARCA_DEPLOYMENT=local
export ARCA_VERIFY_MAX_CONCURRENCY=1
export ARCA_VERIFY_TEMPERATURE=0
export ARCA_VERIFY_MODEL=gpt-oss-verify
export ARCA_VERIFY_BASE_URL=http://127.0.0.1:8085/v1
export ARCA_VERIFY_EVIDENCE_STRICT=1
export ARCA_VERIFY_PLAIN_JSON=${ARCA_VERIFY_PLAIN_JSON:-1}

SRC=${SRC:-/mnt/workspace/runs/20261018-new2q/poem-collection/report.json}
GK=${GK:-/mnt/workspace/NYU_CTF_Bench/test/2021/CSAW-Quals/web/poem-collection}
BASE=${BASE:-/mnt/workspace/runs/20261021-t4b}
ARM=${ARM:-default}     # default | minpack
N=${N:-3}

[ -f "$SRC" ] || { echo "!! 假设集源缺失: $SRC"; exit 2; }
[ -d "$GK" ] || { echo "!! 题目仓缺失: $GK"; exit 2; }
case $ARM in default) ;; minpack) export ARCA_VERIFY_EVIDENCE_MAX_TOKENS=1 ;;
  *) echo "!! ARM 只认 default|minpack"; exit 2 ;; esac

for r in $(seq 1 "$N"); do
  echo "== T4b $ARM r$r start $(date '+%H:%M') =="
  SRC="$SRC" GK="$GK" OUT="$BASE/poem-$ARM-r$r" bash scripts/run-verify-acceptance.sh \
    || echo "!! r$r FAIL（继续下一卷）"
done
echo "== ALL DONE arm=$ARM N=$N $(date '+%H:%M') =="

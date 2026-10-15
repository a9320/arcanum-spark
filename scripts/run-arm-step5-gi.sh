#!/bin/bash
# ============================================================
# step5×step5-profile 臂（gi 题：云端 step-5 Scout + local verify/deepen/arbiter）
# env 配方：ARCA_SCOUT_REASONING_EFFORT=low + ARCA_SCOUT_PROFILE=step5
# 出处：docs/SCOUT-PROFILE-DESIGN.md §5 预注册矩阵（10-15 实测存活：1min 正式卷 5 假设 H1=官方链）
# 用法：DSW 四服务 UP 后——
#   read -s -p "StepFun key: " K && export ARCA_SCOUT_API_KEY="$K"; unset K
#   bash scripts/run-arm-step5-gi.sh
# ============================================================
cd "$(dirname "$0")/.." || exit 1
if [ -z "${ARCA_SCOUT_API_KEY:-}" ]; then
  echo "!! 先注入 key（read -s 交互注入，勿进对话文本）"; exit 1
fi
export ARCA_DEPLOYMENT=local
export ARCA_SCOUT_MODEL=step-5-preview ARCA_SCOUT_BASE_URL=https://api.stepfun.com
export ARCA_SCOUT_MAX_TOKENS=20000 ARCA_SCOUT_REASONING_EFFORT=low ARCA_SCOUT_PROFILE=step5
export ARCA_VERIFY_MAX_CONCURRENCY=3  # verify 并行化（默认串行=10-15 哨杀根因之一，见 muse-3q 脚本注）

RUNS=/mnt/workspace/runs/gi-s5p
mkdir -p "$RUNS/logs"
REL=/mnt/workspace/NYU_CTF_Bench/removed/2022/CSAW-Quals/web/good_intentions
[ -d "$RUNS/good_intentions" ] && mv "$RUNS/good_intentions" "$RUNS/good_intentions.bak-$(date +%H%M)"
echo "== gi step5-profile start $(date '+%H:%M') =="
timeout 1500 python -u -m codeark.cli "$REL" --out "$RUNS/good_intentions" 2>&1 | tee "$RUNS/logs/good_intentions.log"
echo "== gi step5-profile exit=$? bytes=$(stat -c %s "$RUNS/good_intentions/report.json" 2>/dev/null || echo 0) end $(date '+%H:%M') =="

#!/bin/bash
# ============================================================
# 三题基线臂（Muse×default，local 拓扑=带真 verify/deepen/arbiter）
# 预注册配方出处：docs/SCOUT-PROFILE-DESIGN.md §5 + WORK_LOG 2026-10-15
# （探针卷半降级教训=ARCA_DEPLOYMENT 必显式，env 配方收进仓不再散落对话）
# 用法：DSW 四服务 UP 后，bash scripts/run-arm-muse-3q.sh
# ============================================================
cd "$(dirname "$0")/.." || exit 1
export ARCA_DEPLOYMENT=local
export ARCA_SCOUT_MODEL=muse-scout ARCA_SCOUT_BASE_URL=http://127.0.0.1:8081/v1
export ARCA_SCOUT_MAX_TOKENS=20000
# verify 并发=1（10-18 实证回退：并行在 gpt-oss 上零速度收益——GK 串行 3'18" vs 并行 3'28"，
# 且并行下 verify 判决串线/错配风险待隔双变量；旧 10-15 并行=3 的提速动机随 verify 换模消失）
export ARCA_VERIFY_MAX_CONCURRENCY=1
unset ARCA_SCOUT_REASONING_EFFORT ARCA_SCOUT_PROFILE

RUNS=/mnt/workspace/runs/20261015-3q-local
mkdir -p "$RUNS/logs"
for cid in nekocat flask_caching webhooktester; do
  case $cid in
    nekocat) REL=/mnt/workspace/NYU_CTF_Bench/removed/2018/CSAW-Finals/web/nekocat;;
    flask_caching) REL=/mnt/workspace/NYU_CTF_Bench/removed/2020/CSAW-Quals/web/flask_caching;;
    webhooktester) REL=/mnt/workspace/NYU_CTF_Bench/removed/2023/CSAW-Finals/web/webhooktester;;
  esac
  [ -d "$REL" ] || { echo "!! REL 缺失: $REL"; continue; }
  [ -d "$RUNS/$cid" ] && mv "$RUNS/$cid" "$RUNS/$cid.bak-$(date +%H%M)"
  echo "== $cid start $(date '+%H:%M') =="
  timeout 1500 python -u -m codeark.cli "$REL" --out "$RUNS/$cid" 2>&1 | tee "$RUNS/logs/$cid.log"
  echo "== $cid exit=$? bytes=$(stat -c %s "$RUNS/$cid/report.json" 2>/dev/null || echo 0) end $(date '+%H:%M') =="
done

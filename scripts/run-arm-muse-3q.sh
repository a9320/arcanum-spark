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
# verify 并行化（2026-10-15 哨杀定案：默认串行 concurrency=1，5 假设题 verify 段 ~20min 撞 25min 帽；
# qwen-verify -np 4 槽位闲置，开 3 并行=留 1 槽给 Scout 兜底）
export ARCA_VERIFY_MAX_CONCURRENCY=3
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

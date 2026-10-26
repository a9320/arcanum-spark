#!/bin/bash
# ============================================================
# 方差治理 P1 DSW 验收 driver（Exp A + Exp B + conf_ref 零误报闸）
# 预注册：docs/VERDICT-VARIANCE-GOVERNANCE.md §四（判据机读=eval/gov_summary.py）
#   Exp A：gatekeeping 固定假设集 N=5（SRC 默认=10-18 new2q gatekeeping 卷），
#          判据=同假设 confidence 档位一致率 ≥4/5；
#   Exp B：flask_caching 两臂 N=3×2（SRC=runs/20261015-3q-local 卷，复用 t4c 配方，
#          新 BASE 与 10-25 旧 schema 卷隔离），判据=H1 evidence_source 随臂漂移 /
#          H2 零效应对照；
#   闸门：全部卷 confident_refutations（REFUTED ∧ conf≥0.9）保持 0。
# 前台纪律（10-25 补记十六教训）：driver 全程前台顺序执行，任何一段都不得 nohup/
# 后台化——每卷 tee 流式输出 + 每阶段时间戳行持续进终端，平台不判空闲。
# 前提：五服务 UP（VRAM≈126.6G 基线 + :8085 gpt-oss 卡片）。
# 预算：A 5 卷 + B 6 卷 ≈ 1 小时（每卷 timeout 1500s 内）。
# 用法：
#   MODE=A   bash scripts/run-arm-gov.sh      # 只跑 Exp A
#   MODE=B   bash scripts/run-arm-gov.sh      # 只跑 Exp B
#   MODE=ALL bash scripts/run-arm-gov.sh      # A→B→汇总+闸门 一条龙
#   MODE=SUMMARY bash scripts/run-arm-gov.sh  # 只重跑汇总+闸门（补判不跑模型）
# ============================================================
set -u
cd "$(dirname "$0")/.." || exit 1
BASE=${BASE:-/mnt/workspace/runs/20261026-gov}
N_A=${N_A:-5}
N_B=${N_B:-3}
MODE=${MODE:-ALL}

mkdir -p "$BASE"

preflight() {
  echo "== [$(date '+%H:%M:%S')] preflight（import 链 + :8085 路由 + SRC 在位）=="
  PREFLIGHT=1 bash scripts/run-verify-acceptance.sh || { echo "!! preflight 失败，中止"; exit 3; }
}

exp_a() {
  local r
  for r in $(seq 1 "$N_A"); do
    echo "== [$(date '+%H:%M:%S')] Exp A gatekeeping r$r/$N_A start =="
    OUT="$BASE/gov-a-r$r" bash scripts/run-verify-acceptance.sh \
      || echo "!! Exp A r$r FAIL（继续下一卷）"
    echo "== [$(date '+%H:%M:%S')] Exp A r$r done =="
  done
}

exp_b() {
  local arm
  for arm in default minpack; do
    echo "== [$(date '+%H:%M:%S')] Exp B arm=$arm N=$N_B start（复用 t4c 配方）=="
    BASE="$BASE" ARM=$arm N=$N_B bash scripts/run-arm-t4c.sh \
      || echo "!! Exp B arm=$arm 有卷 FAIL（如实记录）"
    echo "== [$(date '+%H:%M:%S')] Exp B arm=$arm done =="
  done
}

summary() {
  local rc=0
  echo "== [$(date '+%H:%M:%S')] 汇总+闸门 =="
  echo "-- Exp A 档位一致率（判据 ≥4/5）--"
  python3 eval/gov_summary.py -m a "$BASE"/gov-a-r* || true
  echo "-- Exp B evidence_source 随臂分布 --"
  python3 eval/gov_summary.py -m b "$BASE"/flaskc-*-r* || true
  echo "-- conf_ref 零误报闸（两实验全卷）--"
  python3 eval/gov_summary.py -m ref "$BASE"/gov-a-r* "$BASE"/flaskc-*-r* || rc=$?
  return $rc
}

case $MODE in
  A) preflight; exp_a; summary ;;
  B) preflight; exp_b; summary ;;
  ALL) preflight; exp_a; exp_b; summary ;;
  SUMMARY) summary ;;
  *) echo "!! MODE 只认 A|B|ALL|SUMMARY"; exit 2 ;;
esac
rc=$?
echo "== GOV DRIVER ALL DONE mode=$MODE rc=$rc $(date '+%H:%M:%S') =="
exit $rc

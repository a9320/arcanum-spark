#!/bin/bash
# ============================================================
# T6 验收臂：固定假设集重跑 gatekeeping（串行，pin 10-18 串行卷假设集）
# 目的：验证 T2/T3 修复——官方链 H2（SCRIPT_NAME 绕过）获得真实判决：
#   非 degraded、非 peg-native 解析失败、hypothesis_id 非空且不回填错配。
# 单变量纪律：只验 verify 契约修复——并发=1（T1 定案）、verify=gpt-oss-verify。
# 前提：DSW 五服务 UP（oneclick）；SRC=今日串行卷 report.json（meta.hypothesis_set 可恢复）。
# 用法：bash scripts/run-verify-acceptance.sh
# 预检：PREFLIGHT=1 bash scripts/run-verify-acceptance.sh（只查仓/模型服务，不跑模型）
# 判据：本地 python eval/check_verify_acceptance.py <OUT>/e2e_report.json --target H2
# ============================================================
set -u
cd "$(dirname "$0")/.." || exit 1
export ARCA_DEPLOYMENT=local
export ARCA_VERIFY_MAX_CONCURRENCY=1          # T1 定案：串行（10-18 实测并行零速益）
export ARCA_VERIFY_MODEL=gpt-oss-verify       # 单变量：只验判决契约修复，不换岗
export ARCA_VERIFY_BASE_URL=http://127.0.0.1:8085/v1
export ARCA_VERIFY_EVIDENCE_STRICT=1          # T4 案甲：验收臂开 E2 逐字引文校验（日常默认宽松）

SRC=${SRC:-/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json}
GK=${GK:-/mnt/workspace/NYU_CTF_Bench/test/2021/CSAW-Quals/web/gatekeeping}
OUT=${OUT:-/mnt/workspace/runs/20261018-accept/gatekeeping-pinned}

[ -f "$SRC" ] || { echo "!! 固定假设集源缺失: $SRC"; exit 2; }
[ -d "$GK" ] || { echo "!! GK 仓缺失: $GK"; exit 2; }

if [ "${PREFLIGHT:-0}" = "1" ]; then
  echo "== preflight =="
  python -c "import codeark" || { echo "!! codeark import 失败"; exit 3; }
  MODELS_JSON=$(mktemp)
  trap 'rm -f "$MODELS_JSON"' EXIT
  code=$(curl -sS -o "$MODELS_JSON" -w '%{http_code}' --max-time 5 \
    "${ARCA_VERIFY_BASE_URL%/}/models" || true)
  if [ "$code" != "200" ]; then
    echo "!! verify 服务未就绪: HTTP $code"
    exit 3
  fi
  if ! grep -q "gpt-oss" "$MODELS_JSON"; then
    echo "!! /models 中未找到 gpt-oss 路由；实际返回："
    cat "$MODELS_JSON"
    exit 3
  fi
  echo "preflight OK: $ARCA_VERIFY_BASE_URL model=gpt-oss-verify"
  exit 0
fi

mkdir -p "$OUT"

echo "== pinned accept start $(date '+%H:%M') src=$SRC =="
timeout 1500 python -u eval/run_gate_e2e.py "$GK" --backend deterministic \
  --hypotheses-from "$SRC" --out "$OUT" 2>&1 | tee "$OUT/run.log"
rc=${PIPESTATUS[0]}
echo "== exit=$rc bytes=$(stat -c %s "$OUT/e2e_report.json" 2>/dev/null || echo 0) end $(date '+%H:%M') =="
exit "$rc"

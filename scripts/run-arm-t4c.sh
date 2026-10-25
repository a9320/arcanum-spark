#!/bin/bash
# ============================================================
# T4 三期：证据包效应自含性假说复测——第三题 flask_caching（default vs minpack）
# 假说（T4b 定谳，reports/20261024-t4b-evidence-migration.md §二.1）：
#   "证据包决定性取决于官方链证据是否自含于假设快照"
#   （poem H1 自含 index.php → 两臂同 CONFIRMED；gatekeeping H2 外引 solve.py → minpack 饿死）。
# 预注册预测：flask_caching 官方链=DESERIALIZATION/PICKLE 族（K2 第四批复核实锤，
#   实证仅存于仓内 README Solution + solve.py 外部工件，manifest notes 在案）：
#   - 假设快照仅引用路径未内联工件内容 → minpack 臂官方链降 UNCERTAIN/REFUTED、
#     default 臂 CONFIRMED ×3 ⇒ 自含性假说第二证据点成立；
#   - 假设快照已转录工件内容（准自含，poem 形）→ 两臂同 CONFIRMED ⇒ 假说需再修正
#     （边界收紧为"Scout 转录=准自含"）。
# 配方对齐 t4b：固定假设集 + gpt-oss-verify + plain-json 验收臂 + temp=0 + 串行；
# 单变量=证据包（default 60000 vs minpack =1）。
# 假设集源=10-21 route A 卷 runs/20261015-3q-local/flask_caching（plain-json 健康卷）。
# 用法（五服务 UP 后）：
#   0) 预注册检查（只读 SRC 假设集，不跑模型）：PREFLIGHT=1 bash scripts/run-arm-t4c.sh
#      —— 打印各假设证据引用，判"内联 vs 外引"，把预测记进判读后再跑臂；
#   1) ARM=default N=3 bash scripts/run-arm-t4c.sh
#   2) ARM=minpack N=3 bash scripts/run-arm-t4c.sh
# 判读：TARGET=<官方链假设id> 已设时每卷自动跑
#   python3 eval/check_verify_acceptance.py <OUT>/e2e_report.json --target "$TARGET"；
#   逐卷提 verdict/degraded：python3 -c "import json;d=json.load(open('<OUT>/e2e_report.json'));[print(v.get('hypothesis_id'),v.get('verdict'),v.get('confidence'),'deg=',v.get('degraded')) for v in d['verifications']]"
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

SRC=${SRC:-/mnt/workspace/runs/20261015-3q-local/flask_caching/report.json}
GK=${GK:-/mnt/workspace/NYU_CTF_Bench/removed/2020/CSAW-Quals/web/flask_caching}
BASE=${BASE:-/mnt/workspace/runs/20261025-t4c}
ARM=${ARM:-default}     # default | minpack
N=${N:-3}
TARGET=${TARGET:-}      # 官方链假设 id（预注册检查后填）

[ -f "$SRC" ] || { echo "!! 假设集源缺失: $SRC"; exit 2; }
[ -d "$GK" ] || { echo "!! 题目仓缺失: $GK"; exit 2; }

if [ "${PREFLIGHT:-0}" = "1" ]; then
  echo "== t4c 预注册检查（只读 SRC 假设集，不跑模型）=="
  python -c '
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
hs = (data.get("meta") or {}).get("hypothesis_set") or data.get("hypothesis_set") or {}
hyps = hs.get("hypotheses") or []
print("hypotheses:", len(hyps))
for h in hyps:
    ev_keys = {k: h[k] for k in h if "evid" in k.lower() or "file" in k.lower() or "path" in k.lower()}
    print("-", h.get("id"), "|", str(h.get("title", ""))[:70])
    for k, v in ev_keys.items():
        print("    ", k, "=", str(v)[:200])
' "$SRC" || { echo "!! 假设集解析失败"; exit 3; }
  echo "== 判读守则：DESER/PICKLE 族假设的 evidence 若=具体路径引用（solve.py/README）"
  echo "   → 预测 minpack 饿死官方链；若=已转录工件内容 → 预测两臂同 CONFIRMED。"
  exit 0
fi

case $ARM in default) ;; minpack) export ARCA_VERIFY_EVIDENCE_MAX_TOKENS=1 ;;
  *) echo "!! ARM 只认 default|minpack"; exit 2 ;; esac

for r in $(seq 1 "$N"); do
  echo "== T4c $ARM r$r start $(date '+%H:%M') =="
  SRC="$SRC" GK="$GK" OUT="$BASE/flaskc-$ARM-r$r" bash scripts/run-verify-acceptance.sh \
    || echo "!! r$r FAIL（继续下一卷）"
  if [ -n "$TARGET" ] && [ -f "$BASE/flaskc-$ARM-r$r/e2e_report.json" ]; then
    python3 eval/check_verify_acceptance.py "$BASE/flaskc-$ARM-r$r/e2e_report.json" \
      --target "$TARGET" || echo "!! checker 对 $TARGET 报 FAIL（判决如实记录，非脚本错误）"
  fi
done
echo "== ALL DONE arm=$ARM N=$N $(date '+%H:%M') =="

#!/usr/bin/env bash
# IC27 合规底座清理：达标后按名单删除，绝不删整组。
#
# 为什么按名单删：资源组 rg-arcanum-ic27 里还有 gate 用的 F0 资源
# （arca-cs-ic27 / arca-lang-ic27）与历史证据，删整组会一并毁掉。
#
# 用法：
#   bash scripts/azure/cleanup_10_services.sh                 # 只列出将删除的资源（默认 dry-run）
#   bash scripts/azure/cleanup_10_services.sh --yes           # 真删
#   bash scripts/azure/cleanup_10_services.sh --yes --keep-log-analytics
#
# 顺序：容器应用 → 环境 → 镜像仓 → 消息（SB/EH）→ 认知服务 → 日志工作区（最后，便于回看摄入量）。
set -uo pipefail

RG="${ARCA_IC27_RG:-rg-arcanum-ic27}"
SUFFIX="${ARCA_IC27_SUFFIX:-ic27}"
YES=0
KEEP_LA=0
SUB=""

while [ $# -gt 0 ]; do
  case "$1" in
    --yes) YES=1 ;;
    --keep-log-analytics) KEEP_LA=1 ;;
    --suffix) SUFFIX="${2:?}"; shift ;;
    --subscription) SUB="${2:?}"; shift ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

ACCOUNT_ARGS=()
[ -n "$SUB" ] && ACCOUNT_ARGS=(--subscription "$SUB")

ACA_ENV="arca-aca-env"
ACA_APP="arca-aca-logflood"
ACR_NAME="arcaacr${SUFFIX}"
SB_NAME="arca-sb-${SUFFIX}"
EH_NAME="arca-eh-${SUFFIX}"
LAW_NAME="arca-law-${SUFFIX}"
COGS=(arca-cs-usage arca-lang-usage arca-di-usage arca-cv-usage arca-sp-usage arca-ai-usage)

say() { printf '%s\n' "$*" >&2; }
doit() {
  if [ "$YES" = 0 ]; then say "[dry-run] $*"; return 0; fi
  say "+ $*"
  "$@"
}

command -v az >/dev/null 2>&1 || { echo "未找到 az CLI" >&2; exit 2; }
if [ "$YES" = 1 ]; then
  az account show "${ACCOUNT_ARGS[@]}" -o none 2>/dev/null || { echo "az 未登录" >&2; exit 2; }
fi

say "资源组=$RG 后缀=$SUFFIX  模式=$([ "$YES" = 1 ] && echo 删除 || echo dry-run)"

doit az containerapp delete -n "$ACA_APP" -g "$RG" --yes
doit az containerapp env delete -n "$ACA_ENV" -g "$RG" --yes
doit az acr delete -n "$ACR_NAME" -g "$RG" --yes
doit az servicebus namespace delete -n "$SB_NAME" -g "$RG"
doit az eventhubs namespace delete -n "$EH_NAME" -g "$RG"
for name in "${COGS[@]}"; do
  doit az cognitiveservices account delete -n "$name" -g "$RG"
done
if [ "$KEEP_LA" = 1 ]; then
  say "保留 Log Analytics：$LAW_NAME（--keep-log-analytics）"
else
  doit az monitor log-analytics workspace delete -n "$LAW_NAME" -g "$RG" --yes --force
fi

say ""
say "未触碰：arca-cs-ic27 / arca-lang-ic27（gate 用的 F0 资源）与资源组本身"
[ "$YES" = 0 ] && say "以上为预览；确认无误后加 --yes 真删"

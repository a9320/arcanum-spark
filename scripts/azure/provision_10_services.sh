#!/usr/bin/env bash
# IC27 合规底座：10 项 Azure 服务的幂等部署（Cloud Shell 可直接跑）。
#
# 为什么存在：Imagine Cup 2027 规则 §7 要求提交时账户上「至少 10 项 Azure 服务、
# 每项 >= $1.00 用量」。F0/Free 层计量为 $0.00 不算数，所以这里按「付费 SKU +
# 最小跑量」建 10 项；单价与区域可用性见同目录 prices-20261117.json 与
# ArcanumSec/imaginecup-2027/Azure-10项服务选型-20261117.md。
#
# 用法（Cloud Shell 或本机 az CLI 均可）：
#   bash scripts/azure/provision_10_services.sh --dry-run          # 只打印将执行的命令
#   bash scripts/azure/provision_10_services.sh                    # 全建（默认 uaenorth）
#   bash scripts/azure/provision_10_services.sh --stage ai         # 只建 5 项 AI 服务
#   bash scripts/azure/provision_10_services.sh --skip aca,eventhubs
#   bash scripts/azure/provision_10_services.sh --subscription <SUB_ID>
#
# 输出：
#   $HOME/azure-ic27.env            凭据（chmod 600，绝不入库；generate_usage.py 读它）
#   ./azure-ic27-resources.json     资源清单（无密钥，可入证据档）
#
# 纪律：
#   * 不 echo 任何密钥到 stdout；env 文件只在最后提示路径。
#   * 幂等：已存在的资源跳过创建，只补齐 env 文件。
#   * 区域：学生订阅策略白名单=indiasouthcentral/eastasia/koreacentral/uaenorth/malaysiawest；
#     默认 uaenorth，Language 付费档必须 eastasia 或 koreacentral（UAENorth 无该计量）。
#   * 计费是真实发生的：达标后立刻跑 cleanup_10_services.sh（时间型四项按小时/天计费）。
set -uo pipefail

RG="${ARCA_IC27_RG:-rg-arcanum-ic27}"
LOC="${ARCA_IC27_LOCATION:-uaenorth}"
LANG_LOC="${ARCA_IC27_LANG_LOCATION:-eastasia}"
SUFFIX="${ARCA_IC27_SUFFIX:-ic27}"
DRY=0
STAGE="all"
SKIP=""
SUB=""
ENV_OUT="$HOME/azure-ic27.env"
MANIFEST="./azure-ic27-resources.json"

CS_NAME="arca-cs-usage"
LANG_NAME="arca-lang-usage"
DI_NAME="arca-di-usage"
CV_NAME="arca-cv-usage"
SP_NAME="arca-sp-usage"
ACR_NAME="arcaacr${SUFFIX}"
LAW_NAME="arca-law-${SUFFIX}"
ACA_ENV="arca-aca-env"
ACA_APP="arca-aca-logflood"
SB_NAME="arca-sb-${SUFFIX}"
EH_NAME="arca-eh-${SUFFIX}"

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --stage) STAGE="${2:?}"; shift ;;
    --skip) SKIP="${2:?}"; shift ;;
    --subscription) SUB="${2:?}"; shift ;;
    --suffix) SUFFIX="${2:?}"; ACR_NAME="arcaacr${SUFFIX}"; LAW_NAME="arca-law-${SUFFIX}"; SB_NAME="arca-sb-${SUFFIX}"; EH_NAME="arca-eh-${SUFFIX}"; shift ;;
    --location) LOC="${2:?}"; shift ;;
    --env-out) ENV_OUT="${2:?}"; shift ;;
    -h|--help) usage ;;
    *) echo "未知参数：$1（--help 看用法）" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '%s\n' "$*" >&2; }
run() {
  if [ "$DRY" = 1 ]; then say "[dry-run] $*"; return 0; fi
  say "+ $*"
  "$@"
}
skipped() {
  case ",${SKIP}," in *",$1,"*) return 0 ;; *) return 1 ;; esac
}
stage_on() {
  [ "$STAGE" = "all" ] || [ "$STAGE" = "$1" ]
}
have_az() { command -v az >/dev/null 2>&1; }

need_az() {
  if ! have_az; then
    if [ "$DRY" = 1 ]; then say "[dry-run] 未检测到 az（真实执行需要它）"; return 0; fi
    echo "未找到 az CLI：Cloud Shell 自带；本机请先安装 azure-cli" >&2
    exit 2
  fi
}

ACCOUNT_ARGS=()
[ -n "$SUB" ] && ACCOUNT_ARGS=(--subscription "$SUB")

preflight() {
  need_az
  [ "$DRY" = 1 ] && { say "[dry-run] 跳过 az login/订阅检查"; return 0; }
  run az account show "${ACCOUNT_ARGS[@]}" --query '{name:name,id:id,user:user.name}' -o table >&2 || {
    echo "az 未登录：Cloud Shell 内直接可用；本机请 az login" >&2; exit 2; }
  run az group create -n "$RG" -l "$LOC" -o none
}

# 取某个认知服务的 endpoint / key（失败返回空串，不打印密钥）
cog_endpoint() { az cognitiveservices account show -n "$1" -g "$RG" "${ACCOUNT_ARGS[@]}" --query properties.endpoint -o tsv 2>/dev/null; }
cog_key() { az cognitiveservices account keys list -n "$1" -g "$RG" "${ACCOUNT_ARGS[@]}" --query key1 -o tsv 2>/dev/null; }
cog_exists() { az cognitiveservices account show -n "$1" -g "$RG" "${ACCOUNT_ARGS[@]}" -o none 2>/dev/null; }

ensure_cog() { # name kind sku location
  local name="$1" kind="$2" sku="$3" loc="$4"
  if [ "$DRY" = 1 ]; then
    say "[dry-run] ensure cog $name ($kind/$sku in $loc)"
  elif cog_exists "$name"; then
    say "= $name 已存在，跳过创建"
  else
    run az cognitiveservices account create -n "$name" -g "$RG" --kind "$kind" --sku "$sku" -l "$loc" --yes -o none || return 1
  fi
  if [ "$DRY" = 0 ]; then
    printf '%s\n' "$(cog_endpoint "$name")"
  fi
}

append_env() { # KEY VALUE
  local key="$1" value="$2"
  [ -z "$value" ] && return 0
  if [ "$DRY" = 1 ]; then say "[dry-run] env $key=<${#value} chars>"; return 0; fi
  printf '%s=%s\n' "$key" "$value" >> "$ENV_OUT"
}

manifest_entry() { # service name sku region role
  if [ "$DRY" = 1 ]; then return 0; fi
  printf '{"service":"%s","name":"%s","sku":"%s","region":"%s","role":"%s"}\n' \
    "$1" "$2" "$3" "$4" "$5" >> "$ROWS"
}

ROWS="$(mktemp)"
trap 'rm -f "$ROWS"' EXIT
[ "$DRY" = 0 ] && : > "$ENV_OUT"

preflight

# ---------------------------------------------------------------- AI 五项 ----
if stage_on ai; then
  if ! skipped content_safety; then
    ep="$(ensure_cog "$CS_NAME" ContentSafety S0 "$LOC")" || say "! Content Safety 创建失败"
    append_env ARCA_IC27_CS_ENDPOINT "$ep"
    [ -n "$ep" ] && append_env ARCA_IC27_CS_KEY "$(cog_key "$CS_NAME")"
    manifest_entry "Azure AI Content Safety" "$CS_NAME" S0 "$LOC" "输入边界注入闸（承重）"
  fi
  if ! skipped language; then
    ep="$(ensure_cog "$LANG_NAME" TextAnalytics S0 "$LANG_LOC")" || say "! Language 创建失败（付费计量仅 eastasia/koreacentral）"
    append_env ARCA_IC27_LANGUAGE_ENDPOINT "$ep"
    [ -n "$ep" ] && append_env ARCA_IC27_LANGUAGE_KEY "$(cog_key "$LANG_NAME")"
    manifest_entry "Azure AI Language" "$LANG_NAME" S0 "$LANG_LOC" "模型面 PII 脱敏（承重）"
  fi
  if ! skipped docintel; then
    ep="$(ensure_cog "$DI_NAME" FormRecognizer S0 "$LOC")" || say "! Document Intelligence 创建失败"
    append_env ARCA_IC27_DOCINTEL_ENDPOINT "$ep"
    [ -n "$ep" ] && append_env ARCA_IC27_DOCINTEL_KEY "$(cog_key "$DI_NAME")"
    manifest_entry "Azure AI Document Intelligence" "$DI_NAME" S0 "$LOC" "PDF/扫描件入库前解析（输入面）"
  fi
  if ! skipped vision; then
    ep="$(ensure_cog "$CV_NAME" ComputerVision S1 "$LOC")" || say "! Vision 创建失败（OCR 计量在 UAENorth 实测存在）"
    append_env ARCA_IC27_VISION_ENDPOINT "$ep"
    [ -n "$ep" ] && append_env ARCA_IC27_VISION_KEY "$(cog_key "$CV_NAME")"
    manifest_entry "Azure AI Vision" "$CV_NAME" S1 "$LOC" "截图/图片 OCR 后再扫（输入面）"
  fi
  if ! skipped speech; then
    ep="$(ensure_cog "$SP_NAME" SpeechServices S0 "$LOC")" || say "! Speech 创建失败"
    append_env ARCA_IC27_SPEECH_ENDPOINT "$ep"
    append_env ARCA_IC27_SPEECH_REGION "$LOC"
    [ -n "$ep" ] && append_env ARCA_IC27_SPEECH_KEY "$(cog_key "$SP_NAME")"
    manifest_entry "Azure AI Speech" "$SP_NAME" S0 "$LOC" "语音转写后再扫（输入面）"
  fi
fi

# ---------------------------------------------------------------- 观测底座 ----
# 先建 Log Analytics：ACA 环境的日志目的地要它的 customerId + 共享密钥，
# 而 ACA 的日志洪流正是 LA 摄入量的来源（一项工作喂两项服务）。
if stage_on observe; then
  if ! skipped log_analytics; then
    run az monitor log-analytics workspace create -n "$LAW_NAME" -g "$RG" -l "$LOC" -o none \
      || say "! Log Analytics 创建失败"
    append_env ARCA_IC27_LAW_NAME "$LAW_NAME"
    if [ "$DRY" = 0 ]; then
      append_env ARCA_IC27_LAW_CUSTOMER_ID "$(az monitor log-analytics workspace show -n "$LAW_NAME" -g "$RG" "${ACCOUNT_ARGS[@]}" --query customerId -o tsv 2>/dev/null)"
    fi
    manifest_entry "Azure Log Analytics" "$LAW_NAME" PerGB2018 "$LOC" "每次判决的审计留痕"
  fi
fi

# ------------------------------------------------------- 运行载体 ----
if stage_on runtime; then
  if ! skipped acr; then
    run az acr create -n "$ACR_NAME" -g "$RG" --sku Standard -l "$LOC" --admin-enabled false -o none \
      || say "! ACR 创建失败（名称需全局唯一，可换 --suffix）"
    append_env ARCA_IC27_ACR_NAME "$ACR_NAME"
    manifest_entry "Azure Container Registry" "$ACR_NAME" Standard "$LOC" "托管扫描 API 镜像仓"
  fi
  if ! skipped aca; then
    if [ "$DRY" = 1 ]; then
      say "[dry-run] ensure ACA env $ACA_ENV + app $ACA_APP（0.5 vCPU / 1Gi / 持续打日志喂 Log Analytics）"
    else
      law_id="$(az monitor log-analytics workspace show -n "$LAW_NAME" -g "$RG" "${ACCOUNT_ARGS[@]}" --query customerId -o tsv 2>/dev/null)"
      law_key="$(az monitor log-analytics workspace get-shared-keys -n "$LAW_NAME" -g "$RG" "${ACCOUNT_ARGS[@]}" --query primarySharedKey -o tsv 2>/dev/null)"
      if [ -z "$law_id" ]; then
        say "! 先建 Log Analytics（--stage observe 或全跑）再建 ACA"
      else
        run az containerapp env create -n "$ACA_ENV" -g "$RG" -l "$LOC" \
          --logs-destination log-analytics --logs-workspace-id "$law_id" --logs-workspace-key "$law_key" -o none \
          || say "! ACA 环境创建失败"
        env_id="$(az containerapp env show -n "$ACA_ENV" -g "$RG" "${ACCOUNT_ARGS[@]}" --query id -o tsv 2>/dev/null)"
        if [ -n "$env_id" ]; then
          tmp_yaml="$(mktemp)"
          cat > "$tmp_yaml" <<'YAML'
location: @@LOC@@
name: @@APP@@
properties:
  environmentId: @@ENV_ID@@
  configuration:
    ingress:
      external: false
  template:
    containers:
      - name: logflood
        image: mcr.microsoft.com/azurelinux/base/core:3.0
        command: ["/bin/bash"]
        args: ["-c", "i=0; while true; do i=$((i+1)); echo \"arcanum-ic27 heartbeat seq=$i payload=0123456789abcdef0123456789abcdef\"; sleep 0.2; done"]
        resources:
          cpu: 0.5
          memory: 1.0Gi
    minReplicas: 1
    maxReplicas: 1
YAML
          sed -i "s|@@LOC@@|$LOC|; s|@@APP@@|$ACA_APP|; s|@@ENV_ID@@|$env_id|" "$tmp_yaml"
          run az containerapp create -n "$ACA_APP" -g "$RG" --yaml "$tmp_yaml" -o none \
            || say "! ACA 应用创建失败（可换镜像重试；环境费仍会累积）"
          rm -f "$tmp_yaml"
          append_env ARCA_IC27_ACA_ENV "$ACA_ENV"
          append_env ARCA_IC27_ACA_APP "$ACA_APP"
          manifest_entry "Azure Container Apps" "$ACA_APP" Consumption "$LOC" "托管扫描入口（并喂 LA 日志）"
        fi
      fi
    fi
  fi
  if ! skipped servicebus; then
    run az servicebus namespace create -n "$SB_NAME" -g "$RG" -l "$LOC" --sku Standard -o none \
      || say "! Service Bus 创建失败（名称需全局唯一）"
    append_env ARCA_IC27_SB_NAMESPACE "$SB_NAME"
    manifest_entry "Azure Service Bus" "$SB_NAME" Standard "$LOC" "扫描任务队列"
  fi
  if ! skipped eventhubs; then
    run az eventhubs namespace create -n "$EH_NAME" -g "$RG" -l "$LOC" --sku Basic --capacity 1 -o none \
      || say "! Event Hubs 创建失败（名称需全局唯一）"
    append_env ARCA_IC27_EH_NAMESPACE "$EH_NAME"
    manifest_entry "Azure Event Hubs" "$EH_NAME" Basic "$LOC" "判决事件流（供评审台消费）"
  fi
fi

# ----------------------------------------------------------------- 收尾 ----
if [ "$DRY" = 0 ]; then
  if [ -s "$ROWS" ]; then
    printf '{"generated":"%s","resource_group":"%s","location":"%s","services":[\n' \
      "$(date -u +%FT%TZ)" "$RG" "$LOC" > "$MANIFEST"
    awk 'NR>1{printf ",\n"} {printf "%s", $0}' "$ROWS" >> "$MANIFEST"
    printf '\n]}\n' >> "$MANIFEST"
    chmod 600 "$ENV_OUT" 2>/dev/null || true
    say ""
    say "资源清单：$MANIFEST"
    say "凭据文件：$ENV_OUT（chmod 600，勿入库；generate_usage.py --env-file 读它）"
    say "下一步：python scripts/azure/generate_usage.py all-ai --env-file $ENV_OUT"
    say "达标核对：python scripts/azure/check_usage.py --run-az"
    say "注意：ACR/ACA/SB/EH/LA 按时间累积，达标后跑 cleanup_10_services.sh"
  else
    say "没有创建任何资源（可能全部被 --skip 或未达阶段条件）"
  fi
fi

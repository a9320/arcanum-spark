#!/bin/bash
# ============================================================
# step5×step5-profile 臂（三真漏报攻坚：picgram / I Got Id / raid_fat_fs_chal）
# 目的：part6 round-two 素材——step-5 侦察官能否提出三条官方链
#   （picgram=EPS-Ghostscript PostScript RCE / I Got Id=Perl 钻石操作符命令注入 / raid_fat=FAT 挂载+__import__ 动态加载）
# 单变量纪律：只换 Scout（云端 step-5+step5 档）；verify/deepen/arbiter=本地默认（qwen/r1/gemma）不动——
#   verify 若仍 UNCERTAIN 不影响本题主问（"提出与否"看假设集），兼收 qwen 保守性追加数据
# env 配方同 run-arm-step5-gi.sh（docs/SCOUT-PROFILE-DESIGN.md §5 预注册矩阵；10-15 实测存活 1min 交卷）
# 用法：DSW 四服务 UP 后——
#   read -s -p "StepFun key: " K && export ARCA_SCOUT_API_KEY="$K"; unset K
#   nohup bash scripts/run-arm-step5-3miss.sh > /mnt/workspace/runs/3miss-s5p/main.log 2>&1 &
# ============================================================
cd "$(dirname "$0")/.." || exit 1
# DSW 持久依赖自举（strands 在 /mnt/workspace/pylibs；新 pod 首次自动安装）
source scripts/dsw-env.sh
if [ -z "${ARCA_SCOUT_API_KEY:-}" ]; then
  echo "!! 先注入 key（read -s 交互注入，勿进对话文本）"; exit 1
fi
export ARCA_DEPLOYMENT=local
export ARCA_SCOUT_MODEL=step-5-preview ARCA_SCOUT_BASE_URL=https://api.stepfun.com
export ARCA_SCOUT_MAX_TOKENS=20000 ARCA_SCOUT_REASONING_EFFORT=low ARCA_SCOUT_PROFILE=step5
export ARCA_VERIFY_MAX_CONCURRENCY=1  # 10-18 实证回退：并行零速益（GK 串行 3'18" vs 并行 3'28"）+错配风险在册

RUNS=/mnt/workspace/runs/3miss-s5p
mkdir -p "$RUNS/logs"
NYU=/mnt/workspace/NYU_CTF_Bench
# 三题身份=data/m8_k1_manifest.json 实查；条目格式 "名称|相对路径"，分号分隔；'I Got Id' 名称与路径均含空格，全程双引号
ITEMS="picgram|test/2020/CSAW-Finals/web/picgram"
ITEMS="$ITEMS;I Got Id|development/2016/CSAW-Quals/web/I Got Id"
ITEMS="$ITEMS;raid_fat_fs_chal|removed/2018/CSAW-Finals/web/raid_fat_fs_chal"

IFS=';'
for entry in $ITEMS; do
  name="${entry%%|*}"
  rel="${entry#*|}"
  if [ ! -d "$NYU/$rel" ]; then
    echo "!! FATAL: 题库缺 $NYU/$rel（跳过 $name）"; continue
  fi
  [ -d "$RUNS/$name" ] && mv "$RUNS/$name" "$RUNS/$name.bak-$(date +%H%M)"
  echo "== 3miss[$name] start $(date '+%H:%M') rel=$rel =="
  timeout 1500 python -u -m codeark.cli "$NYU/$rel" --out "$RUNS/$name" 2>&1 | tee "$RUNS/logs/$name.log"
  echo "== 3miss[$name] exit=$? bytes=$(stat -c %s "$RUNS/$name/report.json" 2>/dev/null || echo 0) end $(date '+%H:%M') =="
done
unset IFS
echo "== 3miss ALL DONE $(date '+%H:%M') =="

#!/bin/bash
# ============================================================
# Arcanum MI300X 一键部署脚本（幂等 / 断点续传 / 配额免疫）
# 用法: bash /mnt/workspace/oneclick-deploy.sh
# 前提: /mnt/workspace 持久区完好（llama.cpp 构建 + Muse GGUF 随持久区幸存）
# 流程: 自检 → 二进制缺失则重建 → 三模型+Muse 母带库 copy-first（缺件才下载）→
#       写启动脚本 → 起 4 服务 → 轮询健康检查
# 全程 ~15-35 分钟（视 hf-mirror 带宽）；中断后重跑即续传
# ============================================================
set -e

LL_BUILD=/mnt/workspace/llama.cpp
LL=$LL_BUILD/build/bin/llama-server
MODELS=/root/models
MASTERS=/mnt/workspace/models-base
MIRROR=https://hf-mirror.com

# 0) 持久区自检（canary=管线实际依赖的持久区资产）。原 ComfyUI 探针随该资产退役
#    已失效——2026-10-15 首战误报：ComfyUI 已清（53G 腾容）但持久区完好。
for d in /mnt/workspace/models-base /mnt/workspace/Muse-Glimmer-30B-GGUF /mnt/workspace/llama.cpp; do
  if [ ! -d "$d" ]; then
    echo "!! /mnt/workspace 持久区异常（缺 $d），确认实例与挂载是否正确"; exit 1
  fi
done

# 1) llama-server 二进制（正常随持久区幸存，丢失才重建）
if [ ! -x "$LL" ]; then
  echo "== llama-server 缺失，重建（约 30 分钟）=="
  if [ ! -d "$LL_BUILD" ]; then
    git clone https://github.com/ggml-org/llama.cpp "$LL_BUILD"
  fi
  cmake -S "$LL_BUILD" -B "$LL_BUILD/build" -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx942 -DCMAKE_BUILD_TYPE=Release
  cmake --build "$LL_BUILD/build" --config Release -j"$(nproc)" --target llama-server llama-cli
fi
echo "== llama-server 就位: $($LL --version 2>/dev/null | head -1) =="

# 2) 目录
mkdir -p $MODELS/gemma4-qat $MODELS/qwen38 $MODELS/r1-32b $MODELS/Muse-Glimmer-30B-GGUF

# dl <url> <dest> [expected_bytes] [expected_sha256]  断点续传 + 字节+SHA256 双硬校验（2026-10-10 外审 P0-④ 字节锚；2026-10-11 DSW 块B 四母带 SHA256 锚定升级）。
# 给了期望字节数时：已存在的文件也先验尺寸（防半截件被"已有即跳过"放行——pod 重建
# 重下 48GB 与跨源偏移两坑同源），下载后再验一次；不匹配 = rm + FATAL 退出。
# 给了期望 SHA256 时：同两段位置验哈希（比字节强——同尺寸内容漂移也拦），字节数保留为第二道。
dl() {
  if [ -f "$2" ]; then
    if [ -n "$3" ]; then
      S=$(stat -c %s "$2")
      if [ "$S" != "$3" ]; then
        echo "FATAL: 已有 $(basename "$2") 字节数 $S != 期望 $3（半截件），删除后重跑本脚本" >&2
        rm -f "$2"
        exit 1
      fi
    fi
    if [ -n "$4" ]; then
      H=$(sha256sum "$2" | cut -d' ' -f1)
      if [ "$H" != "$4" ]; then
        echo "FATAL: 已有 $(basename "$2") sha256 $H != 期望 $4（内容漂移），删除后重跑本脚本" >&2
        rm -f "$2"
        exit 1
      fi
    fi
    echo "已有 $(basename "$2")，校验通过，跳过"; return 0
  fi
  echo "== 下载 $(basename "$2") =="
  curl -L -C - --retry 5 --retry-delay 3 -o "$2" "$1"
  if [ -n "$3" ]; then
    S=$(stat -c %s "$2")
    if [ "$S" != "$3" ]; then
      echo "FATAL: $(basename "$2") 下载后字节数 $S != 期望 $3，删除后重跑本脚本" >&2
      rm -f "$2"
      exit 1
    fi
  fi
  if [ -n "$4" ]; then
    H=$(sha256sum "$2" | cut -d' ' -f1)
    if [ "$H" != "$4" ]; then
      echo "FATAL: $(basename "$2") 下载后 sha256 $H != 期望 $4，删除后重跑本脚本" >&2
      rm -f "$2"
      exit 1
    fi
  fi
}

# seed <src母带> <dest运行> [expected_bytes] [expected_sha256]  母带库优先播种（copy-first，2026-10-15）。
# 根治"只查运行目录 /root/models 不查母带库 models-base → pod 重建必重下 48GB"老毛病
# （WORK_LOG:2631/3068/3429 五连踩）。运行目录已有但字节数不符=半截件（下载/cp 中断），
# 先清再播（R1 清半截件自动化）；母带先过字节+SHA256 双检才 cp（母带异常不播种、绝不改
# 动持久区母带本身，交 dl 走下载兜底）；播种后的 dest 仍由 dl 复验=双闸。
# cp 约 2-3 分钟/件 vs 镜像下载 21 分钟且易超时中断。
seed() {
  local src=$1 dest=$2
  if [ -f "$dest" ]; then
    S=$(stat -c %s "$dest")
    if [ -n "$3" ] && [ "$S" != "$3" ]; then
      echo "!! 运行目录 $(basename "$dest") 字节 $S != 期望 $3（半截件），清除待重播" >&2
      rm -f "$dest"
    fi
  fi
  [ -f "$dest" ] && return 0
  if [ ! -f "$src" ]; then
    echo "== 母带库无 $(basename "$dest")，交 dl 下载 =="
    return 0
  fi
  S=$(stat -c %s "$src"); H=$(sha256sum "$src" | cut -d' ' -f1)
  if { [ -n "$3" ] && [ "$S" != "$3" ]; } || { [ -n "$4" ] && [ "$H" != "$4" ]; }; then
    echo "!! 母带 $(basename "$src") 校验不过（$S 字节 / $H），不播种交 dl 下载" >&2
    return 0
  fi
  echo "== 母带命中 $(basename "$dest")，播种（cp 约 2-3 分钟）=="
  cp "$src" "$dest"
}

# 3) 三个模型（根盘；实例释放即失，靠本脚本重建；SHA256=2026-10-11 持久区母带库实测，masters-sha256.txt）
# 每件两步：seed（母带库优先播种）→ dl（缺失才下载；无论来源都复验字节+SHA256）
GEMMA_DEST=$MODELS/gemma4-qat/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf
GEMMA_BYTES=14249047104
GEMMA_SHA=a7c5bc715f5ff8e99a3e8901ce7d2b42b402c669bf24f7c5250747633d0f5891
QWEN_DEST=$MODELS/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf
QWEN_BYTES=17559178144
QWEN_SHA=3f227079003add2511437e5b1e94812e363385225bf6a9b47b0054a72bc8b01e
R1_DEST=$MODELS/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf
R1_BYTES=19851335840
R1_SHA=bed9b0f551f5b95bf9da5888a48f0f87c37ad6b72519c4cbd775f54ac0b9fc62

seed $MASTERS/gemma4-qat/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf $GEMMA_DEST $GEMMA_BYTES $GEMMA_SHA
dl $MIRROR/unsloth/gemma-4-26B-A4B-it-qat-GGUF/resolve/main/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
   $GEMMA_DEST $GEMMA_BYTES $GEMMA_SHA
seed $MASTERS/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf $QWEN_DEST $QWEN_BYTES $QWEN_SHA
dl $MIRROR/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q4_K_XL.gguf \
   $QWEN_DEST $QWEN_BYTES $QWEN_SHA
seed $MASTERS/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf $R1_DEST $R1_BYTES $R1_SHA
dl $MIRROR/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
   $R1_DEST $R1_BYTES $R1_SHA

# Muse：同款 copy-first（母带库=/mnt/workspace/Muse-Glimmer-30B-GGUF，持久区原件）
MUSE_DEST=$MODELS/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf
MUSE_BYTES=19653960832
MUSE_SHA=ac7023d6a4c704eb9af54ab53e476a66b7f5b6c0ef2fc4a8dde5253c291a6c38
seed /mnt/workspace/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
     $MUSE_DEST $MUSE_BYTES $MUSE_SHA
dl $MIRROR/unsloth/Muse-Glimmer-30B-GGUF/resolve/main/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
   $MUSE_DEST $MUSE_BYTES $MUSE_SHA

# 4) 字节校验（qwen 已知基准；dl() 已前置校验，此处为服务起前最后一道闸——硬失败）
Q=$(stat -c %s $MODELS/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf)
if [ "$Q" = "17559178144" ]; then echo "qwen 校验 OK"; else
  echo "FATAL: qwen 字节数 $Q != 17559178144，拒绝带病起服务，请重跑本脚本" >&2; exit 1; fi

# 5) 写四服务启动脚本（含端口表与清理旧进程）
cat > /root/start-arcanum.sh << 'INNER_EOF'
#!/bin/bash
LL=/mnt/workspace/llama.cpp/build/bin/llama-server
pkill -f llama-server; sleep 3
nohup $LL -m /root/models/gemma4-qat/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
  -a gemma-arbiter -ngl 99 -c 65536 -np 2 --host 127.0.0.1 --port 8084 --jinja \
  > /root/srv_gemma.log 2>&1 &
nohup $LL -m /root/models/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
  -a r1-deepen -ngl 99 -c 32768 -np 2 --temp 0.6 --top-p 0.95 --host 127.0.0.1 --port 8083 --jinja \
  > /root/srv_r1.log 2>&1 &
nohup $LL -m /root/models/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  -a qwen-verify -ngl 99 -c 65536 -np 4 --host 127.0.0.1 --port 8182 --jinja \
  > /root/srv_qwen.log 2>&1 &
nohup $LL -m /root/models/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
  -a muse-scout -ngl 99 -c 98304 -np 1 --temp 1.0 --top-p 0.95 --top-k 64 --host 127.0.0.1 --port 8081 --jinja \
  > /root/srv_muse.log 2>&1 &
echo "4 servers launching"
INNER_EOF
chmod +x /root/start-arcanum.sh

# 6) 启动四服务
bash /root/start-arcanum.sh

# 7) 健康检查（轮询，最长 8 分钟）
echo "== 等待模型加载（根盘每模型约 1 分钟，四路并行）=="
ok=0
for i in $(seq 1 48); do
  sleep 10
  ok=0
  for spec in "8081 muse-scout" "8182 qwen-verify" "8083 r1-deepen" "8084 gemma-arbiter"; do
    p=${spec%% *}; n=${spec##* }
    if curl -s -m 3 127.0.0.1:$p/v1/models 2>/dev/null | grep -q "\"$n\""; then
      ok=$((ok+1))
    fi
  done
  echo "[$((i*10))s] $ok/4 就绪"
  if [ $ok -eq 4 ]; then break; fi
done
if [ $ok -eq 4 ]; then
  echo "=== 全部就绪 ==="
else
  echo "=== 超时未全就绪，排查: tail -20 /root/srv_*.log ==="
fi
rocm-smi --showmeminfo vram | grep -E "Total|Used"

#!/bin/bash
# ============================================================
# Arcanum MI300X 一键部署脚本（幂等 / 断点续传 / 配额免疫）
# 用法: bash /mnt/workspace/oneclick-deploy.sh
# 前提: /mnt/workspace 持久区完好（llama.cpp 构建 + Muse GGUF 随持久区幸存）
# 流程: 自检 → 二进制缺失则重建 → 补下 3 模型到 /root/models →
#       写启动脚本 → 起 4 服务 → 轮询健康检查
# 全程 ~15-35 分钟（视 hf-mirror 带宽）；中断后重跑即续传
# ============================================================
set -e

LL_BUILD=/mnt/workspace/llama.cpp
LL=$LL_BUILD/build/bin/llama-server
MODELS=/root/models
MIRROR=https://hf-mirror.com

# 0) 持久区自检
if [ ! -d /mnt/workspace/ComfyUI ]; then
  echo "!! /mnt/workspace 持久区异常（无 ComfyUI），确认实例与挂载是否正确"; exit 1
fi

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

dl() {  # dl <url> <dest>  断点续传
  if [ -f "$2" ]; then echo "已有 $(basename "$2")，跳过"; return 0; fi
  echo "== 下载 $(basename "$2") =="
  curl -L -C - --retry 5 --retry-delay 3 -o "$2" "$1"
}

# 3) 三个模型（根盘；实例释放即失，靠本脚本重建）
dl $MIRROR/unsloth/gemma-4-26B-A4B-it-qat-GGUF/resolve/main/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
   $MODELS/gemma4-qat/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf
dl $MIRROR/unsloth/Qwen3.8-27B-GGUF/resolve/main/Qwen3.8-27B-UD-Q4_K_XL.gguf \
   $MODELS/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf
dl $MIRROR/bartowski/DeepSeek-R1-Distill-Qwen-32B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
   $MODELS/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf

# Muse：优先用持久区原件（免下载），持久区也没有才从镜像补
if [ ! -f $MODELS/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf ]; then
  if [ -f /mnt/workspace/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf ]; then
    echo "== 从持久区复制 Muse（~1-2 分钟）=="
    cp /mnt/workspace/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
       $MODELS/Muse-Glimmer-30B-GGUF/
  else
    dl $MIRROR/unsloth/Muse-Glimmer-30B-GGUF/resolve/main/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
       $MODELS/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf
  fi
fi

# 4) 字节校验（qwen 已知基准）
Q=$(stat -c %s $MODELS/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf)
if [ "$Q" = "17559178144" ]; then echo "qwen 校验 OK"; else echo "警告: qwen 字节数 $Q != 17559178144"; fi

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
  -a muse-scout -ngl 99 -c 65536 -np 2 --temp 1.0 --top-p 0.95 --top-k 64 --host 127.0.0.1 --port 8081 --jinja \
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

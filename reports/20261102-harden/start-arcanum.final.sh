#!/bin/bash
LL=/mnt/workspace/llama.cpp/build/bin/llama-server
pkill -f llama-server; sleep 3
nohup $LL -m /root/models/gemma4-qat/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
  -a gemma-arbiter -ngl 99 -c 65536 -np 1 --host 127.0.0.1 --port 8084  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --cache-reuse 256 --jinja \
  > /root/srv_gemma.log 2>&1 &
# 2026-10-23 unagi 实证：deepen 数据块≈80.2k tokens（safe 块+confirmed-vulnerability JSON 全量），
# -c 32768 -np 2 → n_ctx_slot=16384 必溢出（exceed_context_size_error，回炉重试同死=6 次截断），
# nvs 4/4 + unagi 3/3 链全占位同源（10-21 gpt-oss/qwen 同病当时只修两家，r1 观察项至此销案）；
# -c 131072 -np 1 = KV 32GiB（+24GiB，总 VRAM ≈125G/192G），80.2k 输入 + 充裕输出余量
nohup $LL -m /root/models/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
  -a r1-deepen -ngl 99 -c 131072 -np 1 --temp 0.6 --top-p 0.95 --host 127.0.0.1 --port 8083  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --cache-reuse 256 --jinja \
  > /root/srv_r1.log 2>&1 &
nohup $LL -m /root/models/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  -a qwen-verify -ngl 99 -c 65536 -np 1 --host 127.0.0.1 --port 8182  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --cache-reuse 256 --jinja \
  > /root/srv_qwen.log 2>&1 &
nohup $LL -m /root/models/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
  -a muse-scout -ngl 99 -c 98304 -np 1 --temp 1.0 --top-p 0.95 --top-k 64 --host 127.0.0.1 --port 8081  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --cache-reuse 256 --jinja \
  > /root/srv_muse.log 2>&1 &
# 2026-10-21 webhooktester H1 实证：-np 4 使 per-slot n_ctx=65536/4=16384，
# 29293 tokens 证据包溢出降级（exceed_context_size_error）；verify 并发=1 已拍板，
# np=1 独占全窗、KV 显存零变化（对齐 muse np=1 先例）；qwen 备胎同机理同修
nohup $LL -m /root/models/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf \
  -a gpt-oss-verify -ngl 99 -c 65536 -np 1 --host 127.0.0.1 --port 8085  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --cache-reuse 256 --jinja \
  > /root/srv_gptoss.log 2>&1 &
echo "5 servers launching"

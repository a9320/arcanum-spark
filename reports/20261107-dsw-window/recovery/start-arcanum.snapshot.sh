#!/bin/bash
LL=/mnt/workspace/llama.cpp/build/bin/llama-server
pkill -f llama-server; sleep 3
nohup $LL -m /root/models/gemma4-qat/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
  -a gemma-arbiter -ngl 99 -c 65536 -np 1 --host 127.0.0.1 --port 8084  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --jinja \
  > /root/srv_gemma.log 2>&1 &
# 2026-11-02 B5 固化：-np 2 → -np 1。arbiter 单次调用（pipeline.py:371 非并发），
# 第二 slot 纯闲置；统一 np 1 = 串话风险面最小化 + KV 略省（实测总 VRAM 降 268MiB）。
# 证据=runs/20261102-harden（B5 应用后五服务 5/5、串话回归 5/5 干净、验收卷判决不变）。
# 2026-10-23 unagi 实证：deepen 数据块≈80.2k tokens（safe 块+confirmed-vulnerability JSON 全量），
# -c 32768 -np 2 → n_ctx_slot=16384 必溢出（exceed_context_size_error，回炉重试同死=6 次截断），
# nvs 4/4 + unagi 3/3 链全占位同源（10-21 gpt-oss/qwen 同病当时只修两家，r1 观察项至此销案）；
# -c 131072 -np 1 = KV 32GiB（+24GiB，总 VRAM ≈125G/192G），80.2k 输入 + 充裕输出余量
nohup $LL -m /root/models/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
  -a r1-deepen -ngl 99 -c 131072 -np 1 --temp 0.6 --top-p 0.95 \
  -ctk q8_0 -ctv q8_0 --host 127.0.0.1 --port 8083  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --jinja \
  > /root/srv_r1.log 2>&1 &
# 2026-11-02 B1 固化：-ctk q8_0 -ctv q8_0（知识库 ID 990/1318/501 同款）。
# 证据=runs/20261102-harden 四卷对照：FK KV f16 vs q8_0，四假设判决逐位一致
# （H1 U0.5/H2 C0.95/H3 C0.95/H4 U0.3）、deg=0/deepen_fail=0；总 VRAM
# 117.6→103.7 GiB（省 13.9 GiB）。墙钟无变化（本卷短输出，KV 带宽非瓶颈）。
# 注意 ROCm FA 的 V-cache 只接 Q8_0/F16，q4/q5 会落 CPU 慢路径（ID 501）——勿改成 q4。
nohup $LL -m /root/models/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf \
  -a qwen-verify -ngl 99 -c 65536 -np 1 --host 127.0.0.1 --port 8182  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --jinja \
  > /root/srv_qwen.log 2>&1 &
nohup $LL -m /root/models/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf \
  -a muse-scout -ngl 99 -c 98304 -np 1 --temp 1.0 --top-p 0.95 --top-k 64 --host 127.0.0.1 --port 8081  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --jinja \
  > /root/srv_muse.log 2>&1 &
# 2026-10-21 webhooktester H1 实证：-np 4 使 per-slot n_ctx=65536/4=16384，
# 29293 tokens 证据包溢出降级（exceed_context_size_error）；verify 并发=1 已拍板，
# np=1 独占全窗、KV 显存零变化（对齐 muse np=1 先例）；qwen 备胎同机理同修
nohup $LL -m /root/models/gpt-oss-20b/gpt-oss-20b-MXFP4.gguf \
  -a gpt-oss-verify -ngl 99 -c 65536 -np 1 --host 127.0.0.1 --port 8085  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 --jinja \
  > /root/srv_gptoss.log 2>&1 &
echo "5 servers launching"

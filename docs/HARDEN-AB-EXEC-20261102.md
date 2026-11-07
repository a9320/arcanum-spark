# B 批加固 A/B 预注册执行单（2026-11-02 起草，本地零模型消耗）

依据：`amd-qa-notes/AMD-MI300X适配笔记-精选汇编.md` §13（AMD 社区问答 1321 条精读）。
A 批（串话防线/加固参数/GPU 判据/依赖验收）已落 `154f7a7`。本单覆盖 **B 批五项**，
全部改变模型输出或性能，**必须 A/B 后才可固化进 oneclick**。

预注册纪律（沿用项目既有）：判据先定、单变量递进、任一硬闸不过即回滚并记 FAIL，
不得事后调参补救；数字引用必须带 prompt 长度/卷时长（§3 六测量伪影）。

---

## §0 前提（缺一不可）

| 闸 | 命令 | 期望 |
|---|---|---|
| 恢复序 | clone/reset → `pip install -r requirements.txt` → `bash deploy/mi300x-oneclick.sh` | 日志见 **`== 加固参数: ...`** 行（A 批四项被当前构建接受的情况）+ **python 验收三行**（torch/hip/cuda_available/gpu_add） |
| 五服务 | `python scripts/check_endpoints.py --gpu` | 5/5 ready + `[OK] gpu gfx=gfx942` + VRAM 读数 |
| **串话回归** | `python scripts/regression_concurrency.py --all-local --rounds 4 --concurrency 3` | **PASS（exit 0）**。FAIL 则本节其余全部暂停 → 走 §13 P0-1 分支（换 llama.cpp 构建 / Vulkan / 钉已验证版本），并重估历史跑批归因 |
| 基线卷 | 见 §1 块 B A 臂 | `SRC` 固定假设集在位：`/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json` |

预算：块 A ~10min + 块 B 6 卷 ~20min + 块 C 6 卷 ~20min + 块 D 探测 ~5min ≈ 1 小时。
全部命令前台执行/或 nohup+轮询（跑批卷用 `timeout` 帽）。

统一产物根：`BASE=/mnt/workspace/runs/20261102-harden`（先 `mkdir -p`）。

---

## §1 判据总表（预注册，先定后跑）

| 项 | 改动 | 对照 | N | 硬闸（任一不过=FAIL 回滚） | 软指标 | 回滚 |
|---|---|---|---|---|---|---|
| **B5** | gemma-arbiter `-np 2` → `-np 1` | 改前 monolith | — | 5/5 就绪；串话回归 PASS | VRAM 略降 | 改回 `-np 2` |
| **B3** | 五服务加 `--cache-reuse 256` | 改前 | 2 卷 | 5/5 就绪；**串话回归 PASS**（cache-reuse 与串话 bug 族同面，必须重测）；两卷输出判决一致 | 第二卷墙钟 ≤ 第一卷（prefix 复用生效） | 删参数重启 |
| **B1** | r1-deepen 加 `-ctk q8_0 -ctv q8_0` | KV f16 同卷 N=3 | 3+3 | ①B 臂 3 卷 `verify_degraded` 全 0；②同假设 verdict 与 A 臂一致（confidence 差 ≤0.1）；③JSON 契约无解析失败 | r1 进程 VRAM 降（预期 KV 32→~16GiB）；单卷墙钟不劣化（社区称快 28%） | 去两参数重启 |
| **B4** | r1-deepen 加 `--reasoning-budget 1024 --reasoning-budget-message "Thinking budget reached. Stop reasoning and output the final answer now."` | B1 定稿配置 | 3+3 | ①deepen 占位/降级 0（历史 unagi 坑不复现）；②判决一致（同上口径）；③无 `invoke error` | 单卷墙钟下降（think 少烧） | 去两参数重启 |
| **B2** | MTP `--spec-type draft-mtp --spec-draft-n-max 2` | 探测优先 | 探测→2+2 | ①模型确有 MTP 头（否则记"不适用"跳过）；②输出 JSON 契约完整（社区有"2x t/s 但输出垃圾"前科）；③判决一致 | decode 提速（muse 长 JSON 场景） | 去参数重启 |

**采样与模型一律不动**（`--temp/.top-p` 保持现有配方；verify 仍 gpt-oss :8085，并发 1）。

---

## §2 块 A：B5 + B3（一次重启，低风险）

```bash
BASE=/mnt/workspace/runs/20261102-harden; mkdir -p "$BASE"
cp /root/start-arcanum.sh "$BASE/start-arcanum.sh.bak-$(date +%H%M)"   # 回滚点
# 1) gemma -np 2 → -np 1（只动 gemma 行）
sed -i '/-a gemma-arbiter/ s/ -np 2/ -np 1/' /root/start-arcanum.sh
grep -A1 'gemma-arbiter' /root/start-arcanum.sh | head -2            # 目视确认 -np 1
# 2) 五服务加 --cache-reuse 256（--jinja 前注入；幂等）
grep -q 'cache-reuse 256' /root/start-arcanum.sh || sed -i 's/ --jinja/ --cache-reuse 256 --jinja/' /root/start-arcanum.sh
grep -c 'cache-reuse 256' /root/start-arcanum.sh                     # 期望 5
# 3) 全量重启 + 就绪闸
pkill -f llama-server; sleep 5; bash /root/start-arcanum.sh
for i in $(seq 1 60); do n=$(pgrep -c llama-server); [ "$n" -ge 5 ] && { echo "READY=$n"; break; }; sleep 10; done
python scripts/check_endpoints.py --gpu | tail -3                    # 期望 5/5 + gpu OK
# 4) 串话回归（本块最关键闸）
python scripts/regression_concurrency.py --all-local --rounds 4 --concurrency 3; echo "stutter-exit=$?"
# 5) 两卷连续（测 prefix 复用口径）
SRC=/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json \
  OUT="$BASE/reuse-r1" bash scripts/run-verify-acceptance.sh; \
SRC=/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json \
  OUT="$BASE/reuse-r2" bash scripts/run-verify-acceptance.sh
# 6) 墙钟对照（两卷 mtime 差 vs 跑批日志时间戳）
ls -l --time-style=+%H:%M:%S "$BASE"/reuse-r*/e2e_report.json
```

判读：串话 FAIL → **立即回滚并停止本单其余各块**（`cp $BASE/start-arcanum.sh.bak-* /root/start-arcanum.sh` + 重启），
转 §13 P0-1 分支排查——串话未清之前不得引入任何缓存/复用类参数（B3/B1/B4 全部搁置）。
两卷判决不一致 → B3 FAIL（cache-reuse 影响复用正确性），回滚 B3、保留 B5。
通过 → 记 PASS，进块 B（不回滚，B5/B3 成为新基线）。

---

## §3 块 B：B1 KV q8_0（r1-deepen 单服务 A/B，单变量）

```bash
BASE=/mnt/workspace/runs/20261102-harden; mkdir -p "$BASE"
# A 臂前置确认：r1 当前为 f16 KV（cmdline 无 ctk/ctv；有则说明上一轮实验参数未回滚）
tr '\0' '\n' < /proc/$(pgrep -f r1-deepen | head -1)/cmdline | grep -E -- "-ctk|-ctv" && echo "!! r1 已带 KV 量化，先回滚再跑 A 臂" || echo "A-ARM-CLEAN(f16)"
for r in 1 2 3; do
  SRC=/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json \
    OUT="$BASE/kv-a-r$r" bash scripts/run-verify-acceptance.sh; echo "== kv-a-r$r exit=$? =="
done
# 切 B 臂：只重启 r1，加 KV 量化（其余参数照抄 oneclick 配方 + A 批加固参数）
pkill -f "r1-deepen"; sleep 5
nohup /mnt/workspace/llama.cpp/build/bin/llama-server \
  -m /root/models/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
  -a r1-deepen -ngl 99 -c 131072 -np 1 --temp 0.6 --top-p 0.95 \
  -ctk q8_0 -ctv q8_0 --cache-reuse 256 \
  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 \
  --host 127.0.0.1 --port 8083 --jinja > /root/srv_r1_kv8.log 2>&1 &
for i in $(seq 1 36); do curl -s -m 3 127.0.0.1:8083/v1/models | grep -q r1-deepen && { echo R1_READY; break; }; sleep 5; done
rocm-smi --showmeminfo vram | grep -iE "used" | head -2               # 显存读数（对照 A 臂同刻）
for r in 1 2 3; do
  SRC=/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json \
    OUT="$BASE/kv-b-r$r" bash scripts/run-verify-acceptance.sh; echo "== kv-b-r$r exit=$? =="
done
```

汇总对比（六卷一次打表）：

```bash
python - <<'PY'
import glob, json
for p in sorted(glob.glob("/mnt/workspace/runs/20261102-harden/kv-*-r*/e2e_report.json")):
    d = json.load(open(p)); m = d.get("meta", {})
    ver = m.get("verifications", [])
    rows = [(v.get("hypothesis_id"), v.get("verdict"), round(float(v.get("confidence") or 0), 2),
             bool(v.get("degraded"))) for v in ver]
    print(p.split("/")[-2], "degraded=", m.get("verify_degraded"),
          "deepen_fail=", len(m.get("deepen_failures") or []), rows)
PY
```

判读：①B 臂任一卷 `verify_degraded>0` 或 deepen 占位 → FAIL 回滚（`pkill -f r1-deepen` + 用块 A 参数重启）；
②同假设 verdict 漂移或 confidence 差 >0.1 → FAIL；③全过 → B1 定稿，记 VRAM/墙钟改善数字。

---

## §4 块 C：B4 reasoning-budget（在 B1 定稿配置上叠加）

```bash
pkill -f "r1-deepen"; sleep 5
nohup /mnt/workspace/llama.cpp/build/bin/llama-server \
  -m /root/models/r1-32b/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf \
  -a r1-deepen -ngl 99 -c 131072 -np 1 --temp 0.6 --top-p 0.95 \
  -ctk q8_0 -ctv q8_0 --cache-reuse 256 \
  --reasoning-budget 1024 \
  --reasoning-budget-message "Thinking budget reached. Stop reasoning and output the final answer now." \
  --cache-ram 0 --no-cache-idle-slots --fit off --ctx-checkpoints 2 \
  --host 127.0.0.1 --port 8083 --jinja > /root/srv_r1_budget.log 2>&1 &
for i in $(seq 1 36); do curl -s -m 3 127.0.0.1:8083/v1/models | grep -q r1-deepen && { echo R1_READY; break; }; sleep 5; done
# 对照臂 = 块 B 的 kv-b（已含 KV 量化、无 budget）；实验臂 N=3：
for r in 1 2 3; do
  SRC=/mnt/workspace/runs/20261018-new2q/gatekeeping/report.json \
    OUT="/mnt/workspace/runs/20261102-harden/budget-r$r" bash scripts/run-verify-acceptance.sh; echo "== budget-r$r exit=$? =="
done
grep -c "invoke error" /root/srv_r1_budget.log || true               # 期望 0
```

判读：deepen 占位/降级 >0 或 `invoke error` 出现 → FAIL（budget 过紧，改 2048 重测一次仍败则搁置）；
判决一致 + 墙钟下降 → PASS。

---

## §5 块 D：B2 MTP 探测（先探后跑）

```bash
LL=/mnt/workspace/llama.cpp/build/bin/llama-server
$LL --help 2>&1 | grep -E -- "--spec-type|--spec-draft-n-max" | head -3
# 模型是否有 MTP 头：启动时看 draft 层日志（或 /props）
grep -iE "draft|mtp" /root/srv_muse.log | tail -3
```

探测无支持/无 MTP 头 → 本项记 **"不适用（当前构建/模型）"**，不硬上。
有 → 对 muse-scout 加 `--spec-type draft-mtp --spec-draft-n-max 2` 重启，A/B 各 2 卷（同 §3 口径），
重点是**输出 JSON 契约完整性**（Scout 交卷解析失败=0）与判决一致。

> **✅ 定谳（2026-11-07 夜窗，11-07 追记）：不适用（Muse-Glimmer 无 MTP 头）**——
> 构建支持（`--spec-type` 枚举含 `draft-mtp`）✓；`srv_muse.log` draft/mtp 零命中 ✓；
> GGUF 头部 5MB metadata 探针仅 `Draft/SMTP/drafted` 文本假阳性（真 MTP 头应出
> mtp/nextn 结构键或张量名）✓。按本节预注册分支结案，B2 出执行单。证据=
> `reports/20261107-dsw-window/recovery/`（srv 日志+oneclick 日志）。

---

## §6 收尾（无论通过与否）

```bash
# 归档：srv 日志 + 全套卷目录 + 本单运行记录
cp /root/srv_*.log /mnt/workspace/runs/20261102-harden/ 2>/dev/null
tar czf /mnt/workspace/runs/20261102-harden.tar.gz -C /mnt/workspace/runs 20261102-harden
ls -lh /mnt/workspace/runs/20261102-harden.tar.gz
```

固化规则：**每通过一项，单独 commit 改 oneclick**（`feat(ops): 固化 B<n> ...（证据=本单 §x 卷）`），
不把多项合并成一个提交（便于单项回滚）。未通过项在 oneclick 注释里记"实验过 FAIL 的原因"。

判读口径：本单全部数字为**单次观察**，报告写"本轮未观察到 X"，不写"已修复"；引用墙钟必带卷名与假设数。
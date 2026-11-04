# 下个 DSW 窗三合一预注册执行单 —— B2 MTP 首验 × 方差治理 Exp A/B × K1 gpt-oss 全量重判（2026-11-04，纯文档）

> 判据出处（先看这些，本单不重复定义）：`docs/VERDICT-VARIANCE-GOVERNANCE.md` §四（Exp A/B，
> 机读判分 `eval/gov_summary.py`）｜`docs/HARDEN-AB-EXEC-20261102.md` §5（B2 探测原文）｜
> `docs/VERIFY-MODEL-AB-DESIGN.md` §7（verify 换 gpt-oss 拍板，本单 K1 块即其后续重判）。
> 纪律：**判据先定后跑；每 PASS 一项单独 commit；所有结论按单次观察口径；跑批一律前台**
> （10-25 教训：nohup 后台 driver 被平台判空闲 SIGTERM 杀，oneclick 幸存但零卷）。
> 数字不粉饰：未在本单或引用文档里实证的耗时/分数一律不写。

## §0 前提（缺一不可）

1. **块 0 判活**：`hostname` + `ls /root/models`。`/root/models` 空 = 新 pod，走第 2 条恢复序；
   持久区盘点四件母带 + `llama.cpp` + laya checkpoint 是否在位。
2. **恢复序（实证版，逐字执行）**：
   ```bash
   git config --global http.version HTTP/1.1
   # 仓缺失 → GitHub clone（bundle 是区间打包，只能 pull 进已有仓、不能 clone 成新仓）；
   # 仓在位 → 开机先 git fetch + reset --hard origin/master（本单以该 HEAD 为准）
   pip install -r requirements.txt        # strands 等钉版以 requirements.txt 为准
   # 播种（必须先 rm 半截件，cp 或 symlink，播完即核字节锚）：
   stat -c %s /mnt/workspace/models-base/gemma4-qat/* \
     /mnt/workspace/models-base/qwen38/Qwen3.8-27B-UD-Q4_K_XL.gguf \
     /mnt/workspace/models-base/r1-32b/*.gguf \
     /mnt/workspace/Muse-Glimmer-30B-GGUF/Muse-Glimmer-30B-KQuant-Dynamic-Q4_K_XL.gguf
   # 期望字节数：14249047104 / 17559178144 / 19851335840 / 19653960832（gpt-oss 母带已在持久区）
   # 然后：仓内 deploy/mi300x-oneclick.sh 覆盖平台旧副本再点火（仓内版 = A 批四项加固 + B1 KV q8_0 + B5 np1 已固化）
   ```
3. **READY 三证**（缺一不可，进程数只是必要非充分——块 7 教训）：
   ① `python scripts/check_endpoints.py --gpu` 五端点全 `[OK]` + `RESULT: READY`；
   ② `:8085` gpt-oss 卡片在位；③ VRAM 读数落在**含 `-ctk q8_0 -ctv q8_0`** 的固化配置带
   （11-02 实测 103.7 GiB used；不带 KV 量化的旧基线 117.6–117.9 出现 = 固化参数没生效，先查 `/proc/<pid>/cmdline`）。
   **运行态唯一权威 = cmdline，不信任何脚本快照**（块 16 教训：快照 ≠ 运行态）。
4. **粘贴块纪律**：一块一贴、禁 heredoc、禁 `exit`；任何带凭据的循环必须"成功即 `break`"
   （11-02 token 明文回显事故 = 无 break 凭据循环所致）。

## §1 判据总表（预注册，先定后跑）

| 块 | 任务 | 通过判据 | 失败分支 | 预算 |
| --- | --- | --- | --- | --- |
| 1 | 开机恢复 | §0.3 READY 三证全绿 | 字节数缺=重播种；oneclick 日志出现下载行=播种路径错，停并核 | ~30–45 min |
| 2 | B2 MTP 首验 | 出二值定论：模型无 MTP 头→"不适用"结案；有头→探测即 PASS（A/B 另议） | 构建不支持=异常（11-02 已实证支持），查构建版本 | ~5 min |
| 3 | 方差治理 Exp A/B | `gov_summary.py` 三判据全绿（档位一致率 ≥4/5；H1 grounding 随臂漂移+H2 对照；conf_ref=0） | 任一不达标=登记册采样类记**负结果**，不改判据、不现场重跑 | ~1 h |
| 4 | K1 gpt-oss 重判 | 20/20 有 report.json + `k1_rescore.sh` manifest SHA 闸 PASS 出分 | rescore exit 2=缺卷/坏卷，幂等补跑；单卷超时记录顺延下窗 | 分 2–3 窗 |
| 5 | 收尾入仓+直推 | push 出现 `master -> master` | 三分型处置（§5） | ~10 min |

**窗口优先级**：块 3 > 块 4（Exp A/B 必须在单窗内一条龙跑完；K1 靠 `k1_batch.sh` 幂等天然可分段。
时间不足时宁可在块 4 中途收工归档，也不砍块 3 的卷数——判据是 N=5/N=3×2 定死的。）

## §2 块 2：B2 MTP 首验（逐字抄 HARDEN-AB-EXEC §5）

```bash
LL=/mnt/workspace/llama.cpp/build/bin/llama-server
$LL --help 2>&1 | grep -E -- "--spec-type|--spec-draft-n-max" | head -3
grep -iE "draft|mtp" /root/srv_muse.log | tail -3
```

裁决三分支：
- **构建不支持**（11-02 实测 `spec-type支持=1`，理论上不应再现）→ 异常，核对 llama.cpp 版本后记录；
- **模型无 MTP 头**（grep 空 + metadata 无 draft 层）→ 记 **"不适用（Muse-Glimmer 无 MTP 头）"**，
  B2 结案出本单，commit `docs(ops): B2 定谳不适用`；
- **有头** → 本块记 PASS（模型侧能力实锤）；muse-scout 加
  `--spec-type draft-mtp --spec-draft-n-max 2` 的 A/B 两卷对照**仅在窗口有富余时执行**，
  重点判据沿用 HARDEN-AB-EXEC §5：Scout 交卷解析失败=0 且判决一致。

## §3 块 3：方差治理 Exp A/B（driver 已具备前台心跳，不外加 nohup）

```bash
BASE=/mnt/workspace/runs/20261104-gov MODE=ALL bash scripts/run-arm-gov.sh
# driver 自带：preflight（import 链 + :8085 路由 + SRC 在位，红即 exit 3）→ Exp A N=5 → Exp B 两臂 N=3 → 汇总+闸门
# 补判不跑模型：BASE=/mnt/workspace/runs/20261104-gov MODE=SUMMARY bash scripts/run-arm-gov.sh
```

判读（全在 driver 末段自动机读，人工只贴输出）：
- Exp A = 同假设 confidence **档位一致率 ≥ 4/5**（基线对照 = 旧数值口径逐位一致率，t4b/t4c 卷可算）；
- Exp B = **H1 evidence_source 分布随臂漂移**（default 主 `repo_file` / minpack 主 `library_knowledge`）
  且与 verdict 相关；H2 两臂均主 `repo_file`（零效应对照）；
- 闸门 = 两实验全卷 `confident_refutations` 保持 **0**。

结果落法：PASS → 记"治理有效（单次观察口径）"进设计稿 §六实施记录；FAIL → 登记册采样类记负结果。
两种结局都收 `20261104-gov/` 入仓（§5），**都不回滚 D1/D2**（已属生产链路）。

## §4 块 4：K1 全量重判（verify=gpt-oss 生产臂，vs 10-03 qwen 基线）

基线对照 = `runs/20261003-k1`（qwen verify 判词：机制 tp12 / 语义 tp13，判决层台账 K1 终态）。
本块在 gpt-oss verify（10-17 拍板生产默认）下重跑同 20 题。**新臂必须走 `K1_BASE=` 参数化**
（本单同日随附提交：`k1_batch.sh` 的 `G=${K1_BASE:-…}`，否则幂等逻辑会把旧基线 20 卷全 skip）：

```bash
# 前置闸：题库与 manifest 在位（缺题库=本块整体顺延，别起半截）
ls /mnt/workspace/NYU_CTF_Bench >/dev/null && echo BENCH_OK
mkdir -p /mnt/workspace/runs/20261104-k1-gptoss
K1_BASE=/mnt/workspace/runs/20261104-k1-gptoss bash scripts/k1_batch.sh
# 前台跑（脚本逐题打 "[k1] <cid> exit=<rc> <HH:MM>" 即心跳）；断窗续跑=同命令重发，已有卷自动 skip
# 全 20 卷齐后判分（sha 闸不匹配或缺题直接 exit 2 不出分）：
bash scripts/k1_rescore.sh /mnt/workspace/runs/20261104-k1-gptoss /mnt/workspace/runs/20261104-k1-gptoss/rescore.json
```

预注册报告口径（收数后本地判读，窗口内只采集）：
- 报 **机制/语义两口径 tp/fn** + 逐题相对 20261003-k1 的**翻转清单**（C↔UNC↔REFUTED 每题列出）；
- **只记录分布差异，不裁决"换模后更好"**（归因是方差治理/台账另案，防单次观察过度解读）；
- 耗时口径：用 `logs/` 逐题时间戳差实算单题带，写入 WORK_LOG 供后续排窗。

## §5 块 5：收尾（无论通过与否）

1. **入仓**（逐条 `git add`，禁 `-A`）：`reports/20261104-<块名>/`（卷目录 + driver 输出
   + 相关 srv 日志 + `start-arcanum.sh` 快照仅作留档并注明"以 cmdline 为准"）；每块单独 commit。
2. **直推三步**（11-02 四条教训固化）：
   ```bash
   git -c http.version=HTTP/1.1 pull --rebase origin master 2>&1 | tail -3   # 先 rebase，防 non-fast-forward
   read -rs -p "GHT=" T && export T; echo; echo "len=${#T}"                  # 单独一条贴，len 36–100
   git -c http.version=HTTP/1.1 push "https://$T@github.com/a9320/arcanum-spark.git" master 2>&1 | tail -2; unset T
   ```
   失败分型：`Invalid username or token`=认证（重注 token）｜`before pushing again`=先 pull --rebase｜
   `port 443 timed out`=网络劣化（可重试，但**循环必须带成功即 break**，禁止裸重试循环）。
3. **持久区归档**：`tar czf /mnt/workspace/runs/20261104-all.tar.gz -C /mnt/workspace/runs 20261104-*`
   （双副本兜底，GitHub push 绿之前不关机）。
4. push 绿 + tar 在位 → **可关机**。

## §6 本单结题动作（跑批窗之外，本地）

- 结果回填：Exp A/B 三判据读数进 `VERDICT-VARIANCE-GOVERNANCE.md` §六实施记录"待 DSW 验收"行；
  B2 三分支结论进 `HARDEN-AB-EXEC-20261102.md` §5；K1 翻转清单与两口径 tp/fn 进判决层台账 + WORK_LOG。
- 本单无论全绿/部分负结果，**都不产生代码改动**；固化项只认"每 PASS 单独 commit"规则。

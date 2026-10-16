# VERIFY-MODEL-AB-DESIGN — Verify 岗换模 A/B（Qwen3.8-27B vs gpt-oss-20b）设计稿 v1

日期：2026-10-16 ｜ 状态：设计稿待实施（纯文档零代码，DSW 端执行）｜ 前置证据：10-15 干净版判读 + routing.py/oneclick/scripts 实读
提案人：用户（10-16 拍板：双臂先各自实测，择优上岗）｜ 撰稿：ZCode 会话

## 1. 背景证据链（五源）

1. **verify=当前全 council 唯一卡点（10-15 干净版）**：flask_caching 3 假设 14min 三判词全 UNCERTAIN；nekocat/webhooktester 双双 25min 哨杀于 verify 阶段（webhooktester 死于"写 VerificationResult"临门一脚=活没干完非卡死）。
2. **慢的定性**=推理工作量×串行结构，解码吞吐是乘数（10-15 23:01 定案⑧⑨）。并发化（c26b399，`ARCA_VERIFY_MAX_CONCURRENCY=3`）治串行一半，**本设计治乘数与判词质量**。
3. **岗位画像（定案④修正版）**："思考型适合 Verify/Arbiter 岗"。现役 qwen-verify=Qwen3.8-27B dense Q4_K_XL（字节锚 17559178144，非思考型），判词保守（全 UNCERTAIN 在案）。
4. **候选 gpt-oss-20b 画像**：OpenAI 开权重（Apache-2.0），MoE 总参 ~21B/激活 ~3.6B（每 token 算力≈现役 1/7.5，正打吞吐乘数），原生 MXFP4（文件 ~12-13GB 级，**下载时以 HF 实际字节实测入锚**），128k ctx，`reasoning_effort` low/medium/high 三档，harmony 格式，agentic/tool-use 为强项。
5. **一箭双雕**：本 A/B 同时=开放项②（干净版全 UNCERTAIN 归因待对照）的对照实验——B 臂若出 CONFIRMED，则"全 UNCERTAIN=qwen 特异性保守"当场归因。

## 2. 目标 / 非目标

- **目标**：预注册 A/B 判定 verify 岗换模去留；双臂数据落账（verify 段墙钟/判词分布/tp/fn）。
- **非目标**：不动 Scout（Muse 冻结红线=K1 基线可比性）；不动 deepen/arbiter（gpt-oss 若 verify 落选，转 Arbiter 岗评估=次选落位，另稿）；本稿不改 oneclick 固化——探针与 A/B 用终端手动命令，拍板后才固化进 oneclick。

## 3. 设计红线（不可违背）

1. **两臂串行**：共享 GPU 算力会污染墙钟数据（10-14 定案②先例）——A/B 臂禁止并行跑。
2. **同题同帽同并发**：双臂除 verify 模型外其余 env 全同（含 `ARCA_VERIFY_MAX_CONCURRENCY=3`；帽 25min 起步，若 B 臂需 2100s 补跑则 A 臂同帽补跑对齐）。
3. **判分口径不双标**：判分用仓内 `data/m8_k1_manifest.json`（根目录旧 manifest 陷阱在册）+ v0.5 等价类，两臂同判。
4. **探针先于 A/B**：三前提探针任一红则中止本设计（死因入错误清单），不硬跑。

## 4. 设计（三段走）

### 4.1 三前提探针（gate，任一红则中止）

- **P1 ROCm/MXFP4 成色**：持久区 llama.cpp 版本实测（gpt-oss 支持需 2025-08 后构建，过旧先重建）；load gpt-oss-20b GGUF，记录是否触发 MXFP4 fallback（HIP kernel 现状待证）与解码 tok/s。fallback 到量化版不算红（VRAM 87.7/205.8G 余量足），只下调倍数预期。
- **P2 structured_output 端到端**：strands `structured_output=VerificationResult` 单假设试调用，JSON schema 必须全量落地。llama-server 四服务已全线 `--jinja`（服务端前提在位，oneclick:155-164 实读），探针验证 harmony tool-call 解析。
- **P3 思考控制生效证据**：API 侧 `reasoning_effort` 若被 llama-server 静默忽略=安慰剂旋钮（`ARCA_SCOUT_MAX_TOKENS` 前车之鉴），必须在服务端钉死思考预算并在卷上留生效证据（思考段有无/长度）。

### 4.2 A/B 两臂（flask_caching 单题起步）

- **A 臂（对照）**=现役：qwen-verify :8182，`scripts/run-arm-muse-3q.sh` 原样。
- **B 臂（候选）**=gpt-oss-20b 起 llama-server（另口 + `ARCA_VERIFY_MODEL`/`ARCA_VERIFY_BASE_URL` 覆盖，env 完整清单纪律），其余与 A 全同。
- **判据（预注册，窗口前不改）**：主=verify 段墙钟（B/A 比）；副=判词分布（CONFIRMED/UNCERTAIN/REFUTED）、判分 tp/fn（v0.5 口径）、node_errors 与 structured_output 落地成功率、报告字节。
- **裁读规则**：
  - ① B 墙钟≤A 且判词不劣（CONFIRMED≥A 且 tp≥A）→ 拍板替换：verify 现役=gpt-oss-20b，固化进 oneclick（qwen 槽换血或双 backend 参数化，实施时定）；
  - ② B 墙钟≤A 但判词更保守或 tp 持平 → 挂观察，加跑第二题（webhooktester=上窗哨杀题，兼测"能否跑完"）再裁；
  - ③ B 墙钟>A 或 structured_output 落地失败 → qwen 留任，gpt-oss 转 Arbiter 岗评估（次选落位，另稿）；
  - ④ 探针红 → 本设计挂起，死因入错误清单。

### 4.3 数据与账目

每臂产物=runs/2026101x-verifyab-{qwen,gptoss}/；tar 回传本地判读；判分件双份留档；WORK_LOG 记账（规则矿纪律：每跑必记）。

## 5. 风险与回退

- MoE 在 HIP 后端性能成色未证（P1 出数）；harmony 停止符/思考段处理未证（P2 出数）。
- gpt-oss 治吞吐不治单假设推理工作量：5 假设题仍可能需 2100s 帽——两臂同帽对齐即可，不影响裁读。
- 回退=零成本：A 臂即现役配置；B 臂三行 env 不设即回。

## 6. 与既有线的联动

- **判分器第二案**（RCE/AUTH_BYPASS 对子）：gpt-oss 若出词表外标签，与 Muse INPUT_VALIDATION 观察同账联动。
- **排期**：既定两臂（并发化自验证 + step5 v1.1 首战）仍为下窗第一优先 → 本设计三探针 + A/B 串行其后（同窗余量或下窗第二优先）。
- **对外素材**：SPACE 定性=约束/遏制类（非检测类），与本项目"检测+判分"构成互补分层（关住 vs 找出来）——#3/#4 补注可引用，未证实数字（12 万行/37 场景）禁入。

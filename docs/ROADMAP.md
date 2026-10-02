# CodeRisk Cloud × Arcanum — Roadmap（里程碑制）

> 原则：本文只写**已达成**与**已立项**，数字与 `docs/EVAL-LEDGER.md` 对账；不写愿景式空头支票。
> 缺陷与优化逐条追踪见项目登记册（WORK_LOG 缺陷与优化登记册 v1，2026-10-01）。

## ✅ v1.0 — 当前态（2026-10-02）

- [x] **PITAX 确定性规则 9 条**（编号与官方 taxonomy v1.6.1 对齐）：PIT-E-23/E-54/T-46/T-51/N-06/E-07/E-14/E-36/E-57；
      扫描面覆盖 AI 根上下文文件（`.mdc`/`.cursorrules` 已入白名单，2026-10-02 修复登记册 #15）
- [x] **确定性测试套件 257 collected / verify.sh 5/5**（正样本检出 + 负样本零误报 + 映射验证 + SARIF + 输出护栏 + 单一数据源防漂移）
- [x] **六节点 Agent 流水线**（Scout→…→Arbiter，strands 编排）：MI300X/gfx942 本地四服务 + 云端五端点 named-routes 双部署
- [x] **Laya 验证预算排序门（gate）**：六代微调 ranker（r0…r6，hard-exam v2 环路 20→21→23→**24/24**，AP=1.0、FN=0 全程保持）；
      gate v1.1 三臂链实跑（v23 ACCEPT：laya 臂与基线逐位一致=只重排证明）；gate v1.2 钉假设集代码落地（`--hypotheses-from`）；
      挂载旋钮 `ARCA_GATE_BACKEND`（缺省 laya）/`ARCA_GATE_MODEL`
- [x] **真仓挂载预演**：variant-25 处女仓 laya-r6 orderer-only 首秀 PASS（CONFIRMED 5/5、fallback=False、907.5s）
- [x] **M8 外部真值协议 v0 + 工具链**：`docs/M8-CTF-TRUTH.md`（NYU CTF Bench 首选/cybench 副源，license 实查）+
      `eval/m8_k1_score.py`（真值判分）+ `eval/m8_select_web.py`（web 类选题器）
- [x] **规则矿管道（C3）**：发现→采集→扫描→分诊→登记全链走通；三仓 1047 个 AI 配置文件基率标定；
      候选规则登记表（五候选+⑦，双门槛纪律：跨 ≥2 仓 ∧ FP=0）

## 🔜 v1.1 — 外部真值与 gate 转正（登记册 P0 项）

- [ ] **K1-min 首张真值对照表**：NYU_CTF_Bench clone → 20 题 web 类人工终选 → e2e 批 → `m8_k1_score`（登记册 #1）
- [ ] **gate v1.2 三臂重验收**：`--hypotheses-from` 钉假设集复验 v25/v27，翻 v27 污染 REJECT（登记册 #2）
- [ ] **laya checkpoint 多副本回传**（登记册 #3）+ **CI Actions**（登记册 #4）
- [ ] **R7 校准轮**：ECE 0.043→0.1016 漂移治理（登记册 #6）

## 🔜 v1.2 — 规模化与经济性

- [ ] **真实 OSS 仓 FP 率标定**：3-5 个真实仓库全链 + 人工核 FP（登记册 #5）
- [ ] **gate v2 预算帽姿态**：从"只重排"到"省验证预算"，前置 = #2 过 + R7 校准过（登记册 #8）
- [ ] **REFUTED 裁决噪声治理**：同仓 N 次重跑统计翻转率 → Scout temp0 开关或缓存复用（登记册 #7）
- [ ] **生产运行统计**：node_errors 率/时长分布/保护触发率（登记册 #12）

## 🔜 远期

- [ ] **172 节点全量规则**（Intents 27 / Techniques 70 / Evasions 63 / Inputs 12）+ 供应链注入规则重设计 + JS 时间炸弹语义检测（PIT-T-50）
- [ ] **可移植性复验**：非 gfx942 CUDA 环境部署验证（登记册 #11）
- [ ] **语义级注入检测**（LLM 二次判断"隐藏指令是否恶意"）+ OWASP LLM Top 10 / MITRE ATLAS 全量映射
- [ ] **自动化 AI 红队基准**：AIPWN.me / Bot-Tricks 攻击场景持续回归

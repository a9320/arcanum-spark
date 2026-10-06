# CodeRisk Cloud × Arcanum — Roadmap（里程碑制）

> 原则：本文只写**已达成**与**已立项**，数字与 `docs/EVAL-LEDGER.md` 对账；不写愿景式空头支票。
> 缺陷与优化逐条追踪见项目登记册（WORK_LOG 缺陷与优化登记册 v1，2026-10-01）。

## ✅ v1.0 — 当前态（2026-10-06 更新）

- [x] **PITAX 确定性规则 9 条**（编号与官方 taxonomy v1.6.1 对齐）：PIT-E-23/E-54/T-46/T-51/N-06/E-07/E-14/E-36/E-57；
      扫描面覆盖 AI 根上下文文件（`.mdc`/`.cursorrules` 已入白名单，2026-10-02 修复登记册 #15）
- [x] **确定性测试套件 289 collected / verify.sh 5/5**（正样本检出 + 负样本零误报 + 映射验证 + SARIF + 输出护栏 + 单一数据源防漂移；257→289 随 hardneg 批次增长）
- [x] **六节点 Agent 流水线**（Scout→…→Arbiter，strands 编排）：MI300X/gfx942 本地四服务 + 云端五端点 named-routes 双部署；
      混合臂 env 覆盖实证（`ARCA_DEPLOYMENT=local` + `ARCA_<STAGE>_{MODEL,BASE_URL,API_KEY}` 零代码换端）+
      `ARCA_SCOUT_MAX_TOKENS` 抬帽新知（6000 帽撞思考型云模型=MaxTokensReached 空卷）
- [x] **Laya 验证预算排序门（gate）**：八代微调 ranker（r0…r8，hard-exam v2 环路 20→21→23→**24/24**，AP=1.0、FN=0 全程保持）；
      gate v1.1 三臂链实跑（v23 ACCEPT：laya 臂与基线逐位一致=只重排证明）；gate v1.2 钉假设集代码落地（`--hypotheses-from`）；
      挂载旋钮 `ARCA_GATE_BACKEND`（缺省 laya）/`ARCA_GATE_MODEL`
- [x] **真仓挂载预演**：variant-25 处女仓 laya-r6 orderer-only 首秀 PASS（CONFIRMED 5/5、fallback=False、907.5s）
- [x] **M8 外部真值协议 v0→v0.2**：`docs/M8-CTF-TRUTH.md`（NYU CTF Bench 首选/cybench 副源，license 实查）+
      `eval/m8_k1_score.py`（真值判分）+ `eval/m8_select_web.py`（web 类选题器）+ 语义等价类 v0.2（新增凭证泄露族）
- [x] **K1-min 首张真值对照表（v1.1 #1，2026-10-05 跑卷/10-06 定版）**：NYU CTF 20 题 web 类全卷 →
      K2 两批五题 intended 源码复核定稿（串题/记忆偏差/JWT 零证据/logic-puzzle 射程外/弱密码学链）→
      两轮重判分收敛：**机制 8/9/3 + 语义 10/5/5/0（总账 20 首次自洽，零模型 token 收回 3+3 TP）**；
      方法学=docs/K2-INTENDED-REVIEW.md；判分件=reports/m8-k1/{k1_score_k2,k1_score_v02,hybrid_score_k2}.json
- [x] **gate v1.2 三臂重验收（v1.1 #2，2026-10-03）**：gate12v3 双 ACCEPT 翻 v27 污染 REJECT（登记册 #2 销号）
- [x] **laya checkpoint 多副本回传（v1.1 #3，2026-10-03）**：三资产 Release 201（登记册 #3 销号）
- [x] **R7 校准轮（v1.1 #6，2026-10-03）**：r7 留任 23/24、ECE 0.1016→**0.0417**（timing-r7 @ebc529f）；
      R8 联合锚定未破 5B 跷跷板（AP 1.0→0.9484）r8 留谱系不晋级；R9 近距克隆批缓行（BOUND-5B=B 侧 FP 方向，gate v1 只重排无害）
- [x] **混合臂盲区验证实验（2026-10-06）**：双题 0/2 判分翻正——rt-chat 召回 3 倍（4→12 假设）且 H5 命中官方 XSS 链交付原语
      （攻击面视野层=云 Scout 可修复）但 XSS 族假设零产出（sink 推理层=模型级短板）；
      混合臂定位=发现力增强器（非判分翻正器）
- [x] **规则矿管道（C3）**：发现→采集→扫描→分诊→登记全链走通；三仓 1047 个 AI 配置文件基率标定；
      候选规则登记表（五候选+⑦，双门槛纪律：跨 ≥2 仓 ∧ FP=0）

- [x] **CI Actions（v1.1 #4，2026-10-02 落地）**：确定性 CI 全量回归（`scripts/test_count.py` 锚 + verify.sh 5/5，零 LLM API 调用；
      引擎集成测试需 Redis 故 CI 沿用 verify.sh 单一入口防口径漂移）；**26 runs 全绿（2026-10-06 GitHub API 实拍，今日 5/5 push 全 success）**；
      README badge 随 D1 双语改造补挂——**v1.1 全项达成收官（2026-10-06）**

## 🔜 v1.2 — 规模化与经济性（gate v2 前置 #2/#6 已满足→解锁）

- [ ] **真实 OSS 仓 FP 率标定**：3-5 个真实仓库全链 + 人工核 FP（登记册 #5）；
      与 IC27 用户验证证据（评分 30%）+ 推广 Demo 素材三线收敛，建议为下一 DSW 主任务
- [ ] **gate v2 预算帽姿态**：从"只重排"到"省验证预算"（前置 #2 ✓ + R7 校准 ✓ 已满足）
- [ ] **REFUTED 裁决噪声治理**：同仓 N 次重跑统计翻转率 → Scout temp0 开关或缓存复用（登记册 #7）
- [ ] **生产运行统计**：node_errors 率/时长分布/保护触发率（登记册 #12）

## 🔜 远期

- [ ] **172 节点全量规则**（Intents 27 / Techniques 70 / Evasions 63 / Inputs 12）+ 供应链注入规则重设计 + JS 时间炸弹语义检测（PIT-T-50）
- [ ] **可移植性复验**：非 gfx942 CUDA 环境部署验证（登记册 #11）
- [ ] **语义级注入检测**（LLM 二次判断"隐藏指令是否恶意"）+ OWASP LLM Top 10 / MITRE ATLAS 全量映射
- [ ] **自动化 AI 红队基准**：AIPWN.me / Bot-Tricks 攻击场景持续回归

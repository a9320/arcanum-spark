# CodeRisk Cloud × Arcanum — Roadmap

> 分层说明：**参赛核心**（9/19 前交付）之外的演进方向写在这里展示长远 vision，不代表现在全做。

## ✅ 已完成（参赛核心基础，本地已验证）

- [x] **9 条 PITAX 规则（编号与官方 taxonomy v1.6.1 对齐）**：PIT-E-23/E-54/T-46/T-51/N-06/E-07/E-14/E-36/E-57
- [x] **零依赖 CLI**：一条命令（`python -m app.pitax.cli <目录>`）演示检出，支持 JSON/SARIF（含 PITAX 元数据）
- [x] **演示仓库生成器**：`python demo/generate_demo_repo.py` 一键生成"故意植入 6 类 AI 漏洞"的仓库
- [x] **测试套件**：36 用例全绿（正样本检出 + 负样本零误报 + CWE/ATLAS/CVE 映射验证 + SARIF 扩展 + 输出护栏）
- [x] **ATLAS/CWE 映射**：AML.T0051.001 = Indirect LLM Prompt Injection（官方）；CWE-77 来自 NVD 对 CVE-2025-53773 的分类
- [x] **Output Guardrail**：系统提示金库 + 报告输出脱敏（防止 Agent 泄露系统提示）
- [x] **Agent 0 流水线集成**：InputSanitizer → Agent 1-4 → 报告生成（含 SARIF 委托 + 护栏）
- [x] **SARIF 2.1.0 扩展**：tool.driver.rules[]（PITAX 规则元数据） + results[].properties.pitax（证据/解码载荷）

## 🔜 第一阶段（参赛后 1-2 周）

- [ ] **172 节点全量规则**：Intents 27 / Techniques 70 / Evasions 63 / Inputs 12
- [ ] **供应链提示注入规则重设计**（当前版会误报，暂不启用）
- [ ] **JS 时间炸弹语义检测**（PIT-T-50）
- [ ] **配置化启停**：`config.py` 加 `PITAX_ENABLED_RULES`，规则可动态启用

## 🔜 第二阶段（1-2 月）

- [ ] **全量 Agent 加固**：Agent 间 HMAC 签名、网络微分段、不可变容器
- [ ] **自动化 AI 红队测试**：CI/CD 集成，用 Bot-Tricks 8 个真实攻击场景做持续基准
- [ ] **AIPWN.me / Bot-Tricks 作为测试基准**：验证工具能否检测真实提示注入/走私攻击

## 🔜 第三阶段（长期）

- [ ] **漏洞赏金计划**（PITAX 漏洞赏金）
- [ ] **语义级注入检测**（需 LLM 判断，非正则）——二次判断"隐藏指令是否恶意"
- [ ] **与 OWASP LLM Top 10 / MITRE ATLAS 全量映射**

## 分层原则

- **参赛核心** = 9/19 前能交付、能演示、能得分的东西
- **Roadmap** = 写文档展示长远 vision，不实际做（避免过度工程）
- 红色警戒：网络微分段/不可变容器/HMAC 是商业级加固，对参赛 Demo 是过度设计，只写进这里
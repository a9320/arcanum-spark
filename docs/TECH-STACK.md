# CodeRisk Arcanum — 技术栈文档

> 整理日期：2026-09-06
> 项目：CodeRisk Arcanum（AI 杭州·码动未来 竞赛项目，AI+超级智能体赛道）
> 架构：6 节点 Agent Graph（模型提假设 + 工具证实/证伪）
> 状态：阶段 A（无卡）全部完成，本地端到端验证通过；阶段 B（Bedrock）等 AWS Visa 卡

---

## 一、整体架构（6 节点 Graph）

```
输入（Git 仓库 / ZIP / 本地文件）
        │
        ▼
┌──────────────────────────────────────────────┐
│ Agent 0 · PITAX 规则层（无 LLM，确定性）      │
│ 9 条 AI 漏洞规则：不可见字符/提示注入/指令覆盖 │
│ /文档投毒/配置后门/编码载荷                   │
│ 输出：ai_findings（agent0 基线事实）          │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ 侦察 Agent · 语义增量提假设（GLM-5.3）        │
│ 工具：pitax_scan（绑定无参）+ agent0 基线注入 │
│ 输出：HypothesisSet（VulnHypothesis + 覆盖说明）│
└──────────────────────────────────────────────┘
        │  假设（基线外增量，带 H1..Hn 编号）
        ▼
┌──────────────────────────────────────────────┐
│ 验证 Agent · 逐假设拆分裁决（DeepSeek-V4-Flash）│
│ 工具：pitax_scan + static_scan + taint_flow  │
│       + dep_scan（绑定无参，结果按文件预跑内嵌）│
│ 输出：VerificationSet（CONFIRMED/REFUTED/     │
│       UNCERTAIN + 工具证据，按 id 与假设对齐） │
└──────────────────────────────────────────────┘
        │  CONFIRMED 条目
        ▼
┌──────────────────────────────────────────────┐
│ 深挖 Agent · 逐条攻击链推演（DeepSeek-V4-Flash）│
│ 输出：AttackChain（前置条件/横向移动/影响/修复）│
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ 裁判官 Agent · 多源合议（GLM-5.3，异构第二票） │
│ 无工具（物理隔离防越权）                      │
│ 输出：FinalReport（findings + conclusion）    │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ 报告 Agent · 渲染（无 LLM，纯模板）           │
│ 输出：JSON / SARIF 2.1.0 / Markdown           │
│ 生成 ≠ 发布（需人类授权）                    │
└──────────────────────────────────────────────┘
```

**核心设计理念（蓝图 §5）：**
- **权威计算确定性**：风险分/汇总值由确定性代码算（`compute_risk_score`），LLM 不碰数值
- **证据可追溯**：每条结论绑定工具实际返回的证据原文（grounded or absent）
- **多源交叉验证**：单源可伪造，多独立来源一致才可信
- **物理隔离防越权**：裁判官只拿汇总证据，不碰原始代码
- **可验证性**：全链路支持 dry-run 离线重演，决策引擎是输入纯函数

---

## 二、技术栈明细

### 2.1 核心框架
| 层 | 技术 | 说明 |
|----|------|------|
| 编排框架 | **Strands** (1.54.0) | Agent 框架：Agent/tool/Agent 结构化输出 |
| 数据模型 | **Pydantic v2** (2.9.0) | 结构化输出契约（BaseModel + Literal 枚举约束） |
| 异步 | **asyncio** | 全流水线异步编排 |

### 2.2 模型层
| 阶段 | 模型 | 说明 |
|------|------|------|
| 当前（无卡） | **AMD DeepSeek-V4-Flash** | 免费，工具调用闭环已验证 |
| 备选 | Cloudflare GPT-OSS-120b | 仅单轮可用（Strands 多轮兼容坑） |
| 卡批后 | **Claude Haiku/Sonnet**（Bedrock） | 复杂推演/合议更稳 |

### 2.3 工具层（Strands @tool）
| 工具 | 职责 | 确定性 |
|------|------|--------|
| `pitax_scan` | 9 条 PITAX AI 漏洞规则（不可见字符/提示注入/文档投毒） | ✅ 确定性 |
| `static_scan` | 静态启发式（命令注入/SQLi/路径穿越/硬编码密钥/不安全哈希） | ✅ 确定性 |
| `taint_flow` | 污点追踪（source→sink 数据流） | ✅ 确定性 |
| `dep_scan` | 依赖清单 OSV/内置库漏洞比对 | ✅ 确定性 |

### 2.4 检测引擎（迁移自 app/pitax）
- `pitax/rules.py`（9 条规则）+ `detectors.py` + `sanitizer.py` + `sarif.py`
- 纯标准库零依赖，确定性规则层

### 2.5 结构化输出契约（models/schemas.py）
- `VulnHypothesis` / `HypothesisSet`（侦察输出）
- `VerificationResult` / `VerificationSet`（验证输出）
- `AttackChain`（深挖输出）
- `FinalReport` / `FinalReportFinding`（裁判合议输出）
- `AgentHandoff`（Agent 间交接契约）

### 2.6 CLI 入口（codeark/cli.py）
```
python -m codeark.cli <repo_dir> [--dry] [--out OUT] [--formats json,sarif,markdown]
```
- 读取仓库 → 6 节点流水线 → 落盘报告 + summary.json

### 2.7 部署（阶段 B，等卡后）
- **AWS Lambda + Bedrock AgentCore**（Serverless，蓝图 §十一）
- ModelScope 创空间（已部署：https://www.modelscope.cn/studios/Weike22/code-risk-arcanum）
- Docker / Docker Compose（CPU + GPU 模式）

---

## 三、测试与验证

### 3.1 测试文件（codeark/tests/）
- `test_pitax_scan.py` — PITAX 扫描逻辑
- `test_dep_scan.py` — 依赖扫描逻辑（6 项）
- `test_scout_loop.py` / `test_scout_loop_v2.py` — 侦察闭环
- `test_model_connect.py` — 模型连通

### 3.2 端到端验收（真实 DeepSeek，本地 demo 仓库）
**已验证通过：**
- 6 节点完整流水线跑通，无崩溃
- 侦察产出 5 条高质量假设（含模型自发现的命令注入隐患）
- 验证 4 CONFIRMED + 1 REFUTED（判断极佳，全程工具证据背书、无幻觉）
- 深挖产出 4 条完整攻击链（前置条件/横向移动/影响/修复）
- 裁判合议 + 报告三格式（JSON/SARIF/Markdown）+ 风险分落盘

**技术关键点：**
- 每个 LLM 节点强制结构化输出 + 文本兜底解析（模型输出成文本时的回退）
- 空/None 防御贯穿全链路（任一节点无料也不崩）

---

## 四、目录结构

```
codeark/
├── agents/          # 6 个 Agent（agent0/scout/verify/deepen/arbiter/report）
├── graph/           # pipeline.py（6 节点编排器 + 权威算分）
├── models/          # schemas.py（结构化输出契约）
├── pitax/           # 9 条 PITAX 规则引擎（迁移自 app/pitax）
├── tools/           # 4 个 Strands 工具
├── tests/           # 测试
└── cli.py           # 命令行入口
```

---

## 五、对比蓝图

| 蓝图要求（§四/§五） | 实现状态 |
|---------------------|----------|
| Agent 0 规则层（无 LLM） | ✅ agent0_pitax.py |
| 侦察 Agent（合并 0/1/1b/1c） | ✅ scout_agent.py + HypothesisSet |
| 验证 Agent（工具证实/证伪） | ✅ verify_agent.py + VerificationSet |
| 深挖 Agent（攻击链） | ✅ deepen_agent.py + AttackChain |
| 裁判官（多源合议防越权） | ✅ arbiter_agent.py + FinalReport |
| 报告 Agent（生成≠发布） | ✅ report_agent.py + 三格式 |
| 权威计算确定性 | ✅ compute_risk_score |
| 证据可追溯 / 多源验证 / 防越权 | ✅ 全链路落地 |
| 可验证性（离线重演） | ✅ dry-run 模式 |

**待办（阶段 B）：**
- [ ] Bedrock 集成（等 AWS Visa 卡）
- [ ] Strands 切 Claude（BedrockModel）
- [ ] AWS 服务（Security Hub / Inspector / Knowledge Bases）
- [ ] Lambda + AgentCore 部署
- [ ] 记忆系统迁移 DynamoDB
- [ ] 演示视频 + PPT（9/13-9/15）
- [ ] 定稿 + 提交（9/16-9/18）
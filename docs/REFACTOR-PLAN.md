# CodeRisk Arcanum — AWS 参赛重构总蓝图（最终整合版）

> 文档状态：最终整合版（2026-09-04 13:13）
> 整合来源：① 获奖项目方法论（5个项目深挖）② Kimi 方案 ③ GLM 方案 ④ 照片文字（Agent协作模式）⑤ Weike 的想法（合并 Agent A）
> 目标赛事：AWS "Agents for Humans" Hackathon（2026-09-14 23:59 PDT 截止）
> 关联文档：docs/WINNER-ANALYSIS.md（获奖项目深度分析）

---

## 〇、一句话蓝图

> **把 CodeRisk 从"本地单机规则流水线"升级为"云原生 Agent 编排平台"：用 Strands SDK 重构 4-Agent 流水线运行在 AWS Bedrock 上，模型负责提出漏洞假设（发现规则库外的新型威胁），工具与数据库负责证实/证伪（杜绝幻觉），人类保留不可逆操作的最终授权（责任边界）。**

**核心判断（三方 AI + 获奖项目 100% 印证）：真正的 AI Agent 安全靠的是「工具权限隔离 + 多源验证 + 诚实可追溯 + 权威确定性分层」这些可测试的工程机制，而不是 prompt 约束。**

---

## 一、架构翻转（Kimi 核心建议）

### 旧架构（规则优先，天花板是规则库）
```
代码 → Agent1 规则扫描 → 全部 findings → Agent2 LLM 总结 → Agent3 验证 → Agent4 报告
问题：LLM 只能看到规则已抓到的东西；规则误报也要 LLM 花 token 解释
```

### 新架构（模型优先，工具验证）⭐
```
代码 → 侦察Agent（模型自主探索，提出漏洞假设）
    → 每个假设 = {位置, 类型, 证据, 置信度, 建议验证方法}
    → 验证Agent（用工具逐条证实/证伪）
    → confirmed / rejected / uncertain
    → 深挖Agent（对 confirmed 做攻击路径推演）
    → 报告Agent（只输出有工具证据支撑的结论）
```

**防幻觉红线（答辩最能打的点）：**
> **假设可以天马行空，结论必须有工具背书。LLM 猜出的每个漏洞，必须附上至少一条工具验证证据（Semgrep 命中、污点路径、CVE 记录、依赖版本比对）才能进最终报告。**

---

## 二、Agent 协作模式选型（照片文字核心贡献）

**结论：Agents-as-Tools + Graph 混合，不用 Swarm。**

| 模式 | 适用场景 | 本项目判断 |
|------|---------|-----------|
| **层级委派 Agents-as-Tools** | 有明确管理者 | ✅ 裁判官调用验证器、验证器调用侦察工具——主流程核心 |
| **自主移交 Swarm** | 无固定领导 | ⚠️ 可选用于"攻击假设生成"阶段的头脑风暴，非主线 |
| **确定性工作流 Graph** | 流程固定 | ✅ 主流程用 Graph 定义固定步骤（侦察→假设→验证→裁判） |
| **Bedrock 托管协作** | 想开箱即用 | ⚠️ 需 AgentCore 落地后再评估，暂作备选 |
| **权限/身份硬限制（IAM）** | 需底层隔离 | ✅ 长期目标：IAM 角色 + 独立 MCP 运行时物理隔绝越权 |

> ⚠️ **重要确认：Amazon Bedrock Agents 已进入维护模式，新客户用 Bedrock AgentCore（更底层运行时）——我们选 AgentCore 完全正确。**

---

## 三、5 层职责约束体系（GLM 核心建议）

> **提示词定义"你是谁"，架构定义"你能做什么"，上下文定义"你知道什么"，工具定义"你能做什么"，契约定义"你输出什么"。高效多Agent系统是这五层叠加，绝非仅靠提示词。**

| 层 | 内容 | CodeRisk 应用 |
|----|------|--------------|
| **第1层 提示词工程** | 人设与规则 | 每个 Agent 的角色定义、行为边界、输出要求 |
| **第2层 结构化协作** | 谁向谁交接 | Agents-as-Tools（裁判官→验证器→侦察工具） |
| **第3层 上下文工程** | 传递什么信息 | 侦察官输出攻击面摘要；验证器输入单个假设对象；裁判官输入结构化结论列表 |
| **第4层 工具与权限** | 能做什么（最硬约束） | 工具白名单 + 权限隔离（给什么工具决定能做什么） |
| **第5层 结构化契约** | 输出什么格式 | Pydantic Schema 强制输出格式，枚举约束杜绝越界 |

**GLM 补的关键洞察：单纯靠提示词的三个致命缺陷**
1. 职责漂移：对话变长，Agent 忘记角色
2. 信息丢失：Agent A 的关键发现没传给 B
3. 无限循环：Agent 互相"让球"谁也不执行

---

## 四、Agent 最终架构（融合 Weike + 三方 AI）

### 总览图（5 Agent 结构 → 6 节点 Graph）

```
┌──────────────────────────────────────────────────────────────┐
│  输入：Git 仓库 / ZIP 上传 / 代码片段                          │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 0：PITAX 前置扫描（保留，规则层）                       │
│  =========================================================== │
│  9 条确定性 AI 漏洞规则（E-23/E-54/T-46/T-51/N-06/E-07/E-14/E-36/E-57）│
│  输出：AI 新漏洞 findings（单独进报告 ai_findings 区块）        │
│  模型：无 LLM（纯规则）                                       │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  侦察 Agent（合并 Agent 1/1b/1c = 你想要的 Agent A）           │
│  =========================================================== │
│  职责：像攻击者一样思考，阅读代码结构，提出漏洞假设             │
│  工具：run_semgrep / trace_taint / check_dependency_vuln /    │
│        attack_pattern_lookup / file_read / list_files / grep  │
│  输出：HypothesisSet（VulnHypothesis 列表 + coverage_notes）  │
│  模型：Claude Haiku（便宜，规则分发+初筛足够）                │
│  ★ 合并 0/1/1b/1c 的价值：少一次数据传递、可并行、输出统一      │
│  ★ 模型自己也检查：发现规则库外的新模式（标 low 置信走 uncertain）│
└──────────────────────────────────────────────────────────────┘
        │  ↓ 每个假设 = {位置,类型,证据,置信度,建议验证方法}
        ▼
┌──────────────────────────────────────────────────────────────┐
│  验证 Agent（原 Agent 3，保留独立）                           │
│  =========================================================== │
│  职责：对每个假设用工具证实/证伪                              │
│  工具：trace_taint / check_dependency_vuln / attack_pattern_lookup / file_read │
│  输出：Verdict（confirmed/rejected/uncertain + 证据原文）    │
│  模型：Claude Sonnet（强推理，判断漏洞真假）                  │
│  ★ 铁律：confirmed 必须附工具证据原文；uncertain 降级人工复核   │
└──────────────────────────────────────────────────────────────┘
        │  ↓ confirmed / rejected / uncertain
        ▼
┌──────────────────────────────────────────────────────────────┐
│  深挖 Agent（新增，模型能力扩展的核心落点）                   │
│  =========================================================== │
│  职责：对 confirmed 漏洞推演完整攻击链（前置条件/横向移动/影响）│
│  输出：AttackChain（威胁剧本，报告从清单升级为剧本）          │
│  模型：Claude Sonnet                                         │
│  ★ PITAX 无缝衔接：推演"攻击者通过 .cursor/rules 劫持 AI 助手→RCE" │
└──────────────────────────────────────────────────────────────┘
        │  ↓
        ▼
┌──────────────────────────────────────────────────────────────┐
│  裁判官 Agent（新增，多源合议）                              │
│  =========================================================== │
│  职责：汇总各验证器意见，做最终裁决                           │
│  工具：只给汇总工具，不直接分析代码（物理隔离越权）            │
│  输出：FinalReport Schema                                    │
│  模型：Claude Sonnet                                         │
└──────────────────────────────────────────────────────────────┘
        │  ↓
        ▼
┌──────────────────────────────────────────────────────────────┐
│  报告 Agent（原 Agent 4，基本保留）                          │
│  =========================================================== │
│  输出：JSON / SARIF 2.1.0 / Markdown / PDF（Nutrient）        │
│  模型：无 LLM（纯模板逻辑）                                   │
│  ★ 报告"生成"与"发布/发送"分离，发布需人类授权（Draft≠Send） │
└──────────────────────────────────────────────────────────────┘
```

### Agent 映射总表

| 新架构节点 | 原架构 | 核心改动 | 模型 | 职责约束重点 |
|-----------|--------|----------|------|-------------|
| Agent 0 | Agent 0 | 保留（规则层） | 无 | 确定性规则，永不抛异常 |
| 侦察 Agent | Agent 1+1b+1c | **合并** + 模型主动检查 | Claude Haiku | 工具白名单（只读+分析） |
| 验证 Agent | Agent 3 | 独立 + 假设逐条验证 | Claude Sonnet | 工具白名单（只给验证工具） |
| 深挖 Agent | 新增 | 攻击链推演 | Claude Sonnet | 结构契约（AttackChain） |
| 裁判官 | 新增 | 多源合议 + 防越权 | Claude Sonnet | 只给汇总工具 |
| 报告 Agent | Agent 4 | 保留 | 无 | 生成≠发布，人类授权 |

**你（Weike）最初想法的落点：**
> 你提的"合并 Agent 0/1/1b/1c 为一个 Agent A，且模型自己也做初步检测"→ 完全实现为「侦察 Agent」：它既跑规则工具（0/1/1b/1c 封装的 @tool），又用模型自己读代码找规则库外的新模式。**你的想法和 Kimi/GLM 的"侦察-验证闭环"天然一致，无需纠结 Agent 数量。**

---

## 五、关键工程机制（获奖项目方法论落地）

### 5.1 工具分级 + 不可逆操作锁定（AegisFlow agent-tools.ts）
```python
# 每个文档/分析操作注册风险等级
@tool
def publish_report(report_id: str) -> str:
    """发布安全报告（不可逆操作，仅限人类授权）"""
    # 内部检查：必须是 HUMAN 触发的签名
    ...
```
- 不可逆操作（报告发布/删除记录/发送通知）→ 仅限 HUMAN，只能从唯一状态触发
- 测试枚举 actor × state 矩阵，断言无任何非人类组合能触达

### 5.2 权威计算确定性（DealForge）
```python
# LLM 只给理由和置信，不计算权威数值
# 严重级/风险评分/报告汇总值 由确定性代码计算
def compute_risk_score(findings: list) -> int:
    """由代码确定性计算，绝不让 LLM 算分"""
    ...
```

### 5.3 多源交叉验证（AegisFlow 4系统 / Signet 七重检查）
- 单一来源可伪造，多独立来源一致才可信
- 决策是"计算"出来的，不是"写死"的（规则读字段不读文件名）
- 权重调不动诚信门槛（integrity cap）

### 5.4 证据可追溯（Chancery grounded or absent）
- 每条 PITAX/验证结论强制绑定证据行 + 来源
- 未落地视为无权限（grounded or absent, not permissive）

### 5.5 证伪记录（Chancery CLAIMS.md）
- Agent 验证失败记录 DISPROVED，不默默忽略
- 诚实可追溯 = 信任的基础

### 5.6 可验证性（Signet/Chancery 纯函数决策）
- 决策引擎是输入纯函数（无模型/时钟/网络/状态），证据包可离线重演
- 大量自动化测试（35/817）

### 5.7 记忆系统前馈（GLM 方法5）
- 记忆系统从"过滤器"改为"主动注入约束"
- 历史误报模式注入假设生成器 prompt，避免重复犯错
- 正确模式优先考虑，提升命中率

---

## 六、上下文传递协议（Agent 间"合同"）

```python
class AgentHandoff(BaseModel):
    """Agent 间交接的标准格式"""
    from_agent: str
    to_agent: str
    context_summary: str       # 摘要，不是全文
    structured_data: dict      # 结构化数据
    instructions: str          # 给下一个 Agent 的具体指令
```

| 传递场景 | 传什么 | 不传什么 |
|---------|--------|---------|
| 侦察→假设 | 攻击面摘要（入口点/信任边界/敏感流） | 整个代码库 |
| 假设→验证 | 单个结构化假设对象 | 整个对话历史 |
| 验证→裁判 | 结构化验证结论列表 | 验证器原始输出 |

---

## 七、结构化输出契约（Pydantic Schema）

```python
class VulnHypothesis(BaseModel):
    title: str
    vuln_type: str  # SQL_INJECTION / COMMAND_INJECTION / PATH_TRAVERSAL ...
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    attack_path: str
    confidence: str  # high/medium/low
    suggested_verification: str  # 建议验证方式

class HypothesisSet(BaseModel):
    hypotheses: list[VulnHypothesis]
    coverage_notes: str  # 强迫模型汇报盲区，避免静默漏目录

class VerificationResult(BaseModel):
    verdict: Literal["CONFIRMED", "REFUTED", "UNCERTAIN"]  # 枚举
    confidence: float
    evidence: str
    verification_method: str  # 强制提供验证方法

class AttackChain(BaseModel):
    preconditions: list[str]
    lateral_moves: list[str]
    impact: str
    remediation: str
```

---

## 八、保留不动的部分（项目灵魂）

| 保留组件 | 理由 |
|---------|------|
| PITAX 9 条规则 | 确定性 AI 漏洞检测，项目差异化卖点 |
| Tree-sitter 静态规则库 | C/Python 精确模式匹配 |
| TaintAnalyzer | 数据流追踪 |
| dependency_scanner (OSV) | 已知漏洞版本比对 |
| report 生成（SARIF/MD/PDF） | 多格式输出 |
| prompt_guard.py | 防系统提示泄露护栏 |
| PITAX taxonomy v1.6.1 对齐 | 编号/映射是信誉资产 |

---

## 九、架构层面要改的

| 现状 | 目标 | 收益 |
|------|------|------|
| Celery + Redis 队列 | AgentCore Orchestrator | 去中间件、简化部署 |
| 自研 LLMClient | Strands Agent 标准调用 | 多模型/工具调用标准 |
| 自研 MemoryLayer | Strands ConversationMemory / DynamoDB | 会话记忆标准+分布式 |
| 本地 GGUF 推理 | Bedrock 云模型（Claude/Titan/Llama） | 免本地 GPU、效果提升 |
| 硬编码编排 | Strands Graph + Agents-as-Tools | 模型驱动 + 结构化 |
| 本地 HTTP + Celery | AWS Lambda + API Gateway | 云端扩缩容 |
| 自写输出脱敏 | Bedrock Guardrails | 托管、有审计记录 |

---

## 十、集成 AWS 安全生态（Kimi 建议，答辩加分项）

| Agent | 当前工具 | 新增 AWS 工具 | 提升 |
|-------|---------|--------------|------|
| Agent 1 | Semgrep/内置规则 | CodeGuru Security + Security Hub | AWS 官方检测 + 自动接收安全发现 |
| Agent 2 | 本地 LLM | Bedrock Knowledge Bases | RAG 检索增强，分析更深 |
| Agent 3 | 本地 CVE 库 | Security Hub + Inspector + SageMaker | 实时 CVE 查询 + 自定义验证模型 |
| Agent 4 | JSON/MD/Rich | QuickSight + S3 + SES | 交互式可视化报告 + 自动分发 |

**集成示例：**
```python
@tool
def query_security_hub(findings: list) -> dict:
    """查询 AWS Security Hub 验证和丰富安全发现"""
    securityhub = boto3.client('securityhub')
    response = securityhub.get_findings(...)
    return {"verified_findings": response['Findings']}

@tool
def invoke_sagemaker_verifier(code_snippet: str) -> dict:
    """调用 SageMaker 端点验证代码片段漏洞可利用性"""
    sagemaker_runtime = boto3.client('sagemaker-runtime')
    response = sagemaker_runtime.invoke_endpoint(...)
    return {"exploitability_score": response['Body'].read().decode()}
```

---

## 十一、部署方案（Kimi 建议）

### 首选：AWS Lambda + Bedrock AgentCore（Serverless）
```
开发者提交代码 → CodeCommit/CodeBuild → Lambda 触发分析 → Bedrock AgentCore（托管 Agent 运行时）→ Strands Agent 执行 4-Agent 流水线 → 结果存 DynamoDB+S3 → 通知集成（SNS/GitHub API）
```

| 部署方案 | 适用场景 | 演示亮点 | 复杂度 |
|---------|---------|---------|--------|
| **Lambda + AgentCore** | 首选，事件驱动、低成本 | Serverless 架构、自动扩展 | 初级 |
| ECS/Fargate | 持续运行、更多控制 | 容器化 + 集群管理 | 中级 |
| EKS | 已有 K8s | Kubernetes 管理 | 高级 |
| App Runner | 简单 Web 应用 | 全托管部署 | 初级 |

---

## 十二、演示与叙事优化（Kimi 核心贡献）

### 叙事转变
| 当前叙事 | 优化后叙事 |
|---------|-----------|
| "本地 AI 代码安全工具，AMD GPU 运行" | "云原生 AI 安全平台，AWS Bedrock 顶尖模型，无需上传源代码" |
| "项目在本地运行" | "无服务器部署，自动扩展，VPC 隔离 + Bedrock Guardrails 保数据安全" |
| "用了 4 个 Agent" | "基于 Strands SDK 的生产级 4-Agent 编排流水线，集成 AWS 安全服务，三重交叉验证" |

### 演示核心亮点（准备要点）
1. 实时演示：现场提交 GitHub 仓库，展示从分析到报告完整流程
2. 云原生特性：CloudWatch 监控仪表盘 + VPC 配置 + Bedrock Guardrails 配置
3. 集成能力：分析结果自动创建 GitHub Issue / 发送 Slack 通知
4. 记忆与学习：DynamoDB 记忆系统持续提升准确率
5. 成本效益：对比传统扫描工具（按次付费 vs 年度许可）
6. **Guardrails 拦截一次提示注入（现场 demo 最出彩）**
7. **OTEL 追踪展示 4-Agent 流水线每一步（答辩观感加分）**
8. **真实 GitHub PR 评论闭环**

---

## 十三、实施路线图（14 天冲刺计划）

### 阶段 A：无卡阶段（现在 → 卡批前）— 全部不依赖 AWS

| 天 | 任务 | 说明 |
|----|------|------|
| Day 1 | 搭目录骨架 | codeark 结构（agents/pitax/tools/models/cli/tests）|
| Day 1 | 迁移 PITAX 9 规则 | 原样搬入新结构，不丢编号 |
| Day 2 | 封装为 Strands @tool | pitax_scan / static_scan / taint_flow / dep_scan |
| Day 2 | 侦察 Agent 骨架 | 提示词 + 工具白名单 + HypothesisSet schema |
| Day 3 | 验证 Agent 骨架 | 提示词 + Verdict schema + 工具白名单 |
| Day 3 | 深挖 Agent + 裁判官骨架 | AttackChain + FinalReport schema |
| Day 4 | Graph 编排骨架 | 节点/边定义，先用免费模型跑通逻辑 |
| Day 4 | Agent 0 + 报告 Agent 对接 | 报告生成≠发布分离 |
| Day 5 | 本地测试跑通 | 用免费模型验证提示词/数据流/结构化输出 |
| Day 5 | 架构图 + 技术栈文档 | 参赛材料 |

### 阶段 B：Bedrock 阶段（卡批后）— 依赖 AWS

| 天 | 任务 | 说明 |
|----|------|------|
| Day 6-7 | Bedrock 集成 | 启用 Bedrock，申请模型访问，测试 Claude/Titan |
| Day 7-8 | Strands 切 Bedrock | BedrockModel 替换，Agent 2/3 跑通 |
| Day 9-10 | AWS 服务集成 | Security Hub / Inspector / Knowledge Bases / SageMaker |
| Day 11 | Lambda + AgentCore 部署 | ECR + Lambda + AgentCore 运行时 + API Gateway |
| Day 12 | 记忆系统迁移 DynamoDB | memory.json → DynamoDB |
| Day 13 | 前端 + 可视化 | QuickSight / Amplify |
| Day 14 | 演示视频 + PPT | 2-3 分钟视频 + 答辩 |

---

## 十四、待确认问题

1. ✅ **Agent 架构**：已确认（6 节点 Graph：Agent0 + 侦察 + 验证 + 深挖 + 裁判 + 报告）——三方 AI + Weike 想法统一
2. ✅ **协作模式**：已确认（Agents-as-Tools + Graph 混合）
3. ⏳ **AWS 账号/Visa 卡**：申请中，卡批后进 Bedrock 阶段
4. ⏳ **Bedrock 模型访问**：需卡批后申请（Claude 系列默认不开放）
5. ⏳ **是否集成 AWS 专有服务**：建议核心重构先做，AWS 服务集成等卡批后

---

## 十五、核心结论

**这份蓝图融合了：**
- 获奖项目 5 大工程机制（工具隔离/多源验证/权威分层/诚实追溯/可验证性）
- Kimi 的架构翻转（模型提假设 + 工具证实/证伪）
- GLM 的 5 层职责约束体系（提示词/架构/上下文/工具/契约）
- 照片文字的协作模式选型（Agents-as-Tools + Graph）
- 你（Weike）的 Agent 合并想法（0/1/1b/1c → 侦察 Agent）

**这份方案可直接指导：**
1. 无卡阶段的代码开发（目录骨架 + PITAX 工具封装 + 各 Agent 骨架）
2. 卡批后的 Bedrock 集成（模型切换 + AWS 服务 + Lambda 部署）
3. 参赛材料准备（架构图 + 演示叙事 + 14 天冲刺）

---

> 附：照片文字（建议.txt）核心观点摘录
> 相比把所有职责塞进提示词，利用框架提供的结构化模式是更高效、更可靠的做法。任务有明确主导者→Agents-as-Tools；需自主协作→Handoffs/Swarms；流程固定→Graph/Workflow；想开箱即用→Bedrock 托管协作；需底层隔离→IAM/AgentCore。

<!-- project: path:/mnt/d/desk-top/code-risk-arcanum -->
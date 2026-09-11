# CodeRisk Arcanum — Agent 模型选型策略

> 版本：2026-09-08  
> 状态：无卡阶段可用（DeepSeek-V4-Flash），卡批后无缝切换（Bedrock）

---

## 一、总览：6 节点 × 模型矩阵

| 节点 | 角色 | 当前默认模型 | 卡批后可选模型 | 工具依赖 | 是否有 LLM | 核心能力要求 |
|------|------|------------|------------|---------|-----------|------------|
| Agent 0 | PITAX 规则层 | **无 LLM** | — | pitax_scan（确定性规则） | ❌ | 零（纯代码） |
| Agent 1 | 侦察官 Scout | DeepSeek-V4-Flash | Claude Haiku | pitax_scan | ✅ | 工具调用 + 结构化输出 |
| Agent 2 | 验证官 Verify | DeepSeek-V4-Flash | Claude Haiku / Sonnet | pitax_scan + static_scan + taint_flow + dep_scan | ✅ | 多工具调度 + 逻辑推理 |
| Agent 3 | 深挖官 Deepen | DeepSeek-V4-Flash | Claude Sonnet | 无（上游证据传入） | ✅ | 复杂推理 + 攻击链构建 |
| Agent 4 | 裁判官 Arbiter | DeepSeek-V4-Flash | Claude Sonnet | 无（纯合议，物理隔离） | ✅ | 多源推理 + 冲突裁决 |
| Agent 5 | 报告官 Report | **无 LLM** | — | 纯模板渲染 | ❌ | 零（纯代码） |

> **关键结论**：Agent 0 和 Agent 5 不需要模型——它们是纯代码确定性层。只有 Agent 1-4 需要 LLM，且全部可换。

---

## 二、各 Agent 详细分析

### Agent 0：PITAX 规则层（无 LLM）

```
输入：仓库文件 → pitax_scan（9 条确定性规则） → 输出：findings 列表
```

- **为什么不需要模型**：这 9 条规则是正则/字符串匹配，不是"猜"——有零宽字符就是有，没有就是没有。LLM 反而可能引入幻觉。
- **定位**：流水线的"种子"——先跑出确定性基线，下游 Agent 在此基础上补充假设。
- **规则清单**：PIT-E-23（不可见字符）/ PIT-E-54（Trojan Source）/ PIT-T-46（配置文件注入）/ PIT-T-51（指令覆盖）/ PIT-N-06（文档投毒）/ PIT-E-07/14/36/57（编码规避×4）

### Agent 1：侦察官 Scout

```
输入：仓库文件 → [LLM + pitax_scan 工具] → HypothesisSet（假设列表）
```

**模型需要做什么：**
- 读取文件内容，理解上下文
- 调用 `pitax_scan` 工具执行检测
- 基于工具返回的 findings，**提出补充假设**（规则库外的新型威胁）
- 结构化输出 `HypothesisSet`（hypotheses + coverage_notes）

**为什么选 DeepSeek-V4-Flash（当前）：**
| 维度 | 评估 |
|------|------|
| 工具调用 | ✅ 已验证闭环（真调用工具，不模拟结果） |
| 结构化输出 | ✅ 输出格式稳定，Pydantic 校验通过 |
| 成本 | ✅ 免费（AMD Radeon Cloud） |
| 上下文 | ✅ 1M tokens，足够处理中等规模仓库 |
| 速度 | ⚠️ 复杂工具调用较慢（需 180s 超时） |

**为什么可以切 Claude Haiku（卡批后）：**
| 维度 | 评估 |
|------|------|
| 工具调用 | ✅ Bedrock 原生支持，Strands SDK 适配 |
| 速度 | ✅ 比 DeepSeek 快，响应更及时 |
| 成本 | ⚠️ 按 token 计费（但 Scout 每轮只调 1-2 次工具） |
| 优势 | ✅ 规则库外的假设质量更高（Haiku 擅长探索性推理） |

**选择 Haiku 而非 Sonnet 的原因：** Scout 的核心是"广度"——快速扫描大量文件提出假设，不需要深层推理。Haiku 速度快、成本低，适合这个定位。

### Agent 2：验证官 Verify

```
输入：HypothesisSet → [LLM + 4 个工具] → VerificationResult（每条：CONFIRMED/REFUTED/UNCERTAIN）
```

**模型需要做什么：**
- 接收 Scout 的假设列表
- **逐个假设调用工具验证**（pitax_scan / static_scan / taint_flow / dep_scan）
- 每条裁决必须附工具证据原文
- 区分三种结果：CONFIRMED（工具证实）/ REFUTED（工具未命中）/ UNCERTAIN（工具无明确结论→降级人工）

**为什么选 DeepSeek-V4-Flash（当前）：**
| 维度 | 评估 |
|------|------|
| 多工具调度 | ✅ 已验证可同时调用 4 种工具 |
| 逻辑推理 | ✅ 能正确区分 CONFIRMED vs UNCERTAIN |
| 成本 | ✅ 免费 |
| 稳定性 | ✅ 25 项测试全绿 |

**为什么卡批后可换 Haiku 或 Sonnet：**
| 模型 | 适用场景 | 选择理由 |
|------|---------|---------|
| **Claude Haiku** | 快速验证批量假设 | 速度快，适合假设多的场景 |
| **Claude Sonnet** | 复杂假设精准验证 | 推理更深，对 UNCERTAIN 判断更准 |

**选择建议：**
- 假设 < 20 条 → Haiku（快）
- 假设 > 20 条 或有高价值目标 → Sonnet（准）

### Agent 3：深挖官 Deepen

```
输入：CONFIRMED findings → [LLM，无工具] → AttackChain（攻击链推演）
```

**模型需要做什么：**
- 接收 Verify 的 CONFIRMED 条目
- **纯推理，无工具调用**（工具证据由上游传入）
- 从攻击者视角推演：前置条件 → 横向移动 → 最终影响 → 修复建议
- 必须锚定工具证据，不得编造

**为什么选 DeepSeek-V4-Flash（当前）：**
| 维度 | 评估 |
|------|------|
| 推理能力 | ✅ 能构建合理攻击链 |
| 事实锚定 | ✅ 输出包含具体文件/行号/代码片段 |
| 成本 | ✅ 免费 |

**为什么卡批后推荐 Claude Sonnet：**
| 维度 | DeepSeek-V4-Flash | Claude Sonnet |
|------|------------------|---------------|
| 推理深度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 攻击链完整性 | 一般（偶有跳跃） | 优秀（连贯性强） |
| 修复建议具体性 | 泛泛而谈 | 具体到行号/替换方案 |
| 成本 | 免费 | 按 token 计费 |

**选择 Sonnet 的原因：** Deepen 是整个流水线"最有创意"的节点——需要想象攻击者如何串联多个漏洞。Sonnet 的推理深度和连贯性明显优于 DeepSeek，能产出更可信的攻击链。

### Agent 4：裁判官 Arbiter

```
输入：HypothesisSet + VerificationResult + AttackChain → [LLM，无工具] → FinalReport
```

**模型需要做什么：**
- 接收三源数据（侦察假设 / 验证裁决 / 深挖攻击链）
- **多源合议**：哪些假设被证实？哪些冲突？
- 裁决原则：CONFIRMED + 攻击链完整 → 进报告；冲突 → 以验证为准
- 物理隔离设计：**裁判官不接触原始代码**，只能做汇总，防止越权

**为什么选 DeepSeek-V4-Flash（当前）：**
| 维度 | 评估 |
|------|------|
| 多源推理 | ✅ 能处理冲突场景 |
| 结构化输出 | ✅ FinalReport 格式稳定 |
| 成本 | ✅ 免费 |

**为什么卡批后推荐 Claude Sonnet：**
| 维度 | 评估 |
|------|------|
| 冲突裁决质量 | Sonnet 更强（能识别微妙矛盾） |
| 输出稳定性 | Sonnet 结构化输出更可靠 |
| 成本 | ⚠️ 略高，但 Arbiter 每轮只跑一次 |

**选择 Sonnet 的原因：** Arbiter 是"最后一道关口"——它的裁决直接决定报告内容。用更强的模型降低误判风险，值得多花一点 token。

### Agent 5：报告官 Report

```
输入：FinalReport → 纯模板渲染 → JSON / SARIF / Markdown
```

- **为什么不需要模型**：报告格式是确定的（SARIF 2.1.0 规范 / Markdown 模板），不需要"思考"。LLM 生成报告反而会引入不一致性。
- **生成 ≠ 发布**：报告只生成不发送，发布需人类授权（红线设计）。

---

## 三、模型切换机制（无卡 → 有卡）

### 当前架构：统一模型工厂

```python
# codeark/agents/scout_agent.py
def make_model(provider: str = "amd") -> OpenAIModel:
    if provider == "amd":
        return OpenAIModel(  # DeepSeek-V4-Flash
            model_id="DeepSeek-V4-Flash",
            client_args={"base_url": "...", "api_key": "..."}
        )
    if provider == "cloudflare":
        return OpenAIModel(  # GPT-OSS-120b
            ...
        )
    if provider == "bedrock":
        return BedrockModel(  # Claude（卡批后启用）
            model_id="anthropic.claude-3-haiku-20240307-v1:0",
            region="us-east-1"
        )
```

### 切换步骤（卡批后只需改一处）

```bash
# 1. 配置 AWS 凭据（一次性）
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=xxx

# 2. 运行代码时指定 provider
python -c "
from codeark.graph.pipeline import CodeRiskGraph
graph = CodeRiskGraph(model_provider='bedrock')  # ← 只改这一行
result = graph.run(files)
"
```

### 各 Agent 的 Bedrock 模型 ID

| Agent | 推荐 Bedrock 模型 | 说明 |
|-------|-----------------|------|
| Scout (1) | `anthropic.claude-3-haiku-20240307-v1:0` | 快速探索 |
| Verify (2) | `anthropic.claude-3-haiku-20240307-v1:0` 或 `sonnet` | 按场景选 |
| Deepen (3) | `anthropic.claude-3-sonnet-20240229-v1:0` | 深度推理 |
| Arbiter (4) | `anthropic.claude-3-sonnet-20240229-v1:0` | 最终裁决 |

> **注意**：Bedrock 模型 ID 可能随时间更新，提交前查 [AWS Bedrock Model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html) 确认最新值。

---

## 四、为什么不全部用最好的模型？

### 成本-效果权衡

| 节点 | 当前模型 | 卡批后模型 | 切换理由 |
|------|---------|-----------|---------|
| Agent 0 | 无 LLM | 无 LLM | 规则层不需要模型 |
| Agent 1 | DeepSeek | Haiku | 广度优先，不需要最强推理 |
| Agent 2 | DeepSeek | Haiku/Sonnet | 按假设数量动态选择 |
| Agent 3 | DeepSeek | **Sonnet** | 推理深度决定攻击链质量 |
| Agent 4 | DeepSeek | **Sonnet** | 裁决质量决定报告可信度 |
| Agent 5 | 无 LLM | 无 LLM | 模板渲染不需要模型 |

**核心原则**：
- **Agent 1/2**：工具调用密集，速度快更重要 → Haiku
- **Agent 3/4**：推理密集，质量更重要 → Sonnet
- **Agent 0/5**：确定性逻辑，不需要模型

### 如果只想用一个模型？

全部用 **Claude Sonnet** 也可以——质量最高，但成本也最高。对于参赛 Demo，这不是问题（演示几次而已）。

---

## 五、无卡现状 vs 卡批后差异

| 能力 | 无卡（DeepSeek） | 卡批后（Bedrock） |
|------|-----------------|------------------|
| Agent 0 PITAX 规则检测 | ✅ 完整可用 | ✅ 完整可用 |
| Agent 1 Scout 假设生成 | ✅ 已验证 | ✅ 更强（Haiku 更快） |
| Agent 2 Verify 多工具验证 | ✅ 已验证 | ✅ 更强（Sonnet 更准） |
| Agent 3 Deepen 攻击链推演 | ✅ 可用 | ✅ 显著提升（推理深度） |
| Agent 4 Arbiter 多源合议 | ✅ 可用 | ✅ 显著提升（裁决质量） |
| Agent 5 Report 模板渲染 | ✅ 完整可用 | ✅ 完整可用 |
| DynamoDB 记忆系统 | ✅ 本地模式可用 | ✅ 切换一行代码 |
| Lambda 部署 | ❌ 不可用 | ✅ 可用 |
| CloudWatch 监控面板 | ❌ 不可用 | ✅ 可用 |

> **关键结论**：无卡状态下，**核心检测能力完整可用**，只是 Agent 3/4 的推理质量有提升空间。比赛提交不受影响。

---

## 六、技术债务与待办

- [ ] 卡批后：把 `make_model("bedrock")` 接入四个 Agent（scout/verify/deepen/arbiter）
- [ ] 卡批后：DynamoDBBackend 从"预写"改为"实建"（填 region + table name）
- [ ] 卡批后：添加 CloudWatch 指标导出（可选，加分项）
- [ ] 长期：考虑为 Agent 3/4 添加 fallback 机制（Bedrock 超时 → 自动切 DeepSeek）

---

*文档由 lolo 根据 codeark/agents/*.py 源码整理*
*更新时间：2026-09-08*

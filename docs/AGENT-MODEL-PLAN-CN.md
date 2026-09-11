# CodeRisk Arcanum — Agent 模型选型方案（国产平替）

> 版本：2026-09-08 v2（基于 Kimi 建议更新）
> 核心原则：架构不变（Strands SDK + 6 节点流水线），模型层替换为国产最优

---

## 一、架构不动，只换模型

```
当前（DeepSeek 单模型）          目标（分层国产模型矩阵）
┌─────────┐                    ┌─────────┐
│ Agent 0  │  PITAX 规则层      │ Agent 0  │  不变（无 LLM）
│  规则层  │  ───────────────→  │  规则层  │
└────┬────┘                    └────┬────┘
     │ 确定性基线                    │ 确定性基线
     ▼                              ▼
┌─────────┐    HypothesisSet       ┌─────────┐
│ Scout   │ ────────────────────→ │ Scout   │  GLM-4-Flash（默认）
│  侦察   │   广度扫描 + 工具调用   │  侦察   │  + DeepSeek-V4-Flash fallback
└────┬────┘                        └────┬────┘
     │ 假设列表                          │ 假设列表
     ▼                                  ▼
┌─────────┐    VerificationResult      ┌─────────┐
│ Verify  │ ────────────────────────→ │ Verify  │  GLM-4（主判）
│  验证   │   CONFIRMED/REFUTED       │  验证   │  + DeepSeek-V4-Pro 召回副审
└────┬────┘                            └────┬────┘
     │ CONFIRMED                             │ CONFIRMED
     ▼                                       ▼
┌─────────┐    AttackChain                  ┌─────────┐
│ Deepen  │ ────────────────────────────→ │ Deepen  │  GLM-4（主力）
│  深挖   │   攻击链推演                    │  深挖   │  + Kimi K2.7 长程备选
└────┬────┘                                └────┬────┘
     │ AttackChain                              │ AttackChain
     ▼                                           ▼
┌─────────┐    FinalReport                     ┌─────────┐
│ Arbiter │ ────────────────────────────────→ │ Arbiter │  GLM-4（单模型）
│  裁判   │   多源合议 + 裁决                   │  裁判   │  → 正式版加 Kimi K2.7 第二票
└────┬────┘                                    └────┬────┘
     │ FinalReport                                    │ FinalReport
     ▼                                                  ▼
┌─────────┐    JSON/SARIF/MD                       ┌─────────┐
│ Report  │ ────────────────────────────────────→ │ Report  │  不变（无 LLM）
│  报告   │   模板渲染                              │  报告   │
└─────────┘                                        └─────────┘
```

---

## 二、推荐模型矩阵（Kimi 建议采纳版）

| Agent | 推荐模型 | 备选 | API Key 文件 |
|-------|---------|------|-------------|
| Agent 0 | 无 LLM | — | — |
| Agent 1 Scout | **GLM-4-Flash** | DeepSeek-V4-Flash | `/mnt/d/API Key/glm-4.7.txt` |
| Agent 2 Verify | **GLM-4** | DeepSeek-V4-Pro（召回副审） | `/mnt/d/API Key/glm-4.7.txt` |
| Agent 3 Deepen | **GLM-4** | Kimi K2.7（长程任务） | `/mnt/d/API Key/glm-4.7.txt` |
| Agent 4 Arbiter | **GLM-4** | Kimi K2.7（第二票） | `/mnt/d/API Key/glm-4.7.txt` |
| Agent 5 Report | 无 LLM | — | — |

### 已有 API Key 清单

| Provider | Key 文件 | 状态 |
|----------|---------|------|
| GLM (智谱) | `glm-4.7.txt` | ✅ 可用 |
| Kimi (Moonshot) | `my-kimi-key.txt` | ✅ 可用 |
| DeepSeek (LobeHub) | `LobeHub-DeepSeek API-key.txt` | ✅ 可用 |
| DeepSeek (官方) | `deepseek API key.txt` | ✅ 可用 |
| AMD Radeon Cloud | `Radeon Cloud.txt` | ✅ 可用（免费） |

---

## 三、为什么选 GLM-4 系列（而非全用 DeepSeek）

### Kimi 的核心判断

> "Agent 3/4 在'代码安全/漏洞审计'这个垂直面上，GLM/Kimi/Qwen 有局部反超证据"

**具体证据：**
- Semgrep 安全漏洞检测基准：GLM-5.2 裸提示词检测到 **39% IDOR**
  - 高于 Claude Code 的 32%
  - 高于 Kimi K2.7-Code 的 22%
  - 高于 DeepSeek V4 的 17%
- GLM-5.1 在 CyberGym 安全代码测试跑出 **68.7 高分**

**为什么 GLM 更适合你们：**
1. 官方文档明确定位：**强工具调用 + 长上下文 + 深度思考**
2. 与你们"代码供应链安全"场景高度同构
3. 结构化输出稳定性在国产模型中领先

### DeepSeek 的定位调整

| 角色 | 模型 | 说明 |
|------|------|------|
| Scout 主力 | GLM-4-Flash | 速度快、成本低 |
| Scout fallback | DeepSeek-V4-Flash | 备用通道 |
| Verify 召回副审 | DeepSeek-V4-Pro | **只负责补漏，不负责最终裁决** |
| Deepen 长程备选 | Kimi K2.7 | 多步骤跨文件攻击链 |
| Arbiter 第二票 | Kimi K2.7 / Qwen3.8-Max | 双模型陪审，压低误报 |

---

## 四、各 Agent 详细选型理由

### Agent 1 Scout（侦察官）→ GLM-4-Flash

**工作特点：**
- 读文件 + 调工具（pitax_scan）+ 结构化输出 HypothesisSet
- 任务明确：扫描、提取、假设生成
- 不需要深度推理，需要的是"快速广度覆盖"

**为什么用 GLM-4-Flash：**
1. **工具调用稳定**：GLM 官方文档明确 Function Calling 支持
2. **成本低**：Flash 系列价格仅为 Pro 的 1/10
3. **速度快**：适合广撒网式扫描

**为什么不选 DeepSeek-Flash 做主力：**
- DeepSeek-V4-Flash 工具调用稳定性已验证，但 GLM-4-Flash 在"代码安全"场景有评测优势
- 保留 DeepSeek-Flash 作为 fallback，确保双通道冗余

---

### Agent 2 Verify（验证官）→ GLM-4（主判）

**工作特点：**
- 接收假设列表 → **逐个调 4 种工具验证** → 给出 CONFIRMED/REFUTED/UNCERTAIN
- 多工具调度 + 逻辑判断
- 需要区分"工具没命中"和"工具能力不足"

**为什么用 GLM-4：**
1. **多工具调度**：Verify 需要同时调度 pitax_scan/static_scan/taint_flow/dep_scan
2. **逻辑推理**：区分 CONFIRMED vs UNCERTAIN 需要推理深度
3. **结构化输出**：VerificationSet 格式严格，GLM-4 输出一致性更好

**DeepSeek-V4-Pro 的角色：**
- 作为**召回副审**，补充高价值目标的漏洞发现
- 不作为最终裁决者（避免噪声带入报告）

---

### Agent 3 Deepen（深挖官）→ GLM-4（主力）

**工作特点：**
- 接收 CONFIRMED 漏洞 → **纯推理**（无工具）→ 输出 AttackChain
- 需要从攻击者视角构建连贯的攻击链
- 修复建议要具体可执行

**为什么用 GLM-4：**
1. **推理深度**：攻击链需要多步连贯推理
2. **安全代码专长**：CyberGym 评测 68.7 分
3. **事实锚定**：更强的证据锚定能力，不编造

**Kimi K2.7 的角色：**
- 当攻击链涉及**多步骤、跨文件、长程代理**时作为备选
- 不适合默认使用（需评测验证）

---

### Agent 4 Arbiter（裁判官）→ GLM-4（单模型）

**工作特点：**
- 接收三源数据 → **多源合议** → 输出 FinalReport
- 核心任务：冲突裁决（假设高置信但验证 REFUTED → 以验证为准）
- 必须保持物理隔离（不接触原始代码）

**为什么用 GLM-4：**
1. **冲突识别**：能识别微妙的矛盾
2. **结构化输出**：FinalReport 格式严格
3. **质量把关**：Arbiter 是最后一道关口

**双模型陪审（正式版）：**
- GLM-4 主裁 + Kimi K2.7 第二票
- 冲突时以 Verify 的工具证据为准
- 压低误报率

---

### Agent 0 & 5 → 无 LLM（不变）

**Agent 0 PITAX 规则层：**
- 9 条确定性规则，正则匹配，不需要模型
- 任何 LLM 都可能引入幻觉，规则层反而是最可信的

**Agent 5 报告渲染：**
- SARIF 2.1.0 规范是确定的
- Markdown 模板是确定的
- LLM 生成报告反而会导致格式不一致

---

## 五、实现方案：统一模型工厂

已创建 `codeark/models/factory.py`，支持：

```python
from codeark.models.factory import make_model, ModelProvider, ModelTier

# 推荐用法
scout_model = make_model(ModelProvider.GLM, ModelTier.FLASH)   # GLM-4-Flash
verify_model = make_model(ModelProvider.GLM, ModelTier.PRO)    # GLM-4
deepen_model = make_model(ModelProvider.GLM, ModelTier.PRO)    # GLM-4
arbiter_model = make_model(ModelProvider.GLM, ModelTier.PRO)   # GLM-4

# 备选通道
kimi_model = make_model(ModelProvider.KIMI, ModelTier.PRO)     # Kimi K2.7
deepseek_model = make_model(ModelProvider.DEEPSEEK, ModelTier.FLASH)  # DeepSeek-V4-Flash
amd_model = make_model(ModelProvider.AMD, ModelTier.FLASH)     # AMD Radeon Cloud（免费）
```

### 回退链设计

每个 Agent 都实现了多模型回退：

```python
def _make_model_fallback() -> OpenAIModel:
    attempts = [
        ("GLM-4", lambda: make_model(ModelProvider.GLM, ModelTier.PRO)),
        ("Kimi K2.7", lambda: make_model(ModelProvider.KIMI, ModelTier.PRO)),
        ("DeepSeek-V4-Pro", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.PRO)),
        ("GLM-4-Flash", lambda: make_model(ModelProvider.GLM, ModelTier.FLASH)),
    ]
    for name, fn in attempts:
        try:
            return fn()
        except Exception as e:
            print(f"[Agent] {name} 初始化失败: {e}")
    raise RuntimeError("所有模型初始化均失败")
```

---

## 六、成本估算

### 演示阶段（10 次完整扫描）

| Agent | 模型 | 每次 tokens | 成本 |
|-------|------|-----------|------|
| Scout | GLM-4-Flash | 8K | ≈¥0.008 |
| Verify | GLM-4 | 12K | ≈¥0.024 |
| Deepen | GLM-4 | 10K | ≈¥0.020 |
| Arbiter | GLM-4 | 8K | ≈¥0.016 |
| **合计** | | **38K** | **≈¥0.07** |

> 即使 100 次扫描，成本也低于 ¥1。

### 比赛 Demo 阶段（3-5 次完整演示）

成本 < ¥0.5，完全可接受。

---

## 七、为什么不选其他国产模型？

| 模型 | 评估 | 结论 |
|------|------|------|
| **GLM-4/4.7** | 安全代码评测领先，工具调用稳定 | ✅ **主力推荐** |
| **Kimi K2.7** | 长程代理能力强，适合 Deepen/Arbiter | ✅ 备选/第二票 |
| **DeepSeek-V4-Flash** | 免费/快速，工具调用已验证 | ✅ Scout fallback |
| **DeepSeek-V4-Pro** | 推理强，但误报率高 | ⚠️ 仅做召回副审 |
| **Qwen3.8** | 结构化输出好，但 API 待验证 | 🔄 预留备选 |
| **Claude/GPT** | 需 AWS/海外卡 | ❌ 不可用 |

---

## 八、实施进度

### ✅ 已完成（2026-09-08）
- [x] 创建 `codeark/models/factory.py`（统一模型工厂）
- [x] 更新 `scout_agent.py`（GLM-4-Flash 默认）
- [x] 更新 `verify_agent.py`（GLM-4 默认）
- [x] 更新 `deepen_agent.py`（GLM-4 默认）
- [x] 更新 `arbiter_agent.py`（GLM-4 默认）
- [x] 创建 `codeark/models/__init__.py`（导出接口）

### 🔧 进行中
- [ ] 安装 `strands-agents` 依赖（v
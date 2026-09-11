# CodeRisk Arcana 项目蓝图（Blueprint v2.1 - 修订版）

> 修订时间：2026-09-10 23:00（GMT+8）
> 修订依据：GLM-5.3 审核报告（`reports/GLM_REVIEW.md`）
> 变更：v2.0 → v2.1，修正 10 处文档错误 + 新增 §11 已知硬伤（待修代码）
> 模型层：GLM-5.3 (`z-ai/glm-5.3-free`) + Kimi-K3 + AMD fallback
> 状态标注：✅ 已验证 · ⚠️ 待验证 · ❌ 已知缺陷 · 🔴 待修硬伤

---

## 0. 一句话定位

**CodeRisk Arcana** = 面向「AI 供应链攻击」的自动化代码安全审计平台。
用多智能体（Multi-Agent）流水线，检测**藏在代码/文档/配置里的提示注入（Prompt Injection）与 AI 层后门**。

**比赛叙事（修订）：** 模型层以**国产大模型**（GLM-5.3 / Kimi-K3）为主力，采用**多供应商路由 + AMD Radeon Cloud 免费兜底**保障可用性。
> ⚠️ 表述要点：国产指**模型来源**；基础设施为混合（TokenRouter 路由 + AMD 云）。
> 不做"全链路自主可控"的过度声明——被审计代码经由第三方路由，需在答辩中主动说明数据流。

---

## 1. 核心命题：为什么需要它

**修订说明（重要）：** v2.0 曾声称这些攻击"传统工具完全看不见"——**不准确**。不可见字符、Bidi、Base64 等**可被确定性规则低成本检出**（本平台 Agent0 正是这么做的）。真正的差异化在于**语义层**。

### 1.1 能力分层（准确表述）

| 层次 | 能力 | 谁来做 | 价值 |
|---|---|---|---|
| **规则层** | 已知模式匹配（Unicode/Bidi/编码载荷） | Agent0（确定性，无 LLM） | 低成本、零幻觉、高精度 |
| **语义层** | 判断**意图**（文档投毒是否是恶意指令？覆盖语义？） | Scout/Verify/Deepen/Arbiter | **传统工具做不到的** |
| **合议层** | 多源交叉验证 + 攻击链推演 + 定稿 | 多智能体 | 降误报、可追溯 |

### 1.2 攻击面覆盖

| 攻击类型 | 载体 | 传统 SAST | CodeRisk |
|---|---|---|---|
| 提示注入后门 | `.cursor/rules`、`copilot-instructions.md` | 默认规则不覆盖，需自定义 | ✅ PIT-T-46 |
| 不可见 Unicode 走私 | 源码字符串（U+200B / Tag 字符） | 需码点级检查（可选） | ✅ PIT-E-23 |
| Trojan Source（双向字符） | 源码注释/字符串 | 部分工具有插件 | ✅ PIT-E-54 |
| 文档投毒 | `README`、`AGENT_GUIDE.md` | ❌ 无 | ✅ PIT-N-06 |
| 编码载荷隐藏 | 硬编码常量（Base64/ROT13/反转/多层） | ❌ 语义不可判 | ✅ PIT-E-07/14/36/57 |

**核心洞察：** 开发者一旦用 Cursor/Copilot/Claude Code 打开被投毒的仓库，AI 助手就被劫持——代码评审防线**从内部瓦解**。这是 2025-2026 的新攻击面。
**CodeRisk 的独特价值 = 语义意图判定 + 多智能体交叉验证**，而非"能看见不可见字符"。

---

## 2. 架构总览

### 2.1 六节点流水线（主线 `codeark/`）

```
输入：仓库文件字典 {path: content}
  │   ⚠️ 应先经 sanitizer 处理再喂 LLM（见 §11-B，当前未接线）
  │
  ├─ [1] Agent0 — PITAX 确定性规则扫描（无 LLM）
  │        └─ 输出：agent0_findings
  │        └─ 定位：高精度基线（**非"ground truth"**——规则层高精度但召回有限）
  │
  ├─ [2] Scout — 侦察官（LLM，提漏洞假设）
  │        └─ 输出：HypothesisSet（假设 + coverage_notes）
  │
  ├─ [3] Verify — 验证官（LLM + 工具，逐条证实/证伪）
  │        └─ 输出：VerificationResult[]（CONFIRMED/REFUTED/UNCERTAIN）
  │
  ├─ [4] Deepen — 深挖官（LLM，对 CONFIRMED 推演攻击链）
  │        └─ 输出：AttackChain[]
  │
  ├─ [5] Arbiter — 裁判官（LLM，多源合议定稿）
  │        └─ 输出：FinalReport（findings + conclusion）
  │
  └─ [6] Report — 报告渲染（无 LLM，确定性模板）
           └─ 输出：JSON / SARIF 2.1.0 / Markdown（生成≠发布）
```

### 2.2 设计铁律（六条，含修订标注）

1. **权威计算确定性** — 风险分由 `compute_risk_score()` 算（高危+3/中危+2/低危+1，封顶100）。
   > 🔴 **修订+H 漏洞**：severity 目前由 LLM 填 → LLM 间接控制分数。应改为**确定性映射打底（PITAX 规则类→默认级），LLM 仅可带证据升级**。
2. **证据可追溯** — 每阶段保留原始证据字段，传递结构化数据而非对话。
3. **生成≠发布** — Report 只落盘，**不发送任何外部渠道**；发布需人类授权。
4. **零幻觉基线** — Agent0 规则层先行。⚠️ 但**不应称其为"ground truth"**，规则层高精度≠全知。
5. **结构化输出 + 文本兜底** — 每个 LLM 节点双重保险。
   > 🔴 **修订+I**：实测 structured_output + 文本兜底**双双失败**（attack_chains=0）。需确认 Kimi 是否支持结构化输出；不支持则该铁律对 3/4 节点是虚构。
6. **容错解析** — 模型输出格式不稳定，解析器必须宽容（见 §7.1）。

---

## 3. 模型层配置（当前实装，2026-09-10）

### 3.1 路由表

| Provider | 模型 ID | Base URL | Key 文件 | Tier |
|---|---|---|---|---|
| **GLM** | `z-ai/glm-5.3-free` | `https://api.tokenrouter.com/v1` | `my-tokenrouter.txt` | FLASH/PRO |
| **KIMI** | `kimi-k3` | `https://api.moonshot.cn/v1` | `my-kimi-key.txt` | FLASH/PRO |
| **DEEPSEEK** | `DeepSeek-V4-Flash`(FLASH) / `DeepSeek-V4-Pro`(PRO) | `https://developer.amd.com.cn/radeon/api/v1` | `Radeon Cloud.txt` | FLASH/PRO |
| **QWEN** | `Qwen3.8-Flash-Next` | `https://developer.amd.com.cn/radeon/api/v1` | `Radeon Cloud.txt` | FLASH/PRO |
| **AMD** | `DeepSeek-V4-Flash` | `https://developer.amd.com.cn/radeon/api/v1` | `Radeon Cloud.txt` | FLASH |

> **修订 4**：`AMD` 行是 `DEEPSEEK` 的**别名**（同端点、同 key、同模型），为兼容旧代码保留。有效配置实为 **4 个 provider**。
> **Tier 语义（补定义）**：FLASH = 低成本/快速；PRO = 高质量/强推理。**注意** `Qwen3.8-Flash-Next` 名为 Flash 但可配 PRO 档（命名与档位不完全对应）。
> **待办**：Kimi/DeepSeek/Qwen 的模型 ID 未经 `/v1/models` 记录验证（文档自身的铁律 §3.3 要求），建议补验。

### 3.2 Agent → 模型分配（当前实装）

| 节点 | 模型 | 理由 |
|---|---|---|
| **Scout** | GLM-5.3 (TokenRouter) | 侦察发散，性价比高 |
| **Verify** | Kimi-K3 | 强推理，主判 |
| **Deepen** | Kimi-K3 | 攻击链推演需长链推理 |
| **Arbiter** | Kimi-K3 | 最终裁决 |
| **Fallback** | DeepSeek-V4-Flash (AMD) | 免费兜底 |

降级链（每个 Agent 的 `_make_model_fallback()`）：
- Scout: GLM → DeepSeek-Flash → **Qwen**（链末是 Qwen）
- Verify/Deepen/Arbiter: Kimi-K3 → DeepSeek-Pro → GLM → DeepSeek-Flash

> **修订 5**：v2.0 称 Fallback"降级链末位"——仅对 Verify/Deepen/Arbiter 成立；Scout 链末是 Qwen。
> 🟠 **风险**：**Qwen 未经真实调用验证**（§6.2 P1），却已在 Scout 降级链中。
> ⚠️ **同质化**：Verify/Deepen/Arbiter 三节点全 Kimi-K3 —— 相关性错误无法被仲裁（见 §11-G）。

### 3.3 关键技术点

**⚠️ 模型 ID 必须查 `/v1/models` 确认，不能猜。**
- TokenRouter 的 GLM 实际 ID = `z-ai/glm-5.3-free`（不是 `glm-5.3`）
- 用错 ID 报 `This token has no access to model xxx`

**Key 文件格式兼容（`_extract_key`）：**
```
Base URL：https://api.tokenrouter.com/v1     ← 全角冒号
Key：sk-s3G…Zz0a   ← 需提取标签后内容
```
直接整文件当 key → `UnicodeEncodeError: 'ascii' codec can't encode '\uff1a'`。
`_extract_key()` 智能提取 + 剔除非 ASCII（51 字符）。
> 🟠 备注：key 文件名 `Radeon Cloud.txt` 含空格，跨 shell/脚本脆弱；key 处理依赖 sed 提取是 hack，建议改用环境变量/密钥管理。

---

## 4. 模块清单

### 4.1 主线 `codeark/`

```
codeark/
├── models/
│   ├── factory.py        # ✅ 模型工厂（路由表 + key 提取 + make_model）
│   │                     #    ⚠️ docstring 仍写 "GLM-5.2"（过期，待修）
│   └── schemas.py        # ✅ Pydantic 契约
├── agents/
│   ├── agent0_pitax.py   # ✅ 节点1：PITAX 规则层（无 LLM）
│   ├── scout_agent.py    # ✅ 节点2：侦察（GLM-5.3）
│   ├── verify_agent.py   # ✅ 节点3：验证（Kimi-K3 + static/taint/dep 工具）
│   ├── deepen_agent.py   # ⚠️ 节点4：深挖（Kimi-K3）解析器 v3
│   ├── arbiter_agent.py  # ✅ 节点5：合议裁判（Kimi-K3）
│   └── report_agent.py   # ✅ 节点6：渲染（JSON/SARIF/MD）
├── graph/
│   └── pipeline.py       # 🔴 六节点编排 + compute_risk_score（含 §11-A 缺陷）
├── tools/
│   ├── pitax_scan.py     # 9 条 PITAX 规则扫描
│   ├── static_scan.py    # 静态启发式
│   ├── taint_flow.py     # 污点追踪
│   └── dep_scan.py       # 依赖 OSV 查漏洞
├── pitax/
│   ├── rules.py          # ✅ 9 条规则元数据（对齐 taxonomy v1.6.1）
│   ├── detectors.py      # 检测器实现
│   ├── sanitizer.py      # 🔴 清理/脱敏（**存在但未接入 pipeline**，见 §11-B）
│   └── sarif.py          # SARIF 输出辅助
└── cli.py                # ✅ 命令行入口
```

> **修订 9**：`sanitizer.py` 虽在模块清单中，但**流水线从未调用它**——这是 §11-B 的逻辑硬伤。

### 4.2 PITAX 规则清单（9 条，官方 taxonomy v1.6.1）

| 编号 | 名称 | 攻击面 | MITRE ATLAS |
|---|---|---|---|
| **PIT-E-23** | Invisible Text | 不可见 Unicode 走私（U+200B、Tag 字符） | AML.T0051.001 |
| **PIT-E-54** | Trojan Source | Bidi 双向字符欺骗（CVE-2021-42574） | AML.T0051.001 |
| **PIT-T-46** | Agent Instruction-File Injection | AI 配置文件后门（CVE-2025-53773） | AML.T0051.001 |
| **PIT-T-51** | Instruction Override | 注释指令覆盖 | AML.T0051.001 |
| **PIT-N-06** | Document / File Upload | 文档投毒 | AML.T0051.001 |
| **PIT-E-07** | Base64 | 单层 Base64 编码载荷 | AML.T0051.001 |
| **PIT-E-14** | ROT13 | ROT13 编码载荷 | AML.T0051.001 |
| **PIT-E-36** | Reverse | 反转编码载荷 | AML.T0051.001 |
| **PIT-E-57** | Layered Encoding | 多层组合编码 | AML.T0051.001 |

> **修订 1（已二次核实，修正 GLM 误判）**：
> - ✅ **保留 CVE-2025-53773**（PIT-T-46）—— 查 NVD + 原研究（embracethered.com）确认：
>   该 CVE 实为 **GitHub Copilot / Visual Studio 命令注入（CVSS 7.8）**，攻击链正是
>   “源码/文档提示注入 → 向 .vscode/settings.json 写入 chat.tools.autoApprove:true
>   → Copilot YOLO 模式 → 本地 RCE”，与本规则**高度相关**。
>   ⚠️ GLM-5.3 曾误判其为 “SharePoint ToolShell” 并建议删除，经查为**误判**，已恢复。
> - ✅ **保留 CVE-2021-42574**（Trojan Source 正确），可补 companion CVE-2021-42694（同形字）。
> - ✅ **ATLAS 统一为 AML.T0051.001**（Indirect）：已核对官方 atlas-data 仓库的 dist/ATLAS.yaml：
>   `.000=Direct`、**`.001=Indirect`**、`.002=Triggered`。本平台载体（文件/文档经 LLM 读取后生效）属 **Indirect = .001**。
>   ⚠️ GLM 建议改 `.002` 是基于命名猜测的**误判**，已根据官方数据回退。
> - ⚠️ **教训固化**：CVE/ATLAS 编号必须逐个查 NVD/官方仓库验证，不得凭记忆或二手结论修改（GLM 也可能错）。

主规则（PRIMARY）：PIT-E-23、PIT-T-46、PIT-T-51、PIT-E-57
来源：Arcanum Prompt Injection Taxonomy（v1.6.1, CC BY 4.0）—— 需附可访问链接与许可原文。

### 4.3 历史遗留代码（非主线）

| 目录 | 说明 | 处置建议（修订 5） |
|---|---|---|
| `app/` | 旧版 Flask + pitax 原始实现 + sanitizer_agent | **移到 `legacy/`**，勿直接删 |
| `engine/` | 旧版 semgrep/taint/llm_client | 移到 `legacy/` |
| `tests/`（根） | 旧测试 | 核对后归档 |
| `app.py` / `streamlit_app.py` | 旧入口 | 归档 |

> **修订**：**9/18 前不要删除**——用 `git tag`/`git archive` 留存历史，或移到 `legacy/` 并写迁移对照 README。
> 迁移前先做**功能盘点 diff**，确认旧 `sanitizer_agent` 的能力真的迁到了 `codeark/pitax/sanitizer.py`（呼应 §11-B）。
> 移动后跑测试套件，防 import 断裂。

---

## 5. 数据契约（schemas.py）

```python
VulnHypothesis     # title/vuln_type/file_path/line/code_snippet/
                   #   attack_path/confidence(**high|medium|low 枚举**)/suggested_verification
HypothesisSet      # hypotheses[] + coverage_notes（强制模型汇报盲区）

VerificationResult # hypothesis_title/verdict(CONFIRMED|REFUTED|UNCERTAIN)/
                   #   confidence(**float 0-1**)/evidence/verification_method
VerificationSet    # results[] + summary

AttackChain        # preconditions[]/lateral_moves[]/impact/remediation
                   # ⚠️ 无 title 字段（模型输出常带标题，被丢弃）

FinalReportFinding # title/vuln_type/file/line/severity/confidence/evidence/
                   #   attack_path/remediation
FinalReport        # findings[] + conclusion

AgentHandoff       # from/to/context_summary/structured_data/instructions
```

> 🟡 **一致性问题**：假设阶段 confidence 是**枚举**，验证阶段是 **float**——转换规则未定义。
> 🟡 **AttackChain 无 title**：而 FinalReportFinding 需要 title（现从 hypothesis_title 取），链标题被丢弃。

---

## 6. 当前进度与已知缺陷

### 6.1 已验证 ✅

| 项 | 证据 |
|---|---|
| 3 个模型真实调用 | GLM-5.3 / Kimi-K3 / DeepSeek 均通 |
| dry-run 离线链路 | ✅ 全链路跑通 |
| 真实 LLM 端到端（第一次） | 678s：Scout 8 假设 → **8 CONFIRMED**（0 REFUTED）→ risk=22 |
| 真实 LLM 端到端（第二次） | Scout 12 假设 → 12 CONFIRMED → risk=22，reports 三格式产出 |
| 解析器 v3 | 用第二次日志样本验证 **12/12 攻击链结构解析成功** |
| Key 提取修复 | 51 字符，无非 ASCII |
| 报告写入修复 | sarif dict 序列化 |

> **修订 6（表述调和）**：v2.0 称"12/12 全部解析成功"，但 §6.2 又列"链8 lateral 为空"。
> 精确表述：**12/12 结构级解析成功；1/12（链8）字段级不完整**。解析成功 ≠ 字段完整。

### 6.2 已知缺陷（优先级经 GLM 审核调整）

| 优先级 | 问题 | 状态 |
|---|---|---|
| **P0** | 🔴 风险分与 LLM 层脱钩（§11-A） | ❌ **未修**，最严重 |
| **P0** | 🔴 平台自身未防提示注入（§11-B） | ❌ 未修 |
| **P0** | ✅ CVE-2025-53773 复核（原 GLM 误判） | ✅ 已核实为真，保留，无需修改 |
| **P0** | 端到端最终确认（v3 跑完整链路） | ❌ 未跑 |
| **P1** | 链8 lateral_moves 为空（归入上条验证） | ⚠️ |
| **P1** | AttackChain 无 title 字段 | ⚠️ |
| **P1** | 🔴 Qwen 未验证却在 Scout 降级链 | ⚠️ |
| **P1** | ATLAS 映射错误（§11-D） | ⚠️ |
| **P2** | `GraphResult` 字段/裁决分布未系统校验 | ⚠️ |
| **P2** | 无私有 eval 集（demo repo 可直接转成 eval） | ⚠️ |
| **P3** | 无 Pro 超时→Flash 自动降级 | ⚠️ |
| **P3** | 三套代码并存 | ⚠️ |
| **P3** | factory.py docstring 过期（GLM-5.2） | ⚠️ 5 分钟可改 |

> **修订 7**：风险分异常（原 P2 埋没）→ **升 P0**；Qwen 未验证（P2）→ **升 P1**。

---

## 7. 踩坑记录（教训库）

### 7.1 Kimi-K3 输出格式不稳定 ⚠️（最重要）

三次端到端，Deepen 输出了**三种不同格式**：

| 次 | 标题格式 | 字段格式 |
|---|---|---|
| 1 | `## Chain-1：标题` | `**Preconditions（前置条件）**` |
| 2 | `## 链 1｜标题` | `- **preconditions**：内容` |
| 3 | `## AC-1｜pitax-1-1：标题` | `**Preconditions**` + `**攻击路径 / Lateral Moves**` |

**结论：解析器必须容错**。v3 已支持 `AC-N`/`链N`/`Chain-N`/`AttackChain N` + 中英文字段别名。

**⚠️ 待覆盖的剩余变体**（GLM 建议）：
- 编号分隔符：`AC-1.` / `1、`（顿号）/ `1)` 等
- `Chain 1`（空格而非连字符）
- 无编号标题：重复的 `## 攻击链`
- 纯粗体标题：`**Chain 1: title**`（非 `##`）
- 代码块包裹：```markdown ... ```
- 斜杠组合字段：`攻击路径 / Lateral Moves`（第3次已出现）
- 全角数字 `链１`

**治本建议（GLM，采纳）**：
1. **prompt 里钉死输出模板 + 完整示例**
2. 要求 **JSON 输出**（structured output / tool calling）
3. **一次性"格式修复"回炉调用**（让模型把自己的输出转成严格 JSON）
4. `temperature=0`
5. 把已观测的 3 种格式**固化成回归测试**

### 7.2 其他坑

- **`$(...)` 被安全层转义** → 读 key 先 `sed` 提取到临时文件
- **日志别写 `/tmp`**（网关重启清空）→ 写项目内 `reports/`
- **Strands 首次导入 60-90s** → 测试超时给足 >100s
- **后台跑用 `setsid`**（`nohup &` 会被回收）
- **`render_report` 的 sarif 是 dict** → 写文件需序列化
- **文件工具（read/write）被沙箱限制在 workspace**，`exec` 可访问项目目录
  > 🔴 **修订 10**：这不是"坑"，是 **P0 安全问题**——若某些工具/Agent 能用 exec 越出 workspace，投毒仓库可能实现**宿主机代码执行**。见 §11-J。

---

## 8. 演示仓库（demo/vuln-demo-repo/）

9 个文件，预期检出 12 处（工具实际返回）：

| 文件 | 注入类型 |
|---|---|
| `.cursor/rules` | PIT-T-46 ×4（第2行，同一句4组件） |
| `.github/copilot-instructions.md` | PIT-T-46 ×2 |
| `docs/AGENT_GUIDE.md` | PIT-N-06（凭据外泄指令） |
| `src/admin_panel.py` | PIT-E-54（Trojan Source，U+202E 等） |
| `src/config.py` | PIT-E-57（双重 Base64）+ 硬编码密钥 |
| `src/rewards.py` | PIT-E-23 ×2（U+200B、U+E0041）+ PIT-T-51 |

> 内部一致性核对 ✅：4+2+1+1+1+3 = 12。
> ⚠️ **度量注水**：`.cursor/rules` 同一行同一句拆成 4 条 finds，会使"检出数"虚高。
> 🟠 **缺失（GLM）**：
> - **无假阳性（FP）度量**——3 个干净文件未命名、未单测，应建 clean repo 测 FP 率。
> - **无反驳样本**——12/12 全 CONFIRMED，验证官从未说"不"。评委必问"什么情况会 REFUTED？"
> - **建议**：把本 demo 的"预期检出表"直接转成 **私有 eval 回归集**。

---

## 9. 交付物与时间线

| 时间 | 事项 |
|---|---|
| **9/13-15** | Demo 视频录制窗口 |
| **9/18** | 初赛提交 |
| **9/30** | 百强公布 |
| **10/31** | 决赛路演（杭州余杭·未科阿里中心） |

---

## 10. GLM-5.3 审核问题清单（已回答）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 模型配置一致性 | 文档与 factory.py 基本一致，但 docstring 过期（GLM-5.2）；AMD 行冗余；须代码级 diff 校验 |
| 2 | 架构合理性 | 六节点合理；但风险分脱钩、同质化、severity 由 LLM 定等漏洞（§11） |
| 3 | 解析器鲁棒性 | v3 仍有变体遗漏（§7.1）；建议治本（模板+JSON+回归测试） |
| 4 | 比赛叙事 | §1 原表述矛盾，已修订（§1.1 分层）；"国产"表述已精确化 |
| 5 | 遗留代码处置 | 方向对，但勿删、先盘点、跑测试 |
| 6 | 缺陷优先级 | 已调整（§6.2） |
| 7 | 合规红线 | GLM 报“假 CVE + ATLAS 错映射”——**经查为 GLM 自身误判**，原引用正确（见 §11-C/D） |

---

## 11. 🔴 已知硬伤（GLM 审核发现，lolo 逐条核实）

> 图例：🔴 待修 / ✅ 已修 / ⚠️ 已核实但无需改

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| **A** | **风险分与 LLM 层脱钩**：`compute_risk_score(res.agent0_findings or ...)` 的 `or` 永久短路，LLM 层产出对分数零影响 | 🔴 P0 | ✅ **已修**（改为 `final_report.findings` 优先，Agent0 兜底） |
| **A2** | **`critical` 严重级不计分**：`_SEV_WEIGHT` 缺 `critical` 键，PIT-T-46/PIT-E-57 被 `.get(sev,1)` 静默当成 low | 🔴 P0 | ✅ **已修**（新增 critical=4）——同一次排查中发现 |
| **B** | **平台自身无注入防护**：4 个 LLM 节点读攻击者控制的仓库内容，`sanitizer.py` 未接线 | 🔴 P0 | ❌ 未修 |
| **C** | ~~CVE-2025-53773 误引~~ **GLM 误判**：该 CVE 经 NVD 核实为 GitHub Copilot 命令注入，与本规则相关 | ⚠️ | ✅ 已核实，**保留引用**（勿再删） |
| **D** | ~~ATLAS 全标 `.001`（应为 `.002`）~~ **GLM 误判**：官方 `.000=Direct/`.001=Indirect`/`.002=Triggered`，本平台属 Indirect=`.001`，**原引用正确** | ⚠️ | ✅ 已核实，回退 `.001` |
| **E** | 叙事自相矛盾（已改 §1） | ✅ 已修 | ✅ 文档层已解决 |
| **F** | "国产模型"叙事不严谨（已改 §0） | ✅ 已修 | ✅ 文档层已解决 |
| **G** | 单模型同质化（3 节点全 Kimi） | 🟠 P1 | ❌ 未修 |
| **H** | severity 由 LLM 定 → 间接控分 | 🟠 P1 | ❌ 未修 |
| **I** | "双重保险"实际只有一重 | 🟠 P1 | ❌ 未修 |
| **J** | exec 沙箱逃逸（平台自身 RCE 风险） | 🔴 P0 | ❌ 未修 |

**其他 GLM 指出的缺失**：
- 无重试/超时/退避策略文档化（降级触发条件未定义：API 错误？超时？解析失败？）
- 无成本/延迟预算（首次 678s，视频演示够用吗？）
- 无去重/合并策略（多假设指向同一 finding，Arbiter 合并规则未文档化）

---

*Blueprint v2.1 · 修订自 v2.0（依据 GLM-5.3 审核）· 由 lolo 整理*

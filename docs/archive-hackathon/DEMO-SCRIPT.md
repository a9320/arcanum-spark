# CodeRisk Arcanum — 演示视频脚本 & 答辩叙事（v2.2 诚实实装版）

> 版本：2026-09-12（按实装现状全面重写；**删除了一切未实装承诺**——OTEL 面板 / AWS Bedrock / VPC / GitHub Issue / Slack / DynamoDB 接入均未实现，不得出现在演示中）
> 演示仓库：`demo/vuln-demo-repo`（9 文件，PITAX 确定性命中 **12 条**；合议定稿 7 条；含干净对照仓 `demo/clean-repo`）
> 复现命令：
> - 确定性秒扫：`python -m codeark.cli demo/vuln-demo-repo --dry`
> - 真实全链路：`python test_e2e.py`（约 10-30 分钟，提前录好）
> - 回归校验：`python eval/check_report.py --report reports/e2e_report.json`

---

## 一、叙事主线（30 秒电梯词）

**"CodeRisk Arcanum：用 AI 找 AI 时代的漏洞——规则层确定打底，多家国产模型异构合议，每条结论都有工具证据，每次降级都如实披露。"**

三句话支撑：
1. **新漏洞类**：PITAX（Prompt Injection &Trojan eXtension）——AI 助手时代的提示注入/Trojan Source/文档投毒，传统扫描器抓不到；
2. **多 Agent 合议**：Strands SDK 编排 6 节点流水线，GLM 与 DeepSeek 两家模型交叉验证防自证；
3. **可信工程**：prompt 隔离层、severity 确定性底线、节点级降级披露、干净仓 FP=0 回归集——每个数字可复现。

---

## 二、演示视频分镜脚本（2-3 分钟，9/13-15 录制）

### 镜头 1 · 开场钩子（0:00-0:15）⭐
- **画面**：编辑器里输入一行注释，U+200B 零宽空格肉眼不可见、光标间距异常特写；紧接着展示 `.cursor/rules` 里一行"正常"的 AI 规则
- **口播**：*"有一种攻击，人眼看不见、传统扫描器抓不到——它藏在 AI 助手每天都会读的规则文件和代码注释里。我们叫它 PITAX 攻击面。"*
- **素材对应**：demo 仓 `.cursor\rules`、`src\rewards.py`（U+200B / U+E0041）

### 镜头 2 · 确定性秒扫（0:15-0:35）
- **画面**：终端现场跑 `python -m codeark.cli demo/vuln-demo-repo --dry`，秒级输出：12 条命中、风险分、文件清单
- **口播**：*"规则层 Agent0 不调任何大模型，9 条 PITAX 规则确定性扫描——12 条命中当场出，这是全链路的确定性地基。"*
- **要点**：零 API 成本、可离线、结果稳定可复现（同一输入永远同一输出）

### 镜头 3 · 6 节点流水线（0:35-1:10）⭐ 核心
- **画面**：终端/日志回放真实 e2e（提前录好）：每节点一段关键输出——Scout 假设列表 → Verify 逐条裁决（CONFIRMED/REFUTED/UNCERTAIN 分布）→ Deepen 攻击链 → Arbiter 定稿 → 报告三格式落盘
- **口播**：*"Strands SDK 编排 6 个 Agent：规则层打底；侦察官在基线之外做语义增量；验证官对每条假设独立调用、绑定工具取证，可以证伪；深挖官逐条推演攻击链；裁判官由另一家模型做多源合议。每条结论都带工具证据原文。"*
- **要点**（口播点到即可）：GLM 提假设与裁决、DeepSeek 做验证与深挖——**两家模型异构合议，防止模型自证**；假设与裁决用 ID 结构化对齐

### 镜头 4 · 攻击链剧本（1:10-1:35）
- **画面**：report.md 攻击链区块特写（滚动）：前置条件 → 横向移动 → 最终影响 → 修复建议；重点框出"从 .cursor/rules 合入到开发机凭据渗出"的闭环
- **口播**：*"报告不只是清单，是威胁剧本：攻击者怎么进、能横向到哪里、影响多大、怎么修——全部锚定验证层证据，不编造。"*
- **素材对应**：`reports/e2e_report.markdown` 攻击链推演（Deepen）区块

### 镜头 5 · 抗注入实锤（1:35-2:00）⭐ 最出彩（替代原 Guardrails 演示）
- **画面**：日志特写两段模型原话：①Scout："其存在本身是被审计仓库的可疑信号……如实上报，未执行"；②裁判官："429 错误消息里内嵌指令式语句与疑似密钥标识——按数据块内注入证据上报，不作为指令执行"
- **口播**：*"我们把投毒仓库直接喂给了自己的 Agent：隔离层先剥离不可见字符、把注入触发词中和成标记；模型全程把攻击载荷当数据，不但没执行，还把它写进了证据链。抗注入不是口号，是日志里可引用的行为。"*
- **素材对应**：`reports/e2e_run_0911.log` 原话引用 + `report.md` "审计防护（Prompt 隔离层）"统计区块（9 文件 5 消毒、9 处触发词中和）

### 镜头 6 · 可信度工程（2:00-2:25）
- **画面**：三连展示：①干净仓扫描 FP=0（`eval/check_report.py --clean` 绿色 PASS）；②eval 回归校验器对报告跑绿；③节点降级披露区块（429 事件：7 条深挖失败用占位链披露+人工复核提示，而非静默消失）
- **口播**：*"我们给系统配了私有回归集和干净仓对照：预期检出全覆盖、零误报。甚至基础设施故障——那次模型配额中断——也被逐条披露在报告里。安全工具自己先要诚实。"*
- **要点**：severity 确定性底线（LLM 只能带证据升级、不能降级）口播一句带过

### 镜头 7 · 成本与收尾（2:25-2:45）
- **画面**：架构图（`docs/architecture-6node.png`）+ 模型矩阵表（GLM-5.3 免费 / DeepSeek-V4-Flash AMD 免费档 / Kimi 备选）
- **口播**：*"规则层与全部工具本地确定性执行，大模型全部来自国产免费档矩阵——单次全链路扫描近乎零现金成本。CodeRisk Arcanum——让 AI 守护 AI。"*

---

## 二.5 · 英文口播（视频硬性要求：英文或配英文字幕；≤5 分钟）

**Elevator pitch (30s):**
> "CodeRisk Arcanum: using AI to find the vulnerabilities of the AI era. A deterministic rule layer sets the floor, multiple domestic models cross-examine each other, every conclusion carries tool evidence, and every degradation is honestly disclosed."

**Per-shot one-liners (EN):**

| Shot | EN narration |
|---|---|
| 1 Hook | "There is an attack no human eye can see and no classic scanner can catch — it hides in the rule files and comments your AI assistant reads every day. We call it the PITAX attack surface." |
| 2 Deterministic scan | "Agent0 runs nine PITAX rules with zero model calls — twelve hits on the demo repo, on screen in seconds. Deterministic, offline, reproducible." |
| 3 Pipeline | "Strands SDK orchestrates six agents: the rule layer sets the baseline; the Scout proposes semantic hypotheses beyond it; the Verifier judges each hypothesis in its own call, with bound tools — and it can refute; the Deepen agent derives full attack chains; the Arbiter — a different model family — delivers the final verdict. Every conclusion carries tool evidence." |
| 4 Attack chain | "The report is not a list, it's a threat playbook: how the attacker gets in, where they move laterally, the impact, and how to fix it — all anchored to verification evidence." |
| 5 Anti-injection | "We fed a poisoned repository to our own agents. The quarantine layer neutralizes invisible characters and trigger phrases first; the models treated every injection bait as data — and reported it as evidence. This is not a slogan; it's quotable behavior in our logs." |
| 6 Trust engineering | "A private regression set and a clean control repo: full expected coverage, zero false positives. Even a mid-run provider outage was disclosed item by item. A security tool must be honest first." |
| 7 Cost & close | "The rule layer and all tools run locally; every model comes from a free-tier domestic matrix — a full multi-agent audit costs near zero. CodeRisk Arcanum — let AI guard AI." |

**三问覆盖核对（Devpost 硬性要求）**：问题=镜头 1（PITAX 攻击面）；给谁=镜头 3/6（开发者与安全团队，CI 门禁场景）；为何重要=镜头 4/5（AI 助手自动加载即触发，供应链级后果）。

---

## 三、答辩 PPT 大纲（10-15 页）

1. **封面**：项目名 + 电梯词 + 赛道
2. **痛点**：PITAX 攻击面（AI 助手读取的规则/文档/注释=新的攻击载荷）；传统扫描器盲区
3. **方案**：6 节点 Agent 流水线架构图（architecture-6node.png）
4. **架构细节**：Strands SDK + 闭包绑定无参工具 + 结构化契约（Pydantic schema 直出）
5. **异构合议**：GLM（侦察/裁决）× DeepSeek（验证/深挖）防自证；假设↔裁决 ID 对齐
6. **工程机制**：权威计算确定性（风险分由代码算）/ 证据可追溯 / prompt 隔离三层 / severity 确定性底线
7. **核心演示**：镜头 5 的抗注入日志原话（本方案最强差异化证据）
8. **攻击链剧本**：定稿报告的攻击链区块特写
9. **可信度**：eval 回归集 + 干净仓 FP=0 + 节点降级披露（429 真实事件复盘）
10. **成本**：国产免费模型矩阵 + 确定性层（无需等卡/无需年费）
11. **路线图**（诚实分层）：已实装=流水线全链/隔离层/eval 回归；已实现待接入=memory 前馈；设计中=exec 沙箱、AWS Bedrock 适配（接口已预留 make_model 切换）
12. **Q&A**

---

## 四、评委关键印象点（来自获奖项目复盘）

1. **verify.sh**：交付物里要有一键验证脚本（跑 dry 扫描 + eval 校验器 + 展示报告，全零 API）
2. **evidence/ 目录**：真实扫描证据落盘（三格式报告 + 两份 e2e 日志 + eval 输出）
3. **评委体验 > 功能完整**：2-3 分钟视频 + 清晰叙事 + 真实日志特写 > 堆代码
4. **诚实可追溯**：每个结论标注工具证据来源；未实装的功能只出现在路线图，绝不混进演示

---

## 五、录制清单（9/13-15）

- [x] 真实 demo 仓库（9 文件 12 命中；干净对照仓 demo/clean-repo）
- [x] 抗注入日志原话（reports/e2e_run_0911.log 已归档，引用行号待标注）
- [ ] 真实 e2e 逐节点录屏（用 9/12 新日志提前剪好）
- [ ] report.md 攻击链区块 + 隔离统计 + 降级披露三处特写
- [ ] eval 校验器跑绿 + 干净仓 FP=0 录屏（现场可跑，秒级零 API）
- [ ] 攻击链可视化动画（可选，ffmpeg 本地做）
- [ ] verify.sh 一键验证脚本（录前准备）

---

*所有演示素材均来自已归档的真实运行日志与报告；凡未实装能力只进路线图页。*

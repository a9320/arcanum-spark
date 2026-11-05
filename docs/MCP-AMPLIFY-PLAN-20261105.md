# MCP 放大主项目方案（第二版 · 2026-11-05 深夜）

> 前置：第一版（MCP-CAPABILITY-PLAN-20261105.md）已落地四工具+formats+40 例。
> 本稿=深度回顾主仓（README/ROADMAP/EVAL-LEDGER/gate/gate_factory/replay/skills）后的下一轮：
> **最大限度呈现主项目的优秀之处**。待拍板，未动手。

---

## 1. 回顾结论：主项目亮点 × MCP 呈现状态

| 主项目资产（证据源） | MCP 现状 | 差距判定 |
|---|---|---|
| PITAX 9 规则 + 51 例基准 strict 100%/FP0（pitax_bench+verify） | 引擎在用 | **检出质量未锚基准**——MCP 测试自说自话 |
| Office 体检 / dep 漏库 / SARIF 报告层 | docs_scan/dep_scan/formats ✅ | 已呈现 |
| **Laya 八代 ranker**：hard-exam 24/24、AP=1.0、FN=0、ECE 0.0417、order-only 契约、Windows CPU 389ms/条实证（EVAL-LEDGER 10-07） | ❌ roadmap 二期 | **主项目最独特的研究成果，零呈现**（用户点名） |
| **instructed 政策路由实证 0/5→9/9 + 0 误触发**（eval/README 方法论） | README 表格 | **AGENTS.md 政策文件没随 plugin 发布**——9/9 的杠杆没装机 |
| 6-agent 流水线+跨家族仲裁+attack chains | README 能力地图 | 叙事已呈现（拍板口径），形态留二期 HTTP |
| 真实 OSS 四仓语义层 FP=0 标定（v1.2 #5） | ❌ | README 硬数字段缺失 |
| K2/M8 真值判分协议（NYU CTF 20 题） | ❌ | 研发资产，不进 MCP（维持） |
| skills/ai-repo-audit 第三形态（Agent Skills 协议） | ❌ | 互链缺失 |
| verify 证据契约/降级兜底/advisory 处置边界 | 工具输出已体现 | 已呈现 |
| 40 例路由集与基准同源 | ✅ | 实测未跑（待 Copilot） |

## 2. 方案（按杠杆排序）

### P1-A：AGENTS.md 政策随 plugin 分发 ⭐最小成本最大杠杆
- **事实**：README 明写推荐形态=ship an AGENTS.md policy with the plugin（instructed 9/9），但 `plugins/arcanum-security/` 里只有 plugin.json/mcp.json——**政策文件从未随发**。
- **做什么**：写 `plugins/arcanum-security/AGENTS.md`（路由政策：四工具分派规则+inline 传参纪律+advisory-only 处置边界+措辞避开触发词——即 2026-11-01 现场事故链的全部教训固化）。
- **价值**：路由方法论（主项目的实测路由科学）从 README 描述变成用户装机即得；40 例实测的 instructed 前提补齐。
- **成本**：低（一个文件+测试锚：政策提到的工具名=四工具白名单）。

### P1-B：pitax_bench 一致性验收（51 例基准同源）⭐"不糊弄"的最硬形式
- **做什么**：MCP 测试从主仓读 `eval/pitax_bench/cases.jsonl`，`code_audit(path=夹具目录)` 跑全 51 例，断言 expected 规则检出逐例一致。
- **价值**：MCP 检出质量直接锚在主仓基准上（"MCP 与 51 例 strict 100%/FP0 基准同源验收"），而非 MCP 自己写的用例自证；对外叙事一句话讲清承重关系。
- **成本**：低（一个参数化测试+夹具生成器；基准缺席时 skipif）。

### P1-C：README「Backed by arcanum-spark」硬数字段
- 51 例 strict 100%/FP0 · OSS 四仓语义层 FP=0 · Laya 24/24 AP=1.0 ECE 0.0417 · CI 26 runs 全绿 · 三形态打包（CLI/MCP/Skill 同一引擎）+ skills/ai-repo-audit 互链。
- **成本**：低（纯文档）。**红线**：只写有证据源的数字（EVAL-LEDGER 可溯）。

### P2：`rank_hypotheses` 第五工具（Laya 产品化）⭐用户点名，主项目独特性最集中
- **接口**：`rank_hypotheses(hypotheses: str(JSON), baseline: str(JSON)=)`；条目字段 `title/vuln_type/file_path/attack_path/code_snippet`（=gate_factory 喂 score_laya 的 items 形态，不改训练分布）。
- **行为**：逐条 P(KEEP)+confidence → 排序表输出 + **order-only 声明**（"advisory ranking; never deletes items"——gate v1 契约原文语义）+ 时延自述（CPU ~0.4s/条）。
- **用户故事**：宿主 agent 扫完拿到几十条候选，问"验证预算先给谁"——这正是主项目 gate 在流水线里干的事，现在直接给任何 agent 用。**训练分布=Scout 假设集，文档如实声明其他输入形态未标定。**
- **依赖/分发（零网络红线不破）**：
  - `arcanum-mcp[laya]` extra：torch(CPU)+transformers+safetensors——主安装零依赖不变；
  - checkpoint=GitHub Release `laya-checkpoints` 三资产**手动下载**，`ARCA_LAYA_PATH` 指路；缺失时输出升级 hint（同 docs_scan 引擎缺失模式）。
- **单一事实源（关键工程决策）**：`score_laya/_laya_state/_load_laya_agent` 现居 `eval/replay.py`（非包）。**提升到主仓 `codeark/graph/laya_runtime.py`**，replay.py 反向转发（单一源不变）；MCP 走 `_import_chain([("codeark.graph.laya_runtime", ...)])`。slim COPY_PLAN **不带**（torch 重依赖）——该工具=full-engine+extra 形态专属，与四工具的"slim 全覆盖"分层诚实披露。
- **风险（如实入文档）**：Windows CPU safetensors mmap 段错误坑（EVAL-LEDGER 10-07 记录，fp32 物化补丁绕开）→ 加载期物化补丁须随 laya_runtime 落地；checkpoint ~GB 级下载门槛。
- **用例**：路由集补 2 例（"12 个假设先验证哪个"正例+"帮我扫描这段文本"判别例——排序器≠检测器）。

### P3（挂账二期，维持上轮拍板）
- 四岗 HTTP 自托管形态（模型端点+pipeline 全链）；skills 深度互链（README 一行已覆盖最小形态）；awesome-copilot PR（路由实测后）。

## 3. 拍板点
1. P1 三项（AGENTS.md 随发 / bench 一致性验收 / README 硬数字段）——建议全上，成本皆低。
2. P2 rank_hypotheses：**本轮实施 or 维持二期**？（若本轮：主仓先做 laya_runtime 提升+Windows mmap 补丁，MCP 后接；工程量中等，风险点已列。）
3. 40 例路由实测+两包发布（上轮遗留）与本轮的先后顺序。

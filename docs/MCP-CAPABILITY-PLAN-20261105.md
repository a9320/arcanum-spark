# MCP 能力承重设计稿（2026-11-05）

> 状态：**已拍板（2026-11-05 用户四项全选推荐项），进入实现**。触发=11-05 用户批评：MCP 未参考主仓资产、用例不许糊弄。
> 本稿任务（收工块第 4 条）：盘点 arcanum-spark 可外露能力 → 按「零模型/确定性/形态」分类 → 每候选给接入成本×展现价值 → 用户拍板后才谈实现。

---

## 1. 盘点：主仓可外露能力资产（代码为准，已逐一核对入口）

| # | 能力 | 代码入口 | 零模型 | 确定性 | 纯标准库 | MCP 形态候选 |
|---|---|---|---|---|---|---|
| A1 | PITAX 规则引擎（现 MCP 双工具的底座） | `codeark/agents/agent0_pitax.py::run_agent0` | ✅ | ✅ | ✅ | 已在用 |
| A2 | **Office 文档投毒体检**（N-06 文档投毒 + E-23 不可见字符 + E-54 Trojan + 编码四件） | `codeark/office_scan.py::scan_office_file/scan_office_tree`；文本抽取 `office_text.py`（zipfile+ElementTree） | ✅ | ✅ | ✅ | **新工具 `docs_scan`** |
| A3 | **依赖已知漏洞比对**（OSV 本地 index + `_LOCAL_VULN_DB` 内置库回落 + PHP 运行时钉检查） | `codeark/tools/dep_scan.py::scan_deps` | ✅ | ✅ | ✅ | **新工具 `dep_scan`** |
| A4 | **多格式报告层**（JSON / SARIF 2.1.0 / Markdown / 自包含 HTML） | `codeark/agents/report_agent.py::render_report`；SARIF 扩展 `pitax/sarif.py` | ✅ | ✅ | ✅ | **工具参数 `formats`**（产物落本地，返回路径） |
| A5 | 输入净化（对源码树 PITAX 预扫描） | `codeark/pitax/sanitizer.py::InputSanitizer/scan_directory` | ✅ | ✅ | ✅ | 低优先（与 code_audit 重叠） |
| A6 | Laya 假设排序器（421M 判分 gate） | `eval/replay.py`（评分底座）+ Laya checkpoint | ✅（推理） | ⚠️ 模型推理 | ❌ 需权重分发 | 候选 `rank_hypotheses`（README 旧设计在案） |
| A7 | 四岗流水线（Scout/Verify/Deepen/Arbiter + verdict 治理 + attack chains 聚合） | `codeark/graph/pipeline.py::CodeRiskGraph` | ❌ 需模型（有 dry 链） | 部分 | ❌ | 不进 stdio 工具（见 §4-C5） |
| A8 | Azure 双服务（Content Safety + Language 脱敏） | `codeark/azure/*` | ❌ 网络+凭据 | ✅ 判定 | ❌ | 不进（违背 MCP「零网络」定位） |
| A9 | K2 判分器 / 双 Scout profile / gate 链 | `eval/t4b_judge.py` 等 | 混合 | — | — | 研发资产→只作验收基准 |
| A10 | 评测用例库 | `eval/pitax_bench/`（51 例，strict 100%/FP0）+ r3–r8 硬负例 + K2 12 失分题 | — | — | — | **路由/工具用例扩面的唯一合法来源** |

**slim wheel 边界**（MCP 默认装机形态）：`build_slim_pitax.py::COPY_PLAN` 只带 `pitax/*` + `pitax_scan.py→scan_engine.py` + `report_agent.py→reporting.py`。A2/A3 **不在包内**——进 slim 需扩 COPY_PLAN（A2 加 2 文件改 3 处 import；A3 加 1 文件，数据=内置库+可选注入）。

## 2. 候选方案（接入成本 × 展现价值）

### C1 `docs_scan` 第三工具 ⭐推荐
- **做什么**：`docs_scan(path, formats?)` 包装 `scan_office_tree`；渲染同 `_render` 风格 + office meta（文件数/部件数/字符数/跳过数——真实扫描范围口径）；产物走 C2。
- **成本**：低。MCP 侧 1 工具函数+渲染+测试；slim COPY_PLAN +2 行（`office_text.py`、`office_scan.py`，改写 3 处 import）。
- **价值**：高。.docx/.xlsx 投毒是 agent 真实输入面（用户真会把文档拖给 Copilot）；N-06 检测面=主仓差异化能力；README 路线图本就挂着 `doc_scan`（under evaluation）。
- **用例来源**：pitax_bench 中 N-06/E-23/E-54 案例的内容重制为 .docx/.xlsx 夹具（内容=真实攻击模式，非编造）；负例=干净文档+跳过格式。

### C2 报告产物参数（工具输出升级）⭐推荐
- **做什么**：`code_audit`/`docs_scan` 增 `formats="sarif,markdown,html"`，调 `render_report`/`build_html` 落盘到 MCP 报告目录（**生成≠发布**纪律保留：只落本地、返回路径，不发送）。
- **成本**：低。`reporting.py` 已在 slim 内；MCP 侧=参数+落盘+路径回传+测试。
- **价值**：中高。SARIF 直接被 GitHub Code Scanning / IDE 消费=接入用户真实工作流；自包含 HTML=演示资产（一条链接打开完整报告）。

### C3 `dep_scan` 第四工具 推荐
- **做什么**：`dep_scan(path)` 包装 `scan_deps`（解析 requirements/pyproject/package.json/composer/Dockerfile）。
- **成本**：低-中。纯标准库+内置漏洞库；slim +1 文件。风险=内置库覆盖面小（真实命中要靠 OSV index 注入或扩 `_LOCAL_VULN_DB`）。
- **价值**：中高。把 MCP 从「提示注入」单维扩到「依赖漏洞」维（PHP2Shell 动机样本的 CVE 画像在案）；展现主仓侦察工具面。
- **用例来源**：真实 CVE 版本号写进夹具依赖清单（如 `composer.lock` 钉旧 PHP 运行时），负例=已修复版本。

### C4 用例扩面（红线执行项，随新工具一起做）
- 12 例 → 30+：每新工具 ≥5 正例（内容从 A10 资产推）+ ≥2 负例 + ≥1 边界（截断/空输入/未知格式）；预注册判据（路由正确率、零 FP 负例通过）。
- **这是"展现项目能力"最实的部分**：路由基准本身=主仓 eval 资产的复用，对外叙事"MCP 的用例集与主仓 51 例基准同源"。

### C5 四岗流水线：不进 stdio 工具（明确不做+理由）
- stdio MCP 无模型端点，跑四岗只有两条路：a) 要求用户配 ARCA_SPARK_PATH+模型 → 装机门槛摧毁 `uvx` 体验；b) dry 链（`_dry_scout/_dry_verify/_dry_chains`）→ 输出是 mock 合议，**正是用户红线"糊弄"的形态**。
- **替代形态**：① README「能力地图」段落：MCP=确定性入口，四岗/attack chains/Azure gate 一条 CLI 命令可达（`python -m codeark.cli scan <repo>`），叙事闭环不冒充；② 后续若做 HTTP 团队形态，再谈挂模型端点。

### C6 `rank_hypotheses`（Laya 排序器）：缓议
- README 旧设计在案（gate 契约不漏判决信息）。拦路虎=**权重分发**（421M checkpoint 走 GitHub Release，MCP「零网络」承诺破例）+ 输入形态（假设集来自流水线，stdio 场景没有假设集）。首批不做，拍板时可定"二期"。

### 不做清单（其余资产的去向）
- A5 净化器与 code_audit 职责重叠；A8 Azure 违背零网络定位；A9 K2 判分器=研发侧，作 MCP 验收基准而非工具。

## 3. 推荐组合（首批拍板项）

**C1+C2+C3+C4 一起上**（三工具+报告产物+真实用例集）：全部零模型/确定性/纯标准库，slim 承载得住，装机体验不变（`uvx` 仍零网络零配置）；MCP 叙事从「两个薄工具」升级为「PITAX 规则 + 文档投毒 + 依赖漏洞 + SARIF 报告」四能力面，每一面都有主仓真实代码背书。

## 4. 待拍板
1. 首批范围：C1+C2+C3+C4？C3 dep_scan 是否并入 code_audit（我建议独立工具，保持 one-job-each）？
2. C6 rank_hypotheses：定为二期 / 彻底放弃？
3. 四岗展现走 README 能力地图（C5-①）是否认可？
4. 用例目标规模：30+ 是否合适（或与 51 例基准对齐到 40+）？

## 5. 拍板结果（2026-11-05，用户四项全选推荐）
1. **首批范围：C1+C2+C3+C4 全上**（docs_scan + formats + dep_scan + 用例 12→30+；dep_scan 为独立工具，保持 one-job-each）。
2. **四岗展现：README 能力地图**（MCP=确定性入口，四岗/Azure gate 一条 CLI 命令可达，不冒充工具）。
3. **rank_hypotheses：定二期**（保留设计，等四岗 HTTP 形态或权重分发方案）。
4. **用例规模：30+**（每新工具 5+ 正例 / 2+ 负例 / 1+ 边界，内容一律从 A10 资产推）。

**实现顺序**：① 主仓 `build_slim_pitax.py` COPY_PLAN 扩（office_text/office_scan/dep_scan 进 slim，import 改写）→ ② MCP `server.py` 引擎解析扩 + `docs_scan`/`dep_scan` 工具 + `formats` 参数 → ③ `routing_cases.json` 12→30+ → ④ 两仓测试/构建回归 + README 能力地图 → ⑤ verify/pytest 全绿后收尾。

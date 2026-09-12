# CodeRisk Arcana — 9/14 提交冲刺计划

> 版本：**v1.1**（2026-09-11 晚增补：Strands SDK 框架适配审查，新增任务 2/3/7 + 明日"架构级改造"两行）
> 制定时间：2026-09-11 ｜ 死线：**9/14 提交**（演示视频按 9/13 录完排期）
> 依据：reports/BLUEPRINT_v2.1.md §6.2/§11 缺陷清单 + 2026-09-11 代码核查 + 框架适配审查
> 命名注意：框架是 **AWS Strands SDK**；Arcanum 是 PITAX 分类法出处（Jason Haddix）。文档/答辩勿混。
> 用途：晚间协作优化的工作清单，逐条过、逐条勾

---

## 基线快照（截至 2026-09-11）

| 状态 | 项 |
|---|---|
| ✅ 已验证 | 3 模型真实调用通（GLM-5.3 / Kimi-K3 / DeepSeek）；dry-run 全链路；两次真实端到端（12 findings → 12 CONFIRMED → 三格式报告） |
| ✅ 已修未验证 | §11-A 风险分脱钩、§11-A2 critical 不计分 —— 今晨已改 `pipeline.py`，**但修复后还没跑过端到端** |
| ❌ 未修 | §11-B sanitizer 未接线；attack_chains=0（Deepen 双保险均失败）；§11-G 三节点同质化；§11-H severity 由 LLM 定；Qwen 未验证却在降级链；无 REFUTED 反例 / 无 FP 度量 |
| ⚠️ 卫生 | codeark/ 与全部近期文档未提交；.venv 是 WSL 建的（Windows 侧断链）；test_e2e.py 硬编码 /mnt/d；API key 明文+路径硬编码 |

---

## 框架适配审查（2026-09-11，Strands SDK × 各 Agent 职责）

> 总体：Strands 选型合适（@tool / structured_output / 多 provider 路由都对味）；
> 问题集中在**节点职责写法**与**框架用法**的四处错配，详见下表。衍生任务已并入今晚/明日清单（标【增补】）。

### 逐节点适配判定

| 节点 | 判定 | 问题 | 处置 |
|---|---|---|---|
| Agent0 / Report | ✅ 适配 | 纯确定性不碰 LLM，正确。但 `render_report` 只消费 findings，**attack_chains 没进报告渲染**——演示"攻击链特写"缺确定性数据来源 | 今晚任务 3 |
| Scout | ⚠️ 职责写窄（最大错配） | 提示词"工具返回什么就汇报什么"→ Scout 沦为 Agent0 复读机（e2e 12 假设=12 命中即证据）；蓝图"模型优先、提规则库外假设"未兑现 | 9/12 架构级改造①，需拍板（见决策③） |
| Verify | ⚠️ 调用结构必然全过 | 单次调用塞全仓+12 假设，pitax_scan 对已知命中必然返回"有"→ 12/12 CONFIRMED 是结构造成的橡皮图章 | 9/12 架构级改造② |
| Deepen | ⚠️ 框架用法自相矛盾 | `build_deepen_agent` 未传 `structured_output_model` 却指望 structured_output →"双保险"只有一重（§11-I）；一次推 12 链输出过长格式漂移（3 次 3 种格式） | 今晚任务 4（含粒度改"每链一调"） |
| Arbiter | ✅ 职责适配 / ❌ 失败路径危险 | 无工具纯合议正确；但解析失败**静默返回空 FinalReport**（arbiter_agent.py:31/47），12 条确认漏洞无声消失、风险分回落 Agent0——"假成功"最危险单点；去重合并规则缺失 | 今晚任务 3；去重规则写进系统提示词 |

### 跨节点共性（框架层）

| # | 问题 | 影响 | 处置 |
|---|---|---|---|
| 一 | **工具参数回传黑洞**：pitax_scan schema 要求模型传 `files`，全仓内容已在 prompt，模型每次调工具须把整个仓库字典重新生成一遍 | token 双倍烧 + 内容被改写/截断风险 | 今晚任务 2（闭包绑定，无参 schema） |
| 二 | **fallback 名不副实**：`_make_model_fallback` 只兜构造失败，API 超时/报错不切换 provider | 11 分钟长跑遇网络抖动整跑报废，演示日最大现场风险 | 今晚任务 7 |
| 三 | 全仓内容喂给每个节点，pipeline 无 per-node 容错 | 一个节点炸全链路炸 | 明日验证拆分后自然收敛；per-node try/except 并入任务 7 |
| 四 | **两处设计断线**：memory 只有 dashboard 在用（§5.7 前馈未闭环）；假设↔裁决靠 title 字符串匹配（脆弱） | 记忆卖点空转；匹配易错位 | memory 接线列入"不做"（赛后）；id 字段并入明日 schema 小修 |

---

## 第 0 步（今晚开工前，10 分钟）：环境与保护

| # | 任务 | 验收标准 |
|---|---|---|
| 0.1 | **git 提交保护**：补 .gitignore（.venv/、__pycache__/、*.bak*、*.zip、.pytest_cache/），提交 codeark/ + docs/ 新文档 + reports/ 蓝图 | `git status` 干净；主线代码在版本控制内 |
| 0.2 | **确认运行环境**：今晚在 WSL（原 .venv）还是 Windows（重装依赖）跑 e2e；统一 test_e2e.py 路径为可移植写法（仿照 codeark/tests 里 `parents[1]` 的做法） | 选定环境里 `python -c "import strands, pydantic"` 成功 |

## 今晚（9/11）：P0 —— 让核心叙事站得住

执行顺序即表格顺序：**所有代码改动都在第三次端到端之前**，让一次跑验证全部改动。
（必做=收工线；选做=时间富余再做）

| # | 任务 | 性质 | 说明 | 验收标准 |
|---|---|---|---|---|
| 1 | **sanitizer 接线（§11-B）** | 必做 | Scout/Verify/Deepen/Arbiter prompt 拼装前统一跑 `codeark/pitax/sanitizer.py`，Sanitize 步骤进 pipeline.py。做完即答辩卖点（"自己抗注入"） | pipeline 存在显式 sanitize 步骤；命中数进 GraphResult；单测覆盖 |
| 2 | **工具参数闭包绑定【增补 Top1】** | 必做（≤1h） | files 用闭包/partial 绑死，schema 改无参工具，模型只发起调用不再生成仓库内容 | tool schema 无参；e2e 日志可见工具正常执行；token 消耗对比留档 |
| 3 | **Arbiter 失败披露 + 报告渲染 attack_chains【增补 Top2】** | 必做（≤1h） | ①解析失败重试一次，仍失败显式报错/降级标注，禁止静默空报告；②`render_report` 增加确定性 attack_chains 区块；③系统提示词写去重合并口径（"独立注入链"vs 工具粒度双口径） | 构造一个坏输出场景单测→报错而非空报告；markdown 报告出现攻击链区块 |
| 4 | **Deepen 治本（含粒度改造）** | 必做 | ①**每链一调**（替代一次全推）；②prompt 钉死 JSON 模板+完整示例；③解析失败一次"格式修复"回炉（temp=0）；④确认 Kimi 经此 client 是否支持 JSON mode，不支持则该节点换支持模型；⑤3 种历史格式变体固化进 test_deepen_parse 回归 | 真实样本解析 12/12；回炉路径有 mock 单测 |
| 5 | **Arbiter 换 GLM-5.3 第二票（§11-G）** | 必做（改一行） | 去相关 + 答辩讲"异构模型合议" | e2e 日志显示 Arbiter 用 GLM |
| 6 | **severity 确定性打底（§11-H）** | 选做 | PITAX 规则默认 severity 打底（rules.py 已有），LLM 只能带证据升级、不可降级/凭空造级 | 单测：LLM 给低级别不影响打底分 |
| 7 | **invoke 级容错降级【增补 Top4，选做但强烈建议】** | 选做（≤1h） | 把节点 invoke 包 try/except：退避重试 1 次→换 provider→仍失败则该节点落确定性降级路径并在报告标注，而不是全链路崩 | 人为注入一次 API 异常，流水线仍能产出带降级标注的报告 |
| 8 | **第三次端到端（收工线）** | 必做 | 上面改动全部生效后 demo/vuln-demo-repo 全链路真跑（~11 分钟，setsid 后台，日志写 reports/） | risk_score 基于 final_report.findings（≠恒 22）；attack_chains ≥ 10；报告三格式+攻击链区块；日志归档 |

> 收工线：1-5 + 8。第 8 步失败不阻塞睡觉，明早第一时间看日志定位。

### 今日执行日志（9/12，任务 6/9-15 全部落地）

- ✅ **P0 模型切换（含计划外发现）**：昨夜 Kimi 余额耗尽后，把 Verify/Deepen 主用切 DeepSeek——但 AMD 真调即 404：**工厂里 `DeepSeek-V4-Pro` 路由从未被验证，AMD 目录（models.list 实测）只有 DeepSeek-V4-Flash / Qwen3.8-Flash-Next / MiniCPM5-2B**。修正为 DeepSeek-V4-Flash 主判（PRO 档语义保留），Kimi 充值后恢复备选；Qwen 真实小调用验证通过（任务 13 ✓）保留 Scout 兜底。异构合议叙事不变：GLM（Scout/Arbiter）vs DeepSeek（Verify/Deepen）
- ✅ 任务 9 Scout 语义增量：agent0 基线注入 `<agent0-baseline-findings.json>` 数据块，职责改为基线外增量发现（文档投毒意图/跨文件逻辑/规则库外注入面），禁止复述基线；无基线时退回旧行为（兼容）
- ✅ 任务 10 Verify 逐假设拆分：`run_verify_split` 每假设独立小调用（假设+该文件原文+四个工具对该文件的确定性预跑结果内嵌），REFUTED/UNCERTAIN 有出现空间；id 结构化对齐（`assign_hypothesis_ids` H1..Hn）替代 title 字符串匹配；semaphore(2) 并发限幅；单条失败降级 UNCERTAIN 不拖垮整批
- ✅ 任务 14 schema 一致性：VulnHypothesis.id / VerificationResult.hypothesis_id / AttackChain.title 落地；confidence 枚举↔float 转换规则写死（high=0.9/medium=0.6/low=0.3）；顺手修掉 `Field(default_factory="")` 隐患（导致 FinalReport.conclusion 实际必填）
- ✅ 任务 6 severity 确定性打底：`apply_severity_floor`——(file_path 归一化, PITAX 规则码) 匹配规则底线，LLM 只能带证据升级；升级条数进 GraphResult/报告 meta
- ✅ 任务 12 eval 回归集：`eval/expected.json`（agent0 12 条按 (file,rule,count) + 定稿 7 条按 (file,vuln_type,min_severity)）+ `eval/check_report.py`（确定性，额外条目仅提示不判败）
- ✅ 任务 11 FP 度量：新建 `demo/clean-repo/`（5 文件含良性 .cursor/rules），实测 pitax/static 均 0 命中；`--clean` 模式验收 FP=0
- 🐛 **计划外修复：CLI 加载器漏扫无扩展名文件**——`.cursor/rules`（AI 助手注入最高危面）被扩展名白名单过滤，dry-run 只读 8 文件丢 4 条 critical 命中；修复后 9 文件 12 命中，风险分 27→43
- ✅ 测试 51/51 全绿（新增 9 项：id 幂等/confidence 规则/拆分对齐/异常降级/文件匹配/打底升级与不造级/eval 正反例）；已提交 `5589f64`
- ⏳ 今日唯一真实 e2e 运行中（`reports/e2e_run_0912.log`）：验证 Scout 增量 + Verify 拆分 + DeepSeek 主判全链路

### 今晚执行日志（9/11 深夜，Windows 侧 `.venv-win`）

- ✅ 0.1/0.2：提交保护完成；新建 Windows venv（strands 1.55.1 / openai 3.13.0 / pydantic 2.13.5）；test_e2e.py 路径可移植化（`Path(__file__).parent`）
- ✅ 任务 1：**发现 `pitax/sanitizer.py` 实为目录扫描器而非 prompt 消毒器**→ 新写 `codeark/graph/quarantine.py` 三层隔离（不可见/Bidi 剥离 + 注入触发词中和 + UNTRUSTED DATA 边界），LLM prompt 用消毒版、工具/Agent0 跑原始版；中间产物（假设/裁决/链 JSON）也再过一遍隔离
- ✅ 任务 2：四个工具模块加 `make_bound_tool(files)` 闭包工厂（空 schema 无参），Scout/Verify 注册绑定版
- ✅ 任务 3：Arbiter 重写——解析失败重试 1 次→确定性兜底定稿（CONFIRMED 机械汇总+conclusion 披露，杜绝静默空报告）；render_report 渲染攻击链/结论/隔离统计/节点降级；去重口径 file_path+vuln_type
- ✅ 任务 4：Deepen 改每链一调 + 严格 JSON 模板 + 括号配平解析器 + 回炉修复 + `ChainList.failures` 降级计数（坏链占位披露，绝不静默 0）
- ✅ 任务 5：Arbiter 构造链 GLM-5.3 PRO 置顶（异构第二票）
- ✅ 任务 7：pipeline 节点级容错——任一 LLM 节点失败落确定性降级路径 + `node_errors` 进报告/摘要/summary.json
- ✅ 确定性测试 39/39 绿（含隔离层 8 项、新解析器、兜底定稿、去重渲染、全节点降级演练）；旧测试裸导入修为 `codeark.` 前缀，repo 根目录 `pytest` 可跑
- ✅ 任务 8：第三次真实端到端跑完（22:07→22:40，EXIT=0，日志 `reports/e2e_run_0911.log` 129KB 归档）。结果：agent0 12 命中 → Scout 8 假设 → Verify 8/8 CONFIRMED → Deepen 8 链（**仅 1 条真实推演，其余 7 条 Kimi 配额 429 走占位披露**）→ Arbiter 定稿 7 条（2 条 invisible-char 条目按 file+vuln_type 合并）→ **risk_score 24 = 3×critical(4) + 4×high(3)，首次基于定稿 findings 计算（旧版恒 22）**；三格式报告齐 + 攻击链区块 + 隔离统计（9 文件中 5 文件消毒、9 处触发词中和）+ 降级披露全部呈现
- 🏆 **抗注入实锤（演示素材）**：Scout 对 `[QUARANTINED]` 声明"其存在本身即可疑信号，如实上报未执行"；Arbiter 把 429 错误消息里内嵌的"请充值"指令样文字与疑似密钥标识判定为"数据块内注入证据，只上报不执行"——模型面对注入诱饵全程只当数据
- 🔴 **P0 阻塞项：Kimi(Moonshot) 账户余额耗尽**（429 insufficient balance），非格式问题。9/12 上午必须解决：Verify/Deepen 切 DeepSeek-V4-Pro 主用（降级链已就位，需真实验证一次工具调用+JSON 质量），Kimi 降备选；保持"≥2 家模型合议"叙事
- 🔒 **凭证脱敏修复**：占位链的 raw 错误节选曾把供应商 `org-…/<ak-…>` 账号标识带进报告文件（HEAD 干净、仅工作区，已就地清洗）；deepen_agent 加 `_redact_creds`（词边界+8 位起，避免误伤 coderisk-arcanum URL），2 条回归测试入库，41/41 绿
- ⚠ 验收线复核：`attack_chains ≥ 10` 不达——本输入 CONFIRMED 上限即 8（每链一调），该阈值定高了；实质缺口是 7/8 占位链等 Kimi 恢复后补跑
- ⏭ 明日顺延：任务 6（severity 打底）；旧 deepen_agent.py.bak-* 系列已忽略不入库

## 明天（9/12）：P1 —— 让评委问不倒

上午做两个**架构级改造**（行为变化大，放端到端跑通之后；各自带回滚线），下午做度量项。

| # | 任务 | 说明 | 验收标准 |
|---|---|---|---|
| 9 | **架构级改造①：Scout 语义增量【增补】** | 基线 findings 作为上下文注入（不再重复调同工具），职责改为"基线之外做语义层发现"：文档投毒意图、跨文件逻辑漏洞、coverage_notes 如实报盲区。**回滚线：中午 12 点无进展即回滚**（叙事收益 vs 行为风险需拍板，见决策③） | e2e 假设数 ≠ agent0 命中数；至少 1 条规则库外假设且能进验证 |
| 10 | **架构级改造②：Verify 按假设拆分【增补 Top3】** | 每条假设独立小调用（假设+相关文件局部+该文件工具结果；工具确定性可 pipeline 预跑）。REFUTED 才有出现空间。时间富余则 asyncio.gather 并行（11 分钟有望压到 2-3 分钟）。**回滚线同上午** | 裁决分布出现 REFUTED/UNCERTAIN；hypothesis↔verdict 用 id 对齐 |
| 11 | **REFUTED 反例 + FP 度量** | demo 干净文件命名 `clean/`（或独立 mini clean repo）；报告干净仓 FP=0 数字 | 与任务 10 合并验收 |
| 12 | **私有 eval 回归集** | 蓝图 §8 预期检出表（4+2+1+1+1+3=12）→ `eval/expected.json` + 校验脚本（确定性） | 脚本对 report.json 跑绿 |
| 13 | **Qwen 处置** | 真实调一次验证，或从 Scout 降级链移除（后者 1 分钟） | 链上无未验证模型 |
| 14 | **schema 一致性小修** | AttackChain 加 title；**VulnHypothesis/VerificationResult 加 id 字段按 id 对齐（替代 title 字符串匹配）【增补】**；confidence 枚举↔float 转换规则写死 | schemas.py 更新，消费方同步 |
| 15 | **factory docstring 过期（GLM-5.2→5.3）** | 5 分钟 | — |

## 9/13：演示与提交日

| # | 任务 | 说明 |
|---|---|---|
| 16 | **叙事对齐实装（重要）** | DEMO-SCRIPT.md 现在写的是 OTEL 面板 / AWS Bedrock / VPC——**均未实装**。按 v2.1 诚实叙事改写：国产模型矩阵 + 多供应商路由 + AMD 免费兜底 + 6 节点工具背书流水线 + Strands 编排。删掉一切未实装承诺 |
| 17 | **录制 2-3 分钟视频** | 钩子（零宽字符闪烁）→ 上传/dry-run 秒出 → 真实端到端逐节点过程（提前录好）→ 报告+**攻击链区块特写**（任务 3 产出）→ sanitizer/降级披露讲成可信度卖点。预生成当天报告防现场超时 |
| 18 | **README 重写** | 以 codeark 主线 + Strands 6 节点叙事；旧目录标注 legacy 不删除（9/18 前不删原则） |
| 19 | **提交前终检** | dry-run + 一次真跑；git tag 留档；zip/ModelScope 空间同步 |

---

## 今晚需要你拍板的 3 个决策

1. **运行环境**：WSL（原 .venv，环境现成）还是 Windows（依赖重装但与当前会话同侧）？→ 影响第 0.2 步。
2. **Arbiter 模型**：换 GLM-5.3（异构、叙事好）还是保持 Kimi（结构化输出更稳，文档写明 trade-off）？
3. **Scout/Verify 架构级改造（任务 9/10）做不做**：做了才兑现"模型优先"叙事、REFUTED 才可能出现；但行为变化大、剩 3 天。我的建议：**做**，各带回滚线，中午止损。

## 明确不做（时间不够，主动砍）

- exec 沙箱/重试退避体系化/DynamoDB 实装/成本预算仪表盘——文档标注"路线图"，不假装完成。
- **memory 前馈接入 pipeline**（蓝图 §5.7）——设计已好但空转，赛后再闭环；答辩如实说"已实现待接入"。
- legacy 代码物理迁移到 legacy/（只做 README 标注，防 import 断裂风险留到赛后）。

## 风险缓冲

- 端到端每次 ~11 分钟且烧免费额度，真跑总共预留 ≤6 次（今晚 2、明晚 2、录制日 2）。
- 若 9/12 晚 attack_chains 仍不达标：降级方案是 Deepen 强制 tool-calling/JSON mode；再不行，视频里用 dry-run 攻击链 + 真跑其余节点，诚实标注。
- 架构级改造（9/10）任一失败 → 回滚到今晚端到端版本，**9/12 18:00 冻结代码结构**，此后只允许文案/配置级改动。

# 复盘：MI300X 本地 e2e 首夜（2026-09-25 晚）

> 范围：本晚从「factory 本地接入编码」到「e2e 三次实跑」的全程问题复盘。
> 配套：WORK_LOG.md（逐时段原始记录）；本文是问题维度的提炼与归档。

---

## 一、今晚成果一览

| 里程碑 | 状态 |
|---|---|
| `ARCA_DEPLOYMENT=local` 本地四阶段路由（factory/routing + 单测） | ✅ eee0de9 |
| README 按实际现状重写（两套模型口径 / 三层结构 / 真实用例数） | ✅ ca4320f |
| Strands×llama.cpp 结构化输出兼容性定性 | ✅ 见 P1 |
| DSW 部署 → preflight 4/4 → e2e 首跑全绿（~10 分钟，零降级） | ✅ |
| test_e2e.py 环境变量接线修复 | ✅ 3f68c83 |
| eval 契约断层修复（报告合并规则行） | ✅ 48436ac |
| .gitattributes 行尾归一 | ✅ 5b5c1e2 |
| Scout 采样稳定化（temperature 0.2 + max_tokens 6000） | ⚠ 已修复待验证（404128f / a1fb327） |

远端 HEAD = `a1fb327`；性能数据点：首跑 ~10 分钟（3 假设）、复跑 40m35s（12 假设，采样病态）——**公平基线数字待稳定后重测**（远程基线 15m07s）。

---

## 二、问题清单

### P1 · Strands 结构化输出 × llama.cpp 兼容性（开工前最大未知）

- **现象/风险**：四个 agent 全走 Strands `structured_output_model=`，机制对 llama.cpp 是否成立未验证（计划遗留查证项）。
- **查证过程**：读本机安装的 strands 源码——`OpenAIModel.structured_output` 走 `client.beta.chat.completions.parse(response_format=pydantic)`，即**非流式 response_format json_schema**；llama-server 原生把 JSON Schema 编译成 GBNF 语法逐 token 约束生成。
- **实拍验证（preflight）**：:8081/:8182/:8083 三端各发一发 json_schema，content 全部为纯 JSON，且 Muse/Qwen/R1 三个思考型模型的 reasoning 通道完好——**语法约束只作用于推理之后的内容**。
- **结论**：Arbiter 原生结构化成立、无需降级；四阶段结构化路径全绿。风险闭环。

### P2 · test_e2e.py 没接环境变量路由（接线缺口）

- **现象**：推进前核实入口时发现 `test_e2e.py` 无参构造 `CodeRiskGraph()` → `stage_models=None` → 落回 legacy 共享模型路径。`ARCA_DEPLOYMENT=local` 对 e2e 入口**不生效**（CLI 入口 `cli.py:88` 是通的，管线本身支持）。
- **修复**（3f68c83）：`main()` 改为 `CodeRiskGraph(stage_models=make_stage_models_from_env())`——env 未设时返回 None，行为不变。
- **验证**：离线断言 graph 绑定 muse-scout@:8081、deepen 带 max_tokens；回归全绿。
- **教训**：README/文档里的命令必须对照实际接线核实，"管线支持"≠"入口接通"。

### P3 · README 全面过时 + 第三方盘点自带错误（69 用例）

- **核实结论**：HEAD、rebrand 后 8 提交、skills/deploy 缺席、DELIVERY_CHECKLIST 过时——均属实；但"69 用例"**错误**：实测 codeark/tests 收集 **84** + 顶层 tests **57** = **141**；verify.sh 实跑子集同样是 84（被 ignore 的三个文件本就 0 用例）。
- **修复**（ca4320f）：README 重写——定位改"两套模型"（API 云端委员会 / MI300X 本地委员会，确定性零 LLM 是运行模式不计入套数）、"two layers"→"three layers"（补 skills/ai-repo-audit）、用例数两处改 84、委员会描述对齐 routing.py 实况、结构树补 skills/deploy/reports/pitax/memory、新增 Self-hosted local council 一节；DELIVERY_CHECKLIST.md 确认无引用后 `git rm`。
- **用户两点修正**：①传智杯出身表述去除（Origin→Provenance，只留 upstream 锚点）；②单机适配层（local_step/Nemotron/XML 格式）降级为"not part of either current setup"附注。

### P4 · eval 检查器 7 条 FAIL —— 契约断层，不是质量退化

- **现象**：`check_report.py` 报 7 条 `final finding missing: xxx [PIT-*]`；但 agent0 层 12/12 全过。
- **根因考古**：expected.json + 检查器是 **Day-2 sprint**（四阶段委员会重构**之前**）定的契约——定稿 findings 本该 = 确定性规则行（PIT-\*）+ LLM 语义增量（"extra, allowed" 注释即为此设计）。铁证：expected 要求 `src/rewards.py` 两条——**没有任何假设覆盖它们**，规则行必须独立进定稿列表。委员会重构后 `render_report` 只取 FinalReport.findings，规则行掉出定稿列表。
- **修复**（48436ac）：`render_report` 从 `meta.agent0_findings` 并入规则行（补 `file_path`/`vuln_type` 别名键贯通 SARIF/MD；同 (file, rule) 去重保留最高 severity），JSON/SARIF/Markdown 三格式同步受益。
- **教训**：**eval 契约必须随架构重构同步迁移**，否则质量门会对着幽灵契约报警。

### P5 · GitHub push 间歇性网络病

- **现象**：多次 `Recv failure: Connection was reset` / 443 连接超时，当晚反复出现；`80fd0e0..3f68c83` 一笔在我重试后成功，`3f68c83..48436ac` 由用户在 Windows 端手动 push 成功，后续基本顺畅。
- **处置**：本地 commit 先落袋、push 异步补；Windows 端与 DSW 侧均可作为备用 push/pull 通道。
- **提醒**：`.env.example`（含真实密钥）永远在排除清单里，任何时候 `git add .` 都是禁区。

### P6 · CRLF 行尾入库（1573 行 diffstat 惊魂）

- **现象**：DSW `git pull 404128f` 的 diffstat 显示 factory.py 1573 行变更，而温度修复实际只动 ~21 行。
- **查证**：`git cat-file` 逐字节对比——`404128f` 把 factory.py 以 **CRLF** 存入 blob（Windows 端提交、autocrlf 未归一），前一笔是 LF；`--ignore-cr-at-eol` 差异 = 21 行，语义零变化。Python 对行尾不敏感，功能无损。
- **修复**（5b5c1e2）：`.gitattributes` 追加 `*.py text eol=lf` + **路径限定** `git add --renormalize "*.py"`。
- **关键规避**：renormalize **绝不**用 `git add .` / 全路径——`.env.example` 含真实密钥且工作区有未暂存修改，全量 renormalize 会把它卷进提交（记忆中的误暂存陷阱）。
- **验证**：其余 .py `ls-files --eol` 本就 LF；新提交出现 "CRLF will be replaced by LF" 警告 = 属性按预期生效。

### P7 · 采样不稳定 #1：Scout 假设回显（复跑 40m35s）

- **现象**：temp=1.0 下 Muse 陷入手算 base64 兔子洞（手算出 0xF0/0x87 垃圾字节并自我怀疑），最终把 12 条规则命中**逐条回显**成假设（`"PITAX rule deterministic hit (dry-run placeholder)"`），而非首跑的 3 条语义增量。下游 Verify×12、Deepen×11 全部翻倍 → **40m35s vs 首跑 ~10 分钟**。
- **连锁质量损失**：H9（config.py 密钥外泄链，全仓库最有价值的发现）被 Verify 判 UNCERTAIN、被 Arbiter 排除——根源是 Scout 的假设描述已被错误解码污染。确定性工具明明已 `decoded_payload` 实锤。
- **管线鲁棒性反证**：12 假设全程零降级；severity 打底按设计抬回 2 条被降级条目；报告完整落盘；risk_score 20 可完全追溯到 findings 数量。
- **修复 #1**（404128f）：`EndpointConfig.temperature` 字段（[0,2] 校验、0 合法）+ chat_completions params 注入 + 本地表 Scout=0.2 + `ARCA_<STAGE>_TEMPERATURE` 覆盖。
- **口径警告**：40m35s 与远程基线 15m07s **不可比**（假设数 12 vs ~3），公平数字必须等采样稳定后重测。

### P8 · 采样不稳定 #2：病态复读循环（重跑实拍）

- **现象**：temp=0.2 后 Scout 对 `LEGACY_MIGRATION_TOKEN`（demo 生成器用同一段 base64 模式重复数百遍构造的载荷，对语言模型是天然复读诱饵）陷入 **degenerate repetition**——同一 64 字符单元逐字吐上千遍。
- **两个教训**：①更低温度更难跳出循环 attractor（0.2 比 1.0 黏）；②同一个毒 token 两次发作形态不同（1.0=手算兔子洞，0.2=纯复读）——**它对 Muse 有毒，与温度无关，只看概率与形态**。
- **兜底链**：Scout 300s 客户端超时 → `⚠ Scout 失败，降级为规则基线假设` → 管线继续。但降级基线也是 ~12 条 → 后续又是 35 分钟，故实拍时建议见 ⚠ 即 Ctrl-C。
- **修复 #2**（a1fb327）：Scout `max_tokens=6000` 硬帽——健康输出（reasoning ~2-3K + 假设 JSON ~1.5K）足够；病态复读最多 ~3 分钟被 length 截断、干净降级，不耗满超时、不冲爆上下文。
- **下一杠杆（若复读仍在）**：`frequency_penalty` / `presence_penalty`（llama.cpp params 原生支持）或 Scout prompt 加"禁止逐条回显基线"约束；temp 回调 0.5 亦是备选。

### P9 · 良性噪音存档（非故障，避免误判）

- `reasoningContent is not supported in multi-turn conversations...`：llama.cpp 对多轮回传 reasoning 字段的提示，流式输出中反复出现，**未影响任何节点**。
- 解释器退出时 `httpcore2 ... RuntimeError: generator didn't stop after athrow()` asyncgen 堆栈：发生在报告落盘**之后**的清理阶段，无害。
- oneclick 脚本在新实例重下 48G 权重（~21 分钟）+ Muse 持久区秒复制 + 30 秒四服务就绪 + VRAM 87.3G 与基线一致——自愈路径按设计工作。

---

## 三、未闭合事项（下次会话入口）

1. **Scout 行为终验**：temp 0.2 + 6000 帽下重跑——假设数应回归 3±1；若帽内截断降级 → 上 penalties；若假设回显 12 条仍在 → Scout prompt 约束。
2. **eval PASS 确认**：对最近一次完整报告跑 `python eval/check_report.py --report reports/e2e_report.json`（含 48436ac 修复，预期原生 PASS）。
3. **公平计时**：稳定后 `time ARCA_DEPLOYMENT=local python -u test_e2e.py` 对比远程基线 15m07s（首跑 ~10 分钟是当前最好的参考点）。
4. 低优先遗留：probe_concurrency 本地档位、llama.cpp 构建 commit 补录、KV q8_0 实验。

## 四、经验教训提炼

1. **采样参数是本地小模型管线的一等工程问题**。云端大模型对温度/重复不敏感的默认假设，在 34 tok/s 的本地 26-32B 模型上全部失效：每个 LLM 阶段都必须有 **token 上限 + 时间上限双界限**，且降级路径要真跑过一遍。
2. **极端 demo 样本是免费的鲁棒性测试集**。重复型 base64 载荷把复读边界、长推理预算、确定性工具与 LLM 判断的分工全部实测了一遍——这些坑修在本地，全路径（含远程）受益。
3. **质量门的契约要跟着架构走**。eval 期望集建于旧架构，委员会重构后无人迁移，第一次真跑就 7 条 FAIL——报警时先考古契约，再怀疑质量。
4. **Windows 开发 + Linux 部署的行尾问题用 .gitattributes 从根上治**，renormalize 必须路径限定（密钥文件永远隔离在外）。
5. **文档口径要跟代码实况对表**：README 的测试数、模型清单、入口命令——每一项都值得一次 `以当前情况为准` 的核实（今晚纠正了"69 用例"的二手错误，也发现并修复了 test_e2e 接线缺口）。

---
*生成于 2026-09-25 收官；对应 WORK_LOG 当晚全部区块。*

# v1.2 真实 OSS 仓 FP 率标定 — 候选仓清单 v1

> 任务来源：ROADMAP v1.2 #1（登记册 #5）——3-5 个真实仓库全链 + 人工核 FP；
> 与 IC27 用户验证证据（评分 30%）+ 推广 Demo 素材三线收敛。
> 本文档=DSW 实例开跑前的选型产出，全部数据为 GitHub REST API 实测（2026-10-07，
> unauthenticated `repos`/`contents`/`git-trees?recursive=1` 三端点，本地 Windows Git Bash）。
> 与 C3 基率标定（rule-mining/，awesome-cursorrules 等语料仓）区分：本批**只收真实产品仓**。

## 一、准入门槛（扫描面实证）

- 扫描扩展白名单 `SCAN_EXTENSIONS`（codeark/pitax/sanitizer.py:31）：`.md .mdc .cursorrules .txt .toml .cfg .ini`
- AI 配置路径特判 `is_ai_config_path`：`.cursor/rules`、`CLAUDE.md`、`.cursorrules`、`copilot-instructions.md`、`AGENTS.md`、`.agents/`
- **硬门槛：根目录或 `.github/` 必须持有至少一个 AI 指令文件**，否则全链跑空卷（无靶面）

## 二、选型标准（5 条）

1. 真实产品仓（非 awesome/规范/教程仓）；
2. 过准入硬门槛（AI 指令文件在库）；
3. 体量分级覆盖（全文件数百→数千，对齐 variant-25 全链 907.5s 成本经验）；
4. 语言/域多样性 + AI 配置范式多样性（AGENTS.md 根文件 vs `.agents/` 技能目录 vs copilot-instructions）；
5. License 允许克隆/扫描/引用（permissive 优先，供 IC27 证据与推广 Demo 引用）。

## 三、候选实测表（2026-10-07 API 实测）

| 仓 | 语言/域 | License | 仓体积 | 全文件 | 扫描面文件 | AI 配置持有 | 判定 |
|---|---|---|---|---|---|---|---|
| axios/axios | JS/HTTP 库 | MIT | 29MB | 578 | 159 | AGENTS.md + .github/copilot-instructions.md（双范式） | **正选 1** |
| pydantic/pydantic | Python/数据校验 | MIT | 469MB | 928 | 129 | .agents/skills/（SKILL.md 新范式） | **正选 2** |
| astral-sh/uv | Rust+Python/打包工具 | MIT/Apache-2.0 | 216MB | 2234 | 613 | AGENTS.md + agents/（config.toml+hooks 脚本） | **正选 3** |
| pandas-dev/pandas | Python/数据科学 | BSD-3 | 415MB | 2959 | 49 | AGENTS.md（单持稀疏） | **正选 4**（兼近干净仓对照） |
| neovim/neovim | C/编辑器 | Apache-2.0 | 402MB | 4167 | 205 | AGENTS.md | 替补（语言多样性用） |
| langchain-ai/langchain | Python/AI 框架 | MIT | 610MB | 3749 | 103 | AGENTS.md | 替补（IC27 域相关性最高；clone 体积大） |
| microsoft/vscode | TS/编辑器 | MIT | 1.5GB | 未细测 | 未细测 | AGENTS.md + .agents/ | 不推荐首选（体积过大） |
| openai/codex | Rust/TS CLI | — | 668MB | — | — | 根目录与 .github/ 均无 | 未过准入 |
| fastapi/fastapi | Python/Web | — | 55MB | — | — | 根目录与 .github/ 均无 | 未过准入 |
| gin-gonic/gin | Go/Web | — | 10MB | — | — | 根目录与 .github/ 均无 | 未过准入 |

**负结果同样有信息量**：三成熟仓（codex/fastapi/gin）零 AI 配置文件——AGENTS.md 协议普及率并非全覆盖，
"扫描空仓=零成本零风险"本身就是 FP 标定的对照事实（记入报告背景节）。

## 四、推荐执行名单（按 DSW 跑批顺序）

**axios → pydantic → uv → pandas**（4 仓，覆盖全文件 578→2959 四档、JS/Python/Rust 三语言、
三类 AI 配置范式、扫描面密度 49→613 两极）：

1. **axios**：最小成本首发，JS 仓验证管线语言无关性；双范式持有；
2. **pydantic**：`.agents/skills/SKILL.md` 新范式首例——对规则矿（C3 候选⑤编码载荷/③多通道冗余）是新形态实弹；
3. **uv**：扫描面最大（613），`agents/hooks/*.py`（AI 钩子脚本）为规则从未触达的文件形态，压测扫描面覆盖；
4. **pandas**：扫描面最稀（49，AI 配置单持）≈ 真实世界"低暴露仓"对照组——预期低 findings，验证管线不空转不误报。

替补启用条件：正选中任一仓确定性扫描零 findings 且人工核无价值 → 换 neovim（换语言域）。

## 五、FP 标定协议草案（对齐既有方法学）

- **阶段 1 确定性扫描**：PITAX 9 规则全仓扫描（秒级），记 findings/千文件密度——兼作全链成本探针（findings≈0 的仓先换后跑）；
- **阶段 2 全链六节点**：`ARCA_DEPLOYMENT=local` + `ARCA_VERIFY_TEMPERATURE=0`（gate v1.1 钉死新知）+ laya-r6 gate 臂（预注册同 gate11 口径）；
- **阶段 3 人工核 FP**：每条 CONFIRMED 逐条源码复核；FP=规则/模型命中但无恶意语义；
  REFUTED-on-intended（K1 口径）单列不混入 FP 率；
- **产出指标**：per-仓 FP 数、FP 率=FP/总 findings、误报形态学归类（喂登记册 #5 + 规则矿观察名单）；
- **联动红利**：真仓实弹 CONFIRMED 证据同时喂 C3 候选规则双门槛（跨 ≥2 仓 ∧ FP=0）——一次跑批两账收益；
- **落账**：跑批日志+判读表落 `reports/v12-fp/<repo>/`，EVAL-LEDGER 回填（纪律：git status --ignored 防静默吞件）。

## 六、风险与缓解

- 全链时长未知（variant-25=907.5s 是唯一锚点，doc 密集仓可能更长）→ 阶段 1 探针前置 + 单仓顺序跑不并行；
- langchain/vscode 体积大 clone 慢 → 已排替补/不推荐；
- API 实测数字会漂（仓在演进）→ DSW 开跑当天 `git clone --depth 1` 后以实际 checkout 重记数字为准；
- axios 默认分支=v1.x（非 main/master），clone 与判分脚本按分支名参数化。

## 七、执行结果（2026-10-07，DSW 实跑）

**结论：四真仓语义层 FP=0（登记册 #5 销号）；副产品=Scout 输入预算帽落地。**

| 仓 | 阶段 1 确定性 | scan-surface 实测 | 阶段 2 假设 | CONFIRMED | 链 | node_errors |
|---|---|---|---|---|---|---|
| axios | 0 命中 | 159 | 0 | 0 | 0 | {} |
| pydantic | 0 命中 | 128 | 3 | 0 | 0 | {} |
| uv | 0 命中 | 613 | 3 | 0 | 0 | {} |
| pandas | 0 命中 | 49 | 1 | 0 | 0 | {} |

- **阳性对照**（防"零命中=仪器瞎"）：vuln-demo 12 hits PASS（check_report 全覆盖无降级）+ variant-23 findings 7/chains 14 与历史锚一致；
- **gate 臂注记（当日两段更新）**：首轮四仓 gate 未激活（CLI 未装配 hypothesis_gate）→ 87e3e38 补齐接线 → pandas 复验臂生产激活实锤：armed laya-r7、enabled=True、重排 [H2,H3,H1] 且 H1 判 degenerate 沉底、CONFIRMED=0 保持。FP=0 结论两口径（nogate 复核数据 + gate 复验臂）一致；
- **过程发现**：axios 首跑 Scout 全量注入 908,615 tokens 撑爆 98,304 ctx（400 降级，90 秒空卷）→ 修复=总量预算帽 `ARCA_SCOUT_MAX_TOTAL_TOKENS`（默认 60000，AI 配置优先+小文件优先确定性装填+超预算整文件跳过披露，73d0b46，回归锚 5 测试）；重跑 199 files/~59,891 tokens、247 skipped；
- **假设质量注记**：pydantic 首假设=".github/zizmor.yml 显式禁用密钥泄露检测规则"（CONFIG_MISCONFIGURATION）——真实安全卫生观察，验证层未升级为 CONFIRMED（禁用扫描规则≠漏洞，判得克制）；
- 原件：**IN-REPO** `reports/v12-fp/`（bundle8=d145ba6，22 件）+ DSW `/mnt/workspace/runs/20261007-v12-fp/` 持久区副本；台账=EVAL-LEDGER 2026-10-07 行。

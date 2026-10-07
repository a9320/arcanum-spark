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

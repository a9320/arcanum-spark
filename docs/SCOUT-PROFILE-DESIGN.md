# SCOUT-PROFILE-DESIGN — 双 Scout（Muse 默认套 / step-5 专设套）设计稿 v1

日期：2026-10-15 ｜ 状态：已实施（同 commit） ｜ 前置证据：DSW 10-13/10-14 两晚 A/B 实弹 + StepFun 官方文档查证
提案人：用户 ｜ 评估与实施：ZCode 会话（WORK_LOG 10-15 块）

## 1. 背景证据链（三源）

1. **两晚死法一致**：step-5 云 Scout 死因=墙钟哨杀（25/30min），`maxtok=0`、死时正式 HypothesisSet 未发出（B 臂 22:03-22:28 exit=124；round3 276KB log 哨杀于 VERIFY 段）。思考型把预算烧在草稿梯子（H1-H12）与推理上。
2. **StepFun 官方文档【实证】**：step-5-preview 为思考型模型；Chat Completions 支持 `reasoning_effort`（low/medium/high 三档，无数值 budget）；`max_tokens` 默认 INF；Messages API 用 `output_config.effort`。
3. **代码事实（0bdd13d 实读）**：
   - 云 Scout 默认路由（`_REMOTE_ROUTE_DEFAULTS["scout"]`）= step-5-preview @ api.stepfun.com，**`reasoning_effort` 默认已是 `medium`**——两晚 B 臂死于 medium 档；
   - `reasoning_effort` 管线**全线预埋**：named/local 路由均支持 `ARCA_SCOUT_REASONING_EFFORT` 覆盖 → `_reasoning_params()` 按 API 风格映射（chat_completions → 请求体 `reasoning_effort` 字段）；`default`/空=不发参数（零行为变化）；
   - **`ARCA_SCOUT_MAX_TOKENS` 在 named 路由与 legacy stage 路径均无消费点（安慰剂旋钮）**——在册"20000 帽未用满"实为"帽从未存在"，真实状态=无帽（服务端 INF）。本设计补透传使在册旋钮真实生效。

## 2. 目标 / 非目标

- **目标**：step-5 在 Scout 岗于墙钟内交出正式卷；把"模型选型问题"改造为"管线参数化问题"；Muse 默认路径**零行为变化**（K1 基线可比性）。
- **非目标**：不做管线两跳拆分（Scout 先交集再深挖，改动大，挂观察）；不动 verify/deepen/arbiter；不改 HypothesisSet schema。

## 3. 设计红线（不可违背）

1. **产出 schema 不分叉**：双套共用 `structured_output_model=HypothesisSet`，判分器/verify/账目零分叉。
2. **default prompt 字节不变**：`SCOUT_PROFILES["default"] is SCOUT_SYSTEM_PROMPT`（单测锁定）。
3. **不发射=零旋钮**：`reasoning_effort` 未显式设置时请求体不出现该字段（`_reasoning_params` 既有语义，不动）。

## 4. 设计（三件套）

### 4.1 手段 b（API 级思考预算）= 零代码 + 透传补齐

- DSW env 一行生效：`ARCA_SCOUT_REASONING_EFFORT=low`（named 路由既有支持）。
- **factory.py 补齐两处透传**：①`_endpoint_from_named_route` 增 `max_tokens`/`temperature`；②`_env_endpoint_config`（legacy stage 路径）增 `reasoning_effort`/`max_tokens`/`temperature`——`ARCA_SCOUT_MAX_TOKENS` 从安慰剂变真旋钮（默认 None=不变）。

### 4.2 手段 a（prompt 预算纪律）= profile 机制 + step5 变体

- `scout_agent.py`：`SCOUT_PROFILES = {"default": SCOUT_SYSTEM_PROMPT, "step5": SCOUT_SYSTEM_PROMPT_STEP5}`；`build_scout_agent/run_scout` 增 `profile` 参数；默认取 `ARCA_SCOUT_PROFILE` env（缺省 `default`，未知值报错快败）。
- step5 变体核心条款（对症两晚死法）：
  - **岗位收敛**：Scout 只产假设集，论证深度留给 Verify 节点（管线本有 verify）；
  - **墙钟自警**：明示本次调用有硬墙钟，思考深度服从产出纪律；
  - **草稿预算**：候选草稿 ≤5 条、每条 ≤3 行要点；收敛 2-4 条主线假设；
  - **经济输出**：直接产出 HypothesisSet，禁止输出前长篇推理文档；
  - 保留原铁律四条（suggested_verification / coverage_notes / 经济引用 / UNTRUSTED）。

### 4.3 单测锚（tests/test_scout_profile.py）

- default profile 同一性（红线 2）；step5 变体含预算纪律关键词；未知 profile 快败；named 路由 `REASONING_EFFORT`/`MAX_TOKENS` env 覆盖生效；legacy 路径同。

## 5. 预注册实验矩阵（DSW 端，规则矿纪律：每跑必记）

| 臂 | 配置 | 状态 |
|---|---|---|
| Muse×default | env 不动（本地 muse-scout） | 三题探针 10-15：Scout 语义 3/3 全 TP（verify 降级=探针口径）；干净版判读中 |
| step5×default | 无 REASONING_EFFORT/PROFILE env（=medium、原 prompt） | **两晚双杀数据**（对照） |
| step5×step5-profile | `ARCA_SCOUT_REASONING_EFFORT=low` + `ARCA_SCOUT_PROFILE=step5` | **✅ 10-15 实测存活**：gi ~1min 正式卷 16105B/5 假设/H1=官方链（含 @admin_only 维度）；泛化待 3q |
| step5×medium-profile（可选第二臂） | 仅 `ARCA_SCOUT_PROFILE=step5` | 待跑（low 是否牺牲深度=开放问题） |

**10-15 判读**：预注册规则①触发——产出✓+召回≥Muse✓ → step5 Scout 存活，混合臂 v2（并集）重开评估；定案④修正为"medium 档超预算，low 档+收敛纪律不超"。**注意：10-15 两臂 verify 均为规则兜底降级（配方漏 ARCA_DEPLOYMENT=local，已固化为 scripts/run-arm-*.sh），CONFIRMED 判词探针口径，tp/fn 定账待干净重跑。**

**判据（预注册，窗口前不改）**：主判据=正式卷产出（exit=0 且 report bytes>10000 且无 node_errors）；副判据=墙钟 <25min、假设数、判分器 tp/fn（Muse 卷对照）。
**裁读规则**：①低档卷产出且召回 ≥Muse → step5 Scout 存活，混合臂 v2 重开评估；②低档卷产出但召回塌方（显著劣于 Muse）→ 支持"思考型不适合 Scout 岗"在册定案，step5 转 Verify/Arbiter 岗实验；③低档仍哨杀 → 墙钟是唯一约束，两跳结构（非目标项）升级立项。

## 6. 风险与回退

- Muse 路径风险=0（default profile 字节不变 + 不发 reasoning_effort；本地 llama-server 原本就忽略该字段）。
- `reasoning_effort=low` 可能削掉 step5 的深度优势本身——这正是实验要测的命题，判读规则 ② 兜底。
- 回退：删 `ARCA_SCOUT_PROFILE` env 即回默认套；代码层 default 路径无任何新分支。

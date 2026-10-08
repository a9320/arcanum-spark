# Gate v2 设计 —— 预算帽姿态（ROADMAP v1.2 #2）

> 状态：**设计稿（未实现）**。§5 验收判据与 §6 实验计划为**预注册**内容——实施与跑批前不改。
> 数字全部来自仓内归档（`reports/`）与 `docs/EVAL-LEDGER.md`，未标注来源的数字一律不采信。

## 1. 目标与现状

v1 gate 是**只重排不删**层：`codeark/graph/gate.py:rerank_hypotheses` 返回深拷贝并排序，
`pruned_ids` 恒为空（`gate.py:169`），pipeline 把该副本交给 Verify
（`codeark/graph/pipeline.py:255-281`），原始 Scout 集另存 `meta.hypothesis_set` 备审计。

v2 的目标：**在同样的裁决质量下少花验证预算**——即把"重排"升级为"选择"，
把不该花 Verify 的假设在进入 Verify 之前剪掉，同时保留完整的可审计剪枝记录。

## 2. 预算模型（为什么值得做）

- **预算单位 = `verify_requests`**。Verify 是**逐假设独立小调用**
  （`codeark/agents/verify_agent.py:316 run_verify_split`，默认 `max_concurrency=1`），
  所以 `verify_requests == len(假设集)`——归档实测全部吻合：variant-23 臂 6 假设/6 请求、
  variant-27 臂 5/5、deterministic 臂 6/5。
- **成本不对称**：gate 自身打分中位 **20.2–22.6 ms/假设**（r3/r5 实测，`timing-r*.json`），
  而一次 Verify 是带工具证据的完整 LLM 调用（量级数十秒）。gate 不是成本，Verify 才是。
- **剪枝有复利**：Deepen 对每条 CONFIRMED 推演攻击链（`pipeline.py:320-331`），
  剪掉一条"会被 CONFIRMED"的假设同时省下 1 次 Verify + 1 次 Deepen——
  这正是必须由 §5 P4 守住的地方。

## 3. 剪枝姿态设计

三种姿态，同一套机制（`prune_mode` 单选，缺省 `off` = v1 语义）：

| 姿态 | 剪枝集合 | 风险 | 证据基础 |
| --- | --- | --- | --- |
| A `structural` | echo ∪ duplicate ∪ degenerate | 结构性最低（§4 论证） | 归档 21 假设实测：命中 1 条 |
| B `threshold` | 叠加 `score < tau` | 中（τ 决定） | hard-exam v2：AP=1.0、FN=0 支持 τ=0.5 |
| C `cap` | 叠加 `rank > max_keep` | 中（K 决定） | 同上；K 必须 ≥ 典型假设数 |

**硬不变量**（任一违反即视为 gate 失败，pipeline 走既有 fallback 路径）：

- **I1 子集性**：`kept ⊆ original`，id 不变、不新增、不重编号。
- **I2 保护优先**：`protected`（有 decoded_payload 实锤且非 echo）**永不剪**。
- **I3 echo 前提**：仅当 `(file, vuln_type)` 命中 agent0 基线键时才可判 echo——
  该规则行会在渲染层被回注（§4），故对规则层无损。
- **I4 duplicate 保首**：同内容键保留 index 最小者。
- **I5 地板**：`min_keep`（缺省 1）保证不剪到空集。
- **I6 原集留档**：`meta.hypothesis_set` 仍存全量；被剪假设可用
  `--hypotheses-from` 钉集重放复核（`eval/run_gate_e2e.py:143`）。
- **I7 预注册**：B/C 姿态必须显式给出 `tau`/`max_keep`，且写进 gate 元数据；
  禁止在 e2e 结果上回头调参。

**元数据契约**（gate 元数据新增字段，渲染层原样落 `meta.gate`）：

```
prune_mode: "off" | "structural" | "threshold" | "cap"
tau / max_keep / min_keep: 数值或 null
pruned_ids: [...]            # 剪掉的 id
prune_reasons: {id: "echo"|"duplicate"|"degenerate"|"below_tau"|"over_cap"}
kept_ids == selected_ids     # 进入 Verify 的集合
budget: {candidates, kept, pruned, saving_ratio}
```

旋钮：`ARCA_GATE_PRUNE`（off 缺省）/ `ARCA_GATE_PRUNE_TAU`（0.5）/
`ARCA_GATE_PRUNE_MAX` / `ARCA_GATE_PRUNE_MIN_KEEP`（1）。非法值走既有"显式失败"策略
（`gate_factory.build_gate_from_env` → `(None, reason)`，无 gate 继续扫，不静默回落）。

## 4. 安全性论证：为什么 A 姿态对规则层无损

- **规则行在渲染层回注**：`codeark/agents/report_agent.py:259-272` 把
  `meta.agent0_findings` 逐条并入 findings（`findings = dedup([*rule_rows, *findings])`），
  且 `apply_severity_floor` 保证规则级别只升不降。所以一条 echo 假设被剪，
  **它的 (file, rule) 结论仍在报告里**——Verify 对它本来就买不到新东西。
- **反向证据（必须承认的损失面）**：语义增量假设（无 agent0 备份）被剪就真的消失。
  variant-23 活标本：`H3 src/privileges.py LOGIC_ERROR` 与 agent0 的
  `src/privileges.py PIT-E-54` **同文件不同漏洞**，H3 被 CONFIRMED——
  这正是"按文件级判 echo"会误剪的反例，故 I3 只认精确键。
- 因此 A 姿态的剪枝面 = 三类构造性冗余；B/C 姿态的剪枝面包含真语义增量，
  只能靠 §5 P4 + §6 的 exam FN=0 双重把关。

## 5. 验收判据（P 系列 v2，替换 v1 的 P1）

对照器 `eval/compare_gate_e2e.py` 现状判 P1 reorder-only / P2 no-fallback /
P3 quality-floor / P4 confirmed-coverage。v2 增补（按 `meta.gate.prune_mode` 分支）：

| 判据 | 内容 | 说明 |
| --- | --- | --- |
| P1' subset-integrity | `kept ∪ pruned == original` 且 `kept ∩ pruned == ∅`、id 不新增 | 取代 reorder-only；`off` 模式下退化为原 P1 |
| P2 no-fallback | 不变 | `gate.fallback == False` |
| P3 quality-floor | 不变 | `confirmed` 与 `final_findings` 均 ≥ 无 gate 基线 |
| P4 confirmed-coverage | 不变（**召回守门员**） | 基线 CONFIRMED ⊆ 臂 CONFIRMED；剪错真威胁在此暴露 |
| P5 budget | `verify_requests(臂) == len(kept)` 且 `≤ 基线 − len(pruned)`；报告 saving% | `pruned=0` 时记 N/A（不算失败） |
| P6 rule-layer preservation | 基线 `meta.agent0_findings` 的每条 (file, rule) 键仍出现在臂 `findings` | 自包含实现（`eval/expected.json` 是 demo 仓专用，不能复用） |
| P7 prune-whitelist | `structural` 模式下 `prune_reasons` 仅含 echo/duplicate/degenerate | 防"结构性姿态"偷偷按分数剪 |

通过 = P1'–P4 全 True（P4 不得为 False）+ P6/P7 True + P5 按模式判定。

## 6. 预注册实验计划

**第 0 步（本地，零 LLM，先做）**：τ 标定。用 `reports/hard-exam-v2/gate_dataset_hard.json`
（24 项 = **KEEP 6 / PRUNE 18**：ECHO 6 + PARA 6 + BOUND-B 5 + REDUN 1；KEEP = 5×BOUND-K + H9）
扫 τ ∈ {0.2, 0.3, 0.4, 0.5, 0.6, 0.7}，记录"KEEP 被误剪数（FN）"与剪枝率；
**τ=0.5 的准入线 = FN=0**（r7 在 AP=1.0/FN=0 下应满足）。τ 一旦选定，写进实验记录，e2e 阶段不改。

**第 1 步（DSW，四服务）**：两考仓 variant-23/27，**钉假设集**（`--hypotheses-from`
指向无 gate 基线报告），消除 Scout 漂移：

| 臂 | 姿态 | 目的 |
| --- | --- | --- |
| Arm 0 | off（v1 现状） | 基线复核（应与归档逐位一致） |
| Arm 1 | structural | A 姿态无损性实证（期望 P4/P6 全 True） |
| Arm 2 | threshold τ=标定值 | B 姿态收益实证（期望 P4 True + P5 有节省） |
| Arm 3（可选） | cap K=4 | C 姿态对照 |

**反作弊三条**：① τ/K 在 Arm 2/3 跑之前确定；② 各臂共用同一钉假设集，禁止"每臂各自 Scout"；
③ 结果不达 P4 就 REJECT 并回滚到 `off`，不许改判据。

## 7. 归档证据实测（诚实基线：v2 今天能省多少）

| 报告 | 假设 | echo | duplicate | degenerate | A 姿态剪枝 |
| --- | --- | --- | --- | --- | --- |
| variant-23_gate_laya | 6 | 0 | 0 | 0 | 0 |
| variant-27_gate_laya | 5 | 0 | 0 | 0 | 0 |
| v12-fp/pandas-e2e-gate | 3 | 0 | 0 | 1（H1，score −749） | 1 |
| v12-fp/pydantic-e2e | 3 | 0 | 0 | 0 | 0 |
| v12-fp/uv-e2e | 3 | 0 | 0 | 0 | 0 |
| v12-fp/pandas-e2e | 1 | 0 | 0 | 0 | 0 |
| v12-fp/axios-e2e | 0 | – | – | – | 0 |
| **合计** | **21** | **0** | **0** | **1** | **1（4.8%）** |

两条必须写进结论的读数：

1. **echo/duplicate 在真仓上零命中**：Scout 的 `vuln_type` 是语义名（`LOGIC_ERROR`、
   `PROMPT_INJECTION`…），agent0 规则行是 PIT 码（`PIT-E-54`…），精确键几乎不可能相等——
   exam 上的 ECHO/PARA 家族（构造时用 PIT 码）可被结构性识别，**真仓的冗余识别不到**。
2. **τ 姿态在真仓上同样零剪**：真仓假设分集中在 0.92–1.0（pandas 例外是 degenerate 惩罚），
   τ=0.5 不触发；exam 上同 τ 剪 18/24（75%）。

**结论（不粉饰）**：gate v2 的预算收益是**分档的**——当前四真仓语料 ≈ 4.8%（1/21），
收益窗口在"Scout 过度产出"的区制（echo/冗余批、大仓多假设、exam 型构造）。
把"省预算"写成常态收益会失真；v2 的真实价值 = ①把剪枝做成可审计机制（元数据+子集不变量+白名单），
②给大仓一个显式预算帽旋钮，③把"哪些冗余能安全剪"这件事用归档证据钉死。

## 8. 实现点清单（下一步，机械可执行）

1. `codeark/graph/gate.py`：`rerank_hypotheses(..., prune_mode="off", tau=0.5, max_keep=None, min_keep=1)`
   → 计算剪枝集、`copied.hypotheses = kept`、元数据按 §3 契约扩字段；`off` 分支保证
   `pruned_ids == []` 且集合不动（现有断言 `codeark/tests/test_gate.py:55`、
   `test_gate_factory.py:70` 保持绿）。
2. `codeark/graph/gate_factory.py`：新增 `resolve_prune()` 解析四个旋钮（非法值抛错，
   由 `build_gate_from_env` 收口为 `(None, reason)`）；`make_laya_gate` /
   `make_deterministic_gate` 的闭包把姿态转发给 `rerank_hypotheses`。
3. `codeark/graph/pipeline.py`：加 I1/I2 防御性校验（越界即 `fallback=True` 并记录原因），
   剪枝字段随 `res.gate` 进报告 meta（现路径已透传）。
4. `eval/run_gate_e2e.py`：加 `--prune/--tau/--max-hypotheses`；summary 增 `pruned`、`budget_saving`。
5. `eval/compare_gate_e2e.py`：按 `prune_mode` 分支判 P1'，新增 P5/P6/P7；MD 表加 Pruned/Saving 两列。
6. 测试：`codeark/tests/test_gate.py`（白名单/保护不剪/地板/子集/off=无操作）、
   `tests/test_gate_v12.py`（旋钮校验+工厂透传）、`tests/test_gate_compare.py`（P5/P6/P7 判定）、
   `tests/test_gate_runner.py`（CLI 透传）；同步 `scripts/test_count.py` 锚（当前 308）。

## 9. 风险登记

- **R1 τ 误剪真语义增量**（无 agent0 备份）→ 守：exam FN=0 准入 + P4 + τ 预注册。
- **R2 结构性姿态在真仓欠火**（实测 0 命中）→ 明确**不做**"按文件级判 echo"：
  variant-23 H3 是反例（同文件不同漏洞且被 CONFIRMED）；词表归一化留待后续单独立项。
- **R3 剪枝改变 Arbiter 输入**（假设变少，结论文本可能变）→ 只作观测项，不进判据。
- **R4 cap 与 Scout 噪声交互**（登记册 #7：pandas 假设 1→3 漂移）→ K 必须 ≥ 典型假设数，
  否则 cap 变成"按噪声剪枝"。
- **R5 语料太小**（21 假设）→ 任何百分比都必须标注语料规模，禁止外推为"生产节省 X%"。

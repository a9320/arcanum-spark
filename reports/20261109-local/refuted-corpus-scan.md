# REFUTED 实体采集（本地归档扫描）— 2026-11-09

> 目的：执行单 §10 待办第 5 项 / 设计稿 D5「真机 FinalReport 出 refuted_on_intended 实体」的
> 前置材料。块 4 三仓（variant-23/27/pandas）11-08 真跑零 REFUTED，本扫描在归档层找现成实体。
> 纪律：只读归档，不重跑模型；单次观察口径，不由此推断当前模型行为。

## 1. 扫描口径

- 范围：`reports/**/*.json` + `../reports-20261023`（≤20MB/件，JSON 可解析）
- 判据：结构内出现 `verdict` 含 `REFUTED`（不匹配日志/文档里的字面量）

## 2. 结果：13 卷 / 21 条 REFUTED 实体

| 卷 | REFUTED | 最大置信 | 备注 |
| --- | --- | --- | --- |
| `v12-fp/pandas-e2e-gate/report.json` | 3 | 0.90 | gate=laya，字段完整（verdict/confidence/evidence） |
| `v12-fp-gate-scores/pandas-r1/report.json` | 3 | 0.80 | 同上 |
| `smoke-armA/search_for_pi/report.json` | 3 | 0.75 | gate disabled |
| `v12-fp/uv-e2e/report.json` | 2 | 0.85 | gate disabled |
| `v12-fp-gate-scores/axios/report.json` | 2 | 0.72 | gate=laya |
| `hybrid-blindspot-20261006/real-time-chat.report.json` | 1 | 0.78 | gate disabled |
| `m8-hybrid/gatekeeping_report.json` | 1 | 0.80 | gate disabled |
| `m8-hybrid/whistleblow_report.json` | 1 | 0.65 | gate disabled |
| `smoke-armA/whistleblow/report.json` | 1 | 0.65 | gate disabled |
| `v12-fp/pandas-e2e/report.json` | 1 | 0.85 | gate disabled |
| `v12-fp/pydantic-e2e/report.json` | 1 | 0.70 | gate disabled |
| `m8-k1/k1_score_k2.json` / `k1_score_v01_20261005.json` | 各 1 | — | score 输出（`judgment.semantic.refuted_on_intended`），非 FinalReport |

实体字段完整：`verdict` + `confidence`（字符串）+ `evidence`（工具取证原文），可直接作 D4/D5 回放输入。

## 3. 兼容性顺带核验（75 卷）

`FinalReport.model_validate` 跑全量归档：**75 卷通过（新字段缺省→[]，向后兼容）**；
9 卷不通过均为**非 FinalReport 格式**误入统计——`single_agent_variant-*/summary.json`
（`findings` 为整数计数）与 `office-demo*/office-report.json`（findings 异 schema），零回归。

## 4. 结论与缺口

1. **归档层实体够用**：21 条真 REFUTED 可作 D4 `verdict_flips` / D5 契约的回放语料。
2. **D5 真机件仍缺**：`refuted_on_intended` 是 D5 新字段，归档卷（旧代码产物）不含它，
   必须有**一次产出 REFUTED 的真跑**才能验收。
3. **缺口（新发现）**：非 gate 卷的 `meta` 无 model/backend/温度字段（只有 gate 块），
   归档无法反查当年配方 ⇒ 想复现 REFUTED 只能猜配置。建议跑批侧补 provenance
   （属输出 schema 改动，待拍板，不在本窗擅动）。
4. **候选清单**（按 REFUTED 条数）：pandas / search_for_pi / uv / axios / pydantic /
   real-time-chat / gatekeeping / whistleblow。下窗任选一并记录所用 verify 模型与温度，
   即可同时补齐「D5 真机件」与「配方可复现」两件事。

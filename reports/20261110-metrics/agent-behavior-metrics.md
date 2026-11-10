# Agent 行为指标（归档回算，零新跑）

- 扫描根：`reports`
- 含 `meta.verifications` 的报告：**73** 份；裁决条目 **309** 条

## 1. 工具调用一致性

| 指标 | 值 |
| --- | --- |
| evidence 非空率 | 1.0 |
| degraded 率 | 0.0162 |
| REFUTED 条目 / 带理由 | 19 / 1.0 |

- method 分布：{'unset': 309}
- evidence_source 分布：{'unset': 231, 'repo_file': 72, 'tool_result': 4, 'library_knowledge': 2}
- node_errors：{'verify': 6, 'deepen': 6, 'arbiter': 6}

## 2. 多轮状态传递（跨卷 verdict 翻转）

- 翻转组合：{'CONFIRMED|UNCERTAIN': 1, 'CONFIRMED|REFUTED': 1}

> 口径：按「报告所在目录」分组，同一 hypothesis_id 在 ≥2 卷出现且 verdict 不一致即记一次翻转；
> 只统计归档里已落盘的卷，不做外推。

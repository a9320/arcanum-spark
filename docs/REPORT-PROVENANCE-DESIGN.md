# 报告 provenance 字段设计提案（2026-11-09，已按 §8 默认值落码）

> 触发：11-09 本地 REFUTED 采集时发现——归档 `report.json` 的 `meta` 只有 gate 块带
> backend/fallback，**没有模型名/温度/commit**，无法反查某一卷当年用的是哪套配方。
> 这直接卡住「复现 REFUTED」与「D5 真机件该用哪套配置跑」两件事。
> 本文记录设计与实现（2026-11-09 落码，§8 默认值），字段属观测层、不参与 gate/判分。

## 1. 现状与证据

| 事实 | 位置 |
| --- | --- |
| `meta` 是 `pipeline.py` 里一个手写 dict，键固定 11 个，无模型/温度/commit | `codeark/graph/pipeline.py:417-438` |
| `meta` 原样透传进 JSON 报告（markdown/html 不渲染 meta） | `codeark/agents/report_agent.py:536-546` |
| 温度只存在于**路由覆盖环境变量** `ARCA_<STAGE>_TEMPERATURE`，未设时 `temperature=None`（不随请求发送→服务器默认） | `codeark/models/factory.py:529,555,647`；`routing.py:34-36` |
| 11-08 块 4 P3/P4 红正是"没人知道温度没钉"——runner 未设，server 默认 0.8 | 执行单 §10（11-08 条） |
| 现有消费方只读已知键，新增键零影响 | `eval/replay.py:131-134`；`eval/compare_gate_e2e.py:42-87` |

## 2. 目标 / 非目标

**目标**：每份 `report.json` 自带「这次跑的是什么」的最小可复现指纹：代码版本、部署形态、
各阶段模型名、端点（脱敏）、关键 tuning（尤其温度与证据预算），以及起止时间。

**非目标**：不记录 prompt/输入内容；不记录 API key/任何凭据；不追改历史卷；
不改 gate/e2e 判据；不引入网络或第三方依赖。

## 3. 字段设计（`meta.provenance`，全部可选、白名单）

```json
"provenance": {
  "schema": 1,
  "codeark_commit": "0f7db3c",
  "deployment": "local",
  "started_at": "2026-11-09T12:00:00Z",
  "finished_at": "2026-11-09T12:26:31Z",
  "models": {"scout": "muse-scout", "verify": "gpt-oss-verify", "deepen": null, "arbiter": null},
  "endpoints": {"scout": "http://127.0.0.1:8081", "verify": "http://127.0.0.1:8085"},
  "tuning": {
    "verify_temperature": 0.0,
    "verify_evidence_max_tokens": 60000,
    "verify_concurrency": 3,
    "scout_max_tokens": null
  },
  "notes": ["verify_temperature unset → server default"]
}
```

填充规则（**只读环境变量与 git，不做任何推断**）：

| 字段 | 数据源 | 缺省 |
| --- | --- | --- |
| `codeark_commit` | `git rev-parse --short HEAD`（仓根，缓存，2s 超时）；env `ARCA_BUILD_COMMIT` 优先 | `"unknown"` |
| `deployment` | 与 `factory.py:720` 同一解析（local/unset/azure/cloud） | `"unset"` |
| `models.*` | 仅 `ARCA_{SCOUT,VERIFY,DEEPEN,ARBITER}_MODEL`；未设=null（**不写内置默认值**，避免与代码默认漂移） | `null` |
| `endpoints.*` | 对应 `*_BASE_URL`，经 `urlsplit` 只留 `scheme://host:port` | `null` |
| `tuning.*` | `ARCA_VERIFY_TEMPERATURE` / `ARCA_VERIFY_EVIDENCE_MAX_TOKENS` / `ARCA_VERIFY_MAX_CONCURRENCY` / `ARCA_SCOUT_MAX_TOKENS`，数字解析 | `null` |
| `started_at/finished_at` | pipeline 入口/出口 UTC ISO8601 | 缺则省略 |

`temperature=null` 时 `notes` 追加 `"verify_temperature unset → server default"`——
把 11-08 那次"以为钉了其实没钉"的坑变成报告里可读的一行。

## 4. 落点与实现形状

1. 新模块 `codeark/obs/provenance.py`（纯标准库）：
   - `collect_provenance(started_at=None) -> dict`：白名单读取 + 脱敏；
   - `_commit()`：`lru_cache`，`subprocess.run(..., timeout=2)`，任何异常→`"unknown"`；
   - `_sanitize_url()`：`urlsplit` 失败→`"redacted"`；丢 userinfo/path/query。
2. `codeark/graph/pipeline.py:421` 的 meta 字面量加一行 `"provenance": collect_provenance(...)`；
   起止时间在 `run()` 首尾取一次。
3. `render_report` 不改（meta 透传已够）；markdown/html 是否展示 provenance 本提案默认**不展示**。

## 5. 隐私与安全（硬约束）

- **绝不读取** `ARCA_*_API_KEY`、`.env`、`~/.git-credentials`；白名单键之外的环境变量一律不碰。
- 端点必须去 userinfo：`https://u:tok@host:8080/v1?k=1` → `https://host:8080`。
- 单测含"哨兵 key"用例：把假 key 塞进 `ARCA_VERIFY_API_KEY`，断言序列化结果里不出现该串。
- commit 哈希属公开信息，可记。

## 6. 兼容性与影响面

- 纯新增键：`eval/replay.py`、`eval/compare_gate_e2e.py`、`eval/check_report.py` 均按已知键取数，
  不受影响；gate 的 `ordered_ids` 对照不含 provenance。
- 旧卷无该键：读取方按"缺失"处理，不补、不推断（文档注明 pre-provenance 不可追溯）。
- 报告体积增量 < 1KB。

## 7. 测试与验收（预注册，实现后照此验收）

单测（新增 `codeark/tests/test_provenance.py`，预计 5 条）：
1. 空环境：`schema/deployment/time` 在位，`models/tuning` 全 null，`notes` 含温度未设提示；
2. 设 `ARCA_VERIFY_TEMPERATURE=0` → `0.0` 且无该 note；非法值（`abc`）→ null + note，不抛；
3. 端点脱敏：带 `user:tok@` 与 query 的 URL → 仅 `scheme://host:port`；
4. 哨兵 key 不泄漏（全 JSON 扫描）；
5. 旧报告（无 provenance）经 `FinalReport.model_validate` 与 replay/compare 工具行为不变。

验收闸（实现窗内）：
- 全量 pytest + `verify.sh` 5/5；
- DSW 一次真跑 `report.json` 出现 provenance，且**同仓两次不同温度**的卷该字段可区分；
- 隐私扫描用例通过；`git status` 无临时件。

工作量估计：新模块 ~70 行 + pipeline 一行 + 测试 ~90 行 + 文档 2 处，**零模型调用**。

## 8. 决策点（2026-11-09 已按默认值实现，复核可改）

1. `endpoints.*` 记，但只留 `scheme://host:port`（去 userinfo/path/query）——**已实现**；
2. `hostname`/pod 名 **不记**（资源标识不进报告）——**已实现为不记**；
3. 旧卷 **不回填**，文档标注 pre-provenance 不可追溯——**已按此执行**；
4. `ARCA_BUILD_COMMIT` **保留**（slim/无 `.git` 场景的 commit 来源）——**已实现**。

实现锚点：`codeark/provenance.py`（新模块）+ `codeark/graph/pipeline.py:421` 的 meta 字面量；
测试 `codeark/tests/test_provenance.py`（6 条）。2026-11-09 实测：全量 622 passed + `verify.sh` 5/5，
dry-run 报告 `meta.provenance` 实拍在位。

## 9. 风险

- slim/打包运行无 `.git` → commit=`unknown`：由 `ARCA_BUILD_COMMIT` 覆盖，构建脚本可注入。
- 运行时 `git` 调用引入延迟/失败：缓存 + 2s 超时 + 异常降级，失败不影响主流程。
- 字段被误当判据：文档明确 provenance 属**观测**，不参与 gate/判分。

# Azure 集成设计与落地台账（IC27 P0）

> 状态（2026-10-28）：**v0 已落地并通过确定性回归**——`codeark/azure/content_safety.py`
> 窄客户端 + 19 个 MockTransport 契约锚 + live 冒烟脚本 + 本文档；**主链路零改动**。
> v1（进 Scout/Verify 生产路径）须真实 Azure 凭据端到端验证后再做，理由见 §8。

## 0. 一句话

同一颗心脏（确定性 9 规则 + 微调判官），Azure 提供两件承重件：
**Azure OpenAI**（Scout/Verify/Deepen/Arbiter 四岗推理）与 **Azure AI Content Safety**
（Prompt Shields + 文本危害，作为通用基线进检测主链路）；Azure AI Foundry Agent Service
与 GitHub Action 是分发面，不是第二套引擎。

## 1. 判据映射（Use of MS Technology 40% 怎么挣）

| 服务 | 在系统中的角色 | 是否可被替换 | 证据形态 |
|---|---|---|---|
| Azure OpenAI | 四岗模型端点（Scout 侦察 / Verify 判决 / Deepen 取证 / Arbiter 合议） | 是（BYOM 同接口） | 每次运行的模型名 + base_url 元数据、A/B 一致率回放 |
| Azure AI Content Safety | 不可信内容进 LLM 之前的**通用基线**（Prompt Shields + 危害分析） | 是（本地确定性隔离仍在） | 报告 `meta.azure.content_safety` + 双路裁决矩阵 |
| Azure AI Foundry Agent Service | 生态门：CodeRisk audit agent（11 月交付） | — | Foundry 上的 agent 清单 + 调用录屏 |
| Container Apps / ACR / Key Vault / Monitor | 部署与凭据底盘（v1 起） | — | 部署清单 + Managed Identity 截图 |

写作口径：**Azure 承担的是「模型推理 + 通用注入基线 + 托管部署」，不是"贴皮调用"**。
半决赛技术复核会 walkthrough，所以每条接线都要有一条可重跑的命令（§9）。

## 2. 架构：一个引擎、多扇门

```
                     ┌──────────────────────── 同一引擎（codeark）────────────────────────┐
  本地免费版  ──────▶ │  Agent0 PITAX(9 规则, 零依赖) → Scout → Verify → Deepen → Arbiter  │
  (CPU/离线)          │         ▲                    │                                     │
  BYOM 版     ──────▶ │         │  quarantine(确定性) │  Azure OpenAI 四岗端点               │
  Azure 云版  ──────▶ │         │  + Content Safety   │  (ARCA_<STAGE>_* env 路由)           │
  Foundry/GA  ──────▶ └─────────┴─────────────────────┴─────────────────────────────────────┘
                                     │
                              报告 JSON/SARIF/HTML
```

关键设计：**门是部署形态，不是代码分叉**。Azure 版与本地版共用 `codeark` 包与同一套
判决契约；Azure 只在两处出现——模型端点（env 路由）与不可信内容基线（本模块）。

## 3. v0 交付物（本次提交）

| 文件 | 作用 | 验收 |
|---|---|---|
| `codeark/azure/content_safety.py` | Content Safety 窄客户端：`shield_prompt()` + `analyze_text()`；env 门控；HTTP/协议失败 fail-closed | 19 tests（`tests/test_azure_content_safety.py`），零联网 |
| `codeark/azure/__init__.py` | 包导出 | — |
| `scripts/smoke/azure_content_safety_smoke.py` | 凭据到位后的第一道 live 验收（两接口 + 判定是否符合预期） | 未配置退出码 2；`--live` 真调用 |
| `docs/AZURE-INTEGRATION.md` | 本文档 | — |

**v0 明确不做**：不改 `codeark/graph/pipeline.py`、不改任何 Agent、不进报告 schema、
不读 `.env`。原因：无凭据时改主链路只能"盲接"，会动 410 测试基线与判决面，风险大于收益。

### v0 失败语义（fail-closed）

| 情形 | 返回 | 报告口径（v1 继承） |
|---|---|---|
| env 缺 ENDPOINT/KEY | `from_env()` 返回 `None` | `configured=false` + `missing=[...]`，**显式记"未启用"** |
| HTTP 4xx/5xx | `degraded=True`，判定 `None` | `degraded=true` + 脱敏 reason；**不得当作 clean** |
| 网络错误/超时 | 同上 | 同上 |
| 响应缺字段/类型不符 | 同上 | 同上 |
| 正常 | 判定 `True/False` | 原样入报告 |

`None ≠ False` 是硬契约：聚合层见到 `None` 必须降级或人工复核，禁止静默通过。
（与 `verify_agent` 的 `degraded=True` 口径一致，见 `docs/VERIFY-EVIDENCE-CONTRACT.md`。）

## 4. env 契约

### 4.1 Content Safety（v0 已消费）

| 变量 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `ARCA_AZURE_CONTENT_SAFETY_ENDPOINT` | 是 | — | `https://<resource>.cognitiveservices.azure.com`（也接受 `*.api.cognitive.microsoft.com`） |
| `ARCA_AZURE_CONTENT_SAFETY_KEY` | 是 | — | 资源密钥；repr/异常/降级原因均脱敏 |
| `ARCA_AZURE_CONTENT_SAFETY_API_VERSION` | 否 | `2024-09-01` | 端点版本；凭据到位后用冒烟脚本逐版本确认 |
| `ARCA_AZURE_CONTENT_SAFETY_TIMEOUT` | 否 | `10`（秒） | 非法值回落默认 |

### 4.2 Azure OpenAI（复用既有四岗路由，无需新代码）

`codeark/models/factory.py` 已支持 `ARCA_<SCOUT|VERIFY|DEEPEN|ARBITER>_{MODEL,BASE_URL,API_KEY,TIMEOUT}`
与共享回退 `ARCA_{MODEL,BASE_URL,API_KEY}`。Azure OpenAI 的 v1 端点形如
`https://<resource>.openai.azure.com/openai/v1`，`MODEL` 填**部署名**（deployment name）。

示例（值用占位符，禁止提交真实 key）：

```bash
export ARCA_SCOUT_MODEL=gpt-5-mini          # = Azure 部署名
export ARCA_SCOUT_BASE_URL=https://arca-openai.openai.azure.com/openai/v1
export ARCA_SCOUT_API_KEY=...               # 只进进程环境，不进仓库
```

> v1 待验点（凭据到位第一件事）：**v1 端点的 API key 鉴权是否接受
> `Authorization: Bearer <key>`**。微软 v1 API 文档示例用 OpenAI SDK + `api_key`（Bearer），
> 而经典 `api-key:` 头是旧版路径。若实测 Bearer 被拒，方案=在 `make_model` 的
> `client_args.headers` 注入 `api-key`，不动四岗 env 契约（改动面 1 处，见 §8）。

## 5. 鉴权与凭据纪律

| 阶段 | 形态 | 说明 |
|---|---|---|
| v0/v1 本地验收 | 资源密钥（Content Safety: `Ocp-Apim-Subscription-Key`；OpenAI: 见 §4.2 待验点） | 只从进程环境读；不写文件、不打印 |
| Azure 云版 | Key Vault + Managed Identity（Container Apps 系统身份） | 顺手修 P1 明文 key 项；密钥不落镜像/仓库 |
| 半决赛复核 | 现场用一次性密钥跑 live 冒烟 | 录屏只拍 endpoint host 与结果，不拍 key |

红线：`key` 出现在日志、报告、截图、Git 历史任一处 = 事故。客户端已做 repr/异常脱敏，
测试专门断言（`test_shield_prompt_http_error_degrades_and_scrubs_key`）。

## 6. 三层防线与双路裁决

被审计仓库本身就是攻击者可控输入（"让审计器把问题全标 REFUTED"）。现有防线是确定性的
`codeark/graph/quarantine.py`（不可见字符剥离 + 触发词中和 + 数据边界声明），Content Safety
补的是**语义层通用基线**，两者不互相替代：

| 层 | 性质 | 覆盖 | 失败时 |
|---|---|---|---|
| quarantine（已有） | 确定性、零网络 | 已知字符/触发词模式 | 逐项计数进 `quarantine_stats` |
| PITAX（已有） | 确定性 9 规则 | AI 代码/prompt injection 的具体形态 | findings 带规则号 |
| Content Safety（v1） | 云服务、概率型 | 通用越狱/注入 + 危害类别 | `degraded=true`，显式记账 |

### 双路裁决矩阵（v1 报告口径）

| PITAX 命中 | CS shield | 组合结论 | 说明 |
|---|---|---|---|
| 是 | 命中 | 确认（双路一致） | 最强证据，报告标 `dual_path=agree` |
| 是 | 未命中 | 确认（代码场景规则优先） | 标 `dual_path=pitax_only`；CS 是通用基线，不覆盖代码语境 |
| 否 | 命中 | 升级 Verify | 标 `dual_path=cs_only`；交判官结合证据判，不直接定罪 |
| 否 | 未命中 | clean | — |
| 任意 | `None`/degraded | **不得 clean** | 标 `degraded` 并要求人工复核；PITAX 独立命中仍成立 |

这张表也是 Demo 的"内行记忆点"：评委看到的是**两条独立证据链 + 显式降级**，而不是
"调了个 API 说 AI 很安全"。

## 7. 报告元数据 schema（v1 目标）

```json
{
  "meta": {
    "azure": {
      "content_safety": {
        "configured": true,
        "endpoint_host": "arca-demo.cognitiveservices.azure.com",
        "api_version": "2024-09-01",
        "shield": {"attack_detected": false, "degraded": false, "reason": ""},
        "text_analysis": {"max_severity": 0, "degraded": false, "reason": ""},
        "coverage": {"documents_total": 0, "documents_scanned": 0, "truncated": false}
      },
      "openai": {"stages": {"scout": "gpt-5-mini", "verify": "gpt-5-mini"}}
    }
  }
}
```

`configured=false` 时必须出现，不能省略——"没启用"和"启用了但没问题"是两种事实。

## 8. v1 接线点与改动清单（待凭据）

| 位置 | 改动 | 回滚开关 |
|---|---|---|
| `codeark/graph/pipeline.py:213`（`quarantine_files` 调用处） | 在消毒前对**原始文件**调 `shield_prompt(documents=...)`；结果与 `quarantine_stats` 同级写入运行元数据 | `ARCA_AZURE_CONTENT_SAFETY_ENABLED=0` 默认关 |
| 同一位置 | 分片与抽样：单请求有长度上限（以官方文档为准），超限按文件切块、记录 `coverage` | 同上 |
| `codeark/graph/pipeline.py` 结果组装 | `meta.azure` 字段（§7），`configured/degraded` 双写 | 同上 |
| `codeark/agents/verify_agent.py` 证据包构造 | 仅当 cs 判定 `True` 且 PITAX 未命中时，把 `cs_only` 作为一条待验证假设/信号送入 Verify（不直接定罪） | 同上 |
| `codeark/models/factory.py` | 若 §4.2 Bearer 实测被拒：`client_args` 注入 `api-key` 头（单点，不动 env 契约） | 不需要（默认路径不变） |

**为什么默认关**：v0 前全量 410 个测试与 K2 回放结论都建立在"本地确定性 + 本地判官"上；
云基线进主链会改变判决分布。v1 必须先在固定假设集上出 **A/B 一致率与降级率**，
再决定默认开。

## 9. 验收阶梯（凭据到位后照抄）

```bash
# 1) 配置状态（零联网，应输出 configured=true）
python scripts/smoke/azure_content_safety_smoke.py

# 2) live 冒烟（两接口；合成注入样本应 attackDetected=True，benign=False）
python scripts/smoke/azure_content_safety_smoke.py --live | tee reports/azure-smoke-$(date +%Y%m%d-%H%M).json

# 3) Azure OpenAI 四岗连通（复用既有端点探针，改 env 指向 Azure）
python scripts/check_endpoints.py

# 4) 单题端到端（Azure OpenAI 四岗 + Content Safety 开关关）
#    比较对象=同一题在本地 gpt-oss 判官下的既有卷（K2 台账方法论）

# 5) N=3 固定假设集（零降级为闸门）→ 再开 Content Safety 主链，A/B 回放一致率
```

验收判据（与既有纪律一致）：
- 冒烟 `ok=true` 且 `elapsed_ms` 可复现量级；
- 单题端到端 `degraded=0`；
- N=3 判决一致率**先出数再定默认值**，不预先承诺"一致率 X%"。

## 10. 成本、区域与配额纪律

- 不写未核数字：本文件不列价格/免费额度；材料引用前须对官方定价页截图留档。
- 区域：Content Safety 与 OpenAI 资源尽量同区（减少跨区延迟）；具体可用区以创建时控制台为准。
- 配额：live 冒烟每次 3 个请求（2 shield + 1 analyze），回放跑批前先看配额页；
  CI 永不真调用（单测全 MockTransport）。
- 数据：冒烟样本是合成字符串，不含真实仓库内容；真实用户仓库扫描前须取得同意（case study 授权书）。

## 11. 红线

1. 主链路接线必须真跑（半决赛 walkthrough），禁止"配置了但没调用"的贴皮。
2. `degraded` 必须显式入报告；任何"静默当 clean"的路径 = 缺陷。
3. 对外材料禁未核数字（Azure 价格、评测分数、用户数）。
4. 密钥不落仓库/日志/截图；`.env.example` 不动、不查、不提交。
5. 不写通用 Agent 框架；Azure 只做承重与分发，不做第二套引擎。

## 12. 参考

- Azure AI Content Safety — Prompt Shields / Text analysis REST API（路径：
  `/contentsafety/text:shieldPrompt`、`/contentsafety/text:analyze`）。
- Azure OpenAI v1 API（`/openai/v1`，OpenAI SDK 兼容；密钥与 Entra ID 两种鉴权）。
- 本仓既有契约：`docs/VERIFY-EVIDENCE-CONTRACT.md`（证据与降级口径）、
  `docs/JUDGE-CONFIDENT-REFUTATION.md`（判决层台账）、`codeark/graph/quarantine.py`（确定性隔离）。
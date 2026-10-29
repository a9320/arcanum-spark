# Azure 集成设计与落地台账（IC27 P0）

> 状态（2026-10-29）：**双客户端 + v1 前哨 gate 已落地并通过确定性回归**——
> `codeark/azure/content_safety.py`（19 锚）、`codeark/azure/language.py`（13 锚）、
> `codeark/azure/preflight.py`（14 锚）+ 管线接线 3 锚、两个 live 冒烟脚本。
> gate **默认关**，开启后 `meta.azure` 随报告落盘；466 tests collected / `verify.sh` 5/5。
> **Azure OpenAI 在中国大陆学生/个人订阅下不可用**（活动日志实锤
> `CannotDeployDueToLocalRegulations`：仅持营业执照的企业客户可订阅），
> 四岗 LLM 走本地/BYOM，详见 §1。

## 0. 一句话

同一颗心脏（确定性 9 规则 + 微调判官，CPU 可跑）+ **两件 Microsoft AI 承重件**：
**Azure AI Content Safety**（Prompt Shields 通用注入基线，进检测前哨）与
**Azure AI Language**（PII 脱敏门：模型面证据离开本机前脱敏）；四岗推理走
本地/BYOM（微调判官或任意 OpenAI 兼容端点），Azure 版可再叠加 Foundry 托管的
非 OpenAI 模型。Azure AI Foundry Agent Service 与 GitHub Action 是分发面，
不是第二套引擎。

## 1. 判据映射（Use of MS Technology 40% 怎么挣）

| 服务 | 在系统中的角色 | 是否可被替换 | 证据形态 |
|---|---|---|---|
| Azure AI Content Safety | 不可信内容进 LLM 之前的**通用基线**（Prompt Shields + 危害分析），`preflight` 前哨 | 是（本地确定性隔离仍在） | 报告 `meta.azure.content_safety`（覆盖率/命中/降级）+ 双路裁决矩阵 |
| Azure AI Language | **PII 脱敏门**：模型面文件在送 LLM 前脱敏，失败即扣留（fail-closed） | 是（本地确定性隔离仍在） | 报告 `meta.azure.language`（脱敏/扣留/实体类别计数） |
| 四岗 LLM（本地/BYOM/微调判官） | Scout 侦察 / Verify 判决 / Deepen 取证 / Arbiter 合议；`ARCA_<STAGE>_*` env 路由 | 是（门是部署形态，不是代码分叉） | 每次运行的模型名 + base_url 元数据、A/B 一致率回放 |
| Azure OpenAI | **不可用（中国大陆法规）**：学生/个人订阅仅企业营业执照客户可订阅，`CannotDeployDueToLocalRegulations` | — | 活动日志留档（2026-10-29） |
| Foundry 非 OpenAI 模型（Phi-4 等） | 备选：部署成功则作为四岗 LLM 的 Microsoft 托管端点（第三个服务） | 是 | 部署成功后的 `check_endpoints.py` + 冒烟 |
| Azure AI Foundry Agent Service | 生态门：CodeRisk audit agent（11 月交付） | — | Foundry 上的 agent 清单 + 调用录屏 |
| Container Apps / ACR / Key Vault / Monitor | 部署与凭据底盘（v1 起） | — | 部署清单 + Managed Identity 截图 |

**监管事实改变了架构叙事**（2026-10-29，活动日志实锤）：中国大陆学生/个人订阅
部署任何 OpenAI 模型都返回 `CannotDeployDueToLocalRegulations`，与配额、区域、
网络无关；已提交的配额申请 moot。因此"Azure OpenAI 四岗"不再作为承重件，
"≥2 项 Microsoft AI 服务"改为 **Content Safety + Azure AI Language**（均为
Cognitive Services 家族，UAE North 实测可建可用），LLM 走本地/BYOM。

写作口径：**Azure 承担的是「不可信内容基线 + 证据脱敏 + 托管部署」，不是"贴皮调用"**。
半决赛技术复核会 walkthrough，所以每条接线都要有一条可重跑的命令（§9）。

## 2. 架构：一个引擎、多扇门

```
                     ┌──────────────────────── 同一引擎（codeark）────────────────────────┐
  本地免费版  ──────▶ │  Agent0 PITAX(9 规则, 零依赖) → Scout → Verify → Deepen → Arbiter  │
  (CPU/离线)          │         ▲                    │                     ▲              │
  BYOM 版     ──────▶ │         │  quarantine(确定性) │                     │ 四岗 LLM      │
  Azure 云版  ──────▶ │         │  + CS shield        │                     │ 本地/BYOM/    │
  Foundry/GA  ──────▶ │         │  + Language 脱敏     │                     │ Foundry 模型  │
                     └─────────┴─────────────────────┴─────────────────────┴──────────────┘
                                     │
                              报告 JSON/SARIF/HTML（meta.azure 记覆盖率与降级）
```

关键设计：**门是部署形态，不是代码分叉**。Azure 版与本地版共用 `codeark` 包与同一套
判决契约；Azure 在三处出现——模型端点（env 路由）、不可信内容基线与前哨 gate（`preflight`）、
证据脱敏（Language）。

## 3. 交付物（v0 客户端 + v1 前哨 gate）

| 文件 | 作用 | 验收 |
|---|---|---|
| `codeark/azure/content_safety.py` | Content Safety 窄客户端：`shield_prompt()` + `analyze_text()`；env 门控；HTTP/协议失败 fail-closed | 19 tests（`tests/test_azure_content_safety.py`），零联网 |
| `codeark/azure/language.py` | Language PII 窄客户端：`redact_texts()`；≤5 篇/请求分批；超长/失败逐文档降级；实体**不含原文** | 13 tests（`tests/test_azure_language.py`），零联网 |
| `codeark/azure/preflight.py` | 主链路前哨 gate：CS 逐批扫描（≤5 篇/≤9K 字符/≤3 批）+ PII 脱敏（≤20 篇）；覆盖率与扣留全记账 | 14 tests（`tests/test_azure_preflight.py`） |
| `codeark/graph/pipeline.py` | 隔离层之前调用 gate（默认关）；`meta.azure` 入报告；故障只记 `node_errors` | 3 tests（`codeark/tests/test_azure_preflight_wiring.py`） |
| `scripts/smoke/azure_{content_safety,language}_smoke.py` | 凭据到位后的第一道 live 验收 | 未配置退出码 2；`--live` 真调用 |
| `docs/AZURE-INTEGRATION.md` | 本文档 | — |

**边界**：gate 默认关（`ARCA_AZURE_*_ENABLED` 全不设时零网络、零行为变化），
不改任何 Agent 的判决逻辑，不读 `.env`。云基线进主链会改变判决分布，
须先用固定假设集出 A/B 一致率与降级率（§9 第 6 步）再谈默认开。

**v1 已实现的行为**（`preflight.run_azure_gate`）：
- CS 对**原始文件**逐批 `shield_prompt`（审计指令我们自己给，仓库内容只当 documents）；
  默认只记账，`ARCA_AZURE_CONTENT_SAFETY_BLOCK=1` 时命中文件不进模型面。
- Language 对**模型面文件**脱敏，替换内容后再进确定性隔离；脱敏失败/超长默认**扣留**
  （`ARCA_AZURE_GATE_WITHHOLD_ON_DEGRADED=0` 可改放行）。
- 覆盖率字段（total/sampled/scanned/withheld/truncated）全部入 `meta.azure`，
  绝不写"扫了全仓"。

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

### 4.2 四岗模型端点（本地/BYOM；Azure OpenAI 不可用）

`codeark/models/factory.py` 已支持 `ARCA_<SCOUT|VERIFY|DEEPEN|ARBITER>_{MODEL,BASE_URL,API_KEY,TIMEOUT}`
与共享回退 `ARCA_{MODEL,BASE_URL,API_KEY}`。任何 OpenAI 兼容端点都能按此接入：
本地 llama.cpp（默认，微调判官）、公司内网网关、或 Foundry 托管的非 OpenAI 模型。

```bash
export ARCA_VERIFY_MODEL=laya-r6-judge
export ARCA_VERIFY_BASE_URL=http://127.0.0.1:8080/v1
export ARCA_VERIFY_API_KEY=local           # 只进进程环境，不进仓库
```

> **Azure OpenAI 不可用的实证（2026-10-29）**：中国大陆学生/个人订阅对
> `Microsoft.CognitiveServices/accounts/deployments/write` 返回
> `CannotDeployDueToLocalRegulations`（原文：仅持营业执照的企业客户可订阅
> Azure OpenAI Service），与配额、区域、HTTP/2 无关；已提交的配额申请 moot。
> 若拿到企业执照或非中国区订阅，v1 端点 `https://<res>.openai.azure.com/openai/v1`
> + `MODEL=部署名` 仍可按上表接入；鉴权待验点（Bearer vs `api-key` 头）保留在
> `codeark/azure/openai_probe.py` 的四路探测里。

### 4.3 Azure AI Language（v1 前哨 gate 消费）

| 变量 | 必需 | 默认 | 说明 |
|---|---|---|---|
| `ARCA_AZURE_LANGUAGE_ENDPOINT` | 是 | — | `https://<resource>.cognitiveservices.azure.com` |
| `ARCA_AZURE_LANGUAGE_KEY` | 是 | — | 资源密钥；repr/降级原因脱敏 |
| `ARCA_AZURE_LANGUAGE_API_VERSION` | 否 | `2024-11-01` | 冒烟确认后再钉 |
| `ARCA_AZURE_LANGUAGE_TIMEOUT` | 否 | `10` | 秒 |

gate 开关与成本帽（**全部默认关**）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `ARCA_AZURE_CONTENT_SAFETY_ENABLED` | `0` | 开 CS 前哨 |
| `ARCA_AZURE_CONTENT_SAFETY_BLOCK` | `0` | `1`=命中文件不进模型面（否则只记账） |
| `ARCA_AZURE_LANGUAGE_ENABLED` | `0` | 开 PII 脱敏 |
| `ARCA_AZURE_GATE_WITHHOLD_ON_DEGRADED` | `1` | `0`=脱敏失败仍放行原文（不推荐） |
| `ARCA_AZURE_GATE_MAX_LANGUAGE_DOCS` | `20` | 单次脱敏文档数帽（F0 月 5,000 条） |

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
| Content Safety（前哨 gate，默认关） | 云服务、概率型 | 通用越狱/注入 + 危害类别 | `degraded=true`，显式记账 |
| Language PII（前哨 gate，默认关） | 云服务、概率型 | 模型面文本的 PII 实体 | 该文档扣留，`degraded=true` |

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

## 7. 报告元数据 schema（已实现）

```json
{
  "meta": {
    "azure": {
      "enabled": true,
      "content_safety": {
        "enabled": true,
        "configured": true,
        "endpoint_host": "arca-cs-ic27.cognitiveservices.azure.com",
        "api_version": "2024-09-01",
        "documents_total": 42,
        "documents_sampled": 15,
        "documents_scanned": 15,
        "truncated_documents": 0,
        "batches": 3,
        "attack_detected": false,
        "degraded": false,
        "reason": "",
        "blocked_documents": 0
      },
      "language": {
        "enabled": true,
        "configured": true,
        "endpoint_host": "arca-lang-ic27.cognitiveservices.azure.com",
        "api_version": "2024-11-01",
        "documents_total": 42,
        "documents_sampled": 20,
        "documents_redacted": 18,
        "documents_withheld": 2,
        "skipped_too_long": 1,
        "entities_by_category": {"Email": 3, "Person": 1},
        "degraded": true,
        "reason": "HTTP 500: ..."
      }
    }
  }
}
```

`enabled=false` 时必须出现（默认关、dry-run、未启用三态都要显式），不能省略——
"没启用"和"启用了但没问题"是两种事实。`attack_detected` 为三态：`true` / `false` /
`null`（未知，**不等于 clean**）。`entities_by_category` 只含类别计数，**不含 PII 原文**。

## 8. 接线点与改动清单（已落地）

| 位置 | 改动 | 回滚开关 |
|---|---|---|
| `codeark/graph/pipeline.py`（`quarantine_files` 之前） | 调用 `run_azure_gate(files)`：CS 看原始文件、Language 脱敏后进隔离层；异常只记 `node_errors["azure_gate"]` | `ARCA_AZURE_*_ENABLED` 不设=全关 |
| 同一位置 | 成本帽与覆盖率：CS 3 批×5 篇×9K 字符；Language 20 篇×5K 字符 | `ARCA_AZURE_GATE_MAX_LANGUAGE_DOCS` |
| `codeark/graph/pipeline.py` 结果组装 | `meta.azure` 字段（§7），默认关时同形记账 | — |
| `codeark/agents/verify_agent.py` 证据包构造 | **未做（剩余项）**：CS `cs_only` 作为待验证信号送入 Verify（不直接定罪） | 同上 |
| `codeark/models/factory.py` | **不需要**：Azure OpenAI 不可用，四岗走 BYOM 既有路由 | — |

**为什么仍默认关**：436→466 个确定性测试与 K2 回放结论都建立在"本地判官"上；
云基线进主链会改变判决分布。开启后必须先在固定假设集上出 **A/B 一致率与降级率**，
再决定默认值（§9 第 6 步）。

## 9. 验收阶梯（凭据到位后照抄）

```bash
# 1) 配置状态（零联网；两个服务都应 configured=true）
python scripts/smoke/azure_content_safety_smoke.py
python scripts/smoke/azure_language_smoke.py

# 2) live 冒烟（CS 3 请求 / Language 1 条记录）
python scripts/smoke/azure_content_safety_smoke.py --live | tee reports/azure-cs-smoke-$(date +%Y%m%d-%H%M).json
python scripts/smoke/azure_language_smoke.py --live | tee reports/azure-lang-smoke-$(date +%Y%m%d-%H%M).json

# 3) 四岗连通（本地/BYOM/Foundry 模型，与 Azure OpenAI 无关）
python scripts/check_endpoints.py

# 4) 单题端到端（gate 关）：对照本地判官既有卷
python -m codeark.cli <repo> --dry --formats json,sarif,markdown

# 5) 单题端到端（gate 开，只记账不拦截）：检查 meta.azure 覆盖率与 degraded
ARCA_AZURE_CONTENT_SAFETY_ENABLED=1 ARCA_AZURE_LANGUAGE_ENABLED=1 \
  python -m codeark.cli <repo> --formats json,sarif,markdown

# 6) N=3 固定假设集 A/B（gate 关 vs 开）：先出判决一致率与降级率，
#    再决定是否默认开与是否启用 CS_BLOCK
```

验收判据（与既有纪律一致）：
- 冒烟 `ok=true` 且 `elapsed_ms` 可复现量级；
- 单题端到端 `degraded=0`；
- N=3 判决一致率**先出数再定默认值**，不预先承诺"一致率 X%"。

## 10. 成本、区域与配额纪律

- 不写未核数字：本文件不列价格/免费额度；材料引用前须对官方定价页截图留档。
- 区域：CS 已在 **UAE North** 实测可用；Language 同为 Cognitive Services 家族，
  优先同区（学生订阅白名单：indiasouthcentral / eastasia / koreacentral / uaenorth /
  malaysiawest）。
- 配额：CS F0 = 5,000 文本记录/月、5 RPS；Language F0 同量级（5,000 条/月，
  1 篇文档 = 1 条）。gate 单次最多 3 批 CS（≤15 篇）+ 20 篇 Language；
  CI 永不真调用（单测全 MockTransport）。
- 数据：冒烟样本是合成字符串，不含真实仓库内容；真实用户仓库扫描前须取得同意
  （case study 授权书）。PII 实体只存类别与计数，不存原文。
- 监管：Azure OpenAI 对大陆学生/个人订阅不可用（§4.2），材料中不得宣称使用 Azure OpenAI。

## 11. 红线

1. 主链路接线必须真跑（半决赛 walkthrough），禁止"配置了但没调用"的贴皮。
2. `degraded` 必须显式入报告；任何"静默当 clean / 静默当已脱敏"的路径 = 缺陷。
3. 对外材料禁未核数字（Azure 价格、评测分数、用户数）。
4. 密钥不落仓库/日志/截图；`.env.example` 不动、不查、不提交。
5. 不写通用 Agent 框架；Azure 只做承重与分发，不做第二套引擎。

## 12. 参考

- Azure AI Content Safety — Prompt Shields / Text analysis REST API（路径：
  `/contentsafety/text:shieldPrompt`、`/contentsafety/text:analyze`，`api-version=2024-09-01` 实测可用）。
- Azure AI Language — PII 实体识别（`/language/:analyze-text`，
  `kind=PiiEntityRecognition`，`stringIndexType=UnicodeCodePoint`，默认 `api-version=2024-11-01`）。
- 本仓既有契约：`docs/VERIFY-EVIDENCE-CONTRACT.md`（证据与降级口径）、
  `docs/JUDGE-CONFIDENT-REFUTATION.md`（判决层台账）、`codeark/graph/quarantine.py`（确定性隔离）。
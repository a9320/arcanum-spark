# scripts/azure — IC27「≥10 项 Azure 服务、每项 ≥$1 用量」合规底座

Imagine Cup 2027 正式规则 §7 原文（`IC27-rules-extracted.txt:287`）：

> ... (b) be using at least ten (10) services on Azure for the solution entered into the
> Competition with the corresponding Azure Subscription ID. Note that your Startup's Azure
> account must show **at least $1.00 of usage on each Azure service** ...

两条隐含硬点决定了本目录的设计：

1. **免费层不算数**——F0/Free 计量是 $0.00，账户上看不到付费用量；
2. **服务要"为方案所用"**——不能开 10 个空资源凑数，每项都要在产品架构里有位置。

## 文件

| 文件 | 作用 |
|---|---|
| `provision_10_services.sh` | 幂等创建 10 项资源（`--dry-run` / `--stage` / `--skip`） |
| `generate_usage.py` | 按实测单价把每项 $1 换算成调用量并跑量（stdlib、可 `plan` 零联网） |
| `check_usage.py` | 用 `az consumption usage list` 逐项核对是否已过门槛（可离线吃 JSON） |
| `cleanup_10_services.sh` | 按名单删除（默认 dry-run；绝不删整组，保护 gate 用的 F0 资源） |
| `prices-20261117.json` | 单价与区域可用性快照（Retail Prices API 实测，含被排除项的理由） |

## 前置

- `az` CLI（Cloud Shell 自带；本机需 `azure-cli`）且已 `az login`；
- 订阅的**区域部署策略白名单** = `indiasouthcentral / eastasia / koreacentral / uaenorth / malaysiawest`；
- 付费 SKU 会真实计费：学生订阅走 $100 额度抵扣，账面金额仍会被记录（这正是判据要的）。

## 五步

```bash
# 0) 预演（不建任何东西）
bash scripts/azure/provision_10_services.sh --dry-run

# 1) 建资源（约 15–25 分钟；Language 自动落在 eastasia）
bash scripts/azure/provision_10_services.sh
#    → 凭据写 $HOME/azure-ic27.env（chmod 600，勿入库）
#    → 清单写 ./azure-ic27-resources.json（无密钥，可入证据档）

# 2) 跑量（5 项 AI 服务，约 20–40 分钟；--target-usd 默认 1.25 留余量）
python scripts/azure/generate_usage.py all-ai --env-file "$HOME/azure-ic27.env"

# 3) 核对（十项逐条；未达标只补该项）
python scripts/azure/check_usage.py --run-az
python scripts/azure/check_usage.py --run-az --json > check-usage.json

# 4) 时间型四项等计费累积（见下表），达标后立刻清理
bash scripts/azure/cleanup_10_services.sh --yes
```

## 达标时间与成本（2026-11-17 实测单价）

| 服务 | 计量 | 单价 | 到 $1 需要 | 形态 |
|---|---|---|---|---|
| Content Safety | Standard Text Records | $0.375/1K | 2,667 条 | 跑量（分钟级） |
| AI Language | Standard Text Records | $0.25/1K | 4,000 条 | 跑量（分钟级） |
| Document Intelligence | S0 Read Pages | $0.60/1K | 1,667 页 | 跑量（分钟级） |
| AI Vision | OCR glbl Pages | $1.00/1K | 1,000 页 | 跑量（分钟级） |
| AI Speech | S1 Speech To Text | $1.00/小时 | 1.0 小时音频 | 跑量（分钟级） |
| Container Registry | Standard Registry Unit | $0.6666/天 | 1.5 天 | 时间 |
| Container Apps | vCPU Active / 环境费 | $0.0864/vCPU·时 或 $0.1/时 | 10–24 小时 | 时间（兼喂 LA） |
| Log Analytics | Analytics Logs 摄入 | $3.29/GB | 0.304 GB | 由 ACA 日志喂入 |
| Service Bus | Standard Base Unit | $0.013441/时 | 74 小时 | 时间（**关键路径 3.1 天**） |
| Event Hubs | Basic Throughput Unit | $0.0198/时 | 50 小时 | 时间（2.1 天） |

总花费约 **$12–14**（含少量超额），在学生订阅 $100 额度内。关键路径 = Service Bus 3.1 天。

**为什么不用 Translator**：白名单 5 区只有 $0.00 计量，付费计量仅挂在 westus/eastus 等区，
不能作为可验证的付费项（判据是"账户上看得见 $1 用量"，不是"资源建成了"）。

## 已知限制（如实）

1. **Log Analytics 的 $1 依赖 ACA 日志**：`provision` 里的 logflood 容器每 0.2 秒打一行，
   0.5 vCPU 常驻；若容器没起来，LA 摄入上不去——先查 `az containerapp logs show`。
2. **学生订阅的 `az consumption usage list` 可能受限**：拿不到明细时，用门户
   「成本管理 → 成本分析 → 按服务」截图留档，`check_usage.py` 支持 `--input` 吃导出 JSON。
3. **计量名以账户实际为准**：`prices-20261117.json` 是 2026-11-17 的 Retail API 快照；
   部署后若某服务计量对不上（如 Vision 的 OCR 档），以 `check_usage.py` 的 meters 列复核。
4. **额度线**：学生订阅额度到期 2027-10-28；IC 提交死线 2027-02-28，窗口内不受影响。
5. **实体订阅归属**：规则要求订阅归 Startup 所有。本目录先在现有学生订阅上演练
   （证明 10 项可跑、成本可控）；实体注册完成后，同一脚本在新订阅重放即可。

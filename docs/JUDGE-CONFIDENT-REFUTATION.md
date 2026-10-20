# 判决层"自信错驳"台账（观察卡 v1）

状态：观察卡（**不定罪**，样本积累中）｜建档：2026-10-18
定位：记录 verify 判决层"高置信地判错"的实弹样本，与判分器词面冤案（下游追词面）严格区分。
联动：`docs/VERIFY-EVIDENCE-CONTRACT.md`（证据层，T4）｜`docs/JUDGE-EQUIV-V2-DESIGN.md`（词面层）｜`docs/K2-INTENDED-REVIEW.md`（真值源）

## 一、定义与判定标准

- **自信错驳**：verdict=`REFUTED` 且 confidence ≥ 0.9，而独立真值（官方 writeup / solve.py / flag 全链）证明该主张真实。
- 与 **UNCERTAIN 不猜** 区分：后者是诚实的不确定，不产生 refuted_on_intended；前者是主动给出错误判决。
- 与 **词面冤案** 区分：类型标签差异（如 RCE vs REMOTE_CODE_EXECUTION）属判分器等价类问题；机制/事实判断错误属判决层问题，两者不可混记。
- 计数口径：每题每卷至多记一条；同一题同一链的多卷复现按独立样本计。

## 二、样本表（截至 2026-10-18，共 2 条）

| # | 卷/臂 | 假设 | 判决 | 模型给出的理由（摘要） | 独立真值 | 定性 |
|---|---|---|---|---|---|---|
| 1 | 10-18 16:26 gatekeeping 并行卷（concurrency=3） | H3 `HEADER_INJECTION`（gunicorn SCRIPT_NAME 头走私绕 nginx `/admin`） | REFUTED 0.9 | gunicorn 不会把客户端 `SCRIPT_NAME` 头映射进 WSGI environ，头只会变成 `HTTP_SCRIPT_NAME` | 官方 readme spoiler + `solve.py`：`SCRIPT_NAME: asdf/` + `/asdf/admin/key` 实际命中 `/admin/key`，链真实 | 自信错驳 |
| 2 | 10-18 20:32 gatekeeping 验收卷（固定假设集、strands 1.56.0、串行） | H2 同一官方链（SCRIPT_NAME 头走私） | REFUTED 0.9 | 同上（"gunicorn 通常不把客户端 SCRIPT_NAME 头写进 environ"） | 同上（writeup + solve.py） | 自信错驳（同题同链跨卷复现） |

共同特征：两次都**没有读仓内官方解**（verify 数据块当时不含 `solution/solve.py`，缺陷②），并用模型对 gunicorn 默认行为的"记忆"替代仓内证据——错驳理由方向一致、置信度一致（0.9），说明不是单次采样噪声。

## 三、明确不是样本（防混账）

- **K1 版 gatekeeping H3 `INFORMATION_DISCLOSURE` CONFIRMED 0.92**：这是**高置信正确**（字面 TP，密钥泄露=官方链交付物），不是错驳。0.92 不得再被引用为"错驳旧账"。
- 旧账 gatekeeping 混合臂 H3 0.92 不计 TP 案：属"不猜/映射口径"议题，不是错驳。

## 四、影响面

- 题目级：`refuted_on_intended=1` 在协议中=独立口径 FP（flag 说了算），gatekeeping 两卷各命中 1 次。
- 机制级：与证据契约缺陷（运行类/仓内文件不在证据链）耦合——**证据不足时应判 UNCERTAIN 而不是 REFUTED**，当前提示词有"未命中→REFUTED"的倾向，需在 T4 案甲中把 E3 推理强制映射为 UNCERTAIN。

## 五、升级与处置门槛

- **不定罪**（当前 2 样本、同题同链）。升为"机制性错驳"需满足其一：跨 ≥2 题复现，或固定假设集 ≥3 卷复现。
- T4 案甲落地后固定假设集复测 gatekeeping：若 H2 仍 REFUTED 0.9（证据包已含 solve.py 仍判错），转判决层第三案（提示词/证据包预算/verify 模型三选一单变量）。
- 若复测变为 UNCERTAIN 或 CONFIRMED：本条关闭，归因证据契约修复。

## 六、预注册实验 v1（2026-10-19，T4 案甲后固定假设集复测）

**目标**：单变量验证“证据包 + E2 严格引文”是否让 H2 从自信错驳变为有据判决。判据在看到结果前固定，不允许事后改判。

**输入**：10-18 串行卷固定假设集（§二样本 2）；gatekeeping 仓；`verify=gpt-oss-verify`；`ARCA_VERIFY_MAX_CONCURRENCY=1`；`ARCA_VERIFY_EVIDENCE_STRICT=1`；strands-agents 1.56.0。

**命令**：
```bash
PREFLIGHT=1 bash scripts/run-verify-acceptance.sh   # 只查仓/模型服务
bash scripts/run-verify-acceptance.sh               # 正式跑
python eval/check_verify_acceptance.py <OUT>/e2e_report.json --target H2
```

**判定表（只看 H2）**：

| 结果 | 判定 | 台账处置 |
|---|---|---|
| A. `CONFIRMED`（任意置信） | 证据契约修复生效 | 样本 2 关闭 |
| B. `UNCERTAIN` 且 method 含 `quote-check-failed`，或无 E1/E2 | 契约按设计拒绝“无据错驳” | 样本 2 关闭，归“证据不足”口径 |
| C. `UNCERTAIN` 非降级、非 quote-check-failed | 判决仍保守，需看证据包实际内容 | 样本保留，判“证据仍不足” |
| D. `REFUTED` ≥0.8，且日志/证据包确认含 `solution/solve.py` | 自信错驳升级为机制性错驳**候选** | 还差跨 ≥2 题或第 3 卷 |
| E. `degraded=True` 或出现 `peg-native` | 不是判决结果，本卷作废 | 先修基建，再复测 |

**附加纪律**：
- 只改一个变量（T4 证据包/E2），不换模型、不改并发、不改假设集。
- 记录 strands 版本、verify 路由、假设集来源；能导出证据包文件列表就导出。
- H2 未出现在假设集 → 实验装配错误，不进入 A–E 判定。
- 若结果为 D，第三案仍按 §五单变量纪律：提示词、证据包预算、verify 模型三选一，不同时动。

## 七、10-19 复跑实证：单次 PASS 不成立，peg-native 是随机事件

同一固定假设集、同一 `gpt-oss-verify`、`strands-agents 1.56.0`，四卷实拍：

| 卷 | 代码 | 证据包 | temp | `verify_degraded` | 降级/判决 |
|---|---|---|---|---|---|
| `gatekeeping-pinned-t4` | c8bdac6 | 默认 60000 | 服务端默认 | 3 | H2/H3/H4 降级；H1 CONFIRMED |
| `gatekeeping-pinned-t4-minpack` | c8bdac6 | `MAX_TOKENS=1` | 服务端默认 | 2 | H2/H3 降级；H1 CONFIRMED；H4 `quote-check-failed` |
| `gatekeeping-pinned-preT4` | c638cf6（T4 之前） | 旧最小包 | 服务端默认 | 2 | H1/H2 降级；H3 CONFIRMED；H4 REFUTED |
| `gatekeeping-pinned-t4-temp0-r1` | c8bdac6 | 默认 60000 | 0 | 2 | H1/H3 降级；H2 CONFIRMED；H4 `quote-check-failed` |
| `gatekeeping-pinned-t4-temp0-r2` | c8bdac6 | 默认 60000 | 0 | 待 dump | 日志：2 CONFIRMED / 2 UNCERTAIN，213.7s |

**结论**：

1. **不是 T4 回归**：T4 之前的 `c638cf6` 同一固定集也出现 2/4 降级；而 10-18 同提交曾 0/4。同一代码、同一模型路由，结果不同。
2. **温度=0 不足以钉住**：r1 与 r2 的判决集不同，说明 llama.cpp/工具调用层仍有非确定性；`peg-native` 会在不同假设上随机出现。
3. **10-18 的 T6 PASS 必须降级为“单次成功样本”**，不能作为稳定验收；凡“verify_degraded=0”宣称都必须附 N≥3 复跑与降级率。
4. **已实施兜底**（`e30612f` + 契约修复阶段补丁）：首次 invoke 两次 peg-native 失败，或“首次成功但缺 id、契约修复调用被 peg-native 拒绝”时，都用 `tools_enabled=False` 的无工具 Agent 做一次纯 JSON 裁决；仅失败路径触发，不改变正常路径。验收脚本钉 `ARCA_VERIFY_TEMPERATURE=0`。**N=3 实拍：r1/r2/r3 = 0/1/0 降级，但 `无工具兜底成功` grep=0**——r1/r3 的零降级是采样运气，不是兜底生效；r2 的 H3 正是契约修复阶段被 peg-native 拒绝，已由本补丁覆盖，待下一轮 N=3 验证。
5. **T4 证据包结论**：尚不能定罪，也不能宣称有效；在 parser 稳定前，T4 效果实验全部暂停，先跑无工具兜底 N≥3 的稳定率。

## 八、10-20 根因定罪与稳定验收：`<|constrain|>VerificationResult` 被 llama.cpp PEG 拒绝

同一固定假设集（gatekeeping H1–H4）、`gpt-oss-verify`、`strands-agents 1.56.0`、`temp=0`、`max_concurrency=1`，新 pod `dsw-2277665` 实拍：

| 阶段 | 代码/开关 | 卷数 | 结果 |
|---|---|---|---|
| 带 structured output（旧默认） | d10ba38 | 3 | degraded 3/1/1；H2 仅 r1 降级 |
| H4 单题，旧兜底 | 3cc6654 | 3 | r1 PASS / r2 缺 id 降级 / r3 兜底成功但 evidence 27<40 |
| H4 单题，plain-json 主路径（首版） | 26be328 | 5 | 5/5 降级；raw 为 `verification_result/status/evidence[]` 变体 |
| H4 单题，补输出契约 | 44578cd | 5 | r1 PASS，其余因 `\x1b`（非法转义或裸控制字符）解析失败 |
| H4 单题，`strict=False` 解码 | b309874 | 5 | **5/5 PASS**（deg False，peg 持平） |
| 全量固定集 N=3，plain-json | b309874 + 验收臂默认 | 3 | **3/3 PASS，`DEG 0`**；H1/H2/H3 CONFIRMED，H4 被 E2 降为 UNCERTAIN |

**根因证据（服务端原文）**，`/root/srv_gptoss.log`：

```
common_chat_peg_parse: unparsed peg-native output: <|channel|>final <|constrain|>VerificationResult<|message|>{"hypothesis_id":...}
```

即 JSON 本身完整合法，llama.cpp 的 PEG 解析器卡在 structured output 的 `<|constrain|>VerificationResult` 标记上。

**已实施**：

1. `ARCA_VERIFY_PLAIN_JSON=1`：verify 主路径关闭 structured output，改纯文本 JSON；`_json_object_from_text` 支持 `verification_result` 包层、`status`→`verdict`、evidence 数组拼接、`\xHH` 非法转义与裸控制字符（`strict=False`）。
2. 无工具兜底 agent 使用专用 system prompt（不再描述工具），并关闭 structured output；契约修复两次缺 id 时也走二次无工具兜底。
3. 兜底增加 attempted/failed 显式日志（旧 `grep 成功=0` 无法区分“未触发”与“触发但失败”）。
4. 验收脚本 preflight 导入 `codeark.agents.verify_agent`（新 pod 缺 strands 当场失败）；验收臂默认 `ARCA_VERIFY_PLAIN_JSON=1`。

**边界**：

- 这是“固定假设集 + gpt-oss 路由 + 验收臂”的稳定 PASS，不泛化到其他题/模型；K1 判分器不受影响，无需重判。
- 生产默认仍保留 structured output（环境变量未设=0）；是否升为全局默认待拍板。
- H4 的 UNCERTAIN 是 E2 引文护栏（引文含 `\x1b`/空格与仓内不逐字），`deg=False`，属判决层正常行为，不计入降级。

### 八·补：T4 证据包解冻首测（2026-10-20 22:13–22:26，N=3×2）

parser 稳定后按单变量纪律跑默认包 vs 最小包（`ARCA_VERIFY_EVIDENCE_MAX_TOKENS=1`），
均为 plain-json 验收臂、固定假设集、`gpt-oss-verify`：

| 臂 | 卷 | DEG | H1 | H2（官方链） | H3 | H4 |
|---|---|---|---|---|---|---|
| default（60000） | 3 | 0/0/0 | CONFIRMED ×3（65） | **CONFIRMED ×3（319）** | CONFIRMED ×3（408） | UNCERTAIN ×3（E2） |
| minpack（1） | 3 | 0/0/0 | CONFIRMED ×3（65） | **UNCERTAIN ×3（151）** | CONFIRMED ×3（144） | UNCERTAIN ×3（E2） |

**结论**：证据包对 H2 是决定性的（有包→CONFIRMED，无包→UNCERTAIN）；H1 不受影响；
H3 判决稳定但证据长度 408→144 明显变短；H4 始终被 E2 引文护栏拦下。两臂 6/6 卷
`CHECK rc=0` 且零降级，说明该对比已不受 parser 噪声干扰。

**边界**：N=3、单仓、单模型、最小包是极端消融（仅假设文件），不能外推为“证据包对
所有题都有效”；default 臂 H2/H3 证据三卷逐字一致属该固定集下的观察，不作为全局确定性宣称。

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

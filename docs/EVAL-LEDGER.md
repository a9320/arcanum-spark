# 实验台账（EVAL-LEDGER）— 仓内引用数字的证据链

目的：代码注释/文档中出现的每一个实验结果数字，必须可溯源到可核验的原始产出。

证据链三层：**原始报告**（DSW 持久区 `/mnt/workspace/runs/`，跨 pod 重建存活）→
**WORK_LOG 区块**（根仓库 `WORK_LOG.md`，逐区块追加、每跑必记）→ **仓内落仓**
（本仓 `reports/`，提交=9e5a0d1 起）。本台账逐项登记四元组：
数字 → 产生方式 → 原始证据位置 → 仓内落仓状态。

纪律：
- 任何实验数字进代码/文档前，先在本台账登记证据位置；无证据位置的数字不得入仓。
- 落仓状态=PENDING 的项，在产出回传归档后翻转为对应 `reports/` 路径，禁止长期悬空。
- 考卷/难负样本为确定性手工构造（anti-leak 断言保证与训练数据零重合），测的是判别
  能力，不代表真实代码分布——真实分布审计依赖 M8 独立标注集（K1 CTF flag 真值，
  设计协议见 `docs/M8-CTF-TRUTH.md`）。

## 台账

| 数字/结论 | 含义 | 产生方式 | 原始证据位置 | 仓内落仓状态 |
|---|---|---|---|---|
| tfidf AP=0.293 | hard_exam/2 基线锚点（N=24，跨机 3 次逐位复现） | `eval/build_hard_exam.py --self-check` + `eval/replay.py score --backend tfidf` | DSW `/mnt/workspace/runs/gate_dataset_hard.json`；根仓库 WORK_LOG 09-29 22:42 区块 | **IN-REPO** `reports/hard-exam-v2/scores_tfidf.log`（AP(KEEP)=0.293，2026-09-30 第三次跨机复现） |
| laya-r2 AP=0.574 | hard_exam/2 上 laya-r2 得分 | `eval/replay.py score --backend laya --model laya-r2` | 同上 | **IN-REPO** `reports/hard-exam-v2/scores_r2.log`（AP(KEEP)=0.574） |
| laya-r3 AP=0.958 | hard_exam/2 上 laya-r3 得分（门 2 v2 通过：H9 rank 1/24、ECHO 谷 0.771、误剪 3 全为 tie） | 同上 `--model laya-r3` | 同上 | **IN-REPO** `reports/hard-exam-v2/scores_r3.log`（AP(KEEP)=0.958；校准 Brier=0.105/ECE=0.153/conf=0.692 与 09-29 记录逐位一致） |
| variant-20 gate 双臂验收 | laya gate（protected=[H1]、H6 沉底）与 deterministic 臂，fallback=False、质量不降（门 3 首验） | `eval/run_gate_e2e.py` | DSW `/mnt/workspace/runs/20260929-gate-v20/`；根仓库 WORK_LOG 09-29 22:42 区块 | 部分：扩仓同型证据已 IN-REPO（下行）；v20 原件仍在 DSW 持久区 |
| **M4 扩仓验收（v23/27 双臂）** | P1 reorder-only + P2 no-fallback **4/4 全过**；P3 两个 FAIL 经假设级三方 diff 判定为 **Verify 采样噪声**（非 gate 劣化；v27 两臂同假设集 5C vs 3C 实证） | `eval/run_gate_e2e.py` + `eval/compare_gate_e2e.py` | DSW `/mnt/workspace/runs/20260930-ablation/`；根仓库 WORK_LOG 09-30 终章区块 | **IN-REPO** `reports/variant-2?_gate_*/`（四臂原始报告）+ `reports/gate-e2e/acceptance-variant-2{3,7}.{json,md}` |
| **M2/M3 三臂消融（6 仓）** | 六agent CONFIRMED 增量 **26**（2-6/仓）vs 单agent claimed **51**（无背书，快 5-10×）vs 规则臂 0 语义——多 agent 的边际价值=验证与裁决层 | `eval/run_single_agent.py` + `python -m codeark.cli` + `eval/summarize_ablation.py` | DSW `/mnt/workspace/runs/20260930-ablation/`；根仓库 WORK_LOG 09-30 终章区块 | **IN-REPO** `reports/ablation/summary-variant-*.md` + `reports/single_agent_variant-*/` + `reports/e2e_variant-2?/` |
| e2e 12 发现/3 假设/3 CONFIRMED/3 链/risk 9 | 本地全链 demo 验收（零降级，真实 DeepSeek） | 本地 `ARCA_DEPLOYMENT=local` 全链 e2e | 本仓 `reports/e2e_report.{json,sarif,markdown}` | IN-REPO |
| **laya-r6 满分卷** | hard_exam/2 上 **24/24**（TP6/FP0/TN18/**FN0**）、AP=1.0、Brier 0.029、ECE 0.1016、wrong_items=[]——BOUND-5B 翻正，微调环路 20→21→23→**24** | `eval/build_r6_hardneg.py`（19 条）→ records_r6.train(510) → `eval/finetune_train.py`（base laya 重训）→ `eval/time_laya.py --model laya-r6` | DSW `/mnt/workspace/models/laya-r6/` + `/mnt/workspace/runs/20260930-r6-train.log`（TRAIN_DONE，第二次运行逐位复现）；根仓库 WORK_LOG 10-01 19:48 区块 | **IN-REPO** `reports/hard-exam-v2/timing-r6.json`（407ef51，与 DSW 实跑逐位核对） |
| **gate v1.1 v23 = ACCEPT（⚠2026-10-02 P4 复核降级为 REJECT，见下行 recheck 行）** | Verify temp=0 三臂：laya **3(3)/10(10) 计数一致**（原判"逐位一致"；P4 复核实为计数巧合——laya 确认集缺基线 CONFIRMED 的 H3，未钉假设集宇宙漂移）；det 4(3)/11(10) 反超 1C（上下文耦合观测项）；Seconds 1563/1167s=真流水线 | `eval/run_gate_e2e.py --backend {laya,deterministic}` + `eval/compare_gate_e2e.py`（`ARCA_DEPLOYMENT=local`+`ARCA_VERIFY_TEMPERATURE=0`） | DSW `/mnt/workspace/runs/20261001-gate11/`（GATE11_ALL_DONE 19:02）；根仓库 WORK_LOG 10-01 19:48 区块 | **IN-REPO** `reports/gate11/acceptance_v23.{md,json}` + `nogate_v23/`、`laya_v23/`、`det_v23/`（407ef51，bundle6 第六轮） |
| **gate11 P4 复核 = v23/v27 全 REJECT** | 对照器新增 **P4 confirmed-coverage**（基线 CONFIRMED 逐键 ⊆ 臂确认集；外审整改 2026-10-02）：v23 laya 丢 H3（P3 计数地板仍 ✅=数量判据盲区实证）、det 全过；v27 laya 丢 H2,H6、det 丢 H2。未钉数据上 id 为位置级键，P4 失败=宇宙漂移或真损失→从严 REJECT；**钉假设集重验收（登记册 #2）由此成为唯一验收路径** | 同上 `compare_gate_e2e.py`（schema /2，P1-P4 四判据） | 本地复算自仓内 `reports/gate11/` 数据（2026-10-02） | **IN-REPO** `reports/gate11-recheck/acceptance_v2{3,7}.{md,json}`（本 commit） |
| **gate v1.1 v27 REJECT 判污染作废** | laya 4(6)/11(13) P3❌，**但三臂假设集 6/7/5**（scout muse temp1.0 每臂独立发挥）且 laya `pruned_ids=[]` 全数送验——CONFIRMED 差额系假设集不同非 gate 伤害，**本 REJECT 不得引用为 laya gate 劣化证据**；~~分数越界~~ H3=1000.8982 **实为 gate 设计内 protected +1000 fail-safe 加成**（`gate.py` laya 分支：`score += 1000.0`，模型原始分 0.8982 在 [0,1] 契约内，两次运行 0.8202/0.8982 同构复现）——"钉假设集"= gate v1.2 改进项，**无钳位需求**（10-01 晚复核订正） | 同上；假设集原件=六跑 `summary.json` 的 hypotheses/verify_requests/gate.scores 字段；加成实现=`codeark/graph/gate.py` laya 分支 | 同上 | **IN-REPO** `reports/gate11/acceptance_v27.{md,json}` + 六跑 `summary.json`（gate.scores 原件在 `laya_v27/summary.json`）（407ef51） |

## 更新记录

- 2026-09-30 初版（外部审计整改第 2 条：终结"数字只活在 docstring"——建立四元组证据链）。
- 2026-09-30 晚 回填：hard_exam/2 三方 score、M4 扩仓、M2/M3 三臂全部 IN-REPO（commit 9e5a0d1，bundle 兜底完成 transfer）；新增 M4 扩仓与三臂消融两行；v20 双臂原件仍标注 DSW 持久区。
- 2026-10-01 回填：R6 满分卷（laya-r6 24/24）、gate v1.1 三臂验收（v23 ACCEPT；v27 REJECT 因 scout 假设集 6/7/5 污染作废，另录 laya-r5 分数越界 H3=1000.9 发现）三行 IN-REPO（数据=407ef51，bundle6 第六轮 transfer；本 commit=台账）。
- 2026-10-01 晚订正：v27 行"分数越界"判定撤回——H3=1000.8982/1000.8202 系 `gate.py` laya 分支 protected +1000 设计加成（fail-safe 排第一），模型原始分 0.8982/0.8202 在 [0,1] 契约内；无钳位需求，gate v1.2 改进项仅剩"钉假设集"。
- 2026-10-02 外审整改：对照器 **P4 confirmed-coverage** 判据落地（数量地板对假设集漂移失明的堵口）+ `m8_k1_score.py` **FN 聚合补全**（tp→False/无假设或全 PRUNE-REFUTED→True/UNCERTAIN 或未验证→null）。gate11 两行验收经 P4 复核改判（v23 ACCEPT→REJECT 丢 H3，v27 REJECT 维持丢 H2,H6/H2）——未钉数据上的预期结果，钉集重验收（登记册 #2）为唯一路径；recheck 产物 IN-REPO（reports/gate11-recheck/，本 commit）。

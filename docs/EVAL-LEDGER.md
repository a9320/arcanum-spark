# 实验台账（EVAL-LEDGER）— 仓内引用数字的证据链

目的：代码注释/文档中出现的每一个实验结果数字，必须可溯源到可核验的原始产出。

证据链三层：**原始报告**（DSW 持久区 `/mnt/workspace/runs/`，跨 pod 重建存活）→
**WORK_LOG 区块**（根仓库 `WORK_LOG.md`，逐区块追加、每跑必记）→ **仓内落仓**
（本仓 `reports/`，批作业产出回传后归档）。本台账逐项登记四元组：
数字 → 产生方式 → 原始证据位置 → 仓内落仓状态。

纪律：
- 任何实验数字进代码/文档前，先在本台账登记证据位置；无证据位置的数字不得入仓。
- 落仓状态=PENDING 的项，在产出回传归档后翻转为对应 `reports/` 路径，禁止长期悬空。
- 考卷/难负样本为确定性手工构造（anti-leak 断言保证与训练数据零重合），测的是判别
  能力，不代表真实代码分布——真实分布审计依赖 M8 独立标注集（K1 CTF flag 真值，已立项）。

## 台账

| 数字/结论 | 含义 | 产生方式 | 原始证据位置 | 仓内落仓状态 |
|---|---|---|---|---|
| tfidf AP=0.293 | hard_exam/2 基线锚点（N=24，跨机 3 次逐位复现） | `eval/build_hard_exam.py --self-check` + `eval/replay.py score --backend tfidf` | DSW `/mnt/workspace/runs/gate_dataset_hard.json` + score stdout；根仓库 WORK_LOG 09-29 22:42 区块 | PENDING → `reports/hard-exam-v2/`（今晚随批作业 tee 落仓） |
| laya-r2 AP=0.574 | hard_exam/2 上 laya-r2 得分 | `eval/replay.py score --backend laya --model /mnt/workspace/models/laya-r2` | 同上，WORK_LOG 09-29 22:42 区块 | PENDING → 同上 |
| laya-r3 AP=0.958 | hard_exam/2 上 laya-r3 得分（门 2 v2 通过：H9 rank 1/24、ECHO 谷 0.771、top-3 误剪 3 全为 0.953 同分 tie） | 同上 `--model /mnt/workspace/models/laya-r3` | 同上，WORK_LOG 09-29 22:42 区块（逐判据明细） | PENDING → 同上 |
| variant-20 gate 双臂验收 | laya gate 臂（hyps 7→req 7、protected=[H1]=1000.99、H6 沉底 0.303）与 deterministic 臂（H2..H6 并列 12.0 不重排），fallback 均 False、对照 09-28 基线质量不降 | `eval/run_gate_e2e.py <repo> --backend laya\|deterministic` | DSW `/mnt/workspace/runs/20260929-gate-v20/{laya_arm,det_arm}/`（报告+summary）；根仓库 WORK_LOG 09-29 22:42 区块 | PENDING → `reports/gate-e2e/` |
| variant-20 六 agent 基线 | 6 假设 4C+2U、合并 findings 10（gate 对照基线） | 全链 e2e（四服务） | DSW `/mnt/workspace/runs/20260928-variant-20/`；根仓库 WORK_LOG 09-28 区块 | PENDING → `reports/gate-e2e/` |
| M2/M3 三臂消融 | 六agent CONFIRMED 口径 vs 单agent claimed 口径（两口径不可混读） vs 规则臂 0 | `eval/run_single_agent.py` + `eval/summarize_ablation.py` | 尚未产生（今晚批作业） | 未产生 → `reports/ablation/`（今晚落仓） |
| e2e 12 发现/3 假设/3 CONFIRMED/3 链/risk 9 | 本地全链 demo 验收（零降级，真实 DeepSeek） | 本地 `ARCA_DEPLOYMENT=local` 全链 e2e | 本仓 `reports/e2e_report.{json,sarif,markdown}` | IN-REPO |

## 更新记录

- 2026-09-30 初版（外部审计整改第 2 条：终结"数字只活在 docstring"——建立四元组证据链，今晚批作业后回填落仓状态）。

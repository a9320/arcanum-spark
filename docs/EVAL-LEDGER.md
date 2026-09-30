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

## 更新记录

- 2026-09-30 初版（外部审计整改第 2 条：终结"数字只活在 docstring"——建立四元组证据链）。
- 2026-09-30 晚 回填：hard_exam/2 三方 score、M4 扩仓、M2/M3 三臂全部 IN-REPO（commit 9e5a0d1，bundle 兜底完成 transfer）；新增 M4 扩仓与三臂消融两行；v20 双臂原件仍标注 DSW 持久区。

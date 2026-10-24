# T4b 证据包可迁移性复测（2026-10-24，poem-collection 两臂 N=3）

**配置**：pod `dsw-2294220`、spark HEAD=`9a796dd`、gpt-oss-verify :8085、固定假设集（源=10-18 new2q poem-collection 卷，4 假设）、plain-json 验收臂、temp=0、串行；单变量=证据包（default `ARCA_VERIFY_EVIDENCE_MAX_TOKENS` 默认 60000 vs minpack `=1`）。输出 `runs/20261021-t4b/poem-{default,minpack}-r{1..3}`。

## 一、六卷实拍（verdict/confidence，六卷零降级）

| 假设 | default-r1 | r2 | r3 | minpack-r1 | r2 | r3 |
|---|---|---|---|---|---|---|
| H1 官方链（src/poems/index.php:2 `$_GET` LFI） | C 0.95 | C 0.95 | C 0.95 | C 1.0 | C 0.95 | C 0.95 |
| H2 docker socket（越界） | UNC 0.6 | REF 0.8 | REF 0.8 | UNC 0.4 | UNC 0.5 | UNC 0.5 |
| H3 .htaccess flag 保护 | C 0.95 | C 0.95 | C 0.95 | UNC 0.3 | UNC 0.3 | UNC 0.3 |
| H4 README flag artifact | C 1.0 | C 1.0 | C 1.0 | C 1.0 | C 1.0 | C 1.0 |

## 二、结论

1. **T4 一期边界修正（本实验主判读）**：一期 gatekeeping 实证"证据包对官方链决定性"（default CONFIRMED ×3 / minpack UNCERTAIN ×3），本期 poem-collection **未复现**——官方链 H1 两臂均 CONFIRMED ×3。根源 = **官方链证据自含性**：poem-collection H1 的证据在假设快照自带的 `index.php` 内（minpack 也完整喂到），gatekeeping H2 依赖外仓 `solution/solve.py`（minpack 饿死）。**T4 结论修正为："证据包决定性取决于官方链证据是否自含于假设文件"——可迁移性 = 部分迁移。**
2. **minpack 证据饥饿签名**：H3 三卷稳定 UNCERTAIN 0.3（default 0.95）——与一期"H3 证据 408→144"同一机制，本期跨过判决阈值；H2 同降区间（0.6→0.4/0.5）。饥饿按假设异质分布，非全称。
3. **越界假设跨卷方差 +1 样本**：default 臂 H2 `UNCERTAIN 0.6 ↔ REFUTED 0.8×2`（判决层台账采样类第 2 实例；REFUTED 0.8 < 0.9，不入高置信错驳）。
4. **管线健康**：六卷零 `degraded`、零 peg-native——plain-json 主路径在第三个 pod 复证稳定。
5. **judge v0.7 首次真实回放 PASS**：default 三卷按 `<cid>/report.json + run2/run3` 布局喂 `--min-runs 3` → `AGG tp=True / fn=False / runs=3 / insufficient=False / confident_refutations=[]`；机制与语义口径同为 tp=1。**阈值校准实弹验证**：H2 REFUTED 0.8 正确地**未**触发 0.9 错驳嫌疑（无误报）。

## 三、台账波及

- `docs/JUDGE-CONFIDENT-REFUTATION.md`：无新样本（0.8 < 0.9）。
- 判决层台账采样类（跨卷方差）：+1 实例（H2 越界假设，跨臂同现）。
- T4 证据契约结论边界修正入本报告；`VERIFY-EVIDENCE-CONTRACT.md` 升版待拍板（建议在其 §结论 追加自含性边界一行）。

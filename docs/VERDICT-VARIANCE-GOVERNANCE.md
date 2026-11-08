# 判决层方差治理设计稿 v1（2026-10-25，纯文档零代码，待拍板）

**输入**：判决层台账采样类三样本（4/4b/4c）+ 契约类三项 + T5 拍板清单剩余项（③④⑤）；T4c 梯度谱系定谳（`reports/20261025-t4c-evidence-gradient.md`）。定位：verify 层五刀已把契约类压到个位数，本稿治理**判决输出的跨运行方差**。
**溯源注（10-25 审计 A-F11）**：采样类样本 #4 的原始记录在主台账（根仓《判决层台账归类-T5输入.md》+ WORK_LOG，均不在本仓）；本仓内可溯源锚=reports/20261024-t4b（#4b）与 reports/20261025-t4c（#4c）两份报告。

## 一、核心立论：方差分两种，治理方向相反

| | 假方差（措辞抖动） | 真方差（证据状态差异） |
|---|---|---|
| 实例 | 台账 4：定性词措辞抖动→`C 0.95 ↔ UNC 0.4` 大幅摆动；4b：`UNC 0.6 ↔ REF 0.8` | 台账 4c：minpack 饥饿下 `UNC 0.4 ↔ C 0.9`（库行为证实面转参数知识承担） |
| 本质 | 同一证据状态，confidence 锚在 mild/moderate/severe 类措辞上抖动 | 证据包内容不同，判决依据真的变了 |
| 治理 | **压平**：离散分档消放大器（D1） | **显式化**：grounding 溯源 + 饥饿标记（D2/D3），不压平——压平真方差=掩盖信息缺失 |

混治理是反模式：把 4c 的 0.4 拉齐到 0.9 会把"证据不足"伪装成"稳定确认"。

## 二、治理杠杆（D1-D5）

### D1 confidence 离散五档（T5 清单③落地，P1）

- **现状**：prompt 允许 0~1 自由数值（实测落点 0.3/0.4/0.5/0.6/0.75/0.9/0.95/1.0，档距不均无定义）；`confidence_to_float`（schemas.py:31）已有 high=0.9/medium=0.6/low=0.3 枚举兜底但仅解析侧、未进 prompt；数值直通。
- **改动**：VERIFY_ONE prompt 钉五档枚举+判据定义；解析侧加 round-to-nearest-anchor（tie 取低保守档）：
  - `0.95` 仓内文件逐字证据直接证实（E2 逐字引文命中）；
  - `0.9` E1/E2 证据证实但含推断链；
  - `0.75` 部分仓内证据 + 库知识补全；
  - `0.5` 证据不足一半 / 依赖未验证外部行为；
  - `0.3` 纯推理（E3）或证据饥饿。
- **预期**：措辞抖动失去放大器（0.4/0.6 级摆动收敛进同档）；0.9 错驳阈值与档位自然对齐。
- **风险**：档位定义本身是新措辞锚——靠预注册实验验档间稳定性（§四）；存量卷数值不在档上，判分器按 round 口径统一（回放可复算）。

### D2 判决依据溯源字段 `evidence_source`（新，P1 与 D1 同刀）

- **现状**：E1/E2/E3 只是 prompt 约定（CONFIRMED 需 E1/E2），输出不含 grounding 标记，4c 的"参数知识承担"不可见。
- **改动**：VerificationResult 增加 `evidence_source` 枚举：`repo_file`（仓内逐字引文）/ `tool_result` / `library_knowledge`（模型参数知识，非仓内）/ `reasoning_only`；CONFIRMED 且含 `library_knowledge` 打标 `partial_grounding`。
- **预期**：0.4↔0.9 类真方差从"莫名抖动"变成可解释差异（default 卷应主要落 repo_file，minpack 卷落 library_knowledge）——t4c 六卷即现成回放材料。

### D3 证据包健康度前置标记 `starving`（T5 清单④的 verify 侧延伸，P2）

- **现状**：证据包预算逻辑在 `_evidence_pack`，塞不下时静默截断；饥饿只在事后由方差反推（4c）。
- **改动**：pack 构建后输出统计（pack_tokens / 假设点名文件覆盖率）；覆盖率低于阈值 → 判决记 `starving=True`。
- **预期**：判分器把"证据不足卷"与采样方差分开计数（台账 4c 根因定性从混合拆开）；生产边界（非极端消融）的轻度饥饿可见。

### D4 跨卷方差指标自动化（judge v0.7 增量，P2）

- **现状**：v0.7 已 N≥3 聚合（tp=任一卷 C / fn=全卷一致才 True / insufficient），但跨卷 verdict 翻转要靠人工读台账。
- **改动**：聚合行加 `verdict_flips`（同假设多卷 verdict 不一致即记，含档位对齐后的翻转）；flips>0 的判决进复核候选清单。
- **预期**：台账采样类归类自动化，复核有了机选入口（与 confident_refutations 并列的第二复核臂）。

### D5 FinalReport 输出契约钉死（T5 清单⑤，P2）

- confidence 强制数字型 / `verification_method` 枚举（消字面量 "E2"）/ degraded.reason 分类学（`contract/parse/tool-fail/context`）/ 驳判理由透传 / lateral 与 remediation 分离（台账 6/7 联动）。
- **预期**：契约类 1/2 的 schema 重试自愈路径整体退役；语义类 6/7 的报告层字段分离。

## 三、与 T5 拍板清单映射

清单①N≥3、②高置信错驳检测 → 已落地（judge v0.7）；清单③ → D1；清单④ → D3+D5；清单⑤ → D5。新增 D2/D4 为台账 4c 数据驱动增量（T5 成文时无此证据）。

**排期建议**：P1 = D1+D2（同一刀，动 verify prompt+schema+解析，一次 pytest 护航）；P2 = D3+D4+D5（judge 与 FinalReport 层，可与 P1 同窗或顺延）。

## 四、预注册验收实验（下个 DSW 窗，与 K1 重判共用开机）

1. **档间稳定性**：gatekeeping 固定假设集 N=5 重跑（新 schema 臂）——判据：同假设 confidence 档位一致率 ≥ 4/5（基线=旧数值口径逐位一致率，t4b/t4c 卷可算出对照值）。
2. **grounding 可解释性**：t4c 六卷假设集在新 schema 下重跑 minpack 臂 N=3——判据：H1 的 evidence_source 分布随臂漂移（default 主 repo_file / minpack 主 library_knowledge）且与 verdict 相关；H2 两臂均主 repo_file（零效应对照）。
3. **无误报闸**：confident_refutations 在两实验中保持 0（0.9 档不变，不因分档制造错驳误报）。

## 五、拍板项

1. 五档 vs 三档（建议**五档**：三档太粗会制造新的同档异质）；
2. round-to-anchor 平手规则（建议 tie→**低档保守**，0.4→0.3？0.4 距 0.3/0.5 等距——若采五档 0.4 恰为 0.3/0.5 中点，tie→0.5 还是 0.3 需定；建议 tie→0.5 因 0.3 档语义含"饥饿"与"纯推理"，并入会污染 D3 信号）；
3. P1/P2 同窗一刀还是分两刀（建议 **P1 先行**，D2 的字段设计依赖 D1 落地后的回放观察）；
4. 验收实验是否与 K1 全 20 题重判同窗（共用开机，预算 ~1 小时）。

## 六、实施记录（P1=D1+D2，2026-10-25）

- **拍板采纳**（用户"按建议来"）：五档 / 平手取更靠近 0.5 的锚（0.4→0.5，推广后 0.825→0.75）/ P1 先行 / 验收实验留 DSW 窗。
- **D1**：VERIFY_ONE / NOTOOLS / PLAIN_JSON_CONTRACT 三 prompt 块钉五档判据；解析侧 `snap_confidence`（env `ARCA_VERIFY_CONFIDENCE_ANCHORS` 默认 1，=0 回退自由数值口径）在两个模型输出收口点生效（`_normalize_verifications` 结构化路径 + `_coerce_verification` 宽松/纯文本路径）；内部构造（降级记录 0.3 等）不经治理不受影响。
- **D2**：`VerificationResult` 增 `evidence_source`（自由字符串入库防 junk 炸校验，归一化层清洗为四值）+ `partial_grounding`（派生字段，模型不得产出：CONFIRMED ∧ library_knowledge）；prompt 三块加四选一指引。
- **测试**：`codeark/tests/test_verdict_governance.py` 9 锚（snap 锚值/平手/夹取/env 关闸/清洗/派生/双收口贯通/prompt 契约）；410 collected 全绿零回归。
- **待 DSW 验收**（预注册 §四）：①gatekeeping 固定假设集 N=5 档位一致率 ≥4/5；②t4c minpack 臂重跑 H1 grounding 分布随臂漂移（H2 零效应对照）；③confident_refutations 保持 0。
  **✅ 三判据全达标（2026-11-08 DSW 窗，spark `b425fdd`，单次观察口径）**：①4/4=100%（H1 C0.95×5/H2 C0.95×5/H3 C0.95×5/H4 U0.3×5）②H1 default 主 repo_file×3 → minpack 主 library_knowledge×2+repo_file×1（漂移直证），H2 两臂 repo_file×3（零效应）③0——**"治理有效"记入，D1/D2 真机验收关闭**。观察项：H1 今 C0.95 vs 11-02 参照 U0.5（跨窗漂移，本窗含 D5 prompt 变更，不归因）。

## 七、实施记录（P2：D4 2026-11-07 上半天 + D3 2026-11-07 晚）

- **D4（跨卷方差指标自动化）**：`eval/m8_k1_score.py` `_verdict_flips`（同假设跨卷 verdict/五档档位不一致即记，仅计 ≥2 卷在场的假设）+ `_aggregate_runs`/`_aggregate` 两级计数；复核第二臂与 confident_refutations 并列。六卷实测 0 翻转（2026-11-06 卷）。测试=`tests/test_m8_k1_score.py` D4 区。
- **D3（证据包饥饿前置标记）**：
  - **schema**：`VerificationResult` +4 字段 `starving/pack_tokens/pack_coverage(点名覆盖率)/pack_fraction(包宽率)`——均"我方计算，模型不得产出"，`_apply_governance` 清零，`_stamp_pack_health` 为唯一写入点（严格降级分支之后回填，降级路径同样带统计）。
  - **双触发（对 §二 D3 规格的偏离；**2026-11-08 用户拍板追认 1.0/0.5**）**：规格原文只写"点名覆盖率 < 阈值"；实施发现 **minpack 臂（budget=1）下点名文件被 force 进包 ⇒ 点名覆盖率恒 1.0，恰在 4c 饥饿机理上全盲** ⇒ 增第二触发**包宽率** `pack_fraction=pack_tokens/全仓 tokens`（minpack 趋 0）。阈值 env：`ARCA_VERIFY_STARVING_COVERAGE`（默认 1.0）/`ARCA_VERIFY_STARVING_MIN_FRACTION`（默认 0.5）；0=关闸；1e-9 容差防浮点误报。fp 幻觉路径（pack=全量）两率恒 1.0 不误报。
  - **判分器**：verdict 行透传 `starving`（旧 JSON 无键→False 零回归）；flips 逐条附 `starved_runs`（该假设饥饿卷序号）——翻转涉饥饿卷归"证据状态差异"，与纯采样方差分开判读；`_aggregate_runs`/`_aggregate` 增 `starved_verdicts` 与 `flips_with_starved_runs`（4c 根因定性从混合拆开的机读入口）。
  - **测试**：`codeark/tests/test_verify_starving.py` 13 锚（阈值默认/env/非法回退；全包两率 1.0；点名截断 coverage=0.5；幻觉 fp；**minpack 形 coverage 盲区+fraction 点亮**；双闸关闸统计照常；stamp 保字段；治理清零）+ `tests/test_m8_k1_score.py` D3 区 4 锚；verify.sh 5/5。
  - **真机验收（留窗）**：随下窗任一 minpack/default 双臂跑观测——判据=minpack 卷 `starving=True`（包宽率触发）/ default 卷全 False；**只观察遥测，不改 Exp A/B 预注册闸门**。
    **✅ 已达标（2026-11-08 DSW 窗，b425fdd）**：minpack H1 三卷亮（**coverage 触发器**——点名 README 被 budget 截；包宽率 0.5543 贴 0.5 阈上未触发=边界样本）/default 全灭。**阈值拍板（11-08）：保持 0.5**（验收已过不动，边界样本记档等 K1 数据）；**边界发现记档**：verify 输入被 scout 上游截 ~60k→pack_fraction 测不到上游饥饿（该层=degraded_reason=context，D5 接住）。

## 八、实施记录（P2 之 D5 + D2 缺口修复，2026-11-08）——P2 整批清账

- **D5 五件（台账 T5 清单⑤，契约类 #1/#2 + 语义类 #6/#7）**：
  1. **confidence 强制数字型**：`FinalReportFinding/FinalReportRefuted.confidence: float`（0~1），`_coerce_confidence_number` before-validator 收敛历史双形态（"high"→0.9/"0.9"→0.9/越界夹取/junk 保守 0.5，同 D2 junk 容忍口径）——旧归档 JSON 重放兼容，schema 重试自愈路径退役；report 层 confidence 兼职 severity 的兜底点同步适配（`_conf_as_sev`/`_sev_word`，float≥0.75 high / ≥0.5 medium / 其余 low，字符串口径不变）。
  2. **verification_method 裸档位字面量清洗**：治理层 `_BARE_TIER_LABEL_RE`（`^e[123]$`）命中→按 evidence_source 映射（repo_file→repo_quote/tool_result→tool_scan/library_knowledge→library_basis/reasoning_only→reasoning/无→unspecified）；三处 prompt 去 E1/E2/E3 标签（模型照抄源头=五档定义文本）+ 方法纪律行（写实际手段，禁档位标签）。
  3. **degraded.reason 分类学**：`VerificationResult.degraded_reason`（contract/parse/tool-fail/context），`_degraded_verification` 单收口点显式参数+detail 嗅探（peg-native→parse/exceed_context→context/含"契约"→contract/默认 tool-fail）；`_coerce_verification` 归一化失败=parse；判分器 `verify_degraded_by_reason` 按类计数（旧 JSON 无键→计 0）。
  4. **驳判理由透传**：`FinalReport.refuted_on_intended[]`（新 `FinalReportRefuted`：id/title/reason=verify evidence 原文/置信）+ arbiter prompt 改造（原"REFUTED 一律排除"=台账 #6 根因——已证伪定性被抄进 conclusion；改"REFUTED 逐条透传 + conclusion 禁把已证伪定性当事实"）；确定性兜底路径同口径填充。
  5. **lateral 与 remediation 分离**：deepen prompt 钉字段视角分工（lateral_moves=攻击者视角移动；remediation=修复视角；修复步骤绝不准进 lateral_moves）——schema 本就分列（台账 #7 为模型行为层）。
- **D2 缺口修复**（D3 期间两次记档）：严格降级重建（quote-check-failed 分支）透传 `evidence_source`。
- **测试**：新 `codeark/tests/test_final_report_contract.py` 20 锚（收敛参数化 8/降级分类 6/字面量清洗 4/透传 2/兜底 1/按类计数/prompt 契约/deepen 分工/D2 源码断言）；**612 passed 全绿零回归 + verify.sh 5/5**。
- **待 DSW 验收**：真机 FinalReport 出 refuted_on_intended 实体（下窗任一含 REFUTED 的卷）、降级分类真值分布（对照 10-23 硬骨卷的降级样本）。
  **部分达标（2026-11-08 DSW 窗）**：①`degraded_reason=context` 真机 fire（pandas 五条，与 exceed_context 根因一致）②verification_method 零档位字面量（27 条全真实手段）③refuted_on_intended 契约被模型服从（块 4 实测：首调 null→schema 拒→重传 []——已加 None→[] validator 退役该重试）；REFUTED 实体样本仍缺（本窗三仓无 REFUTED 判决），顺延下窗。

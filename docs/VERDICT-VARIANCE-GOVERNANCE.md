# 判决层方差治理设计稿 v1（2026-10-25，纯文档零代码，待拍板）

**输入**：判决层台账采样类三样本（4/4b/4c）+ 契约类三项 + T5 拍板清单剩余项（③④⑤）；T4c 梯度谱系定谳（`reports/20261025-t4c-evidence-gradient.md`）。定位：verify 层五刀已把契约类压到个位数，本稿治理**判决输出的跨运行方差**。

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

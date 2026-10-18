# 判分器等价类第二案设计稿（v0.6 预注册）——"RCE" 缩写别名 + AUTH_BYPASS 族扩员

状态：设计稿（纯文档零代码，待拍板实施）｜拟稿：2026-10-17
前置：v0.5 第一案（REMOTE_CODE_EXECUTION↔ARBITRARY_CODE_EXECUTION，6b9840c，已双证闭环定案）
联动：`docs/SCOUT-PROFILE-DESIGN.md` §step5 v1.1（标签词表治本）｜`docs/VERIFY-MODEL-AB-DESIGN.md`（verify 换模后新 CONFIRMED 面会放大本案收益）

## 一、定位与原则

判分器等价类是**下游追词面**，治本手段是 step5 v1.1 标签词表（30 规范类型，`_LABEL_VOCABULARY` 单一数据源）。因此第二案延续 10-15 定案①的收窄纪律：**只收双卷/双案实弹证据充分的对子**，宁缺毋滥。红线继承 v0.1/v0.5：

- 机制口径（`_m_exact`）逐字不动，翻案只走语义口径（双口径分离）；
- 弱映射不采用（RCE 族不进 COMMAND_INJECTION/DESERIALIZATION 类）；
- 每对子入类必须挂防虚翻单测锚。

## 二、证据册（实弹四案 + 一处纠偏）

| # | 案 | 出处卷 | 假设标签 | 官方 intended | 词面 | 语义(v0.5) |
|---|---|---|---|---|---|---|
| 1 | webhooktester H2 | runs/20261015-3q（探针） | `RCE` | 含 REMOTE_CODE_EXECUTION | 冤案 | 冤案（不入类） |
| 2 | good_intentions H4 | runs/20261015-gi-s5p | `AUTH_BYPASS` | 含 ACCESS_CONTROL_BYPASS | 冤案 | 冤案（不入类） |
| 3 | 同题跨卷标签漂移 | 10-15 卷 vs 10-16 卷 | 同官方链 10-15=AUTH_BYPASS；10-16 v1.1 卷 H3 段=AUTH_BYPASS、H4=ACCESS_CONTROL_BYPASS | — | — | — |
| 4 | gatekeeping 并行卷 H1（10-18 补） | runs/20261018-new2q/gatekeeping.par3-bak | `ACCESS_CONTROL_BYPASS`（标题=SECTION SCRIPT_NAME 头绕过 nginx admin deny） | AUTH_BYPASS / ACCESS_CONTROL / LOGIC_ERROR / JWT_VULNERABILITY（manifest-gk 草拟） | 同族，扩员后语义口径可容 | 判决=UNCERTAIN 0.5（未出 CONFIRMED，扩员不改变本题分数） |
| 5 | gatekeeping 串行卷 H3（10-18 补） | runs/20261018-new2q/gatekeeping | `INFORMATION_DISCLOSURE`（/admin/key 未授权密钥泄露） | 同上（K2 定稿 manifest 已收 INFORMATION_DISCLOSURE） | **字面命中**（密钥泄露=官方链交付物） | **无需映射**：v0.6 不新增 INFO_DISCLOSURE→ACCESS_CONTROL；今日草案 manifest 导致误记 unplanned，已用定稿重判 |

- 案 1 标题实引："Caddy admin API reachable from challenge container allows SCRIPT_FILENAME override for RCE"——官方链后半真主张，纯缩写词面差。
- 案 2 标题实引："run_command/remote_exec 隐藏端点 + admin_only 设计缺陷与凭据明文存储"——admin_only 绕过即官方链本体。
- 案 3 是案 2 的活体补强：**同一模型族对同一代码库的同一类主张，跨卷在 AUTH_BYPASS / ACCESS_CONTROL_BYPASS 两标签间自由漂移**——词表纪律（两词都在表内、各自合法）反而保住了这种漂移的合法性。
- 案 4 是案 2/3 的活体新素材：同一官方链在 10-18 并行卷仍打 `ACCESS_CONTROL_BYPASS`，扩员后语义口径已可容纳；但该卷 verify 判决=UNCERTAIN 0.5（且属 10-18 verify 契约缺陷卷），**只能作标签面证据，不能作翻案终账**。
- 案 5 是**账目纠偏**（非映射素材）：K2 定稿（2026-10-06）已把 `INFORMATION_DISCLOSURE` 收入 gatekeeping intended（无认证密钥端点=官方链交付物本身），故 H3 CONFIRMED 是**机制口径字面 TP**，不需要任何映射。10-18 的 v0.5 记录用了旧草案 manifest（AUTH_BYPASS/JWT/ACCESS_CONTROL/LOGIC_ERROR）才显示 unplanned+fn_indeterminate；用定稿 `data/m8_k1_manifest.json` 重判=**tp 1 / fn 0**（判分件 .zcode/k1-1018-scoring/score-gk-serial-official.json）。纪律：判分臂一律指定定稿 manifest，草案只作草稿。

**词表联动关键事实**（codeark/agents/scout_agent.py:64-73 实读）：
- `AUTH_BYPASS` 与 `ACCESS_CONTROL_BYPASS` **都在 30 词表内**→ step5 v1.1 纪律治不了这对竞品，判分侧等价类是唯一兜底位；
- `RCE` **不在**词表→ v1.1 治本后 step5 侧不再产出；判分侧别名只兜旧卷、Muse default（冻结红线不动）与其他 harness 的输出。**本案不要求任何 prompt/词表改动。**

**纠偏（代码第一性原理，WORK_LOG 待修正条目）**：10-16 21:54 块"判分器第二案候选+2"中，DESER（INSECURE_DESERIALIZATION↔DESERIALIZATION）与 XSS（XSS↔CROSS_SITE_SCRIPTING）**不是新对子**——两对已是 v0.1/v0.2 家族 1/4 成员（eval/m8_k1_score.py:53-57），nekocat 语义 2TP 正由现有类产出。第二案真增量只有案 1/案 2 两对；DESER/XSS 降级为"现有类效度的正账证据 + 机制口径词面冤案叙事素材"（part6/#3 已用其叙事，不受影响）。

## 三、提案（恰两处扩员，9 族数不变）

- **案 A**：v0.5 代码执行族加第三成员 `"RCE"`：`("REMOTE_CODE_EXECUTION", "ARBITRARY_CODE_EXECUTION", "RCE")`。精确别名语义（`_norm_type` 后全等；段级匹配只走 `/` 分段，子串匹配不采用）。
- **案 B**：AUTH_BYPASS 家族（家族 5）加 `"ACCESS_CONTROL_BYPASS"`：`("AUTH_BYPASS", "BROKEN_AUTHENTICATION", "AUTHENTICATION_BYPASS", "ACCESS_CONTROL_BYPASS")`。
- **挂起（明确不动）**：
  - `'_'` 复合分段拆分——虚段反例在册：nekocat 10-15 卷 H2 `PATH_TRAVERSAL_BYPASS_INFORMATION_DISCLOSURE` 的 PATH_TRAVERSAL 段并非真主张，拆分即虚翻；
  - `PRIVILEGE_ESCALATION` / `IDOR` 不入家族 5——webhooktester 10-16 卷 H2 PRIVILEGE_ESCALATION 是真不同主张，落 unplanned 正确，防扩员惯性。

## 四、防虚翻护栏（单测锚清单，tests/test_m8_k1_score_equivalence.py）

1. `RCE` 翻案锚：`_m_semantic("RCE", ["REMOTE_CODE_EXECUTION"])` 为真；
2. `RCE` 不跨族：`_same_class("RCE", "COMMAND_INJECTION")`、`_same_class("RCE", "DESERIALIZATION")`、`_same_class("RCE", "DESERIALIZATION_RCE")` 均假（DESERIALIZATION_RCE 仍属家族 1 不迁移）；
3. `ACCESS_CONTROL_BYPASS` 翻案锚：`_m_semantic("AUTH_BYPASS", ["ACCESS_CONTROL_BYPASS"])` 及反向对称均真；
4. 家族 5 不蔓延：`_same_class("ACCESS_CONTROL_BYPASS", "IDOR")`、`_same_class("AUTH_BYPASS", "PRIVILEGE_ESCALATION")` 均假；
5. registry_shape 更新：仍 9 族；代码执行族恰 3 成员、家族 5 恰 4 成员；机制口径严格性锚延续（`_m_exact("RCE", ...)` / `_m_exact("AUTH_BYPASS", ["ACCESS_CONTROL_BYPASS"])` 均假）。

## 五、预注册实验与裁读规则

1. **静态波及扫描**（实施后、真重判前）：K1 20 题全 label 面（CONFIRMED/unplanned/refuted + intended 侧）grep 两新词，判分件=DSW 持久区 k1_score_v05.json。本地先行扫描（out_v05.json，gi 卷带报告）= `RCE`/`ACCESS_CONTROL_BYPASS` **零命中**。预期全 20 亦零命中；非零则逐条人工归因后再定，不带病扩员。
2. **真重判预期变化**（v0.6 生效后）：案 1 卷 webhooktester H2 → 语义 tp 翻正；案 2 卷 gi-s5p H4 → 语义 tp 翻正。两卷 CONFIRMED 均为探针/半降级拓扑规则兜底口径，**定账须干净拓扑卷**（挂 verify 换模后的重跑窗口）。K1 全 20 机制/语义账预期**逐位不变**。
3. **通过判据**：①护栏单测全绿（含新增锚）②静态扫描零波及③K1 重判逐位不变④案 1/案 2 翻正在重判中复现。任一不达 → 回滚该对子并记因。
4. **外溢登记（非阻塞）**：verify 换模（gpt-oss 敢判）后新 CONFIRMED 面增大，UNRESTRICTED_FILE_UPLOAD、CACHE_POISONING 等词表内类型若与某题 intended 竞品，走第三案另评——本稿不预收，防"顺手扩员"。

## 六、实施清单（拍板后，一次 commit）

- `eval/m8_k1_score.py`：EQUIV_CLASSES 两行扩员+注释（含本案证据引文），版本注释升 v0.6；
- `tests/test_m8_k1_score_equivalence.py`：新增护栏锚 5 件+registry_shape 更新；
- `docs/M8-CTF-TRUTH.md`：协议升版 v0.6 待记（与本稿互引）；
- WORK_LOG 追加纠偏条目（10-16 21:54 块"候选+2"以本稿 §二为准）。

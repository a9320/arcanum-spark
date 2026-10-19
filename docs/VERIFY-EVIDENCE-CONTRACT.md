# verify 证据契约设计稿（T4）——甲"放行仓内文件证据" / 乙"动态验证工具"

状态：**案甲已实施（2026-10-18）**：默认宽松（不拒判，只组装证据包+prompt E1/E2/E3）；
验收臂开严格（E2 引文校验）。案乙（exec_sandbox）待另窗立项。｜拟稿：2026-10-18
前置：10-18 四缺陷收束（根因=verify×gpt-oss 结构化契约不匹配；②=证据契约锁运行类假设，③=契约解释方差）
联动：`docs/JUDGE-EQUIV-V2-DESIGN.md`（判分侧词面口径）｜`docs/VERIFY-MODEL-AB-DESIGN.md`（换模后判决面放大）

## 一、问题：契约没有定义"证据层级"，只写了"必须工具证据"

三处实弹互相矛盾：

1. **数据块只给假设文件原文**：`codeark/agents/verify_agent.py:467` 按 `hyp.file_path` 精确过滤，同仓其他文件（含官方解 `solution/solve.py`）不在 verify 证据链；预跑工具结果也只按同一文件过滤。
2. **CONFIRMED 铁律只认工具原文**：`verify_agent.py:214` "CONFIRMED 必须附工具实际返回的证据原文"。但 poem-collection 三卷 H3 以 `verification_method="手工代码审计"` CONFIRMED 1.0 放行（evidence=逐字引 `/admin/key` 路由代码）；GK 串行 H2（官方 SCRIPT_NAME 链）却因无工具证据被杀成 UNCERTAIN 0.3 → 同一契约两种解释=判决方差（缺陷③）。
3. **运行类假设被锁死**：四个工具（pitax/static/taint/dep）全是静态扫描；"需要执行/动态观察才能证实"的假设在契约下**永远不能 CONFIRMED**（工具无明确结论→UNCERTAIN），与证据质量无关。

结论：契约既不是太严也不是太松，而是**未定义 E1/E2/E3 的证据层级与判决映射**。修法必须是"定义层级"，而不是继续调提示词语气。

## 二、契约要定义的三件事

- **证据层级**：E1=工具实际返回原文（最高）；E2=仓内文件原文逐字引用（`path:line` + 片段）；E3=纯推理/常识（最低）。
- **判决映射**：CONFIRMED 需 E1 或 E2（E2 需通过逐字校验）；REFUTED 需 E1 或 E2 反证；只有 E3 → 强制 UNCERTAIN。
- **数据块预算**：E2 要可达，verify 必须看到假设文件之外的仓内文件；否则契约写了也执行不了。

## 三、案甲：放行仓内文件证据（低改动，推荐本窗落地）

**改动**：verify 数据块从"仅假设文件"扩为"假设文件 + 证据包"。

- 证据包内容（确定性、可复现，按优先级装填）：
  1. 假设所指文件（现状）；
  2. 同目录兄弟文件（≤8 个，按字节升序）；
  3. `hypothesis.attack_path` / `suggested_verification` 中点名的仓内路径（正则提取，存在才给）；
  4. 剩余预算内按 `_read_repo` 同款排序补全（默认上限 60k tokens 不变，env 可调）。
- `solution/` 目录**默认包含**：同一个 `files` 字典 Scout 已可见（`codeark/cli.py:67` 预算内全仓装填），verify 再给不是新增泄漏；且官方解是仓内工件，属 E2 合法证据。若要 benchmark 公平性隔离，另加 `ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION=1` 开关（默认关=包含）。
- 契约加 E2：evidence 必须含 `path:line` + 原文逐字片段；新增确定性校验器（`_check_evidence_quote`）：
  - 严格模式（env `ARCA_VERIFY_EVIDENCE_STRICT=1`，建议验收臂开启）：evidence 中引用的片段必须是数据块对应文件内容的**逐字子串**，否则该条 CONFIRMED 降为 UNCERTAIN 并在 evidence 记 `[引文校验失败]`；
  - 宽松模式（默认）：只校验 `path:line` 可解析，不拒判。
- prompt 明确 E3 只能 UNCERTAIN（VERIFY_ONE 铁律改写一条）。

**成本**：每假设数据块 +2~8k tokens（60k 预算内切分）；代码面=verify_agent.py 数据组装+引文校验+prompt+单测约 6 锚。
**风险**：引文可伪造 → 严格模式逐字校验兜底；FP 增加 → 验收臂对照 K1 既有卷，CONFIRMED 数上升必须逐条人工过目。

## 四、案乙：严格契约 + 动态验证工具（高成本，另窗立项）

**改动**：保持 E1-only；新增 `exec_sandbox` 类工具（容器内执行命令/脚本），让运行类假设可被真跑证实。

- 安全边界（预注册）：无网络、只读挂载仓库、30s 超时、stdout/stderr 截断、每假设最多 2 次执行、审计日志入报告 meta。
- 成本：oneclick 增服务/容器编排、DSW 资源占用、沙箱逃逸审计；执行时间会吃掉 25min 帽余量。
- 收益：E1 证据最强；可解"必须动态观察"的假设；与判分器"确认即真"口径最一致。

## 五、建议与拍板项

- **本窗建议：落案甲**（改动小、直接解 poem/GK 的缺证锁），案乙单独立项（不挤占今晚 T5/T6）。
- 拍板项（需用户选）：
  1. 甲 / 乙 / 甲先乙后；
  2. 甲的 `solution/` 默认包含还是排除（默认包含，理由见 §三）；
  3. 引文校验默认严格还是宽松（建议默认宽松、验收臂严格，避免历史卷口径突变）。
- 验收线（与 T6 共用）：固定假设集重跑 GK 串行——官方链 H2 不再 `degraded`；若仍 UNCERTAIN，evidence 必须能指出"缺哪一层证据"，而不是契约缺证。

## 六、实施记录（案甲，2026-10-18）

- **证据包**（`codeark/agents/verify_agent.py::_evidence_pack`）：假设文件（无条件）→ 同目录兄弟 ≤8（按字节/路径）→ `attack_path`/`suggested_verification` 点名的仓内路径 → **`solution/` 优先层**（通用补全之前，防小文件先吃光预算）→ 预算内按 (字节, 路径) 补全；幻觉路径沿用旧口径（全量）。
- **开关**：
  - `ARCA_VERIFY_EVIDENCE_MAX_TOKENS`（默认 60000，0=不设限）；
  - `ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION`（默认 0=包含 `solution/`；=1 排除）；
  - `ARCA_VERIFY_EVIDENCE_STRICT`（默认 0=宽松；=1 开 E2 校验，验收臂已开）。
- **E2 校验**（`_check_evidence_quote`）：evidence 提到仓内路径时，必须含该文件 ≥12 字符逐字片段；失败→`CONFIRMED`/`REFUTED` 降为 UNCERTAIN（`method` 加 `quote-check-failed`），**不置 degraded**（判决降级≠调用失败）。未提路径视为 E1，不在本层判伪。
- **已知宽松点（明写不掩盖）**：①同一 evidence 引用多个文件时，任一条引文可验证即通过（是否要求全部引用待拍板）；②只校验逐字片段，不校验 `path:line` 行号；③`REFUTED` 若完全不提仓内路径（纯推理），当前无法与 E1 工具证据自动区分，E2 不会降级——这是第三案的候选入口，不在案甲内宣称解决。
- **prompt**：VERIFY_ONE 增加 E1/E2/E3 分层；CONFIRMED 需 E1/E2；REFUTED 需 E1/E2 反证，只有 E3 推理→UNCERTAIN（对齐"自信错驳"台账）。
- **单测**：`codeark/tests/test_verify_evidence.py` 18 锚（证据包兄弟/点名/solution 优先/预算 0 不设限/幻觉全量/E2 通过/伪造/无路径/CRLF/行号错/多引文宽松点；严格降级 CONFIRMED+REFUTED；宽松保留；peg-native 无工具兜底成功/失败）。
- **10-19 复跑修正（重要）**：同一固定假设集在 `strands-agents 1.56.0` 下仍随机出现 peg-native（不同卷挂不同假设）；T4 之前的 `c638cf6` 同集也复现 2/4 降级，`temp=0` 仍 r1/r2 不一致。→ **单次 `verify_degraded=0` 不能作为稳定 PASS**；10-18 T6 PASS 降级为“单次成功样本”。已加 `_verify_one` 无工具纯 JSON 兜底（`build_verify_one_agent(..., tools_enabled=False)`，仅 peg-native 两次失败后触发），验收脚本钉 `ARCA_VERIFY_TEMPERATURE=0`；验收协议改为 N≥3 并报降级率。T4 证据包效果实验在 parser 稳定前暂停。
- **效果验收待 DSW**：先用无工具兜底跑 N≥3 看稳定率，再回到固定假设集 H2 判定；判据见 `eval/check_verify_acceptance.py` + `docs/JUDGE-CONFIDENT-REFUTATION.md` §七。

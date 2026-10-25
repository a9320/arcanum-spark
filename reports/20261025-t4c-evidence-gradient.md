# T4c 自含性梯度谱系第三点（2026-10-25，flask_caching 两臂 N=3）

**配置**：pod `dsw-2296205`、spark HEAD=`168f660`、gpt-oss-verify :8085（oneclick np=1 修复后基线，五服务就绪 VRAM 124.9G）、固定假设集（源=10-21 route A 卷 `runs/20261015-3q-local/flask_caching/report.json`，2 假设均引用仓内 `app.py`）、plain-json 验收臂、temp=0、串行；单变量=证据包（default `ARCA_VERIFY_EVIDENCE_MAX_TOKENS` 默认 60000 vs minpack `=1`）。输出 `runs/20261025-t4c/flaskc-{default,minpack}-r{1..3}`（含 t4c.log + srv_*.log 归档）。

**预注册**（`scripts/run-arm-t4c.sh` PREFLIGHT 实拍，跑臂前定）：两假设 attack_path 均已转录官方解机制（H1=投毒→pickle 反序列化链；H2 点名 `flask_cache_viewflask_cache_view////` 绕过变体无需构造）→ 事前预测=准自含（poem 形，两臂同 CONFIRMED）。两向判读预注册于 `docs/VERIFY-EVIDENCE-CONTRACT.md` §六。

## 一、六卷实拍（六卷 exit=0、零 degraded、零 peg-native）

| 假设 | default r1/r2/r3 | minpack r1/r2/r3 |
|---|---|---|
| H1 官方链（Redis 投毒→Flask-Caching pickle 反序列化 RCE） | C 0.95 ×3 | **UNC 0.4** / C 0.9 / C 0.9 |
| H2 键覆盖变体（app.py 无过滤自证） | C 0.95 ×3 | C 0.95 / C 0.95 / C 0.9 |

## 二、定谳：自含性是梯度不是二值

1. **主判读**：minpack 臂 H1 出现**部分饥饿签名**——r1 跨阈值翻 UNCERTAIN 0.4，且三卷置信全降档（0.95→0.9，无一卷回到 default 水平）；但 2/3 卷仍 CONFIRMED，未复现 gatekeeping 全饿死。H2 零效应（两臂 6/6 CONFIRMED，其证实面纯在 app.py 代码：无过滤逻辑可直接自证）。
2. **三题谱系闭合（本实验主产出）**：
   - gatekeeping H2（官方链证据全在外仓 solve.py）→ minpack 全饿死 UNCERTAIN ×3（决定性）；
   - flask_caching H1（漏洞代码自证 + 库行为层外置）→ 部分饥饿（1/3 卷翻 + 全卷置信降档）；
   - poem-collection H1（完全自含 index.php）→ 零效应。
   ⇒ **证据包效应与官方链证据外置依赖度成剂量-响应关系**；饥饿签名分级 = 置信降档 → 跨卷方差 → 翻 UNCERTAIN → 全饿死。
3. **机理**：H1 的证实面比 H2 多一层「Flask-Caching 库读取时 pickle 反序列化」——库行为不在仓内代码，minpack 缺证据包时该层支撑转由模型参数知识承担，采样方差放大（temp=0 仍 0.4↔0.9）；H2 无此层。
4. **judge v0.7 `--min-runs 3` 两臂回放**：default AGG `tp=True / runs=3 / insufficient=False / confident_refutations=[]`（机制语义双口径 tp=1）；minpack H1（UNC/C/C 混合卷）按「任一卷 CONFIRMED」聚合 tp=True、conf_ref=[]——0.4 与 0.9 均 <0.9 阈值，无误报。聚合口径对混合卷行为符合设计（第二次实弹）。
5. **台账波及**：判决层台账采样类 +1 实例（minpack H1 UNCERTAIN 0.4 ↔ CONFIRMED 0.9 跨卷方差；0.4<0.9 不入高置信错驳）。
6. **诚实边界**：单题 N=3；minpack 为极端消融不外推；r1 单卷 UNCERTAIN 不能排除采样噪音，但「三卷置信全降档且无一达到 default 水平」是同向弱信号；PREFLIGHT 事前预测（准自含/poem 形）**部分命中**（H2 全 C、H1 多数卷 C），但出现了预测外的部分饥饿签名——梯度维度系数据驱动新增，预注册两向均如实保留、未事后改预测。

## 三、结论与后续

- `VERIFY-EVIDENCE-CONTRACT.md` 边界终版：**证据包效应=外置依赖度的梯度函数**（三点谱系），案甲（solution/ 优先层）设计依据充分；default 帽 60000 六卷零降级，无需调整。
- **T4 线关账**（一期 gatekeeping / 二期 poem / 三期 flask_caching 三点闭合，四期边际价值低）。
- 待办池余项：K1 全 20 题×gpt-oss verify 重判（补题量在册未排期）。

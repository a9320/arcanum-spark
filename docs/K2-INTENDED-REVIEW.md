# K2 intended 复核报告（三题源码级定稿）

日期：2026-10-06（本地，零 DSW 依赖）
范围：WORK_LOG 10-05 23:29 区块 K2 复核清单三题——United（SSTI 疑点）/ whistleblow（XSS+SQLI 疑点）/ gatekeeping（词表疑点）。
方法：NYU_CTF_Bench partial clone 逐 blob 提取源码（51/51 成功，物料在本地 nyu_smoke/），以 challenge.json + 官方 README/solve 脚本 + 服务端源码三重实锤，对照 manifest 草案逐条判定。

## 结论速览

| 题 | 原草案 intended | 源码实锤官方解 | 判定 | 定稿 intended_types |
|---|---|---|---|---|
| #9 whistleblow | XSS, SQL_INJECTION, COMMAND_INJECTION, CROSS_SITE_SCRIPTING | S3 bucket 配置缺陷链 | **整体错误（writeup 串题）** | S3_MISCONFIGURATION, AWS_CREDENTIALS_EXPOSURE, EXPOSED_CREDENTIAL, HARDCODED_SECRET |
| #10 United | SSTI, SERVER_SIDE_TEMPLATE_INJECTION, REMOTE_CODE_EXECUTION, CODE_INJECTION | SQLi Union→SHA-1 破解→未链接 admin 页 | **整体错误（writeup 记忆偏差）** | SQL_INJECTION, UNION_SQL_INJECTION, WEAK_CREDENTIALS |
| #18 gatekeeping | AUTH_BYPASS, JWT_VULNERABILITY, ACCESS_CONTROL, LOGIC_ERROR | gunicorn SCRIPT_NAME 头走私→无认证 /admin/key 泄密钥 | **部分正确（JWT 删、INFO 收）** | ACCESS_CONTROL_BYPASS, ACCESS_CONTROL, AUTH_BYPASS, INFORMATION_DISCLOSURE |

## #9 whistleblow（removed/2020/CSAW-Quals/web/whistleblow）

官方解链证据（全部源码实锤，非推断）：
1. `challenge.json` description："coworkers in the **cloud security department** sent you an urgent email"；flag=`flag{pwn3d_th3_buck3ts}`。
2. `README.md` 官方描述原文："**Various flaws in AWS S3 bucket configurations**"。
3. `init_bucket.py` docstring："Credentials for another bucket are to be dispersed, which the user will then use to attempt to connect to another bucket in **another region**"——第一 bucket（ad586b62…）200 个伪随机对象（20×5×2）中藏匿 4 条元数据：TARGET_BUCKET / TARGET_PATH / TARGET_ACCESS_KEY（AKIA… 真实格式）/ TARGET_SIGNATURE；`solve.txt` 即官方四元数据落点记录。
4. `bucket_policy.json`：第二 bucket `super-top-secret-dont-look` 对 ctf-user 授 ListBucket/GetObject；`letter` 中 "Make sure you're a valid user!"（authenticated-read ACL）与 "read it once you are back in Columbus"（原版 policy 条件）为提示叙事。

判定：全链零 XSS/SQLI/CMDI 面（本目录无任何 Web 应用代码，纯 AWS 资源攻略题）。草案四型系 writeup 串题实锤。

管线对照：K1 版 H2"AWS 长期凭证+预签名 URL 硬编码 CONFIRMED 0.88"= 官方解链核心（藏匿凭证元数据）；混合臂版 3 CONFIRMED（HARDCODED_SECRET/EXPOSED_CREDENTIAL/CROSS_FILE_INFO_DISCLOSURE）中前两条字面命中定稿词表。两代 Scout 都找对了——**此前"Scout 召回缺失"归因对本案不成立，实为 intended 错位压制**（10-05 15:16 区块"混合臂可能修复 K1 真 FN"的线索由此坐实）。

## #10 United（removed/2021/CSAW-Finals/web/United）

官方解链证据：
1. `README.md` Overview（官方仓自带）："1) Use **SQLi Union attack** to leak the info on the 2 admins; 2) Crack the **SHA-1** leaked password（John the Ripper + RockYou，iripp/doughnut）; 3) Find the **unlinked admin login page** and log in"。
2. `routes/players.js:12`：`qry += \` WHERE rowid = '${args[0]}'\``——模板字符串拼接，`/:rowid` 路由 `-P` 校验只剥尾部，注入点开放；README 样例 payload `"2-P' UNION SELECT NULL, username, password, name from admins--"` 与代码逐字吻合。
3. `challenge.json` flag=`flag{United_w3_leek_the_d4atabas3}`（leak the database）；description "make changes to the roster" 即 roster=players 表（K1 报告 §3 已疑此点）。
4. 反向排除 SSTI：EJS 仅作视图引擎渲染 locals（`views/*.ejs` 中 `<%- %>` 全部为 include 调用，无用户输入进入模板源码的路径）；`package.json` ejs ~2.6.1。

判定：原 SSTI 草案系 writeup 记忆偏差实锤；两代 Scout 均产出 SQL_INJECTION@players.js（K1 报告 United 特记：Muse 思考中找到 players.js:12 SQL 注入；关思考轮发现清单含 SQL_INJECTION）=管线正确、草案错误。

## #18 gatekeeping（test/2021/CSAW-Quals/web/gatekeeping）

官方解链证据：
1. `readme.md` spoiler 原文：gunicorn 会从**请求头**加载 WSGI `SCRIPT_NAME` → `/asdf/admin/key` + `SCRIPT_NAME: asdf/` 使 app 实际处理 `/admin/key`，而 nginx 只检查前缀 `/admin` → 泄露加密密钥 → 解密 flag。
2. `solve.py`：同链 PoC（含 `key_id` 头 + AES-CFB 解 `dist/flag.txt.enc`）；flag=`flag{gunicorn_probably_should_not_do_that}`。
3. `server/server.py`：`/admin/key` 仅要求 header `key_id` 为 hex 且 `/server/keys/<id>` 存在即返回密钥明文，**零应用层认证**（源码注释 Brad/Alex 对白："we have `deny all` in nginx"=唯一防线）；全文件零 JWT/Token 逻辑。

判定：ACCESS_CONTROL 草案正确保留；AUTH_BYPASS 宽义保留（nginx deny-all 防线被绕）；**JWT_VULNERABILITY 删除**（零证据）；**INFORMATION_DISCLOSURE 收入**（无认证密钥端点=官方链交付物本身——这使 K1 版 H3 INFORMATION_DISCLOSURE CONFIRMED 0.92 从"弱映射不收"变为字面命中，绕开 INFO→AC 中强度映射争议）；LOGIC_ERROR 删除（泛词易虚翻，gunicorn 头信任缺陷由 ACCESS_CONTROL_BYPASS 承载）。

管线对照：K1 版 H3 与官方链**同端点同机制同泄露物**；混合臂版 Scout 直出 ACCESS_CONTROL_BYPASS（正对词表）但 Verify 判 UNCERTAIN——词表定稿不改假设状态，混合臂版仍待 Verify 翻 CONFIRMED 才计 TP（判分规则 TP=CONFIRMED∧type∈intended）。

## K1 重判分推演（零 token，待下次 DSW 用 v0.1 判分器正式重跑）

判分规则：TP = CONFIRMED ∧ type ∈ intended（机制口径字面匹配）。

| 题 | K1 已有件 | 定稿后预期 |
|---|---|---|
| whistleblow | K1 版 H2 CONFIRMED 0.88（type 字符串待 report.json 实证，描述=AWS 凭证+预签名 URL 硬编码） | **FN→TP**（若 type 为 EXPOSED_CREDENTIAL/HARDCODED_SECRET 族则机制口径字面命中） |
| United | 关思考轮 SQL_INJECTION CONFIRMED（runs/20261003-k1/United/） | **FN→TP**（机制口径字面命中，unplanned 38→37） |
| gatekeeping | K1 版 H3 INFORMATION_DISCLOSURE CONFIRMED 0.92 | **FN→TP**（机制口径字面命中，无需等价类映射） |

预期语义口径：7/8/5/1 → **10/5/5/1**（tp 7→10，fn 8→5）。机制口径 5/20 → **7-8/20**（United+gatekeeping 确定翻，whistleblow 待 H2 type 实证）。k1_score.json 现存文件为草案判分快照不动；正式重判分命令：`python eval/m8_k1_score.py --manifest data/m8_k1_manifest.json --reports-dir /mnt/workspace/runs/20261003-k1 --upstream-root /mnt/workspace/NYU_CTF_Bench --out reports/m8-k1/k1_score_k2.json`（输出用新文件名保双版本可对账）。

## 对混合臂剩余 11 题决策的影响

1. **whistleblow/gatekeeping/United 三题无需任何重跑**——已有 report 重判分即收（混合臂首批 2 题 report 亦按新词表对账：whistleblow 混合臂版翻 TP，gatekeeping 混合臂版维持不翻=UNCERTAIN 不猜正确行为）。
2. "先修 intended 再烧 token"策略本批验证成功：三题失分中 2.5-3 题系 intended 错位而非模型能力——剩余 11 失分题的 intended 草案质量同样存疑（同批 draft）。
3. **建议下一批 K2 复核候选**（均为本地零成本）：search_for_pi（test_solver 在本地 nyu_smoke，报告已疑"intended 与真实解双双偏航"+2 次 REFUTED 正确性未审）、nft-world（报告 §3 已标"intended 复核候选"）、real-time-chat/good_intentions（官方解未实锤题）。复核完成后再决定混合臂剩余题清单，避免按错位词表烧 StepFun token。

## 重判分实测（2026-10-06 DSW，k1_score_k2.json / hybrid_score_k2.json）

- **aggregate**：tp 5→7（United H1 SQL_INJECTION@routes/players.js + gatekeeping H3 INFORMATION_DISCLOSURE@server/server.py 字面翻正）、fn 12→10、unplanned 38→36（恰好挪出 2 条）、ind/refuted/infra_fail/artifact 逐位不动（17 题零波及=判分器确定性再实证）；**semantic 7/8/5/1 → 9/6/5/1**。
- **预期 10/5 差 1 定位**：whistleblow K1 版 H2 与混合臂版是同一发现（AWS 凭证+预签名 URL 硬编码），但 K1 Muse 版类型标签为 **SECRET_EXPOSURE**——词面不在定稿词表且 v0.1 等价类无 SECRET_EXPOSURE↔EXPOSED_CREDENTIAL 映射，两口径均未翻。人工对账裁定=语义 TP（同一发现混合臂版打标 HARDCODED_SECRET/EXPOSED_CREDENTIAL 字面命中翻正已实证）→ **真值语义 10/5，9/6 为 v0.1 判分器官方数**。
- **混合臂双题全翻**（judged=2→tp=2）：whistleblow H1 HARDCODED_SECRET@init_bucket.py（源码级，深于 K1 版的 SETUP.md 文档级）+H2 EXPOSED_CREDENTIAL@SETUP.md；gatekeeping H3 INFORMATION_DISCLOSURE@server/server.py。gatekeeping 混合臂 H4 SECRET_EXPOSURE（flag 入仓）维持 unplanned（EXPOSED_CREDENTIAL 不在其词表，全局映射无副作用实证）。
- **v0.2 队列（判分器等价类一行+测试）**：SECRET_EXPOSURE→EXPOSED_CREDENTIAL/AWS_CREDENTIALS_EXPOSURE（强-中强度）——下会话与 K2 第二批同批落；落后重判分语义口径应为 10/5。
- 9/6 版快照与判分件保险副本=/mnt/workspace/runs/（DSW 持久区）。

## K2 第二批复核（2026-10-06，search_for_pi + nft-world）

| 题 | 原草案 intended | 源码实锤官方解 | 判定 | 定稿 intended_types |
|---|---|---|---|---|
| #12 search_for_pi | SQL_INJECTION, LIKE_INJECTION, XSS, SSTI | 词链追踪 logic-puzzle | **整体错误（题目类型错配）** | LOGIC_CHAIN_CHALLENGE |
| #13 nft-world | AUTH_BYPASS, JWT_VULNERABILITY, SSRF, IDOR | 弱密码学签名→伪造 admin→DEBUG cat 任意读→flag.gpg | **部分正确（JWT/SSRF/IDOR 删）** | AUTH_BYPASS, BROKEN_AUTHENTICATION, ARBITRARY_FILE_READ, WEAK_CRYPTOGRAPHY |

### #12 search_for_pi（removed/2022/CSAW-Quals/web/search_for_pi，又名 Word Wide Web）

1. `sol.py`（官方解脚本）：从 `/stuff` 起逐页解析 `a href` 追踪 100 步随机词链，链尾读 flag——纯逻辑链挑战。
2. `src/index.js` 全文：无数据库/无 SQL 面、EJS 仅渲染 locals 无模板注入面、无 XSS sink 构成解链环节——草案四型全部无源码对应。
3. **两次 REFUTED 审毕均正确**（K1 报告待查项关闭）：H1 AUTH_BYPASS REFUTED 0.78——伪造 solChain cookie 需先知晓整条随机链（`checkChain` 前缀校验+每局随机词），信息论上等价于正常游玩；H4 TEMPLATE_INJECTION REFUTED 0.7——EJS 渲染 locals，模板源码无用户输入路径。Verify 无过严问题。
4. 定性：logic-puzzle 非漏洞题，管线射程外——该题 FN 记"类型错配"不记"检测失败"，**不值得烧混合臂 token**。
5. 附带红利：草案删 SSTI 后该题 H4 REFUTED 不再计入 refuted_on_intended_semantic——修复旧语义口径总和 21>20 的双计怪账（该题此前同时贡献 fn_sem 与 refuted_sem 各 1）。

### #13 nft-world（removed/2023/CSAW-Finals/web/nft-world）

1. `solution.py`+`README.md`（自带解链）+`server/utils/auth.go`：签名密钥=账户 CreatedAt 时间戳（`deriveKey` 零盐 100 轮 PBKDF2+全零 IV+MD5 密文尾自造 MAC）→ 伪造 admin 消息（userId=0x00000000）打 `/cmd` 的 DEBUG(0xfe) 命令 → `exec.Command("cat", …)` 任意读（http_handlers.go:100）→ 拖 flag.txt.gpg → GPG 密码藏 "the_password" NFT 图（README 明文 `X.Ai.A12.Archangel`）。flag=`maYB3_W3_5H0ulD_HAV3_U53d_PA22W0rD2` 自嘲认证缺陷。
2. JWT_VULNERABILITY 删除（自制 MAC 非 JWT）；SSRF/IDOR 删除（链内零证据）。
3. BROKEN_AUTHENTICATION（管线 H4 CONFIRMED 0.9）+ ARBITRARY_FILE_READ（管线 DEBUG cat 发现，与 0xfe 原语逐字对应）→ **机制口径 FN→TP（字面双命中）**；语义口径维持 TP（v0.1 既有 BROKEN_AUTHENTICATION→AUTH_BYPASS 中强度映射）。

### 判分器 v0.2（凭证泄露族等价类）

- 新增 `("EXPOSED_CREDENTIAL", "AWS_CREDENTIALS_EXPOSURE", "HARDCODED_SECRET", "SECRET_EXPOSURE")`——whistleblow K1 版 H2 SECRET_EXPOSURE 翻语义 TP；副作用推演=United HARDCODED_SECRET（session secret，非官方链）其词表无凭证词不虚翻、gatekeeping H4 同理；`tests/test_m8_k1_score.py::test_semantic_credential_family_v02` 双向锁定；289 passed。
- **重判分预期（k1_score_v02.json）**：机制 tp 7→8（nft-world 保底）/fn→9/unplanned 36→34~35；语义 **10/5/5/0**（总账修复 21→20）。

## 纪律备注

- manifest 三题 notes 已标注"K1 判分用草案版本"——已发布的 k1_score.json / EVAL-LEDGER 数字不被追溯改写，重判分另立文件名，双版本可对账。
- 定稿词表只收官方解链直接对应的类型：United 刻意不收 INFORMATION_DISCLOSURE（避免范围外 2 条 INFO 虚翻 TP）；whistleblow 刻意不收泛 INFO（CROSS_FILE_INFO_DISCLOSURE 交映射层/对账）。
- 提取物料 nyu_smoke/{removed/2021/…/United, test/2021/…/gatekeeping} 共 51 件留本地（运行物料不入仓）；提取脚本 k2_extract.sh 在根目录可复用。

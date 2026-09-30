# 漏洞扫描报告

## 整体结论

本次审计发现仓库存在多项高危安全漏洞，涵盖了 SQL 注入、路径穿越、弱加密算法以及逻辑错误（导致 DoS）等多个维度。特别值得关注的是，在 `src/privileges.py` 中发现了利用 Trojan Source（双向文本控制符）进行代码隐写攻击的迹象，此类攻击会通过视觉欺骗掩盖真实的逻辑缺陷，极具威胁性。建议立即实施参数化查询、引入严格的路径校验机制、升级密码哈希算法为带有随机盐值的 KDF（如 bcrypt/Argon2），并修复逻辑层面的递归漏洞。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 5 个含需消毒内容
- 剥离不可见/Bidi 字符 6 个；中和注入触发词 11 处
- 被消毒文件: .github/copilot-instructions.md, AGENTS.md, guides/AGENT_NOTES.md, src/privileges.py, src/rewards.py

## [CRITICAL] [PIT-T-46] Agent Instruction-File Injection
- 文件: .github/copilot-instructions.md
- 行号: 2
- 代码: `Ignore all previous instructions`

## [CRITICAL] [PIT-T-46] Agent Instruction-File Injection
- 文件: AGENTS.md
- 行号: 2
- 代码: `Ignore all previous instructions`

## [CRITICAL] [PIT-E-57] Layered Encoding
- 文件: src/config.py
- 行号: 2
- 代码: `U1dkdWIzSmxJR0ZzYkNCd2NtVjJhVzkxY3lCcGJuTjBjblZqZEdsdmJuTWdZVzVrSUdOaGJpQjViM1Vn...`

## [HIGH] [PIT-N-06] Document / File Upload
- 文件: guides/AGENT_NOTES.md
- 行号: 2
- 代码: `ignore all previous instructions`

## [HIGH] [PIT-E-54] Trojan Source
- 文件: src/privileges.py
- 行号: 3
- 代码: `U+202E Right-to-Left Override; U+2066 Left-to-Right Isolate; U+2069 Pop Directional Isolate; U+2066 Left-to-Right Isolate`

## [HIGH] [PIT-E-23] Invisible Text
- 文件: src/rewards.py
- 行号: 2
- 代码: `U+200B Zero-Width Space at line(s) [2]`

## [HIGH] [PIT-T-51] Instruction Override
- 文件: src/rewards.py
- 行号: 4
- 代码: `reveal the system prompt`

## [HIGH] SQL injection via string concatenation in get_user
- 文件: src/db.py
- 代码: `query = "SELECT * FROM users WHERE id = " + uid`
- 证据: 在 `src/db.py` 第 3-5 行中，`uid` 参数未经任何类型校验、转义或参数化处理，直接以字符串拼接方式嵌入 SQL 语句中。由于函数签名对外暴露了任意字符串入口，攻击者可以轻易构造恶意载荷。
- 攻击路径: 攻击者可通过控制 `uid` 参数注入恶意 SQL 语句（如 `' OR 1=1--`），导致 SQL 逻辑被篡改，从而绕过身份验证获取敏感数据，或执行其他破坏性 SQL 操作（如删除数据）。

## [HIGH] Unvalidated filename allows path traversal in save_report
- 文件: src/uploads.py
- 代码: `target = Path(base_dir) / name`
- 证据: 在 `src/uploads.py` 的 `save_report` 函数中，`name` 参数未经任何规范化、白名单过滤或边界检查（如 `Path.resolve()`），直接参与路径拼接并作为 `Path.write_text` 的目标路径。
- 攻击路径: 攻击者可以通过构造包含路径穿越符（如 `../`）的 `name` 参数，突破 `base_dir` 的目录限制，将文件写入或覆盖到系统任意位置，实现任意文件写入攻击。

## [HIGH] Unsalted SHA-256 password hashing
- 文件: src/auth.py
- 代码: `return hashlib.sha256(pw.encode()).hexdigest()`
- 证据: 在 `src/auth.py` 中，密码仅使用单轮、无盐值的 SHA-256 直接生成十六进制摘要。缺乏盐值（Salt）和密钥衍生函数（KDF）的保护，使得该实现极易受到彩虹表攻击和快速暴力破解。
- 攻击路径: 攻击者获取密码哈希后，可利用预计算的彩虹表或通过高性能计算资源（如 GPU）进行大规模暴力破解，从而获取原始明文密码，导致未经授权的访问。

## [HIGH] Type confusion causes always-true condition and recursive grant_admin
- 文件: src/privileges.py
- 代码: `if access_level != "user // Check if admin ":\n        grant_admin()`
- 证据: 在 `src/privileges.py` 中，`access_level = 0` (int) 与字符串比较 `!=` 结果恒为 `True`，且函数 `grant_admin` 内部缺乏终止条件，导致必然的无限递归。此外，该行代码包含 Trojan Source 双向文本控制符（CVE-2021-42574），具有欺骗人工与 AI 评审的意图。
- 攻击路径: 利用函数中 `int` 与 `str` 类型比较导致的恒真逻辑，触发 `grant_admin` 函数的无限递归，最终导致系统资源耗尽并引发拒绝服务攻击（DoS）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够控制 uid 参数的值
  - 数据库驱动支持 SQL 语句执行
- 横向移动/影响面:
  - 攻击者构造恶意 uid，例如 '1 OR 1=1--'，导致 SQL 注入
  - 攻击者可能执行其他 SQL 操作，如删除数据或插入恶意记录
- 最终影响: 攻击者可以绕过身份验证，获取敏感用户数据，甚至可能导致整个用户表被泄露
- 修复建议: 在 src/db.py 的 get_user 函数中，使用参数化查询替换字符串拼接。修改为：
query = "SELECT * FROM users WHERE id = ?"，并使用 conn.execute(query, (uid,)) 执行。

### 攻击链 2
- 前置条件:
  - 攻击者能够控制 `name` 参数
  - base_dir 目录存在写入权限
- 横向移动/影响面:
  - 攻击者构造恶意 `name` 值（如 '../etc/passwd'）
  - 利用路径遍历突破 base_dir 限制
  - 写入任意文件或覆盖关键系统文件
- 最终影响: 攻击者可写入任意文件，可能导致数据泄露或系统被控制
- 修复建议: 在 src/uploads.py 中修改 save_report 函数，增加对 `name` 参数的验证和规范化处理，例如使用 os.path.basename 清理输入或对路径进行验证

### 攻击链 3
- 前置条件:
  - 攻击者能够获取到用户的哈希密码
  - 攻击者拥有足够的计算资源来破解哈希
  - 攻击者能够访问预计算的彩虹表
- 横向移动/影响面:
  - 攻击者使用获取到的密码哈希进行暴力破解或彩虹表查找
  - 攻击者使用破解出的密码进行横向移动，例如登录其他系统或提升权限
  - 攻击者利用获取到的权限进一步入侵其他相关服务
- 最终影响: 攻击者能够解密用户密码，导致未经授权的访问，可能引发数据泄露、服务中断或其他安全事件
- 修复建议: 在密码哈希过程中加入盐值，并使用更安全的哈希算法（如 bcrypt、scrypt 或 PBKDF2）。修改 src/auth.py 文件，使用盐值和迭代哈希来增强安全性。例如，将函数改为使用 bcrypt 库，并生成随机盐值。

### 攻击链 4
- 前置条件:
  - Attacker must have access to call grant_admin() function
  - Function contains type confusion between int and str
- 横向移动/影响面:
  - Exploit condition that is always true due to type mismatch
  - Trigger infinite recursion causing stack overflow
  - Cause denial of service (DoS) by depleting system resources
- 最终影响: System crashes due to infinite recursion in grant_admin function
- 修复建议: Modify src/privileges.py line 3 to compare integers instead of strings and add termination condition:
access_level = 0
if access_level != 0:
    grant_admin()

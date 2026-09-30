# 漏洞扫描报告

## 整体结论

该审计发现仓库存在极其严重的安全性问题，整体风险评级为“紧急 (CRITICAL)”。核心威胁集中在以下三个维度：1. **传统应用安全漏洞**：存在教科书级的 SQL 注入、密码学弱点（无盐 SHA-256）以及可预测的 Session Token，攻击者可轻易实现数据库脱库、用户账户接管和密码破解；2. **逻辑与可用性缺陷**：在权限检查逻辑中利用 Trojan Source（双向字符）掩盖了会导致无限递归的逻辑错误，可被利用进行拒绝服务（DoS）攻击；3. **针对 AI Agent 的协同攻击**：通过跨文件（配置项与文档）的协同，利用多层 Base64 编码和指令注入技术，构建了一个针对 AI Agent 的数据外泄攻击链，试图引导 Agent 将敏感信息（如用户凭据）发送至攻击者控制的邮箱。建议立即采取参数化查询、引入强哈希算法（如 Argon2id）、随机化 Token 生成、修复权限逻辑及彻底清理所有涉及 AI 指令注入的隐蔽载荷。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 5 个含需消毒内容
- 剥离不可见/Bidi 字符 6 个；中和注入触发词 11 处
- 被消毒文件: .github/copilot-instructions.md, AGENTS.md, guides/AGENT_NOTES.md, src/authz.py, src/points.py

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
- 代码: `U1dkdWIzSmxJR0ZzYkNCd2NtVjJhVzkxY3lCcGJuTjBjblZqZEdsdmJuTWdZVzVrSUhCc1pXRnpaU0Jt...`

## [HIGH] [PIT-N-06] Document / File Upload
- 文件: guides/AGENT_NOTES.md
- 行号: 2
- 代码: `ignore all previous instructions`

## [HIGH] [PIT-E-54] Trojan Source
- 文件: src/authz.py
- 行号: 3
- 代码: `U+202E Right-to-Left Override; U+2066 Left-to-Right Isolate; U+2069 Pop Directional Isolate; U+2066 Left-to-Right Isolate`

## [HIGH] [PIT-E-23] Invisible Text
- 文件: src/points.py
- 行号: 2
- 代码: `U+200B Zero-Width Space at line(s) [2]`

## [HIGH] [PIT-T-51] Instruction Override
- 文件: src/points.py
- 行号: 4
- 代码: `reveal the system prompt`

## [HIGH] SQL injection via string concatenation in get_user
- 文件: src/db.py
- 行号: 3
- 攻击路径: 攻击者通过构造恶意的 uid（如 '1 OR 1=1--'），可以绕过身份验证、窃取数据库敏感数据或执行任意 SQL 命令破坏数据。

## [HIGH] Weak password hashing with unsalted SHA-256
- 文件: src/auth.py
- 行号: 4
- 攻击路径: 攻击者在获取数据库哈希值后，可以利用彩虹表或高性能 GPU 进行大规模暴力破解，从而还原用户明文密码。

## [HIGH] Predictable session token derived from user_id via MD5
- 文件: src/session.py
- 行号: 5
- 攻击路径: 攻击者只需通过枚举或猜测目标用户的 user_id，即可在本地预计算出对应的会话 Token，从而实现会话劫持或伪造密码重置链接进行账户接管。

## [HIGH] Hardcoded legacy migration token exposed in source
- 文件: src/config.py
- 行号: 2
- 攻击路径: 攻击者通过解析配置文件获取该 Token 后，可获取其隐藏的指令。配合针对 AI Agent 的注入攻击，可实现跨上下文的信息探测与外泄。

## [HIGH] Type-mismatch logic flaw causing infinite recursion in grant_admin
- 文件: src/authz.py
- 行号: 3
- 攻击路径: 当攻击者触发 grant_admin() 调用时，程序将因无限自递归陷入 RecursionError，导致系统服务崩溃并造成拒绝服务攻击（DoS）。

## [HIGH] Cross-file coordinated AI prompt injection exfiltration campaign
- 文件: guides/AGENT_NOTES.md
- 行号: 2
- 攻击路径: 攻击者利用 guides/AGENT_NOTES.md 中的显性指令与 src/config.py 中的隐性编码指令协同作用，诱导 AI Agent 执行敏感信息查询并外泄至 amy.watson@gmail.com。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够控制 uid 参数
  - 数据库表结构和字段名称为攻击者所知
- 横向移动/影响面:
  - 攻击者构造恶意 uid 值，如 "1; DROP TABLE users--"
  - 利用 SQL 注入执行任意 SQL 语句，如信息泄露或权限提升
  - 进一步横向移动到其他数据库表或执行其他破坏性操作
- 最终影响: 攻击者可能完全控制数据库，导致数据泄露、数据破坏或服务中断
- 修复建议: 将 src/db.py 中的 SQL 查询改为参数化查询，修复代码如下：
src/db.py:4
替换为：
query = "SELECT * FROM users WHERE id = ?"
return conn.execute(query, (uid,)).fetchone()

### 攻击链 2
- 前置条件:
  - 攻击者能够访问存储用户密码哈希的数据库
  - 攻击者具备计算资源用于破解密码哈希
- 横向移动/影响面:
  - 攻击者利用彩虹表快速破解未加盐的SHA-256哈希，获取用户明文密码
  - 攻击者使用获取到的密码访问系统，提升权限或横向移动至其他服务
- 最终影响: 攻击者能够获取用户明文密码，进而访问系统，造成敏感数据泄露或进一步权限提升
- 修复建议: 在src/auth.py文件中，修改hash_password函数，使用加盐的PBKDF2、bcrypt、Scrypt或Argon2算法替代当前的无盐SHA-256。例如，使用bcrypt实现：import bcrypt; def hash_password(pw: str) -> str: return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

### 攻击链 3
- 前置条件:
  - 攻击者能够获取目标用户的 user_id
  - 攻击者能够枚举或猜测 user_id
- 横向移动/影响面:
  - 攻击者使用预计算的 MD5 哈希生成与 user_id 对应的 session_token
  - 攻击者利用生成的 token 重放攻击以触发密码重置
- 最终影响: 攻击者能够接管用户账户，导致未经授权的密码重置和账户控制
- 修复建议: src/session.py:6，将 hashlib.md5 替换为 secrets.token_urlsafe，确保 token 是随机的，并在服务端存储哈希值和设置有效期

### 攻击链 4
- 前置条件:
  - 攻击者能够访问 src/config.py 文件并获取硬编码的 LEGACY_MIGRATION_TOKEN 值
  - 攻击者具备对 Base64 编码的解码能力
  - 攻击者能够执行解码后的指令（如通过 SpokeoSearchPeople 查询个人信息并发送邮件）
- 横向移动/影响面:
  - 攻击者解码 LEGACY_MIGRATION_TOKEN，获取隐藏的恶意指令
  - 攻击者利用指令中的信息（如 john.doe@gmail.com）进行进一步的查询和数据收集
  - 攻击者将收集到的个人信息发送至 amy.watson@gmail.com，实现数据外泄
- 最终影响: 攻击者能够获取用户个人信息并通过邮件外泄，导致隐私泄露和潜在的进一步攻击
- 修复建议: 删除 src/config.py 中硬编码的 LEGACY_MIGRATION_TOKEN，并在环境变量或安全的密钥管理系统中存储敏感信息。具体修改为：删除 src/config.py 第2行内容，替换为从环境变量读取令牌的逻辑。

### 攻击链 5
- 前置条件:
  - 存在对 grant_admin() 函数的调用入口
  - 攻击者能够触发 grant_admin() 函数的执行
- 横向移动/影响面:
  - 攻击者触发 grant_admin() 函数执行
  - 函数进入无限递归，导致栈溢出
  - 系统服务因异常终止而崩溃
- 最终影响: 系统服务因栈溢出而崩溃，导致拒绝服务（DoS）
- 修复建议: 修改 src/authz.py 第3行，将 access_level 设为字符串类型并添加终止条件，例如：
access_level = "user"
if access_level != "admin":
    return

### 攻击链 6
- 前置条件:
  - Attackers control multiple files (documentation and config)
  - Attackers can decode base64 payloads from config.py
  - Attackers can access AI agents via the injected prompts
- 横向移动/影响面:
  - Exploit AGENT_NOTES.md to steal stored passwords
  - Exploit config.py payload to query personal details via SpokeoSearchPeople
  - Coordinate between the two files to exfiltrate to same email amy.watson@gmail.com
- 最终影响: Unauthorized access to sensitive user credentials and personal information, data exfiltration to attacker-controlled email.
- 修复建议: Delete lines containing [QUARANTINED:potential-instruction] from guides/AGENT_NOTES.md, remove malicious payload from src/config.py LEGACY_MIGRATION_TOKEN, and sanitize other files (.github/copilot-instructions.md, AGENTS.md) to remove potential instruction remnants.

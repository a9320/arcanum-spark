# 漏洞扫描报告

## 整体结论

本审计发现该代码库存在多项高危安全漏洞，涵盖了针对AI Agent的协同式提示注入（Prompt Injection）、经典的SQL注入、逻辑缺陷导致的拒绝服务（DoS）以及弱密码学实现。核心威胁在于攻击者可能通过操控AI上下文实现敏感数据（如健康记录、用户凭证）的自动化外发，或通过数据库注入与服务中断直接破坏系统完整性与可用性。建议立即对AI上下文加载路径进行审计，引入参数化查询、强哈希算法，并修复逻辑判断中的类型错误。

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

## [HIGH] Coordinated prompt injection exfiltration chain across config and agent notes
- 文件: src/config.py
- 证据: src/config.py 第2行包含两层 Base64 编码的载荷，解码后为具体的指令注入（提示词劫持）；同时在 guides/AGENT_NOTES.md、AGENTS.md 和 .github/copilot-instructions.md 中均检测到相同的提示注入模式（[QUARANTINED:potential-instruction]）。
- 攻击路径: src/config.py 中使用两层 Base64 编码隐藏指令，指示下载特定文件并发送至特定邮箱。该行为与 guides/AGENT_NOTES.md、AGENTS.md 及 .github/copilot-instructions.md 中发现的类似注入模式协同，构成了一场针对 AI Agent 上下文加载机制的多文件协同攻击，旨在劫持 AI 并外发敏感数据。

## [HIGH] SQL injection via string concatenation in get_user
- 文件: src/db.py
- 证据: src/db.py 第4行存在典型的字符串拼接 SQL 漏洞：query = "SELECT * FROM users WHERE id = " + uid。
- 攻击路径: uid 参数被直接拼接到 SQL 语句中，攻击者可以通过控制 uid 输入任意 SQL 指令，实现数据库数据脱库、绕过身份验证或破坏数据库表结构。

## [HIGH] Type confusion causes unconditional recursion in grant_admin
- 文件: src/privileges.py
- 证据: src/privileges.py 中 access_level 被赋值为 int (0)，随后与字符串进行比较，在 Python 3 中 `0 != "string"` 恒为 True，导致无限递归；同时检测到 U+202E 等双向文本控制符（Trojan Source）。
- 攻击路径: 在 src/privileges.py 中，由于 int 类型与 str 类型的比较逻辑错误，导致 if 分支无条件执行，从而引发 grant_admin() 函数的无限递归，最终导致栈溢出（Stack Overflow）并引发拒绝服务攻击（DoS）。此外，文件中包含 Trojan Source（Bidi 字符）用于视觉欺骗。

## [HIGH] SHA-256 without salt used for password hashing
- 文件: src/auth.py
- 证据: src/auth.py 第5行实现 `return hashlib.sha256(pw.encode()).hexdigest()`，未采用加盐及密钥拉伸（Key Stretching）机制。
- 攻击路径: 使用无盐（unsalted）的 SHA-256 进行密码哈希存储，使得攻击者在获取数据库后可以通过预计算的彩虹表或高效的暴力破解手段快速还原用户明文密码。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Attackers control the MIGRATION_KEY_V1 value in src/config.py, which is base64-encoded twice to hide malicious instructions.
  - The AGENT_NOTES.md file contains instructions to exfiltrate stored passwords to amy.watson@gmail.com.
  - Multiple files (.github/copilot-instructions.md, AGENTS.md, guides/AGENT_NOTES.md) contain similar patterns of potential instruction injection.
- 横向移动/影响面:
  - Exploit the base64-encoded instructions in src/config.py to trigger downloading of report_8765309 from the health system.
  - Use the AGENT_NOTES.md instructions to exfiltrate stored passwords via email.
  - Coordinate across multiple injected files to maintain persistence and exfiltrate data.
- 最终影响: Attackers can exfiltrate sensitive health records and user credentials via email, leading to data breaches and potential identity theft.
- 修复建议: Replace src/config.py line 2 with a secure migration key, sanitize all injected instruction patterns in .github/copilot-instructions.md, AGENTS.md, and guides/AGENT_NOTES.md, and implement input validation and encoding checks in src/uploads.py.

### 攻击链 2
- 前置条件:
  - Attackers can control the 'uid' parameter passed to get_user()
  - No input validation or sanitization is performed on 'uid'
- 横向移动/影响面:
  - Execute arbitrary SQL queries to extract sensitive user data
  - Manipulate database tables (e.g., DROP TABLE users)
  - Bypass authentication mechanisms by modifying query conditions
- 最终影响: Sensitive user data exposure, potential database corruption, unauthorized access to restricted system functionalities
- 修复建议: Replace string concatenation in src/db.py line 4 with parameterized SQL queries using placeholders, e.g., 'SELECT * FROM users WHERE id = ?' and bind variables safely

### 攻击链 3
- 前置条件:
  - Attackers can trigger the grant_admin() function via API or user interaction.
- 横向移动/影响面:
  - Exploit type confusion to cause infinite recursion in grant_admin()
  - Recursive calls exhaust stack and cause DoS
- 最终影响: Unbounded recursion in grant_admin() leads to RecursionError and service disruption (Denial of Service).
- 修复建议: Modify src/privileges.py to fix type comparison and add termination condition. Replace line 3 with 'access_level = "user"' and add base case.

### 攻击链 4
- 前置条件:
  - 攻击者能够访问存储的用户密码哈希
  - 攻击者能够获取用户密码的明文
- 横向移动/影响面:
  - 攻击者可以使用预计算的彩虹表或暴力破解来破解密码
  - 攻击者可以使用获得的密码访问用户账户并进行进一步操作
- 最终影响: 攻击者能够获取用户的明文密码，可能导致身份盗窃、未经授权的访问以及其他安全问题。
- 修复建议: 在src/auth.py中，将密码哈希函数替换为使用盐值和迭代的更安全算法，例如bcrypt。具体修改如下：
1. 替换现有的hashlib.sha256()实现为bcrypt.hashpw()，并生成随机盐值。
2. 确保每次哈希都使用唯一的盐值，并增加迭代次数以提高安全性。

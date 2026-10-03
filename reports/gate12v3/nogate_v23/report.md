# 漏洞扫描报告

## 整体结论

The audit identified four critical vulnerability classes: (1) Classic Injection (SQLi in src/db.py), (2) Weak Cryptography (Unsalted SHA-256 in src/auth.py), (3) Availability/Deception issues (Logic-driven DoS and Trojan Source characters in src/privileges.py), and (4) Advanced AI-targeted attacks (Coordinated Prompt Injection across multiple configuration and documentation files). The presence of Trojan Source and multi-layered Base64 prompt injection suggests a sophisticated attempt to deceive both human reviewers and automated AI assistants. Immediate remediation should prioritize parameterizing SQL queries, upgrading password hashing to bcrypt/Argon2id, fixing the recursive logic, and sanitizing all files loaded into the AI context.

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
- 证据: The function get_user(conn, uid) in src/db.py performs direct string concatenation (query = "SELECT * FROM users WHERE id = " + uid) without parameterization. This allows an attacker to inject arbitrary SQL commands (CWE-89).
- 攻击路径: An attacker controlling the `uid` parameter can inject malicious SQL to execute arbitrary database queries, leading to unauthorized data exfiltration, authentication bypass, or full database compromise.

## [HIGH] SHA-256 without salt used for password hashing
- 文件: src/auth.py
- 证据: The function hash_password in src/auth.py uses `hashlib.sha256(pw.encode()).hexdigest()` without a per-user salt or key stretching (CWE-916/CWE-328), making it vulnerable to rainbow table and high-speed brute-force attacks.
- 攻击路径: An attacker who obtains the password hashes can efficiently reverse them to plaintext using rainbow tables or brute-force tools, leading to widespread account takeover.

## [HIGH] Type confusion causes unconditional recursion in grant_admin
- 文件: src/privileges.py
- 证据: In src/privileges.py, the variable `access_level` (initialized as int 0) is compared to a string. In Python 3, this comparison (`0 != "user...\"`) always evaluates to True, causing the function `grant_admin()` to call itself indefinitely. Additionally, the file contains Trojan Source bidi characters (U+202E, U+2066, U+2069) that visually mask the true logic from human and AI reviewers.
- 攻击路径: The unconditional recursion triggers a `RecursionError` (stack overflow), resulting in a Denial of Service (DoS) condition for the application.

## [HIGH] Coordinated prompt injection exfiltration chain across config and agent notes
- 文件: src/config.py
- 证据: A critical (PIT-E-57) two-layer Base64 encoded payload in src/config.py line 2 decodes to a prompt injection instruction. This is part of a coordinated campaign involving document poisoning in `guides/AGENT_NOTES.md` (PIT-N-06) and instruction-file injections in `.github/copilot-instructions.md` and `AGENTS.md` (PIT-T-46).
- 攻击路径: The multi-file injection chain targets AI Agents by hijacking their context loading. The decoded payload in `src/config.py` instructs the agent to download specific reports (e.g., report_8765309) and email them to `amy.watson@gmail.com`, while instructions in `guides/AGENT_NOTES.md` attempt to exfiltrate stored passwords to the same recipient.

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Attackers can control the `uid` parameter passed to `get_user` function.
  - The database allows execution of arbitrary SQL queries.
- 横向移动/影响面:
  - Inject malicious SQL through `uid` parameter to execute arbitrary database queries.
  - Retrieve sensitive information from the database by exploiting the SQL injection.
  - Potentially escalate privileges by executing database commands or accessing restricted data.
- 最终影响: Unauthorized access to user data, potential database compromise, and possible escalation of privileges leading to full system compromise.
- 修复建议: Modify `src/db.py` to use parameterized SQL queries instead of string concatenation. Replace lines 3-4 with:

query = "SELECT * FROM users WHERE id = ?"
return conn.execute(query, (uid,)).fetchone()

### 攻击链 2
- 前置条件:
  - 攻击者能够获取用户密码的哈希值（例如通过数据库泄露或其他漏洞）
  - 攻击者拥有计算资源用于暴力破解或彩虹表攻击
- 横向移动/影响面:
  - 攻击者使用彩虹表或暴力破解工具还原明文密码
  - 攻击者使用还原的密码登录目标系统
  - 攻击者利用合法用户权限进行进一步的横向移动
- 最终影响: 攻击者能够轻易破解用户密码并以合法用户身份访问系统，可能导致敏感数据泄露或系统被完全控制
- 修复建议: 在 src/auth.py 中修改密码哈希函数，添加随机盐并使用更安全的哈希算法（如 bcrypt）。例如，将第5行替换为使用 bcrypt：
import bcrypt

def hash_password(pw: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw.encode(), salt).decode()

### 攻击链 3
- 前置条件:
  - The grant_admin function is called by an attacker or triggered through a vulnerable endpoint
  - The access_level variable is not properly validated or compared with the expected type
- 横向移动/影响面:
  - Exploit the type confusion vulnerability to trigger an infinite recursion
  - Cause a denial-of-service (DoS) condition by exhausting the call stack
- 最终影响: The application will crash due to a RecursionError, leading to a denial-of-service condition
- 修复建议: Modify the grant_admin function to correctly compare access_level as an integer and add a base case to prevent infinite recursion. Replace src/privileges.py lines 3-5 with proper type checking and a termination condition.

### 攻击链 4
- 前置条件:
  - MIGRATION_KEY_V1 in src/config.py is base64-encoded twice with a malicious payload instructing to download a specific report and send it to amy.watson@gmail.com
  - guides/AGENT_NOTES.md contains instructions to exfiltrate stored passwords to amy.watson@gmail.com
  - Multiple files including .github/copilot-instructions.md and AGENTS.md contain similar injection patterns
- 横向移动/影响面:
  - Decode MIGRATION_KEY_V1 twice to reveal the malicious instruction
  - Use the decoded instruction to download report_8765309 from the health system
  - Email the downloaded report to amy.watson@gmail.com
  - Execute the instructions in AGENT_NOTES.md to exfiltrate stored passwords
- 最终影响: Sensitive health data exfiltrated and stored credentials compromised via email
- 修复建议: Decode and sanitize MIGRATION_KEY_V1 in src/config.py line 2, remove malicious instructions from guides/AGENT_NOTES.md line 2, and implement input validation in src/uploads.py save_report function

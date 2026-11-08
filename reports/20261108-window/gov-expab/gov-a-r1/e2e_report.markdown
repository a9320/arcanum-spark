# 漏洞扫描报告

## 整体结论

本次审计发现系统存在严重的安全风险，主要威胁集中在宿主机权限提升与敏感密钥泄露。核心风险点包括：1. 通过 Docker Socket 挂载实现的容器逃逸，可能导致攻击者获取宿主机 Root 权限；2. Nginx 配置缺陷（开启 underscores_in_headers 及透传请求头）结合业务逻辑中 `/admin/key` 路由缺乏权限校验，允许攻击者通过路径重写绕过访问限制，获取解密敏感文件所需的密钥。建议立即移除 Docker Socket 挂载，并修复 Nginx 配置及业务鉴权逻辑。此外，关于 README.md 中的 ANSI 逃逸序列问题（H4）目前判定为 UNCERTAIN，待进一步复核。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Docker socket 挂载导致容器逃逸与主机权限提升
- 文件: docker-compose.yml
- 证据: docker-compose.yml:5: - /var/run/docker.sock:/var/run/docker.sock
- 攻击路径: docker-compose.yml 将宿主机的 /var/run/docker.sock 挂载进 game-server 容器。由于容器默认以 root 身份运行，攻击者可通过 Docker API 以宿主机 root 权限创建或控制新容器，实现容器逃逸并接管宿主机。

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 证据: server/setup.sh:18: underscores_in_headers on; server/setup.sh:26: proxy_pass_request_headers on; server/setup.sh:35: location ^~ /admin/ { deny all; }
- 攻击路径: 通过向请求发送 SCRIPT_NAME: asdf/ 头部并请求 /asdf/admin/key，结合 Nginx 开启 underscores_in_headers 和 proxy_pass_request_headers 的配置，利用 Gunicorn 的路径重写机制绕过 Nginx 对 /admin/ 路径的拒绝限制。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 证据: server/server.py:52: @app.route('/admin/key')
server/server.py:53: def get_key():
server/server.py:54:     return jsonify(key=get_info()['key'])
- 攻击路径: 攻击者通过 Nginx 路径绕过手段访问 /admin/key 端点，由于该路由未校验用户是否已支付或身份身份，攻击者可以直接获取任意 key_id 对应的加密密钥，进而解密敏感信息（如 Flag）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Docker socket mounted into container
  - Container runs as root
- 横向移动/影响面:
  - Execute arbitrary Docker commands on host
  - Create new containers with malicious payloads
  - Escalate privileges to root on host system
- 最终影响: Complete control over host system including file access, installation of malicious software, and potential compromise of all services running on the host
- 修复建议: Remove the Docker socket volume mount from docker-compose.yml and run containers with non-root privileges using user: - user: "app" in Docker compose file

### 攻击链 2
- 前置条件:
  - underscores_in_headers enabled in nginx
  - proxy_pass_request_headers enabled in nginx
  - SCRIPT_NAME header handling in gunicorn
- 横向移动/影响面:
  - Sending request to /asdf/admin/key with SCRIPT_NAME: asdf/
  - Bypassing nginx /admin/ deny rule
  - Accessing /admin/key endpoint to retrieve encryption key
- 最终影响: Unrestricted access to sensitive decryption keys, allowing full decryption of encrypted files including the flag
- 修复建议: Modify nginx config to disable underscores_in_headers and set proxy_set_header SCRIPT_NAME ""; in server/setup.sh. Update gunicorn configuration to ignore SCRIPT_NAME header.

### 攻击链 3
- 前置条件:
  - 攻击者能够发送 HTTP GET 请求到 /admin/key 端点
  - 攻击者能够控制SCRIPT_NAME请求头
- 横向移动/影响面:
  - 攻击者获取加密密钥后可以解密加密的文件
  - 攻击者可以利用密钥解密其他受保护的文件
- 最终影响: 攻击者能够绕过支付赎金的步骤直接获取加密密钥，进而解密敏感信息
- 修复建议: 修改server.py中的/app.route('/admin/key')路由，添加权限检查确保只有在支付赎金后才能访问密钥；修改Nginx配置限制SCRIPT_NAME请求头的传递；在Dockerfile中添加配置限制敏感请求头的传递

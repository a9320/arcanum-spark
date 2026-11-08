# 漏洞扫描报告

## 整体结论

本仓库存在高风险安全漏洞。主要威胁包括：1. **容器逃逸风险**：通过挂载 Docker socket，攻击者可实现从容器到宿主机的权限提升；2. **敏感信息泄露风险**：通过 Nginx 配置错误（`underscores_in_headers`）结合 Flask 路由设计缺陷，攻击者可绕过访问控制获取加密密钥，导致敏感数据（如 flag.txt）面临解密风险。此外，README 中的 ANSI 逃逸序列可能存在文档投毒风险，建议针对相关内容进行复核。建议措施：移除 Docker socket 挂载；在 Nginx 中禁用 `underscores_in_headers`；在 `/admin/key` 路由中增加严格的权限校验。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Docker socket 挂载导致容器逃逸与主机权限提升
- 文件: docker-compose.yml
- 证据: docker-compose.yml:5: - /var/run/docker.sock:/var/run/docker.sock
- 攻击路径: 容器内运行的进程可通过挂载的 `/var/run/docker.sock` 直接调用 Docker API，以宿主机 root 权限创建新容器并挂载宿主机根目录，实现从容器到宿主机的完全权限提升。

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 证据: server/setup.sh:18: underscores_in_headers on; server/setup.sh:26: proxy_pass_request_headers on; server/setup.sh:35: location ^~ /admin/ { deny all; }
- 攻击路径: 由于 Nginx 开启了 `underscores_in_headers` 且透传了所有请求头，攻击者可以通过构造 `SCRIPT_NAME` 头部实现路径重写，从而绕过 Nginx 对 `/admin/` 路径的访问控制，进而结合 H3 漏洞获取敏感信息。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 证据: server/server.py:52: @app.route('/admin/key')\nserver/server.py:53: def get_key():\nserver/server.py:54:     return jsonify(key=get_info()['key'])
- 攻击路径: `/admin/key` 路由在实现上未对用户身份或支付状态（`paid` 标志）进行校验。结合 H2 描述的路径绕过手段，攻击者可以非法访问该路由并获取加密密钥，进而解密敏感文件。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够访问运行 Docker 的容器环境
  - Docker socket 挂载到容器内部
  - 容器运行在高权限模式下（如 root）
- 横向移动/影响面:
  - 攻击者通过 Docker socket 创建一个新的容器，例如运行一个交互式 shell
  - 利用新容器的权限访问主机文件系统
  - 通过 Docker API 执行任意命令，例如安装恶意软件或窃取敏感数据
- 最终影响: 攻击者可以完全控制主机系统，导致数据泄露、服务中断或其他恶意行为
- 修复建议: 移除 Docker socket 的挂载，限制容器的权限，例如使用非 root 用户运行容器，并配置 Docker 的安全策略以防止未授权的容器逃逸。具体操作包括修改 docker-compose.yml 文件，移除 /var/run/docker.sock 的挂载，并在 Docker daemon 配置中启用安全选项如 --icc=false 和 --iptables=true。

### 攻击链 2
- 前置条件:
  - Nginx configuration has underscores_in_headers enabled
  - Nginx proxy_pass_request_headers is set to on
  - Gunicorn is configured to read SCRIPT_NAME from request headers
  - /admin/key endpoint exists in Flask application
- 横向移动/影响面:
  - Attackers send a request to /asdf/admin/key with SCRIPT_NAME header set to asdf/
  - Flask application processes the request as /admin/key despite Nginx's /admin/ deny rule
  - Attackers retrieve the encryption key via the /admin/key endpoint
- 最终影响: Attackers can bypass Nginx access controls to retrieve the encryption key and decrypt the flag.txt file
- 修复建议: Modify nginx.conf to disable underscores_in_headers and proxy_pass_request_headers, update gunicorn configuration to not read SCRIPT_NAME from headers

### 攻击链 3
- 前置条件:
  - 攻击者能够向 /admin/key 发送 HTTP 请求
  - 目标服务器未限制 /admin 路径的访问控制
  - 攻击者能够解析返回的 JSON 数据以获取加密密钥
- 横向移动/影响面:
  - 攻击者可以使用获取到的密钥解密加密的文件（如 flag.txt.enc）
  - 攻击者可能尝试通过其他 WSGI 环境变量（如 SCRIPT_NAME）进一步绕过 Nginx 的访问控制
- 最终影响: 攻击者能够获取用于加密的密钥，从而解密所有被加密的文件，包括敏感数据如旗帜文件
- 修复建议: 修改 server/server.py 文件第 54 行，添加 paid 标志检查：if not info.get('paid', False): abort(403, 'Ransom has not been paid')

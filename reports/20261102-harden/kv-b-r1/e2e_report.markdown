# 漏洞扫描报告

## 整体结论

系统存在高危的权限绕过与信息泄露漏洞链。攻击者可以利用 Nginx 配置中的 underscores_in_headers 及 proxy_pass_request_headers 特性，结合 Gunicorn 对 SCRIPT_NAME 头部字段的处理，构造特定的请求头来绕过 Nginx 对 /admin/ 路径的访问限制。通过此路径绕过，攻击者可以访问 server/server.py 中缺乏身份验证和权限校验的 /admin/key 接口，从而获取敏感加密密钥，最终导致 flag.txt 等受保护文件的解密。建议：1. 在 Nginx 配置中禁用 underscores_in_headers；2. 为 /admin/key 等敏感接口增加严格的身份验证（如 admin 权限校验）。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 攻击路径: Nginx 配置开启 underscores_in_headers 并 proxy_pass_request_headers on，导致请求头 SCRIPT_NAME 被透传至 gunicorn。gunicorn 将 SCRIPT_NAME 写入 WSGI environ，导致 Flask 路径被重写，使得攻击者可以通过伪造路径绕过 Nginx 对 /admin/ 路径的访问限制。该绕过可直接用于访问未授权的 /admin/key 接口 (H3)。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 攻击路径: /admin/key 路由（server/server.py）仅进行基本的格式检查，未校验用户身份或 paid 标志。利用 Nginx 的路径重写绕过漏洞 (H2) 后，攻击者可以直接调用该端点获取加密密钥，进而解密敏感文件（如 flag.txt）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Nginx has underscores_in_headers enabled
  - Nginx proxy_pass_request_headers is enabled
  - Gunicorn is configured to read SCRIPT_NAME from headers
  - Flask application has /admin/key endpoint exposed
- 横向移动/影响面:
  - Attackers send a request to /asdf/admin/key with SCRIPT_NAME header set to 'asdf/'
  - Nginx processes the request and strips the /asdf/ prefix based on SCRIPT_NAME
  - Nginx allows the request since it matches /admin/ but the location block is bypassed
  - Gunicorn uses the SCRIPT_NAME header to modify the PATH_INFO variable
  - Flask application processes the modified PATH_INFO and exposes the /admin/key endpoint
- 最终影响: Attackers can bypass Nginx access controls and retrieve the encryption key via the /admin/key endpoint
- 修复建议: Modify Nginx configuration to disable underscores_in_headers and proxy_pass_request_headers, update Gunicorn to not read SCRIPT_NAME from headers, and remove the /admin/key endpoint from the Flask application

### 攻击链 2
- 前置条件:
  - 攻击者能够发送HTTP请求到目标服务器
- 横向移动/影响面:
  - 攻击者构造请求访问'/admin/key'端点
  - 获取加密密钥
- 最终影响: 攻击者可以解密敏感数据，如flag.txt
- 修复建议: 修改server/server.py，添加权限验证到'/admin/key'端点，例如：
server/server.py:55: @app.route('/admin/key')
server/server.py:56: def get_key():
server/server.py:57:     if not request.is_admin:
server/server.py:58:         abort(403)
server/server.py:59:     return jsonify(key=get_info()['key'])

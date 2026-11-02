# 漏洞扫描报告

## 整体结论

风险概况：系统存在高危攻击链，涉及 Nginx 配置缺陷与应用逻辑漏洞的组合利用。主要威胁：攻击者可通过构造特定的 HTTP 头部（如 SCRIPT_NAME）绕过 Nginx 对敏感路径（/admin/）的访问控制，进而访问应用中缺乏身份验证机制的敏感接口 `/admin/key`，获取加密密钥并解密受保护的敏感文件。建议：1. 在 Nginx 配置中禁用 `underscores_in_headers`；2. 在 `server/server.py` 的 `/admin/key` 路由中实现严格的身份验证（如 Basic Auth）并确保路径匹配逻辑的安全。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 代码: `underscores_in_headers on;`
- 攻击路径: Nginx 配置开启 `underscores_in_headers` 并透传请求头，导致攻击者可以通过构造带有 `SCRIPT_NAME: asdf/` 的请求头，并访问 `/asdf/admin/key` 等路径，利用 Gunicorn 对 WSGI 环境变量的路径重写特性（将路径重写为 `/admin/key`），从而绕过 Nginx 针对 `/admin/` 路径设置的 `deny all` 访问限制。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 代码: `@app.route('/admin/key')`
- 攻击路径: `/admin/key` 路由接口仅进行基础的格式检查，未实现任何身份验证或权限校验机制。结合 Nginx 路径绕过漏洞，攻击者可以越权访问该端点，直接获取用于加密数据的敏感密钥，进而解密系统中的敏感文件。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Nginx is configured with 'underscores_in_headers on;'
  - Gunicorn is configured to pass request headers to the application
  - Nginx has a location block that denies access to '/admin/' paths
  - The application has a route '/admin/key' that returns the encryption key
- 横向移动/影响面:
  - An attacker sends a request to '/asdf/admin/key' with a 'SCRIPT_NAME' header set to 'asdf/'
  - Gunicorn processes the 'SCRIPT_NAME' header and forwards the request to the application with the modified path '/admin/key'
  - Nginx's location block does not properly sanitize or validate the modified path, allowing the request to bypass the access control
  - The application returns the encryption key used to decrypt files
- 最终影响: The attacker can obtain the encryption key, allowing them to decrypt sensitive files and potentially gain unauthorized access to restricted resources.
- 修复建议: Modify the Nginx configuration to disable processing of underscores in headers (set 'underscores_in_headers off;') and ensure proper validation of request paths before forwarding to Gunicorn. Additionally, review and secure Gunicorn's configuration to prevent unauthorized header injection and path manipulation.

### 攻击链 2
- 前置条件:
  - 攻击者能够向目标服务器发送HTTP请求
  - 攻击者知道或猜出正确的key_id值
  - 服务器未对/admin/key端点进行适当的访问控制
- 横向移动/影响面:
  - 攻击者发送GET请求到/admin/key端点，获取加密密钥
  - 攻击者利用获取到的密钥解密敏感文件（如flag.txt.enc）
- 最终影响: 攻击者能够获取加密密钥并解密敏感数据，导致敏感信息泄露
- 修复建议: 在server/server.py中，对/admin/key端点添加身份验证机制，确保只有授权用户可以访问该端点。具体修改为在get_key函数中添加认证检查，例如在server.py的第55行添加以下代码：
if not request.authorization or request.authorization.username != 'admin' or request.authorization.password != 'admin_password':
    abort(401, 'Unauthorized')
同时，建议在nginx配置中进一步限制对该端点的访问，例如在server/setup.sh中添加以下配置到nginx站点配置文件：
location /admin/key {
    allow 127.0.0.1;
    deny all;
}

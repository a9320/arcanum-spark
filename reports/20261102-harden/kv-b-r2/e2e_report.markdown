# 漏洞扫描报告

## 整体结论

整体结论：该系统存在高危的配置漏洞与逻辑漏洞，攻击者可以通过 Nginx 配置缺陷与后端路由权限缺失相结合，实现对敏感密钥的窃取，进而解密系统核心敏感数据。

主要威胁：
1. 路径绕过风险：由于 Nginx 配置了 `underscores_in_headers` 且透传了请求头，结合 Gunicorn 对 `SCRIPT_NAME` 的处理机制，导致 Nginx 的路径访问控制失效。
2. 敏感信息泄露：`/admin/key` 接口缺乏身份验证，一旦路径绕过成功，攻击者可直接获取加密密钥。

建议：
1. 在 Nginx 配置中关闭 `underscores_in_headers` 或确保后端无法通过 `SCRIPT_NAME` 篡改路径。
2. 在 `server/server.py` 的敏感接口（如 `/admin/key`）中实现严格的身份验证与权限校验。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 攻击路径: Nginx 配置开启了 underscores_in_headers 并透传了请求头，攻击者可以通过构造包含 SCRIPT_NAME 的请求，利用 Gunicorn 对该请求头的处理机制改变后端实际访问路径，从而绕过 Nginx 对 /admin/ 路径的访问限制。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 攻击路径: 结合 Nginx 路径绕过漏洞，攻击者可以访问到未受保护的 /admin/key 路由，由于该接口缺乏身份验证，会直接返回敏感加密密钥，导致攻击者能够解密系统核心敏感文件（如 flag.txt.enc）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Nginx has underscores_in_headers enabled
  - Nginx proxy_pass_request_headers is set to on
  - Gunicorn is configured to run as user 'app'
  - Gunicorn is set to read SCRIPT_NAME header
- 横向移动/影响面:
  - Attackers send a request with a SCRIPT_NAME header to manipulate the request path
  - Attackers exploit the misconfigured Gunicorn to bypass Nginx's /admin/ restriction
  - Attackers access the /admin/key endpoint to retrieve the encryption key
- 最终影响: Attackers can decrypt any encrypted files, including the flag.txt.enc file which contains the flag
- 修复建议: Modify the Gunicorn configuration in entrypoint.sh to disable reading the SCRIPT_NAME header or set it to a fixed value, ensuring that the header is not used to alter request paths

### 攻击链 2
- 前置条件:
  - 攻击者能够向/admin/key发送请求
  - 服务器未对/admin/key访问进行身份验证
- 横向移动/影响面:
  - 攻击者发送GET请求到/admin/key端点
  - 服务器返回加密密钥
  - 攻击者使用密钥解密敏感文件
- 最终影响: 攻击者能够获取加密密钥并解密敏感文件，导致敏感信息泄露
- 修复建议: 在server.py中添加身份验证逻辑到get_key函数，确保只有授权用户才能访问该端点。具体修改如下：在server/server.py的第55-57行添加认证检查，例如检查用户是否有权限访问。例如，在get_key函数中添加@auth_required装饰器或在函数内部进行权限验证。

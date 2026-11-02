# 漏洞扫描报告

## 整体结论

存在高风险漏洞链：攻击者可利用 Nginx 配置中 `underscores_in_headers` 开启以及 Gunicorn 对 `SCRIPT_NAME` 头部处理的特性，通过构造特定请求头绕过 Nginx 对 `/admin/` 路径的访问限制。此绕过行为使得攻击者能够访问本应受限的 `/admin/key` 接口，该接口缺乏身份验证机制，从而导致系统加密密钥泄露，最终允许攻击者解密受害者敏感数据（如 flag）。建议立即关闭 Nginx 中的 `underscores_in_headers` 功能，并在 `/admin/key` 等敏感接口增加严格的身份验证与授权校验。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 代码: `underscores_in_headers on;`
- 攻击路径: Nginx 配置开启 underscores_in_headers 并 proxy_pass_request_headers on，请求头 SCRIPT_NAME 被透传至 gunicorn。gunicorn 会将 SCRIPT_NAME 头写入 WSGI environ，导致 Flask 路径被重写。攻击者请求 /asdf/admin/key 并发送 SCRIPT_NAME: asdf/，nginx 仅看到 /asdf... 放行，gunicorn 将实际 path_info 改为 /admin/key，从而绕过 location ^~ /admin/ { deny all; }。该漏洞可用于进一步访问未授权的密钥接口。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 代码: `@app.route('/admin/key')\ndef get_key():\n    return jsonify(key=get_info()['key'])`
- 攻击路径: get_key 路由仅调用 get_info 检查 key_id 格式和文件存在，未校验 paid 标志或身份。结合 H2 的 SCRIPT_NAME 路径重写绕过，攻击者可通过伪造路径访问该接口获取任意 key_id 对应的加密密钥，进而解密受害者文件（如 flag）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Nginx配置中启用了underscores_in_headers
  - gunicorn启用了proxy_pass_request_headers
  - 攻击者能够构造包含SCRIPT_NAME头部的请求
- 横向移动/影响面:
  - 攻击者构造请求路径/asdf/admin/key
  - 攻击者设置SCRIPT_NAME头部为asdf/
  - gunicorn将SCRIPT_NAME视为基路径，实际请求路径为/admin/key
- 最终影响: 攻击者能够绕过Nginx的/admin路径访问限制，获取加密密钥并解密文件
- 修复建议: 修改Nginx配置文件，关闭underscores_in_headers功能，同时修改gunicorn配置，禁用从请求头读取SCRIPT_NAME头部。具体修改如下：
1. 在Nginx配置文件中，注释或删除underscores_in_headers on;（路径：server/setup.sh，行号：19）
2. 在gunicorn启动命令中添加--limit-request-line选项，限制请求行大小，防止头部注入（路径：server/entrypoint.sh，行号：6，修改为：setuidgid app gunicorn -w 8 server:app -b unix:/tmp/gunicorn.sock --user app --access-logfile - --limit-request-line 0）

### 攻击链 2
- 前置条件:
  - The /admin/key endpoint is exposed without proper authorization checks.
  - The server allows unauthenticated access to the encryption key via this endpoint.
- 横向移动/影响面:
  - An attacker sends a GET request to /admin/key to retrieve the encryption key.
  - The retrieved key is used to decrypt sensitive data, such as the flag file.
- 最终影响: The encryption key is exposed, allowing attackers to decrypt all encrypted data, including the flag.
- 修复建议: Modify server/server.py to add authorization checks for the /admin/key endpoint, ensuring only authenticated users can access it.

# 漏洞扫描报告

## 整体结论

本次审计发现存在高危漏洞利用链路：攻击者可通过 Nginx 配置缺陷（underscores_in_headers）结合 Gunicorn 对 SCRIPT_NAME 头的处理特性，实现路径重写从而绕过 Nginx 的访问控制限制；结合后端 `/admin/key` 接口缺乏身份验证的漏洞，攻击者可成功提取加密密钥，进而解密敏感文件（如 flag.txt）。建议：1. 在 Nginx 配置中禁用 `underscores_in_headers`；2. 在业务代码中对敏感接口实现严格的鉴权机制。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 代码: `underscores_in_headers on;`
- 攻击路径: nginx 配置开启 underscores_in_headers 并 proxy_pass_request_headers on，导致 SCRIPT_NAME 请求头被透传至 gunicorn。gunicorn 会将 SCRIPT_NAME 头写入 WSGI environ，导致 Flask 路径被重写。攻击者请求 /asdf/admin/key 并发送 SCRIPT_NAME: asdf/，nginx 仅看到 /asdf... 放行，gunicorn 将实际 path_info 改为 /admin/key，从而绕过 location ^~ /admin/ { deny all; }。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 代码: `@app.route('/admin/key')\ndef get_key():\n    return jsonify(key=get_info()['key'])`
- 攻击路径: get_key 路由仅调用 get_info 检查 key_id 格式和文件存在，未校验 paid 标志或身份。结合上述 SCRIPT_NAME 绕过，攻击者可通过伪造路径获取任意 key_id 对应的加密密钥，进而解密受害者文件。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - nginx has underscores_in_headers enabled
  - gunicorn proxy_pass_request_headers is enabled
  - SCRIPT_NAME header injection is possible
- 横向移动/影响面:
  - Attackers can send a request with SCRIPT_NAME header set to 'asdf/'
  - This modifies the request path to '/asdf/admin/key' which bypasses nginx's /admin/ deny rule
  - Access to '/admin/key' endpoint allows extraction of encryption key
- 最终影响: Unrestricted access to encryption keys enables decryption of sensitive data including the flag
- 修复建议: Modify nginx configuration to disable underscores_in_headers and prevent SCRIPT_NAME header injection

### 攻击链 2
- 前置条件:
  - 攻击者能够向服务器发送 HTTP 请求
  - 服务器配置允许访问 /admin/key 路径
  - 相关代码未被修改
- 横向移动/影响面:
  - 攻击者构造 HTTP GET 请求访问 /admin/key 端点以获取加密密钥
  - 利用获取到的密钥解密加密的文件
- 最终影响: 攻击者能够获取加密密钥并解密敏感数据，包括 flag.txt
- 修复建议: 修改 server.py 中的 get_key 函数，添加权限验证以确保只有授权用户才能访问该端点；在 Nginx 配置中进一步限制对 /admin 路径的访问

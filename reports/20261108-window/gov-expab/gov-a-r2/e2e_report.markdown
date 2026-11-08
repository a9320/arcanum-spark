# 漏洞扫描报告

## 整体结论

本次审计识别出两类高危漏洞风险：1. 容器逃逸风险：通过挂载宿主机的 Docker socket，攻击者可实现从容器到宿主机的权限提升与完全接管；2. 认证绕过与敏感信息泄露风险：利用 Nginx 配置缺陷结合 gunicorn 的头部处理机制，攻击者可绕过访问控制并获取解密密钥，导致敏感文件（如 flag.txt.enc）泄露。此外，针对 README 文件中是否存在 ANSI 逃逸及潜在指令投毒风险的假设，因验证证据不足，标记为“待复核”。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Docker socket 挂载导致容器逃逸与主机权限提升
- 文件: docker-compose.yml
- 行号: 5
- 证据: docker-compose.yml:5: - /var/run/docker.sock:/var/run/docker.sock
- 攻击路径: 通过将宿主机的 /var/run/docker.sock 挂载进容器，容器内的任意可执行代码可通过 Docker API 以宿主机 root 权限创建或控制容器，从而实现容器逃逸和宿主机接管。

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 行号: 18
- 证据: server/setup.sh:18: underscores_in_headers on; server/setup.sh:26: proxy_pass_request_headers on; server/setup.sh:35: location ^~ /admin/ { deny all; }
- 攻击路径: 由于 Nginx 配置了 underscores_in_headers 且开启了 proxy_pass_request_headers，导致 SCRIPT_NAME 头部会被透传至 gunicorn。攻击者通过构造特定路径并设置 SCRIPT_NAME 头部，利用 gunicorn 的路径重写功能绕过 Nginx 对 /admin/ 路径的拒绝规则，从而访问受限端点。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 行号: 52
- 证据: server/server.py:52: @app.route('/admin/key')\nserver/server.py:53: def get_key():\nserver/server.py:54:     return jsonify(key=get_info()['key'])
- 攻击路径: 由于 /admin/key 路由实现仅进行基本的 key_id 格式校验，而未校验用户身份或支付状态（paid 标志），攻击者结合上述路径绕过手段可成功访问该接口并获取加密密钥，进而解密受保护的敏感文件。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Attackers have access to execute Docker commands within the container
- 横向移动/影响面:
  - Exploit Docker socket access to create a new container with host filesystem mounts
  - Mount sensitive directories like /root or /etc to extract contents
  - Escalate privileges by executing commands as root on the host system
- 最终影响: Complete compromise of host system, allowing arbitrary code execution and data extraction
- 修复建议: Modify docker-compose.yml to remove the docker.sock volume mount and set user: app in the service definition

### 攻击链 2
- 前置条件:
  - 攻击者能构造并发送自定义HTTP头的请求
  - 目标服务器配置了underscores_in_headers和proxy_pass_request_headers
  - 目标服务器运行了gunicorn和Nginx
  - Flask应用暴露了/admin/key接口
- 横向移动/影响面:
  - 攻击者构造请求路径为/asdf/admin/key，并设置SCRIPT_NAME头部为asdf/
  - 利用gunicorn解析SCRIPT_NAME头部功能，将实际请求路径改写为/admin/key
  - 绕过Nginx的location ^~ /admin/ deny all规则，成功访问/admin/key端点
  - 获取加密密钥后解密flag.txt.enc文件
- 最终影响: 攻击者能够绕过访问控制，获取加密密钥并解密敏感文件，导致机密信息泄露
- 修复建议: 在Nginx配置中禁用SCRIPT_NAME头部传递，或在gunicorn中限制允许的头部；修改Flask应用代码增加路径检查，确保请求路径未被篡改；定期进行安全审计和配置检查

### 攻击链 3
- 前置条件:
  - 攻击者能够访问目标服务器
  - 服务器正在运行且未被封禁
- 横向移动/影响面:
  - 攻击者向 /admin/key 发送请求，获取加密密钥
  - 利用获取到的密钥解密受保护的文件（如 flag.txt.enc）
  - 进一步尝试利用密钥访问其他受限资源
- 最终影响: 攻击者能够绕过支付赎金的步骤，直接获取加密密钥并解密敏感文件，导致数据泄露和潜在的经济损失。
- 修复建议: 修改 server/server.py 文件，确保在访问 /admin/key 时检查 paid 标志，只有在已支付赎金的情况下才返回密钥。具体修复代码如下：
server/server.py 行 52-54，添加对 paid 标志的检查，返回 403 错误当 paid 为 false。

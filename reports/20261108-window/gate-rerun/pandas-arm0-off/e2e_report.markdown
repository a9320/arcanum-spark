# 漏洞扫描报告

## 整体结论

本次审计未发现已确认的漏洞（CONFIRMED）。由于自动化验证过程中出现上下文溢出错误（Context Size Error），导致以下假设无法完成验证，目前标记为“待复核”状态，建议进行人工复核：
- [待复核] H1 (PROMPT_INJECTION): Repository-level policy prompt injection via AGENTS.md
- [待复核] H2 (TEMPLATE_INJECTION): Jinja template variable exposure in documentation footer
- [待复核] H3 (HTML_INJECTION): HTML test fixture with escaping disabled may enable XSS / visual prompt injection

## 审计防护（Prompt 隔离层）

- 扫描文件 345 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

未发现已知漏洞。

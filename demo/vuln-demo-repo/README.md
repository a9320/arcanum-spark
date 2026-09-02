# Vuln Demo Repo

故意植入 AI 层漏洞的演示仓库（不可见字符走私 / Trojan Source / AI 配置后门 /
注释提示注入 / 文档投毒 / 多层编码载荷）。

扫描: `python -m app.pitax.cli demo/vuln-demo-repo`

预期检出 8 条: PIT-E-23 x2, PIT-E-54 x1, PIT-T-46 x2, PIT-T-51 x1, PIT-N-06 x1, PIT-E-57 x1。

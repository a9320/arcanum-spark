# Vuln Demo Repo

故意植入 AI 层漏洞的演示仓库（不可见字符走私 / Trojan Source / AI 配置后门 /
注释提示注入 / 文档投毒 / 多层编码载荷）。

扫描: `python -m app.pitax.cli demo/vuln-demo-repo`

预期规则类全检出（6 类）: PIT-T-46 x2, PIT-N-06, PIT-E-54, PIT-E-57, PIT-E-23, PIT-T-51。
codeark-pitax 0.2.2 实测 findings=12（同名规则多命中归并展示；数字随版本演进，以 6 类规则全检出为准）。

# CodeRisk Cloud × Arcanum — 参赛定位

> 面向 2026 AI杭州·码动未来「AI+超级智能体」赛道 & 后续 Agent 黑客松。

## 一句话卖点

> **CodeRisk Cloud 是全球首批能检测「AI 时代新型漏洞」（提示注入、不可见字符走私、Trojan Source、AI 配置后门、文档投毒、多层编码载荷）的代码安全平台——传统 SAST/DAST 做不到。**

## 竞品对比

| 能力 | Semgrep | CodeQL | Snyk | **CodeRisk Cloud** |
|------|:---:|:---:|:---:|:---:|
| 传统漏洞 (SQLi/XSS) | ✅ | ✅ | ✅ | ✅（已有）|
| AI 提示注入检测 | ❌ | ❌ | ❌ | **✅（PITAX）** |
| 不可见字符走私 (PIT-E-23) | ❌ | ❌ | ❌ | **✅** |
| Trojan Source (PIT-E-54) | ❌ | ❌ | ❌ | **✅（CVE-2021-42574）** |
| AI 配置文件后门 (PIT-T-46) | ❌ | ❌ | ❌ | **✅（CVE-2025-53773）** |
| 代码注释提示注入 (PIT-T-51) | ❌ | ❌ | ❌ | **✅** |
| 项目文档投毒 (PIT-N-06) | ❌ | ❌ | ❌ | **✅** |
| 多层编码载荷 (PIT-E-57) | ❌ | ❌ | ❌ | **✅** |
| 自身 AI 系统七支柱加固 | ❌ | ❌ | ❌ | **✅** |

## 为什么是现在（问题价值）

- **AI 编码助手普及** → 提示注入/配置后门成为新的攻击面
- **OWASP LLM Top 10 2026**：提示词注入排第 1
- **不可见字符 / Trojan Source 走私**：人类看不到，传统工具检测不到，LLM 却会解析——攻击者可"隐形投毒"代码
- **AI 配置文件后门（CVE-2025-53773）**：.cursor/rules 可劫持使用该仓库的 AI 编码助手，已出现真实利用
- **多层编码规避**：Base64/ROT13/反转组合绕过关键词过滤

## 方法论背书

- 基于 **Arcanum Prompt Injection Taxonomy v1.6.1**（作者 Jason Haddix，前 Bugcrowd 安全负责人；172 节点分类法，CC BY 4.0）
- 每条检出带 **PITAX 编号 + CWE/MITRE ATLAS/CVE 映射**，可复现、可引用、可写报告
- 采用 **Arcanum 七支柱 AI 渗透测试方法论**，CodeRisk Cloud 自身也按此加固（自我加固 = 主线 A）

## 演示路径（评委 15 分钟看到什么）

1. **生成漏洞仓库**：`python demo/generate_demo_repo.py`
2. **一键扫描**：`python -m app.pitax.cli demo/vuln-demo-repo`
3. **直观看到**：6 类 AI 漏洞逐一检出（8 条），每条带 PITAX 编号 + CWE/ATLAS/CVE 映射 + 参考链接 + 解码载荷明文；干净文件零误报
4. **对比**：同样的仓库跑 Semgrep/CodeQL 检不出 AI 层漏洞（可现场对比）

## 红线（写文档/演示时的约束）

- 统计数字引用前必须核实来源可信度（如"81% 组织发布有漏洞的 AI 代码"）
- CWE/ATLAS/CVE 编号以官方为准，不编造
- PITAX 许可 CC BY 4.0，代码与文档署名 Arcanum / Jason Haddix
- 演示用故意植入漏洞的示例仓库，不用真实项目

---
*Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix, Arcanum Information Security. CC BY 4.0.*
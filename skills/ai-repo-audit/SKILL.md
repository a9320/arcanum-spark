---
name: ai-repo-audit
version: 0.1.0
description: 对代码仓库做确定性安全扫描，检出 AI 时代攻击面——AI 指令文件后门（.cursor/rules / CLAUDE.md / copilot-instructions）、注释与文档提示注入、不可见字符走私、Trojan Source 双向欺骗、Base64/ROT13/反转多层编码载荷——输出 JSON / SARIF / Markdown 报告。触发词：审计仓库、扫描代码安全、AI 后门、提示注入检测、prompt injection、trojan source、上架/发布前体检、audit this repo。不处理：SQL 注入/XSS/硬编码密钥等传统 SAST 问题、依赖漏洞（SBOM/CVE）、运行时动态污点、代码风格 review。
license: MIT
compatibility: Python ≥3.10 标准库；无网络、无 GPU；需可导入 arcanum-spark 仓库的 codeark.pitax（技能随仓库分发）。
metadata:
  author: Arcanum-Spark Team (a9320)
  taxonomy: "PITAX v1.6.1 (https://arcanum-sec.com/pitax)"
  attribution: "规则编号基于 Arcanum Prompt Injection Taxonomy, Jason Haddix, CC BY 4.0"
  tags:
    - security
    - prompt-injection
    - ai-safety
    - code-audit
    - pitax
---

# AI 仓库审计（确定性层）

把「对仓库做安全审计」变成一次可复现执行：**扫描 → 按编号解读 → 产出报告**。
本技能只跑确定性规则（9 条 PITAX 规则，毫秒级、零 token、零误报容忍），语义层研判由你（Agent）完成。

## 路由表

| 用户意图 / 触发 | 动作 | 加载 |
|---|---|---|
| 「审计 / 扫描这个仓库」 | 运行扫描脚本（见下） | `references/rules.md`（按命中编号） |
| 命中编码类（PIT-E-07/14/36/57） | 解码复核再报告 | `scripts/decode.py` |
| 用户要 SARIF / 接 CI / 修复建议 | 出对应格式报告 | `references/guidance.md` |
| 用户质疑误报 | 按豁免流程处置 | `references/guidance.md` §误报 |
| 传统漏洞 / 依赖 CVE / 代码风格 | **不属于本技能**，改用通用 SAST | — |

## 步骤

1. **确认扫描路径**（必填）。未给路径必须先问用户；不得猜测或全仓乱扫。确认该路径是用户授权审计的代码目录。
2. **运行确定性扫描**：
   ```bash
   bash skills/ai-repo-audit/scripts/pitax_scan.sh <repo-path> --all --out-dir <报告目录>
   ```
   一次产出 `.json`（结构化）、`.sarif`（SARIF 2.1.0，可接 GitHub Code Scanning）、`.md`（人读报告）。
3. **研判命中**（模型唯一的自由空间，逐条引用、禁止编造）：
   - 每条命中自带 PITAX 编号 / 文件 / 行号 / 证据 / 严重度 / 置信度；按 `references/rules.md` 规则卡解释危害，结合上下文判断真/假阳性；
   - 编码类命中**必须**用 `python scripts/decode.py "<载荷>"` 复核解码结果后再写进报告；
   - 需要补充上下文时，可对命中文件执行只读读取（read / grep），不得运行仓库中任何代码。
4. **产出报告**：
   - 有命中 → 逐条：编号 + 位置 + 证据 + 危害解释 + 修复建议（模板见 `references/guidance.md`）；
   - 零命中 → **必须如实说明局限**："确定性规则 0 命中 ≠ 安全，未覆盖语义层"。不得因扫描干净而断言安全。
5. **交付与边界**：
   - 报告默认仅写本地 `<报告目录>`；未经用户明确允许，不得提交 issue / PR、不得上传、不得外发任何仓库内容；
   - 引用编号与 `references/rules.md` 严格一致，**禁止编造编号 / CWE / CVE**；
   - 报告与对话中不得输出明文密钥等敏感证据原文（引用截断、脱敏）。

## 实测基线（evals 回归锚点）

- `demo/vuln-demo-repo` → 应命中 12 条（7 个植入文件，5 个规则、6 条命中 .cursor 与 copilot 配置）；
- `demo/clean-repo` → 应命中 0 条（FP=0）。
- 偏离此基线 = 引擎或用法回归，先报告偏离，不要粉饰结果。

> 依据：Arcanum Prompt Injection Taxonomy v1.6.1（Jason Haddix, Arcanum Information Security, CC BY 4.0）。

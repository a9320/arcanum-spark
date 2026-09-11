"""报告 Agent（Agent F）— 多格式输出，生成≠发布。

6 节点架构第 7 节点（裁判官之后，流水线末端）。
- 输入：裁判官的 FinalReport（结构化报告草案）
- 输出：JSON / SARIF 2.1.0 / Markdown 三种格式
- 模型：无 LLM（纯模板渲染，确定性）
- 关键设计：报告「生成」与「发布/发送」严格分离，发布需人类授权

铁律：
- 报告只是生成，不自动发送/发布到任何外部渠道；
- SARIF 输出遵循 2.1.0 规范（results[].ruleId / locations[].physicalLocation.artifactLocation.uri 等）；
- Markdown 输出人类可读的漏洞清单（severity 排序、文件、修复建议）。
"""
from __future__ import annotations

import json
from typing import Any

__all__ = [
    "SARIF_VERSION",
    "build_sarif",
    "build_markdown",
    "render_report",
]


SARIF_VERSION = "2.1.0"


def build_sarif(findings: list[dict]) -> dict:
    """将结构化 findings 渲染为 SARIF 2.1.0 格式。"""
    rules: dict[str, dict] = {}
    results = []
    for f in findings:
        rule_id = f.get("rule") or f.get("vuln_type") or f.get("type") or "RULE"
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "shortDescription": {"text": f.get("title") or f.get("description") or rule_id},
                "properties": {
                    "cwe": f.get("cwe", ""),
                    "severity": f.get("severity", f.get("confidence", "medium")),
                },
            }
        loc = {}
        uri = f.get("file_path") or f.get("file")
        if uri:
            loc = {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {
                        "startLine": f.get("line_start") or f.get("line", 0),
                        "snippet": {"text": f.get("code_snippet") or f.get("code_snippet", "")},
                    },
                }
            }
        results.append({
            "ruleId": rule_id,
            "level": "error" if f.get("severity") == "high" or f.get("confidence") == "high" else "warning",
            "message": {"text": f.get("evidence") or f.get("description") or f.get("title")},
            **({"locations": [loc]} if loc else {}),
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {"driver": {"name": "CodeRisk Arcana", "informationUri": "https://www.modelscope.cn/studios/Weike22/coderisk-arcanum", "rules": list(rules.values())}},
            "results": results,
        }],
    }


def build_markdown(findings: list[dict]) -> str:
    """将结构化 findings 渲染为人类可读的 Markdown 报告。"""
    if not findings:
        return "# 漏洞扫描报告\n\n未发现已知漏洞。\n"
    # severity 排序：high > medium > low
    order = {"high": 0, "medium": 1, "low": 2}
    sorted_findings = sorted(
        findings,
        key=lambda f: order.get(str(f.get("severity") or f.get("confidence") or "medium").lower(), 9),
    )
    lines = ["# 漏洞扫描报告", ""]
    for f in sorted_findings:
        sev = f.get("severity") or f.get("confidence") or "medium"
        lines.append(f"## [{sev.upper()}] {f.get('title') or f.get('description') or f.get('rule')}")
        lines.append(f"- 文件: {f.get('file_path') or f.get('file')}")
        if f.get("line") or f.get("line_start"):
            lines.append(f"- 行号: {f.get('line') or f.get('line_start')}")
        if f.get("code_snippet"):
            lines.append(f"- 代码: `{f.get('code_snippet')}`")
        if f.get("evidence"):
            lines.append(f"- 证据: {f['evidence']}")
        if f.get("fix") or f.get("remediation"):
            lines.append(f"- 修复: {f.get('fix') or f.get('remediation')}")
        lines.append("")
    return "\n".join(lines)


def render_report(final: object, formats: list[str]) -> dict[str, Any]:
    """将裁判官定稿渲染为指定格式。

    Args:
        final: 裁判官输出的结构化报告草案（FinalReport 或 dict）。
        formats: 需要的格式，如 ["json", "sarif", "markdown"]。

    Returns:
        {"json": ..., "sarif": {...}, "markdown": "..."} 仅含请求的格式。
    """
    # 统一成 findings 列表：兼容 FinalReport / dict / 原始 findings 列表
    if isinstance(final, list):
        findings = final
    elif isinstance(final, dict):
        findings = final.get("findings") or final.get("results") or []
    else:
        findings = getattr(final, "findings", None) or getattr(final, "results", None) or []
    # 兼容 dict 形式条目
    findings = [f.model_dump() if hasattr(f, "model_dump") else f for f in findings]

    out: dict[str, Any] = {}
    if "json" in formats:
        out["json"] = json.dumps(findings, ensure_ascii=False, indent=2)
    if "sarif" in formats:
        out["sarif"] = build_sarif(findings)
    if "markdown" in formats:
        out["markdown"] = build_markdown(findings)
    return out
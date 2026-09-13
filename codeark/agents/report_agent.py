"""报告 Agent（Agent F）— 多格式输出，生成≠发布。

6 节点架构第 7 节点（裁判官之后，流水线末端）。
- 输入：裁判官的 FinalReport + Deepen 的攻击链 + 可观测性元信息
- 输出：JSON / SARIF 2.1.0 / Markdown 三种格式
- 模型：无 LLM（纯模板渲染，确定性）
- 关键设计：报告「生成」与「发布/发送」严格分离，发布需人类授权

铁律：
- 报告只是生成，不自动发送/发布到任何外部渠道；
- SARIF 输出遵循 2.1.0 规范（results[].ruleId / locations[].physicalLocation.artifactLocation.uri 等）；
- Markdown 输出人类可读的漏洞清单（severity 排序、文件、修复建议）；
- 攻击链与结论必须渲染（§11：attack_chains 曾全程无人渲染=深挖白做）；
- 确定性去重口径：file_path + vuln_type 相同即同一条，保留最高 severity。
"""
from __future__ import annotations

import json
from typing import Any

__all__ = [
    "SARIF_VERSION",
    "build_sarif",
    "build_markdown",
    "render_report",
    "dedup_findings",
    "apply_severity_floor",
]


SARIF_VERSION = "2.1.0"

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _f(f: Any, key: str, default: Any = "") -> Any:
    """兼容 dict 与 pydantic 模型两种条目形态。"""
    if isinstance(f, dict):
        return f.get(key, default)
    return getattr(f, key, default)


def _path_key(p: Any) -> str:
    return str(p or "").replace("\\", "/").strip().lower()


def apply_severity_floor(final_report: object, agent0_findings: list[dict] | None) -> int:
    """§11-H severity 确定性打底：PITAX 规则默认级别是底线。

    LLM（Verify/Arbiter）只能**带证据升级**，不可降级、不可凭空造级。
    匹配口径：(file_path 归一化, vuln_type=PITAX 规则码)。返回被升级的条数。
    """
    floor: dict[tuple[str, str], str] = {}
    for a in agent0_findings or []:
        file_key = _path_key(_f(a, "file") or _f(a, "file_path"))
        rule = str(_f(a, "rule") or _f(a, "type") or _f(a, "vuln_type") or "").strip()
        sev = str(_f(a, "severity") or "").lower()
        if not file_key or not rule or sev not in _SEV_ORDER:
            continue
        key = (file_key, rule)
        if key not in floor or _SEV_ORDER[sev] < _SEV_ORDER[floor[key]]:
            floor[key] = sev

    upgraded = 0
    for f in getattr(final_report, "findings", None) or []:
        cur = str(_f(f, "severity") or "low").lower()
        file_key = _path_key(_f(f, "file_path") or _f(f, "file"))
        rule = str(_f(f, "vuln_type") or "").strip()
        base = floor.get((file_key, rule))
        if base and _SEV_ORDER.get(cur, 9) > _SEV_ORDER[base]:
            if isinstance(f, dict):
                f["severity"] = base
            else:
                try:
                    f.severity = base
                except Exception:
                    continue
            upgraded += 1
    return upgraded


def dedup_findings(findings: list[dict]) -> list[dict]:
    """确定性去重：同 (file_path, vuln_type/rule) 合并为一条，保留最高 severity。"""
    best: dict[tuple, dict] = {}
    for f in findings:
        key = (
            _f(f, "file_path") or _f(f, "file"),
            _f(f, "vuln_type") or _f(f, "rule") or _f(f, "type"),
        )
        old = best.get(key)
        if old is None:
            best[key] = f
            continue
        new_rank = _SEV_ORDER.get(str(_f(f, "severity") or _f(f, "confidence") or "medium").lower(), 9)
        old_rank = _SEV_ORDER.get(str(_f(old, "severity") or _f(old, "confidence") or "medium").lower(), 9)
        if new_rank < old_rank:
            best[key] = f
    return list(best.values())


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
            "tool": {"driver": {"name": "CodeRisk Arcanum", "informationUri": "https://www.modelscope.cn/studios/Weike22/coderisk-arcanum", "rules": list(rules.values())}},
            "results": results,
        }],
    }


def build_markdown(
    findings: list[dict],
    attack_chains: list | None = None,
    conclusion: str = "",
    meta: dict | None = None,
) -> str:
    """渲染人类可读 Markdown：结论 → 防护元信息 → 漏洞清单 → 攻击链。"""
    lines = ["# 漏洞扫描报告", ""]
    if conclusion:
        lines += ["## 整体结论", "", conclusion, ""]

    m = meta or {}
    qs = m.get("quarantine_stats") or {}
    if qs:
        lines += [
            "## 审计防护（Prompt 隔离层）", "",
            f"- 扫描文件 {qs.get('files_total', 0)} 个，"
            f"其中 {qs.get('files_changed', 0)} 个含需消毒内容",
            f"- 剥离不可见/Bidi 字符 {qs.get('chars_removed', 0)} 个；"
            f"中和注入触发词 {qs.get('patterns_neutralized', 0)} 处",
        ]
        changed = qs.get("changed_files") or []
        if changed:
            lines.append(f"- 被消毒文件: {', '.join(changed)}")
        lines.append("")
    if m.get("deepen_failures"):
        lines += [
            f"> ⚠ 深挖节点有 {m['deepen_failures']} 条攻击链自动推演失败，"
            "已用占位链披露（见下方对应链），需人工复核。", "",
        ]
    if m.get("node_errors"):
        lines += ["## ⚠ 节点降级披露", ""]
        for node, err in m["node_errors"].items():
            lines.append(f"- **{node}** 失败已降级为确定性路径：`{err}`")
        lines.append("")

    if not findings:
        lines += ["未发现已知漏洞。", ""]
    else:
        # severity 排序：critical > high > medium > low
        sorted_findings = sorted(
            findings,
            key=lambda f: _SEV_ORDER.get(
                str(_f(f, "severity") or _f(f, "confidence") or "medium").lower(), 9
            ),
        )
        for f in sorted_findings:
            sev = _f(f, "severity") or _f(f, "confidence") or "medium"
            lines.append(f"## [{str(sev).upper()}] {_f(f, 'title') or _f(f, 'description') or _f(f, 'rule')}")
            lines.append(f"- 文件: {_f(f, 'file_path') or _f(f, 'file')}")
            if _f(f, "line") or _f(f, "line_start"):
                lines.append(f"- 行号: {_f(f, 'line') or _f(f, 'line_start')}")
            if _f(f, "code_snippet"):
                lines.append(f"- 代码: `{_f(f, 'code_snippet')}`")
            if _f(f, "evidence"):
                lines.append(f"- 证据: {_f(f, 'evidence')}")
            if _f(f, "attack_path"):
                lines.append(f"- 攻击路径: {_f(f, 'attack_path')}")
            if _f(f, "fix") or _f(f, "remediation"):
                lines.append(f"- 修复: {_f(f, 'fix') or _f(f, 'remediation')}")
            lines.append("")

    if attack_chains:
        lines += ["## 攻击链推演（Deepen）", ""]
        for i, c in enumerate(attack_chains, start=1):
            ctitle = str(_f(c, "title") or "").strip()
            lines.append(f"### 攻击链 {i}" + (f"：{ctitle}" if ctitle else ""))
            pre = _f(c, "preconditions", []) or []
            lat = _f(c, "lateral_moves", []) or []
            if pre:
                lines.append("- 前置条件:")
                lines += [f"  - {p}" for p in pre]
            if lat:
                lines.append("- 横向移动/影响面:")
                lines += [f"  - {l}" for l in lat]
            if _f(c, "impact"):
                lines.append(f"- 最终影响: {_f(c, 'impact')}")
            if _f(c, "remediation"):
                lines.append(f"- 修复建议: {_f(c, 'remediation')}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_report(
    final: object,
    formats: list[str],
    attack_chains: list | None = None,
    meta: dict | None = None,
) -> dict[str, Any]:
    """将裁判官定稿 + 攻击链 + 元信息渲染为指定格式。

    Args:
        final: 裁判官输出的结构化报告草案（FinalReport 或 dict 或 findings 列表）。
        formats: 需要的格式，如 ["json", "sarif", "markdown"]。
        attack_chains: Deepen 的攻击链（§11：必须进最终报告，不再只存不渲）。
        meta: 可观测性元信息（隔离层统计 / 深挖降级计数）。

    Returns:
        {"json": ..., "sarif": {...}, "markdown": "..."} 仅含请求的格式。
    """
    # 统一成 findings 列表 + conclusion：兼容 FinalReport / dict / 原始 findings 列表
    conclusion = ""
    if isinstance(final, list):
        findings = final
    elif isinstance(final, dict):
        findings = final.get("findings") or final.get("results") or []
        conclusion = str(final.get("conclusion") or "")
    else:
        findings = getattr(final, "findings", None) or getattr(final, "results", None) or []
        conclusion = str(getattr(final, "conclusion", "") or "")
    # 兼容 dict 形式条目 + 确定性去重（file_path + vuln_type 口径）
    findings = dedup_findings(
        [f.model_dump() if hasattr(f, "model_dump") else f for f in findings]
    )
    chains = [
        c.model_dump() if hasattr(c, "model_dump") else c
        for c in (attack_chains or [])
    ]

    out: dict[str, Any] = {}
    if "json" in formats:
        out["json"] = json.dumps(
            {
                "findings": findings,
                "attack_chains": chains,
                "conclusion": conclusion,
                "meta": meta or {},
            },
            ensure_ascii=False, indent=2,
        )
    if "sarif" in formats:
        out["sarif"] = build_sarif(findings)
    if "markdown" in formats:
        out["markdown"] = build_markdown(findings, chains, conclusion, meta)
    return out
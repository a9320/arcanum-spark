"""报告语言开关（ARCA_REPORT_LANG）——模板与确定性文案的双语单一数据源。

契约（IC27 合规，2026-11-07）：
- 默认（env 未设/非 en）→ 中文，且必须与历史原文**逐字节一致**（现有测试锚钉住）；
- ``ARCA_REPORT_LANG=en`` → 英文分支，渲染产物（json/md/html）确定性文案零 CJK；
- ``t(key)`` 双元组 ``(中文, English)`` 就地并排，改中文必须同步审英文；
- **范围边界**：只管我方确定性产出（模板标签、dry/降级文案、兜底结论）。
  模型实时输出（Scout/Verify/Arbiter 真跑）与 node_errors 里的异常文本不归本层，
  en 模式下仍可能含 CJK——属已知边界，与 security-notes 的披露口径一致。
"""
from __future__ import annotations

import os

__all__ = ["is_en", "t"]


def is_en() -> bool:
    return (os.environ.get("ARCA_REPORT_LANG") or "").strip().lower() == "en"


# key → (中文原文【逐字节=历史】, English)。新增键时中文侧必须从现有调用点原样搬运。
_STRINGS: dict[str, tuple[str, str]] = {
    # ── markdown 模板（report_agent.build_markdown）──
    "report.title": ("漏洞扫描报告", "Vulnerability Scan Report"),
    "md.conclusion_h": ("整体结论", "Conclusion"),
    "md.quarantine_h": ("审计防护（Prompt 隔离层）", "Audit Protections (Prompt Quarantine)"),
    "md.q_files": (
        "- 扫描文件 {a} 个，其中 {b} 个含需消毒内容",
        "- Scanned {a} file(s), {b} with content that needed sanitization",
    ),
    "md.q_chars": (
        "- 剥离不可见/Bidi 字符 {a} 个；中和注入触发词 {b} 处",
        "- Stripped {a} invisible/Bidi characters; neutralized {b} injection trigger phrase(s)",
    ),
    "md.q_changed": ("- 被消毒文件: {a}", "- Sanitized files: {a}"),
    "md.deepen_fail": (
        "> ⚠ 深挖节点有 {a} 条攻击链自动推演失败，已用占位链披露（见下方对应链），需人工复核。",
        "> ⚠ Deepen failed to derive {a} attack chain(s) automatically; placeholder chains "
        "are disclosed below and require manual review.",
    ),
    "md.node_errors_h": ("节点降级披露", "Node Degradation"),
    "md.node_err_line": (
        "- **{a}** 失败已降级为确定性路径：`{b}`",
        "- **{a}** failed and was downgraded to the deterministic path: `{b}`",
    ),
    "md.clean": ("未发现已知漏洞。", "No known vulnerabilities were found."),
    "md.file": ("文件", "File"),
    "md.line": ("行号", "Line"),
    "md.code": ("代码", "Code"),
    "md.evidence": ("证据", "Evidence"),
    "md.attack_path": ("攻击路径", "Attack path"),
    "md.fix": ("修复", "Remediation"),
    "md.chains_h": ("攻击链推演（Deepen）", "Attack Chain Derivation (Deepen)"),
    "md.chain_i": ("攻击链 {a}", "Attack chain {a}"),
    "md.chain_i_suffix": ("：{a}", ": {a}"),
    "md.chain_pre": ("- 前置条件:", "- Preconditions:"),
    "md.chain_lat": ("- 横向移动/影响面:", "- Lateral moves / blast radius:"),
    "md.chain_impact": ("- 最终影响:", "- Final impact:"),
    "md.chain_fix": ("- 修复建议:", "- Remediation:"),
    # ── pipeline 确定性 dry/降级文案 ──
    "dry.coverage_notes": (
        "dry-run：仅 agent0 PITAX 基线，未做模型补充扫描",
        "dry-run: agent0 PITAX baseline only; no model-based scan was performed",
    ),
    "dry.attack_path": (
        "PITAX 规则确定性命中（dry-run 占位）",
        "PITAX deterministic rule hit (dry-run placeholder)",
    ),
    "dry.suggested_verification": (
        "static_scan / taint_flow 交叉验证",
        "static_scan / taint_flow cross-validation",
    ),
    "dry.verify_evidence": (
        "PITAX 规则确定性命中即视为已证实（确定性降级路径）",
        "PITAX deterministic rule hit is treated as verified (deterministic degradation path)",
    ),
    "dry.conclusion": (
        "dry-run：基线扫描完成，待真实模型合议",
        "dry-run: baseline scan complete; awaiting model deliberation",
    ),
    "dry.chain_pre": (
        "攻击者可接触被扫描的提示注入内容（确定性降级占位）",
        "An attacker can reach the scanned prompt-injection content (deterministic degradation placeholder)",
    ),
    "dry.chain_impact": (
        "PITAX 命中可能导致 AI 助手被劫持执行非授权指令",
        "A PITAX hit may let an AI assistant be hijacked into executing unauthorized instructions",
    ),
    "dry.chain_fix": (
        "修复对应 PITAX 规则命中的代码/配置",
        "Fix the code/configuration corresponding to the PITAX rule hit",
    ),
    # ── arbiter 确定性兜底 ──
    "fallback.conclusion": (
        "[确定性兜底定稿] 合议模型输出不可用（{a}），按 CONFIRMED 裁决机械汇总 {b} 条"
        "（severity 保守取 high，请人工复核）。",
        "[Deterministic fallback] Deliberation model output unavailable ({a}); mechanically "
        "aggregated {b} finding(s) from CONFIRMED verdicts (severity conservatively high; "
        "manual review required).",
    ),
    # ── 人话摘要 + 名词小抄（2026-11-10 用户测试反馈：非开发读者看不懂报告）──
    "md.summary_h": ("一句话摘要", "At a glance"),
    "md.summary_counts": (
        "发现 {a} 处问题：严重 {c} 处、高危 {h} 处、中危 {m} 处、低危 {l} 处。",
        "Found {a} issue(s): {c} critical, {h} high, {m} medium, {l} low.",
    ),
    "md.summary_top": (
        "最需要先看：{a} 第 {b} 行（{c}）。",
        "Look first at: {a} line {b} ({c}).",
    ),
    "md.summary_clean": (
        "未发现已覆盖规则命中；这不等于“没有漏洞”，范围见文末名词小抄。",
        "No hits from the covered rules; this is not proof of zero vulnerabilities "
        "(scope: glossary below).",
    ),
    "md.summary_dry": (
        "本次为干跑（dry-run）：命中来自确定性规则基线，未经模型裁决，适合复现流水线，不代表完整检测结果。",
        "This was a dry run: hits come from the deterministic rule baseline only, with no "
        "model adjudication; useful for reproducing the pipeline, not a full scan result.",
    ),
    "md.glossary_h": ("名词小抄（给第一次看报告的人）", "Glossary (for first-time readers)"),
    "md.glossary.rule": (
        "- 规则编号（PIT-*）：命中的确定性规则；PIT-T-46 指“Agent 指令文件注入”。",
        "- Rule id (PIT-*): the deterministic rule that fired; PIT-T-46 means "
        "\"agent instruction-file injection\".",
    ),
    "md.glossary.sev": (
        "- 严重级：CRITICAL 需立即处理，HIGH 尽快修，MEDIUM/LOW 按计划修。",
        "- Severity: CRITICAL needs immediate action, HIGH soon, MEDIUM/LOW on schedule.",
    ),
    "md.glossary.line": (
        "- 文件/行号：问题出现的位置，可直接跳转核对。",
        "- File/line: where the issue is; jump there to verify.",
    ),
    "md.glossary.score": (
        "- 风险分（0-100）：由代码按严重级累加，不由模型给出。",
        "- Risk score (0-100): summed by code from severities, never produced by the model.",
    ),
    "md.glossary.verdict": (
        "- UNCERTAIN：证据不足时不硬判；确认必须有工具输出（E1）或仓内原文+行号（E2）。",
        "- UNCERTAIN: no forced verdict without evidence; CONFIRMED requires tool output (E1) "
        "or verbatim repo text with line numbers (E2).",
    ),
}


def t(key: str, **kwargs) -> str:
    """取双语串；带 kwargs 时按模板格式化（中文侧格式化结果须与历史 f-string 逐字节一致）。"""
    try:
        zh, en = _STRINGS[key]
    except KeyError:
        raise KeyError(f"report_lang: unknown key {key!r}") from None
    template = en if is_en() else zh
    return template.format(**kwargs) if kwargs else template

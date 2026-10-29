"""HTML 报告契约锚：自包含、全转义、只渲染已有事实、Azure 记账显式。"""
from __future__ import annotations

import json

from codeark.agents.report_agent import build_html, render_report

FINDINGS = [
    {
        "severity": "high",
        "title": "Prompt injection in system prompt file",
        "file_path": "prompts/system.txt",
        "line": 12,
        "rule": "PIT-T-51",
        "code_snippet": "ignore all previous instructions",
        "evidence": "the file overrides the reviewer",
        "attack_path": "attacker edits prompt file",
        "fix": "treat prompt files as untrusted input",
    },
    {
        "severity": "low",
        "title": "Weak guard",
        "file_path": "app/guard.py",
    },
]


def test_html_is_self_contained_and_escapes_dynamic_content():
    evil = dict(FINDINGS[0], title='<script>alert("x")</script>')
    html = build_html([evil], meta={"agent0_findings": []})

    assert html.startswith("<!doctype html>")
    assert "<script>" not in html                      # 动态内容必须转义
    assert "&lt;script&gt;alert" in html
    assert "src=" not in html and "href=\"http" not in html  # 自包含：无外部资源
    assert "<style>" in html


def test_html_renders_counts_severities_and_fields():
    html = build_html(FINDINGS, conclusion="Two issues found.", meta={
        "agent0_findings": [{"title": "x"}, {"title": "y"}],
        "hypothesis_set": {"hypotheses": [{"title": "h1"}]},
        "verifications": [{"verdict": "CONFIRMED"}, {"verdict": "UNCERTAIN"}],
        "verify_degraded": 1,
    })

    assert "Two issues found." in html
    assert "sev-high" in html and "sev-low" in html
    assert "prompts/system.txt" in html and "line 12" in html
    assert "PIT-T-51" in html
    assert "2" in html and "Findings (2)" in html
    assert "degraded verdicts" in html


def test_html_without_findings_says_so():
    html = build_html([], meta={})
    assert "No known vulnerabilities" in html


def test_html_renders_attack_chains():
    chains = [{
        "title": "Exfil via prompt",
        "preconditions": ["attacker controls prompt file"],
        "lateral_moves": ["read env"],
        "impact": "secret leak",
        "remediation": "isolate prompts",
    }]
    html = build_html(FINDINGS, attack_chains=chains, meta={})
    assert "Attack chains (1)" in html
    assert "Exfil via prompt" in html
    assert "attacker controls prompt file" in html
    assert "secret leak" in html


def test_html_azure_disabled_is_explicit():
    html = build_html([], meta={"azure": {"enabled": False,
                                          "content_safety": {"enabled": False},
                                          "language": {"enabled": False}}})
    assert "Azure gate" in html
    assert "<strong>disabled</strong>" in html


def test_html_azure_enabled_shows_coverage_and_withheld():
    html = build_html([], meta={"azure": {
        "enabled": True,
        "content_safety": {
            "enabled": True, "documents_total": 10, "documents_scanned": 7,
            "batches": 2, "attack_detected": True, "degraded": False,
            "blocked_documents": 1,
        },
        "language": {
            "enabled": True, "documents_sampled": 5, "documents_redacted": 4,
            "documents_withheld": 1, "entities_by_category": {"Email": 2},
            "degraded": True,
        },
    }})
    assert "scanned 7/10 files" in html
    assert "attack_detected=True" in html
    assert "redacted 4/5 files" in html
    assert "withheld=1" in html
    assert "Email=2" in html


def test_render_report_html_only():
    out = render_report({"findings": FINDINGS, "conclusion": "c"}, ["html"], meta={})
    assert set(out) == {"html"}
    assert "<!doctype html>" in out["html"]
    assert "Findings (2)" in out["html"]
    json.dumps({"html_len": len(out["html"])})  # 只是确保可序列化上下文无异常
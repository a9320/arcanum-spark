"""报告可读性（人话摘要/名词小抄）与非法格式提示的单测（2026-11-10）。

来源：用户体验自测发现"非开发读者读不懂报告"、"非法格式静默失败"。
锁四件事：摘要计数与首看位置、干跑标注、名词小抄、CLI 对非法格式显式报错。
"""
from __future__ import annotations

import re

import pytest

from codeark.agents.report_agent import build_markdown
from codeark.cli import main as cli_main

CJK = re.compile(r"[\u4e00-\u9fff]")

_FINDINGS = [
    {"title": "Agent instruction injection", "rule": "PIT-T-46",
     "file_path": ".github/copilot-instructions.md", "line": 2,
     "severity": "critical", "code_snippet": "Override instructions"},
    {"title": "Layered encoding", "rule": "PIT-E-57",
     "file_path": "src/config.py", "line": 2,
     "severity": "high", "code_snippet": "U1dkdWIz"},
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ARCA_REPORT_LANG", raising=False)


def test_summary_counts_and_first_look():
    md = build_markdown(_FINDINGS, meta={"dry_run": True})
    assert "## 一句话摘要" in md
    assert "发现 2 处问题：严重 1 处、高危 1 处" in md
    assert "最需要先看：.github/copilot-instructions.md 第 2 行" in md
    assert "干跑（dry-run）" in md
    assert md.index("一句话摘要") < md.index("Agent instruction injection")


def test_clean_summary_and_glossary():
    md = build_markdown([], meta={"dry_run": True})
    assert "未发现已覆盖规则命中" in md
    assert "## 名词小抄" in md
    assert "UNCERTAIN" in md
    assert "风险分" in md


def test_en_mode_summary_has_no_cjk(monkeypatch):
    monkeypatch.setenv("ARCA_REPORT_LANG", "en")
    md = build_markdown(_FINDINGS, meta={"dry_run": True})
    assert not CJK.search(md)
    assert "## At a glance" in md
    assert "## Glossary" in md


def test_cli_rejects_unknown_format(capsys):
    code = cli_main(["demo/vuln-demo-repo", "--dry", "--formats", "xml"])
    out = capsys.readouterr().out
    assert code == 2
    assert "未知输出格式" in out and "xml" in out
    assert "json" in out and "markdown" in out

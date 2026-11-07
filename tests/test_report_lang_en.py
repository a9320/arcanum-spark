"""报告语言开关契约锚 — 默认中文逐字节不变；ARCA_REPORT_LANG=en 确定性文案零 CJK。

范围边界（与 codeark/report_lang.py 披露一致）：模型实时输出与 node_errors 异常文本
不归本层；本文件只钉我方确定性产出（模板标签 / dry 与降级文案 / 兜底结论）。
"""
from __future__ import annotations

import json
import re

import pytest

from codeark.agents.arbiter_agent import _deterministic_fallback_report
from codeark.agents.report_agent import build_markdown
from codeark.graph.pipeline import CodeRiskGraph
from codeark.models.schemas import HypothesisSet

CJK = re.compile(r"[\u4e00-\u9fff]")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ARCA_REPORT_LANG", raising=False)


def _rich_markdown() -> str:
    return build_markdown(
        [{"title": "T", "file_path": "a.py", "line_start": 1, "code_snippet": "x",
          "evidence": "e", "attack_path": "ap", "remediation": "r", "severity": "high"}],
        attack_chains=[{"title": "c1", "preconditions": ["p"], "lateral_moves": ["l"],
                        "impact": "i", "remediation": "r"}],
        conclusion="done",
        meta={
            "quarantine_stats": {"files_total": 3, "files_changed": 1, "chars_removed": 7,
                                 "patterns_neutralized": 2, "changed_files": ["a.py"]},
            "deepen_failures": 2,
            "node_errors": {"scout": "boom"},
        },
    )


def test_default_markdown_byte_anchors():
    md = _rich_markdown()
    # 中文默认路径的逐字节锚（改模板必须同步更新本锚并证明等价）
    for anchor in (
        "# 漏洞扫描报告",
        "## 整体结论",
        "## 审计防护（Prompt 隔离层）",
        "- 扫描文件 3 个，其中 1 个含需消毒内容",
        "- 剥离不可见/Bidi 字符 7 个；中和注入触发词 2 处",
        "- 被消毒文件: a.py",
        "> ⚠ 深挖节点有 2 条攻击链自动推演失败，已用占位链披露（见下方对应链），需人工复核。",
        "- **scout** 失败已降级为确定性路径：`boom`",
        "- 文件: a.py",
        "- 行号: 1",
        "- 代码: `x`",
        "- 证据: e",
        "- 攻击路径: ap",
        "- 修复: r",
        "## 攻击链推演（Deepen）",
        "### 攻击链 1：c1",
        "- 前置条件:",
        "- 横向移动/影响面:",
        "- 最终影响: i",
        "- 修复建议: r",
    ):
        assert anchor in md
    assert CJK.search(md)


def test_en_markdown_zero_cjk(monkeypatch):
    monkeypatch.setenv("ARCA_REPORT_LANG", "en")
    md = _rich_markdown()
    assert not CJK.search(md)
    for anchor in ("# Vulnerability Scan Report", "## Conclusion", "- File: a.py",
                   "- Line: 1", "- Code: `x`", "### Attack chain 1: c1"):
        assert anchor in md


def test_empty_findings_lang_branch(monkeypatch):
    md_default = build_markdown([])
    assert "未发现已知漏洞。" in md_default
    monkeypatch.setenv("ARCA_REPORT_LANG", "en")
    md_en = build_markdown([])
    assert "No known vulnerabilities were found." in md_en
    assert not CJK.search(md_en)


def test_dry_copy_lang_branch(monkeypatch):
    graph = CodeRiskGraph(dry=True)
    # 默认 = 历史原文
    hs_default = graph._dry_scout({"a.py": "x"}, [
        {"file": "a.py", "type": "PIT-T-46", "title": "t", "line": 1},
    ])
    assert hs_default.coverage_notes == "dry-run：仅 agent0 PITAX 基线，未做模型补充扫描"
    assert hs_default.hypotheses[0].attack_path == "PITAX 规则确定性命中（dry-run 占位）"
    ver_default = CodeRiskGraph._dry_verify(hs_default)
    assert ver_default[0].evidence == "PITAX 规则确定性命中即视为已证实（确定性降级路径）"
    chains_default = CodeRiskGraph._dry_chains([object()])
    assert chains_default[0].impact == "PITAX 命中可能导致 AI 助手被劫持执行非授权指令"

    # en = 英文分支，零 CJK
    monkeypatch.setenv("ARCA_REPORT_LANG", "en")
    hs_en = graph._dry_scout({"a.py": "x"}, [
        {"file": "a.py", "type": "PIT-T-46", "title": "t", "line": 1},
    ])
    assert not CJK.search(hs_en.coverage_notes)
    assert not CJK.search(hs_en.hypotheses[0].attack_path)
    assert not CJK.search(hs_en.hypotheses[0].suggested_verification)
    ver_en = CodeRiskGraph._dry_verify(hs_en)
    assert not CJK.search(ver_en[0].evidence)
    chains_en = CodeRiskGraph._dry_chains([object()])
    for c in chains_en:
        assert not CJK.search(c.preconditions[0] + c.impact + c.remediation)


@pytest.mark.asyncio
async def test_dry_pipeline_reports_zero_cjk_in_en(monkeypatch):
    """dry 全链渲染：en 模式下 json/md 确定性文案零 CJK；默认模式中文锚在位。"""
    result_default = await CodeRiskGraph(dry=True).run({"a.py": "x"})
    md_default = result_default.reports["markdown"]
    assert "# 漏洞扫描报告" in md_default
    payload_default = json.loads(result_default.reports["json"])
    assert payload_default["conclusion"] == "dry-run：基线扫描完成，待真实模型合议"

    monkeypatch.setenv("ARCA_REPORT_LANG", "en")
    result_en = await CodeRiskGraph(dry=True).run({"a.py": "x"})
    for fmt in ("markdown", "json"):
        assert not CJK.search(result_en.reports[fmt]), f"{fmt} 含 CJK"
    payload_en = json.loads(result_en.reports["json"])
    assert payload_en["conclusion"].startswith("dry-run: ")


def test_fallback_conclusion_lang_branch(monkeypatch):
    out = _deterministic_fallback_report([], [], None, reason="boom")
    assert out.conclusion.startswith("[确定性兜底定稿]")
    monkeypatch.setenv("ARCA_REPORT_LANG", "en")
    out_en = _deterministic_fallback_report([], [], None, reason="boom")
    assert out_en.conclusion.startswith("[Deterministic fallback]")
    assert not CJK.search(out_en.conclusion)

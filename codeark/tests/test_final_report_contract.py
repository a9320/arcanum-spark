"""方差治理 D5 测试锚（2026-11-08，台账 T5 清单⑤/设计稿 §二 D5 实施）。

覆盖：confidence 数字型收敛（含历史双形态兼容）/ degraded_reason 分类学 /
verification_method 裸档位字面量清洗 / 驳判理由透传（schema+兜底路径）/
report 层 float 置信 severity 兜底 / 判分器按类计数 / prompt 契约锚 /
D2 缺口（严格降级透传 evidence_source，源码级断言）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codeark.agents.arbiter_agent import (
    ARBITER_SYSTEM_PROMPT,
    _deterministic_fallback_report,
)
from codeark.agents.deepen_agent import DEEPEN_SYSTEM_PROMPT
from codeark.agents.report_agent import _conf_as_sev, _sev_word
from codeark.agents.verify_agent import (
    PLAIN_JSON_CONTRACT,
    VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT,
    VERIFY_ONE_SYSTEM_PROMPT,
    _apply_governance,
    _coerce_verification,
    _degraded_reason,
    _degraded_verification,
    _normalize_verifications,
)
from codeark.models.schemas import (
    FinalReport,
    FinalReportFinding,
    FinalReportRefuted,
    VerificationResult,
)
from eval import m8_k1_score as m8


def _v(**kw) -> VerificationResult:
    base = dict(hypothesis_id="H1", hypothesis_title="t", verdict="CONFIRMED",
                confidence=0.9, evidence="e", verification_method="static scan")
    base.update(kw)
    return VerificationResult(**base)


# ── confidence 数字型收敛（台账契约类 #2）──

@pytest.mark.parametrize("raw,want", [
    ("high", 0.9), ("MEDIUM", 0.6), ("low", 0.3),
    ("0.9", 0.9), (0.75, 0.75), (1.5, 1.0), (-0.1, 0.0), ("junk", 0.5),
])
def test_confidence_numeric_coercion(raw, want):
    f = FinalReportFinding(title="t", vuln_type="x", file_path="f", confidence=raw)
    assert f.confidence == want
    r = FinalReportRefuted(title="t", confidence=raw)
    assert r.confidence == want


def test_confidence_default_and_old_archive_roundtrip():
    assert FinalReportFinding(title="t", vuln_type="x", file_path="f").confidence == 0.9
    # 旧归档 JSON（"high" 字符串）重放不炸且语义保持
    old = {"title": "t", "vuln_type": "x", "file_path": "f", "confidence": "high"}
    assert FinalReportFinding.model_validate(old).confidence == 0.9


def test_none_list_fields_coerced_to_empty():
    # D5 打磨（块 4 实测）：模型首调传 null → 就地收敛空列表，schema 重试退役
    r = FinalReport.model_validate({"findings": None, "refuted_on_intended": None})
    assert r.findings == [] and r.refuted_on_intended == []


def test_gate_runner_pins_temperature():
    # 块 4 负结果闭环：run_gate_e2e 钉 ARCA_VERIFY_TEMPERATURE=0（源码级断言）
    import inspect
    from eval import run_gate_e2e
    assert 'os.environ.setdefault("ARCA_VERIFY_TEMPERATURE", "0")' in inspect.getsource(run_gate_e2e)


# ── degraded_reason 分类学（台账契约类 #4 设计输入）──

def test_degraded_reason_sniffing():
    assert _degraded_reason("服务端 peg-native format 拒绝") == "parse"
    assert _degraded_reason("exceed_context_size_error") == "context"
    assert _degraded_reason("id 契约修复调用失败：xx") == "contract"
    assert _degraded_reason("Server disconnected after 300s") == "tool-fail"
    assert _degraded_reason("anything", "parse") == "parse"  # 显式优先
    assert _degraded_reason("anything", "bogus") == "tool-fail"  # 非法回落


def test_degraded_verification_carries_reason():
    v = _degraded_verification(type("H", (), {"id": "H2", "title": "t"})(),
                               "id 契约无工具兜底失败：缺 id")
    assert v.degraded is True and v.degraded_reason == "contract"
    assert v.verification_method == "none(degraded)"


def test_coerce_parse_failure_classified():
    from types import SimpleNamespace
    hyp = SimpleNamespace(id="H1", title="t")
    v = _coerce_verification({"verdict": "CONFIRMED"}, hyp)  # 缺必填 → 宽松路径降级
    assert v.degraded and v.degraded_reason == "parse"


# ── verification_method 裸档位字面量清洗（台账契约类 #1）──

def test_governance_rewrites_bare_tier_label():
    assert _apply_governance(_v(verification_method="E2",
                                evidence_source="repo_file")).verification_method == "repo_quote"
    assert _apply_governance(_v(verification_method="e1",
                                evidence_source="tool_result")).verification_method == "tool_scan"
    assert _apply_governance(_v(verification_method=" E3 ",
                                evidence_source=None)).verification_method == "unspecified"
    # 非裸档位的方法描述不受影响
    assert _apply_governance(_v(verification_method="static scan + quote")).verification_method == \
        "static scan + quote"


# ── 驳判理由透传（台账语义类 #6）──

def test_fallback_report_carries_refuted():
    vs = [
        _v(hypothesis_id="H1", verdict="CONFIRMED", confidence=0.95),
        _v(hypothesis_id="H2", hypothesis_title="stored XSS", verdict="REFUTED",
           confidence=0.9, evidence="spans are escaped at line 42"),
    ]
    report = _deterministic_fallback_report(vs, [], None, reason="test")
    assert len(report.refuted_on_intended) == 1
    r = report.refuted_on_intended[0]
    assert r.hypothesis_id == "H2" and "escaped" in r.reason and r.confidence == 0.9


def test_arbiter_prompt_requires_refuted_passthrough():
    assert "refuted_on_intended" in ARBITER_SYSTEM_PROMPT
    assert "禁止把已证伪假设定性当作事实" in ARBITER_SYSTEM_PROMPT


# ── report 层 float 置信 severity 兜底 ──

def test_conf_as_sev_and_sev_word():
    assert _conf_as_sev(0.95) == "high" and _conf_as_sev(0.6) == "medium"
    assert _conf_as_sev(0.3) == "low" and _conf_as_sev("high") == "high"
    assert _conf_as_sev(None) == "" and _conf_as_sev(True) == ""
    assert _sev_word({"severity": "critical", "confidence": 0.3}) == "critical"
    assert _sev_word({"confidence": 0.9}) == "high"
    assert _sev_word({}) == "medium"


# ── 判分器按类计数 ──

def test_judge_counts_degraded_by_reason():
    report = {"meta": {"hypothesis_set": {"hypotheses": [
        {"id": "H1", "vuln_type": "PIT-T-46", "title": "t"}]},
        "verifications": [
            {"hypothesis_id": "H1", "hypothesis_title": "t", "verdict": "CONFIRMED",
             "confidence": 0.9, "degraded": False},
        ]}}
    out = m8.judge_question({"challenge_id": "c1", "intended_types": ["PIT-T-46"]}, report, None)
    assert out["pipeline"]["verify_degraded_by_reason"] == {
        "contract": 0, "parse": 0, "tool-fail": 0, "context": 0}


# ── prompt 契约锚（去 E1/E2/E3 标签）──

def test_prompts_free_of_tier_labels():
    for p in (VERIFY_ONE_SYSTEM_PROMPT, VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT,
              PLAIN_JSON_CONTRACT):
        # 档位定义处不得再携带 E1/E2/E3 标签（模型照抄进 verification_method 的源头）
        assert "（E2" not in p and "（E3）" not in p and "E1/E2 证据" not in p
    assert '禁止写 "E1/E2/E3"' in VERIFY_ONE_SYSTEM_PROMPT
    assert '禁止写 "E1/E2/E3"' in VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT
    assert '禁止 "E1/E2/E3"' in PLAIN_JSON_CONTRACT


# ── deepen 字段视角分工（台账语义类 #7）──

def test_deepen_prompt_separates_lateral_from_remediation():
    assert "攻击者视角" in DEEPEN_SYSTEM_PROMPT and "修复视角" in DEEPEN_SYSTEM_PROMPT
    assert "绝不准写进" in DEEPEN_SYSTEM_PROMPT


# ── D2 缺口（源码级断言：严格降级重建透传 evidence_source）──

def test_strict_degrade_rebuild_passes_evidence_source():
    import inspect
    from codeark.agents import verify_agent as va
    src = inspect.getsource(va)
    assert "evidence_source=getattr(result, \"evidence_source\", None)" in src

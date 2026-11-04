from __future__ import annotations

import json

import pytest

from codeark.graph import pipeline as pl
from codeark.graph.gate import rerank_hypotheses
from codeark.models.schemas import (
    FinalReport,
    HypothesisSet,
    VerificationResult,
    VulnHypothesis,
)


def _hyp(hid: str, title: str, vuln_type: str, file_path: str, attack_path: str) -> VulnHypothesis:
    return VulnHypothesis(
        id=hid,
        title=title,
        vuln_type=vuln_type,
        file_path=file_path,
        line_start=1,
        line_end=1,
        code_snippet="x",
        attack_path=attack_path,
        confidence="high",
        suggested_verification="static_scan",
    )


def test_gate_protects_evidence_keep_but_echo_first_prunes_redundancy():
    hypotheses = HypothesisSet(
        hypotheses=[
            _hyp("H9", "Exfil chain", "SECRET_EXFIL", "src/config.py", "decoded payload sends keys"),
            _hyp("REDUN-1", "Encoded payload", "PIT-E-57", "src/config.py", "decoded payload sends keys"),
            _hyp("B", "ordinary semantic", "NEW", "src/new.py", "cross-file impact"),
        ],
        coverage_notes="test",
    )
    baseline = [{
        "file": "src/config.py",
        "type": "PIT-E-57",
        "pitax": {"decoded_payload": "decoded evidence"},
    }]

    result = rerank_hypotheses(hypotheses, baseline)
    ids = [h.id for h in result.hypothesis_set.hypotheses]

    assert ids[0] == "H9"
    assert ids[-1] == "REDUN-1"
    assert set(ids) == {"H9", "REDUN-1", "B"}
    assert result.metadata["protected_ids"] == ["H9"]
    assert result.metadata["echo_ids"] == ["REDUN-1"]
    assert result.metadata["pruned_ids"] == []


def test_gate_external_scores_keep_stable_ties_and_never_delete():
    hypotheses = HypothesisSet(
        hypotheses=[
            _hyp("H1", "same", "A", "a.py", "one"),
            _hyp("H2", "same", "B", "b.py", "two"),
            _hyp("H3", "same", "C", "c.py", "three"),
        ],
        coverage_notes="test",
    )
    result = rerank_hypotheses(hypotheses, scores={"H1": 0.5, "H2": 0.5, "H3": 0.5}, backend="stub")
    assert [h.id for h in result.hypothesis_set.hypotheses] == ["H1", "H2", "H3"]
    assert result.metadata["selected_ids"] == ["H1", "H2", "H3"]


@pytest.mark.asyncio
async def test_pipeline_passes_gated_copy_and_archives_both(monkeypatch):
    hypotheses = HypothesisSet(
        hypotheses=[
            _hyp("", "first", "A", "a.py", "one"),
            _hyp("", "second", "B", "b.py", "two"),
        ],
        coverage_notes="test",
    )
    verification_ids: list[str] = []
    arbiter_ids: list[str] = []

    monkeypatch.setattr(pl, "run_agent0", lambda _files: [])

    async def fake_scout(*_args, **_kwargs):
        return hypotheses

    async def fake_verify(hypothesis_set, *_args, **_kwargs):
        verification_ids.extend(h.id for h in hypothesis_set.hypotheses)
        return [VerificationResult(
            hypothesis_id=h.id,
            hypothesis_title=h.title,
            verdict="CONFIRMED",
            confidence=0.9,
            evidence="e",
            verification_method="test",
        ) for h in hypothesis_set.hypotheses]

    async def fake_deepen(*_args, **_kwargs):
        return []

    async def fake_arbiter(hypothesis_set, *_args, **_kwargs):
        arbiter_ids.extend(h.id for h in hypothesis_set.hypotheses)
        return FinalReport(findings=[], conclusion="test")

    monkeypatch.setattr(pl, "run_scout", fake_scout)
    monkeypatch.setattr(pl, "run_verify_split", fake_verify)
    monkeypatch.setattr(pl, "run_deepen", fake_deepen)
    monkeypatch.setattr(pl, "run_arbiter", fake_arbiter)
    monkeypatch.setattr(
        pl,
        "render_report",
        lambda *_args, **kwargs: {
            "json": json.dumps(kwargs.get("meta", {})),
            "sarif": {},
            "markdown": "",
        },
    )

    def gate(hypothesis_set, _baseline):
        return rerank_hypotheses(hypothesis_set, [], scores={"H1": 0.1, "H2": 0.9}, backend="test")

    result = await pl.CodeRiskGraph(model=object(), hypothesis_gate=gate).run({"a.py": "x"})

    assert verification_ids == ["H2", "H1"]
    assert arbiter_ids == ["H2", "H1"]
    assert [h.id for h in result.hypothesis_set.hypotheses] == ["H1", "H2"]
    assert [h.id for h in result.gated_hypothesis_set.hypotheses] == ["H2", "H1"]
    assert result.gate["backend"] == "test"
    report_meta = json.loads(result.reports["json"])
    assert report_meta["gate"]["ordered_ids"] == ["H2", "H1"]
    assert report_meta["hypothesis_set"]["hypotheses"][0]["id"] == "H1"
    assert report_meta["gated_hypothesis_set"]["hypotheses"][0]["id"] == "H2"


@pytest.mark.asyncio
async def test_pipeline_gate_failure_is_fail_open(monkeypatch):
    hypothesis = HypothesisSet(
        hypotheses=[_hyp("", "first", "A", "a.py", "one")],
        coverage_notes="test",
    )
    captured: list[str] = []

    monkeypatch.setattr(pl, "run_agent0", lambda _files: [])

    async def fake_scout(*_args, **_kwargs):
        return hypothesis

    async def fake_verify(hypothesis_set, *_args, **_kwargs):
        captured.extend(h.id for h in hypothesis_set.hypotheses)
        return []

    async def fake_deepen(*_args, **_kwargs):
        return []

    async def fake_arbiter(*_args, **_kwargs):
        return FinalReport(findings=[], conclusion="test")

    monkeypatch.setattr(pl, "run_scout", fake_scout)
    monkeypatch.setattr(pl, "run_verify_split", fake_verify)
    monkeypatch.setattr(pl, "run_deepen", fake_deepen)
    monkeypatch.setattr(pl, "run_arbiter", fake_arbiter)
    monkeypatch.setattr(pl, "render_report", lambda *_args, **_kwargs: {"json": "{}", "sarif": {}, "markdown": ""})

    def broken_gate(*_args):
        raise RuntimeError("gate secret=sk-test-secret")

    result = await pl.CodeRiskGraph(model=object(), hypothesis_gate=broken_gate).run({"a.py": "x"})

    assert captured == ["H1"]
    assert result.gate["fallback"] is True
    assert "sk-test-secret" not in result.gate["reason"]


# ── gate v2 structural 姿态（GATE-V2-DESIGN §6 v1.1：仅 off/structural）──


def _prune_fixture() -> HypothesisSet:
    return HypothesisSet(
        hypotheses=[_hyp("H1", "t", "PIT-E-57", "a.py", "x")],
        coverage_notes="test",
    )


def test_structural_prune_drops_echo_duplicate_degenerate_keeps_semantic():
    """echo/duplicate/degenerate 剪除，语义增量保留；元数据契约齐。"""
    hypotheses = HypothesisSet(
        hypotheses=[
            _hyp("E1", "echo row", "PIT-E-57", "src/config.py", "baseline echo"),
            _hyp("S1", "semantic", "LOGIC_ERROR", "src/new.py", "cross-file impact"),
            _hyp("D1", "semantic", "LOGIC_ERROR", "src/new.py", "cross-file impact"),  # 与 S1 同内容
            _hyp("G1", "repeat", "WEAK", "src/x.py", "a" * 200),
        ],
        coverage_notes="test",
    )
    baseline = [{"file": "src/config.py", "type": "PIT-E-57"}]

    result = rerank_hypotheses(hypotheses, baseline, prune_mode="structural")

    kept = [h.id for h in result.hypothesis_set.hypotheses]
    assert kept == ["S1"]
    assert result.metadata["prune_mode"] == "structural"
    assert result.metadata["pruned_ids"] == ["E1", "D1", "G1"]
    assert result.metadata["prune_reasons"] == {
        "E1": "echo", "D1": "duplicate", "G1": "degenerate",
    }
    assert result.metadata["kept_ids"] == result.metadata["selected_ids"] == kept
    assert result.metadata["budget"] == {
        "candidates": 4, "kept": 1, "pruned": 3, "saving_ratio": 0.75,
    }


def test_structural_never_prunes_protected_evidence():
    """I2：protected（同文件有 decoded_payload 实锤、非同键 echo）永不剪。"""
    hypotheses = HypothesisSet(
        hypotheses=[
            _hyp("P1", "evidence", "SECRET_EXFIL", "src/config.py", "decoded payload exfil"),
            _hyp("S1", "semantic", "LOGIC_ERROR", "src/new.py", "cross-file impact"),
        ],
        coverage_notes="test",
    )
    baseline = [{
        "file": "src/config.py",
        "type": "PIT-E-57",
        "pitax": {"decoded_payload": "decoded evidence"},
    }]

    result = rerank_hypotheses(hypotheses, baseline, prune_mode="structural")

    assert [h.id for h in result.hypothesis_set.hypotheses] == ["P1", "S1"]
    assert result.metadata["prune_reasons"] == {}
    assert result.metadata["protected_ids"] == ["P1"]


def test_structural_min_keep_floor_restores_earliest():
    """I5：剪到地板以下时按 index 从早到晚回补（保首）。"""
    hypotheses = HypothesisSet(
        hypotheses=[
            _hyp("E1", "echo1", "PIT-E-57", "src/config.py", "one"),
            _hyp("E2", "echo2", "PIT-E-58", "src/config.py", "two"),
            _hyp("E3", "echo3", "PIT-E-59", "src/config.py", "three"),
        ],
        coverage_notes="test",
    )
    baseline = [
        {"file": "src/config.py", "type": "PIT-E-57"},
        {"file": "src/config.py", "type": "PIT-E-58"},
        {"file": "src/config.py", "type": "PIT-E-59"},
    ]

    result = rerank_hypotheses(hypotheses, baseline, prune_mode="structural", min_keep=2)

    assert [h.id for h in result.hypothesis_set.hypotheses] == ["E1", "E2"]
    assert result.metadata["pruned_ids"] == ["E3"]


@pytest.mark.parametrize("mode", ["threshold", "cap"])
def test_shelved_prune_modes_raise_explicitly(mode):
    """§6 v1.1：threshold/cap 已搁置——显式报错，不静默回落为 off。"""
    with pytest.raises(ValueError):
        rerank_hypotheses(_prune_fixture(), [], prune_mode=mode)


def test_prune_knob_validation():
    with pytest.raises(ValueError):
        rerank_hypotheses(_prune_fixture(), [], prune_mode="structural", tau=0.5)
    with pytest.raises(ValueError):
        rerank_hypotheses(_prune_fixture(), [], prune_mode="off", max_keep=4)
    with pytest.raises(ValueError):
        rerank_hypotheses(_prune_fixture(), [], prune_mode="off", min_keep=0)


def test_pipeline_gate_invariants_defense():
    """I1/I2 防御校验：越界即抛错（调用点收口为 fallback=True）。"""
    original = HypothesisSet(
        hypotheses=[
            _hyp("H1", "a", "A", "a.py", "one"),
            _hyp("H2", "b", "B", "b.py", "two"),
        ],
        coverage_notes="test",
    )
    gated = HypothesisSet(
        hypotheses=[_hyp("H1", "a", "A", "a.py", "one")],
        coverage_notes="test",
    )
    pl.CodeRiskGraph._check_gate_invariants(original, gated, {"pruned_ids": ["H2"]})  # 合法

    with pytest.raises(ValueError, match="I1"):
        pl.CodeRiskGraph._check_gate_invariants(original, gated, {"pruned_ids": []})
    with pytest.raises(ValueError, match="I2"):
        pl.CodeRiskGraph._check_gate_invariants(
            original, gated, {"pruned_ids": ["H2"], "protected_ids": ["H2"]}
        )

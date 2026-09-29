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

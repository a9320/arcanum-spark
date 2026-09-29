from __future__ import annotations

import pytest

from codeark.graph import pipeline as pl
from codeark.models.schemas import FinalReport, HypothesisSet, VerificationResult, VulnHypothesis


@pytest.mark.asyncio
async def test_explicit_memory_service_feeds_scout_and_records_verdict(monkeypatch):
    class MemoryStub:
        def __init__(self):
            self.prompt_calls = 0
            self.records = []

        def build_insight_prompt(self):
            self.prompt_calls += 1
            return "历史模式：先验证再下结论"

        def record_verdict(self, key, verdict):
            self.records.append((key, verdict))

    memory = MemoryStub()
    hypothesis = HypothesisSet(hypotheses=[VulnHypothesis(
        title="semantic finding",
        vuln_type="SQL_INJECTION",
        file_path="src/db.py",
        line_start=1,
        line_end=1,
        code_snippet="query(user)",
        attack_path="user input reaches query",
        confidence="medium",
        suggested_verification="static_scan",
    )], coverage_notes="test")
    captured = {}

    monkeypatch.setattr(pl, "run_agent0", lambda _files: [])

    async def fake_scout(_files, model=None, prompt_files=None, agent0_findings=None,
                         fallback_model=None, memory_prompt=""):
        captured["memory_prompt"] = memory_prompt
        return hypothesis

    async def fake_verify(hypothesis_set, *_args, **_kwargs):
        h = hypothesis_set.hypotheses[0]
        return [VerificationResult(
            hypothesis_id=h.id,
            hypothesis_title=h.title,
            verdict="REFUTED",
            confidence=0.8,
            evidence="clean tool result",
            verification_method="static_scan",
        )]

    async def fake_deepen(*_args, **_kwargs):
        return []

    async def fake_arbiter(*_args, **_kwargs):
        return FinalReport(findings=[], conclusion="test")

    monkeypatch.setattr(pl, "run_scout", fake_scout)
    monkeypatch.setattr(pl, "run_verify_split", fake_verify)
    monkeypatch.setattr(pl, "run_deepen", fake_deepen)
    monkeypatch.setattr(pl, "run_arbiter", fake_arbiter)
    monkeypatch.setattr(pl, "render_report", lambda *_args, **_kwargs: {
        "json": "{}", "sarif": {}, "markdown": ""
    })

    result = await pl.CodeRiskGraph(model=object(), memory_service=memory).run({"src/db.py": "query(user)"})

    assert memory.prompt_calls == 1
    assert captured["memory_prompt"] == "历史模式：先验证再下结论"
    assert memory.records == [("SQL_INJECTION@src/db.py", "REFUTED")]
    assert result.node_errors == {}

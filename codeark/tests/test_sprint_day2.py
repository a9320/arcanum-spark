"""9/12 冲刺的确定性回归测试（任务 6/9/10/12/14）— 零 LLM 调用。

覆盖：
- schema 一致性：assign_hypothesis_ids 幂等、confidence_to_float 转换规则
- Verify 逐假设拆分：id 结构化对齐、顺序回排、invoke 异常降级 UNCERTAIN、
  预跑工具结果按文件过滤
- severity 确定性打底：LLM 降级被抬回规则底线、升级不被改动
- eval 校验器：agent0 覆盖 + 定稿底线 + 干净仓 FP=0
"""
from __future__ import annotations

import json

from codeark.agents.report_agent import apply_severity_floor
from codeark.agents.verify_agent import (
    _coerce_verification,
    _match_file,
    run_verify_split,
)
from codeark.models.schemas import (
    FinalReport,
    FinalReportFinding,
    HypothesisSet,
    VulnHypothesis,
    assign_hypothesis_ids,
    confidence_to_float,
)


# ────────────────────────── 任务 14：schema 一致性 ──────────────────────────

def _mk_hyps() -> HypothesisSet:
    return HypothesisSet(
        hypotheses=[
            VulnHypothesis(
                title=f"假设{i}", vuln_type="PIT-T-46", file_path="f.py",
                line_start=1, line_end=1, code_snippet="x",
                attack_path="p", confidence="high", suggested_verification="pitax_scan",
            )
            for i in range(1, 4)
        ],
        coverage_notes="c",
    )


def test_assign_hypothesis_ids_idempotent():
    hs = _mk_hyps()
    assign_hypothesis_ids(hs)
    assert [h.id for h in hs.hypotheses] == ["H1", "H2", "H3"]
    hs.hypotheses[0].id = ""
    assign_hypothesis_ids(hs)
    assert hs.hypotheses[0].id == "H1"          # 只补空缺，不覆盖已有
    assert hs.hypotheses[1].id == "H2"


def test_confidence_to_float_rules():
    assert confidence_to_float("high") == 0.9
    assert confidence_to_float("medium") == 0.6
    assert confidence_to_float("low") == 0.3
    assert confidence_to_float(0.75) == 0.75
    assert confidence_to_float(2) == 1.0        # 数值夹取 [0,1]
    try:
        confidence_to_float("super")
        assert False, "未知枚举应抛 ValueError"
    except ValueError:
        pass


def test_coerce_verification_enum_confidence():
    v = _coerce_verification(
        {"hypothesis_title": "t", "verdict": "CONFIRMED", "confidence": "high",
         "evidence": "e", "verification_method": "pitax_scan"},
        hyp=None,
    )
    assert v.confidence == 0.9 and v.verdict == "CONFIRMED"


# ────────────────────────── 任务 10：逐假设拆分验证 ──────────────────────────

class _FakeResult:
    def __init__(self, payload: str):
        self.structured_output = None
        self._payload = payload

    def __str__(self) -> str:
        return self._payload


class FakeAgent:
    """structured_output 缺失 → 走文本 JSON 截取回退路径；可注入异常。"""

    def __init__(self, payloads=None, exc_at=None):
        self.payloads = payloads or []
        self.exc_at = exc_at
        self.calls: list[str] = []
        self._i = 0

    async def invoke_async(self, prompt: str):
        self.calls.append(prompt)
        i = self._i
        self._i += 1
        if self.exc_at is not None and i == self.exc_at:
            raise RuntimeError("boom")
        payload = self.payloads[min(i, len(self.payloads) - 1)]
        return _FakeResult(payload)


def _verdict_json(verdict: str) -> str:
    # 模拟真实模型：不带 hypothesis_id（由 _coerce_verification 从假设对象补齐）
    return json.dumps({
        "hypothesis_title": "t", "verdict": verdict,
        "confidence": 0.8, "evidence": "工具证据", "verification_method": "pitax_scan",
    }, ensure_ascii=False)


def test_run_verify_split_id_alignment_and_order(monkeypatch):
    import codeark.agents.verify_agent as va

    files = {"src/a.py": "x = 1\n", "src/b.py": "y = 2\n"}
    hs = _mk_hyps()
    hs.hypotheses[0].file_path = "src/a.py"
    hs.hypotheses[1].file_path = "src/b.py"
    hs.hypotheses[2].file_path = "src/missing.py"   # 仓库外路径 → 全量兜底
    assign_hypothesis_ids(hs)

    fake = FakeAgent(payloads=[_verdict_json("CONFIRMED"), _verdict_json("REFUTED"),
                               _verdict_json("UNCERTAIN")])
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files: fake)
    results = _run(run_verify_split, hs, files)

    assert [r.hypothesis_id for r in results] == ["H1", "H2", "H3"]
    assert [r.verdict for r in results] == ["CONFIRMED", "REFUTED", "UNCERTAIN"]
    # 预跑结果按假设文件过滤进各自数据块
    assert "precomputed-pitax-results.json" in fake.calls[0]
    assert "<hypothesis-H1.json>" in fake.calls[0]
    assert "<hypothesis-H2.json>" in fake.calls[1]


def test_run_verify_split_invoke_failure_degrades(monkeypatch):
    import codeark.agents.verify_agent as va

    files = {"src/a.py": "x = 1\n"}
    hs = _mk_hyps()
    hs.hypotheses = hs.hypotheses[:1]
    assign_hypothesis_ids(hs)

    fake = FakeAgent(exc_at=0)
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files: fake)
    results = _run(run_verify_split, hs, files)
    assert len(results) == 1
    assert results[0].verdict == "UNCERTAIN"
    assert "降级" in results[0].evidence and "boom" in results[0].evidence


def _run(coro_fn, *args, **kwargs):
    import asyncio
    return asyncio.run(coro_fn(*args, **kwargs))


def test_match_file_separators():
    assert _match_file({"file": "src\\a.py"}, "src/a.py")
    assert _match_file({"path": "SRC/A.PY"}, "src/a.py")
    assert not _match_file({"file": "src/b.py"}, "src/a.py")
    assert not _match_file("not-a-dict", "src/a.py")


# ────────────────────────── 任务 6：severity 确定性打底 ──────────────────────────

def _agent0() -> list[dict]:
    return [
        {"file": ".cursor/rules", "type": "PIT-T-46", "severity": "critical", "line": 2},
        {"file": "src\\rewards.py", "type": "PIT-T-51", "severity": "high", "line": 4},
    ]


def test_severity_floor_blocks_llm_downgrade():
    rep = FinalReport(findings=[
        FinalReportFinding(title="t1", vuln_type="PIT-T-46", file_path=".cursor\\rules",
                           severity="medium", confidence="high"),
        FinalReportFinding(title="t2", vuln_type="PIT-T-51", file_path="src/rewards.py",
                           severity="low", confidence="high"),
    ])
    n = apply_severity_floor(rep, _agent0())
    assert n == 2
    assert rep.findings[0].severity == "critical"
    assert rep.findings[1].severity == "high"


def test_severity_floor_keeps_escalation_and_unrelated():
    rep = FinalReport(findings=[
        FinalReportFinding(title="t1", vuln_type="PIT-T-46", file_path=".cursor/rules",
                           severity="critical", confidence="high"),   # LLM 升级保持
        FinalReportFinding(title="t2", vuln_type="SQL_INJECTION", file_path="db.py",
                           severity="low", confidence="high"),        # 规则库外不造级
    ])
    n = apply_severity_floor(rep, _agent0())
    assert n == 0
    assert rep.findings[0].severity == "critical"
    assert rep.findings[1].severity == "low"


# ────────────────────────── 任务 12：eval 校验器 ──────────────────────────

def _write_report(tmp_path, payload: dict) -> "Path":
    p = tmp_path / "report.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_check_report_main_pass_and_fail(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    import check_report as cr

    expected_path = cr.Path(__file__).resolve().parents[2] / "eval" / "expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    # 合规样本直接从 expected.json 生成，保证与回归集始终一致
    agent0 = [
        {"file": r["file_path"], "type": r["rule"]}
        for r in expected["agent0_required"] for _ in range(r.get("count", 1))
    ]
    finals = [
        {"file_path": r["file_path"], "vuln_type": r["vuln_type"],
         "severity": r["min_severity"]}
        for r in expected["final_required"]
    ]
    ok = _write_report(tmp_path, {"findings": finals, "meta": {"agent0_findings": agent0}})
    assert cr.check_main(ok, expected_path) == 0

    bad_finals = finals[:-1]
    bad_finals[0] = dict(bad_finals[0], severity="low")   # 降级违反规则底线
    bad = _write_report(tmp_path, {"findings": bad_finals, "meta": {"agent0_findings": []}})
    assert cr.check_main(bad, expected_path) == 1


def test_check_report_clean_fp_zero(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    import check_report as cr

    empty = _write_report(tmp_path, {"findings": []})
    assert cr.check_clean(empty) == 0
    fp = _write_report(tmp_path, {"findings": [
        {"file_path": "src/utils.py", "vuln_type": "PIT-E-23", "severity": "low"},
    ]})
    assert cr.check_clean(fp) == 1

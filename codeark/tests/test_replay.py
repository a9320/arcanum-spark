"""eval/replay.py 单元测试 — 确定性标注 / 指标 / 日志扫描，零 LLM、零真实报告。

eval/ 不是包（无 __init__.py），按路径加载模块本体。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "replay", Path(__file__).resolve().parents[2] / "eval" / "replay.py"
)
replay = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(replay)


def _hyp(**kw):
    d = dict(id="H1", title="t", vuln_type="VX-1", file_path="src/a.py",
             line_start=1, line_end=1, code_snippet="x", attack_path="a",
             confidence="high", suggested_verification="s")
    d.update(kw)
    return d


def _base(**kw):
    d = dict(file="src/a.py", type="PIT-X-1", title="bt", severity="high",
             description="d", code_snippet="c")
    d.update(kw)
    return d


# ────────────── 确定性标注规则 ──────────────

def test_echo_exact_file_type_prunes():
    items = replay.label_items([_hyp(vuln_type="PIT-X-1")], [], [_base()])
    assert items[0]["label"]["gate"] == "PRUNE"
    assert items[0]["label"]["note"] == "echo"
    assert items[0]["heuristics"]["echo_of_baseline"]["match"] == "exact_file_type"


def test_semantic_new_file_keeps():
    items = replay.label_items([_hyp(file_path="src/other.py")], [], [_base()])
    assert items[0]["label"]["gate"] == "KEEP"
    assert items[0]["label"]["note"] == "new_file"
    assert items[0]["heuristics"]["new_file_vs_baseline"] is True


def test_evidence_backed_keep_decoded_payload():
    b = _base(type="PIT-E-57", pitax={"decoded_payload": "LEGACY=="})
    items = replay.label_items(
        [_hyp(vuln_type="EXFIL", file_path="src/a.py", attack_path="exfil channel")], [], [b])
    assert items[0]["label"]["gate"] == "KEEP"
    assert items[0]["label"]["note"] == "evidence"
    assert items[0]["heuristics"]["evidence_backed"] is True


def test_duplicate_prunes_later_copy():
    items = replay.label_items(
        [_hyp(id="H1", title="dup test", attack_path="same path here"),
         _hyp(id="H2", title="dup test", attack_path="same path here")], [], [_base()])
    assert items[1]["label"]["gate"] == "PRUNE"
    assert items[1]["label"]["note"] == "duplicate"
    assert items[1]["heuristics"]["duplicate_of"] == "H1"


def test_degenerate_repetition_prunes():
    items = replay.label_items(
        [_hyp(file_path="src/z.py", attack_path="LEGACY" * 200)], [], [_base()])
    assert items[0]["heuristics"]["degenerate"] is True
    assert items[0]["label"]["gate"] == "PRUNE"


def test_verdict_join_confirmed_keeps():
    vers = [dict(hypothesis_id="H1", verdict="CONFIRMED", confidence=0.9,
                 verification_method="m", evidence="e", hypothesis_title="t")]
    items = replay.label_items([_hyp(file_path="src/new.py")], vers, [_base()])
    assert items[0]["pipeline"]["verdict"] == "CONFIRMED"
    assert items[0]["label"]["gate"] == "KEEP"


# ────────────── triage（Scout 终验判读口径）──────────────

def test_triage_healthy_vs_echo():
    healthy = replay.label_items(
        [_hyp(id=f"H{i}", file_path=f"src/n{i}.py") for i in (1, 2, 3)], [], [_base()])
    assert any("✅" in line for line in replay.triage(healthy))
    echoey = replay.label_items([_hyp(id=f"H{i}") for i in range(1, 10)], [], [_base()])
    assert any("⚠" in line for line in replay.triage(echoey))


# ────────────── 指标 ──────────────

def test_average_precision():
    assert replay.average_precision(["KEEP", "PRUNE", "KEEP"]) == pytest.approx((1.0 + 2 / 3) / 2)
    assert replay.average_precision(["PRUNE", "PRUNE"]) == 0.0


def test_brier_and_ece():
    assert replay.brier_score([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    assert replay.brier_score([0.5, 0.5], [1, 0]) == pytest.approx(0.25)
    assert replay.expected_calibration_error([1.0, 0.0], [1, 0]) == pytest.approx(0.0)
    # 两条都落 [0.8,0.9) 桶：acc=0.5, conf=0.8 → ECE=0.3
    assert replay.expected_calibration_error([0.8, 0.8], [1, 0]) == pytest.approx(0.3)


# ────────────── 抽取 ──────────────

def test_extract_from_report_roundtrip():
    rep = {"findings": [{"file_path": "src/a.py", "vuln_type": "PIT-X-1"}],
           "meta": {"agent0_findings": [_base()],
                    "hypothesis_set": {"hypotheses": [_hyp()], "coverage_notes": "c"},
                    "verifications": []}}
    hyps, vers, base, finals = replay.extract_from_report(rep)
    assert len(hyps) == 1 and len(vers) == 0 and len(base) == 1 and len(finals) == 1


def test_extract_from_log_skips_truncated_json():
    good = json.dumps({"hypotheses": [{"id": "H1", "title": "t"}], "coverage_notes": "x"})
    text = f"[Pipeline] ok\n{good}\nnoise {{\"hypotheses\": [{{\"id\": \"H2\""
    out = replay.extract_from_log(text)
    assert out and out[0]["id"] == "H1"


def test_score_tfidf_ranks_novel_above_echo():
    baseline = [_base(file=".cursor/rules", type="PIT-T-46", title="Agent Instruction-File Injection",
                      description="指令覆盖 Ignore all previous instructions")]
    items = [
        {"id": "H1", "title": "Agent Instruction-File Injection in cursor rules",
         "vuln_type": "PIT-T-46", "file_path": ".cursor/rules"},
        {"id": "H2", "title": "quantum flux capacitor desync leak",
         "vuln_type": "NEW-1", "file_path": "src/quantum.py"},
    ]
    scores = replay.score_tfidf(items, baseline)
    assert scores[1] > scores[0]

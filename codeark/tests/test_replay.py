"""eval/replay.py 单元测试 — 确定性标注 / 指标 / 日志扫描，零 LLM、零真实报告。

eval/ 不是包（无 __init__.py），按路径加载模块本体。
"""
from __future__ import annotations

import argparse
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


# ────────────── join 兜底（join-miss 两连跑修复，2026-09-26）──────────────

def test_join_title_fallback_and_orphan():
    hyps = [_hyp(id="H1", title="dup test"), _hyp(id="H2", title="other")]
    vers = [
        {"hypothesis_id": "", "hypothesis_title": "dup test", "verdict": "CONFIRMED"},
        {"hypothesis_id": "H9", "hypothesis_title": "ghost", "verdict": "REFUTED"},
    ]
    id_join, title_join, orphans = replay.join_verdicts(hyps, vers)
    assert id_join == {}
    assert title_join["H1"]["verdict"] == "CONFIRMED"
    assert len(orphans) == 1 and orphans[0]["hypothesis_id"] == "H9"


def test_join_title_multi_candidate_abstains():
    hyps = [_hyp(id="H1", title="same"), _hyp(id="H2", title="same")]
    vers = [{"hypothesis_id": "", "hypothesis_title": "same", "verdict": "CONFIRMED"}]
    _, title_join, orphans = replay.join_verdicts(hyps, vers)
    assert title_join == {} and len(orphans) == 1


def test_join_id_wins_over_title():
    hyps = [_hyp(id="H1", title="t"), _hyp(id="H2", title="t")]
    vers = [{"hypothesis_id": "H2", "hypothesis_title": "t", "verdict": "CONFIRMED"}]
    id_join, title_join, _ = replay.join_verdicts(hyps, vers)
    assert "H2" in id_join and title_join == {}


def test_label_items_title_join_and_method():
    vers = [{"hypothesis_id": "WRONG", "hypothesis_title": "t", "verdict": "CONFIRMED"}]
    items = replay.label_items(
        [_hyp(id="H1", title="t", file_path="src/new.py")], vers, [_base()])
    assert items[0]["pipeline"]["join_method"] == "title"
    assert items[0]["pipeline"]["verdict"] == "CONFIRMED"
    assert items[0]["label"]["gate"] == "KEEP"


# ────────────── triage 口径放宽 + 合串归一化 ──────────────

def test_triage_healthy_cap_relaxed_to_6():
    six = replay.label_items(
        [_hyp(id=f"H{i}", file_path=f"src/n{i}.py") for i in range(1, 7)], [], [_base()])
    assert any("✅" in line for line in replay.triage(six))
    seven = replay.label_items(
        [_hyp(id=f"H{i}", file_path=f"src/n{i}.py") for i in range(1, 8)], [], [_base()])
    assert not any("✅" in line for line in replay.triage(seven))


def test_split_merged_paths():
    assert replay.split_merged_paths("src/a.py") == ["src/a.py"]
    assert replay.split_merged_paths(
        "src/a.py, src/b.py", known_files={"src/a.py", "src/b.py"}) == ["src/a.py", "src/b.py"]
    assert replay.split_merged_paths(
        "src/a.py, nowhere.py", known_files={"src/a.py"}) == ["src/a.py, nowhere.py"]
    assert replay.split_merged_paths("a.py;b.py") == ["a.py", "b.py"]
    assert replay.split_merged_paths("") == []


def test_cmd_build_in_final_with_merged_file_path(tmp_path):
    report = {"findings": [{"file_path": "src/a.py, src/new.py", "vuln_type": "VX-9"}],
              "meta": {"agent0_findings": [_base()],
                       "hypothesis_set": {"hypotheses": [
                           _hyp(id="H1", title="t", file_path="src/new.py", vuln_type="VX-9")],
                           "coverage_notes": "c"},
                       "verifications": []}}
    rp = tmp_path / "rep.json"
    rp.write_text(json.dumps(report), encoding="utf-8")
    assert replay.cmd_build(argparse.Namespace(report=str(rp), log=[], out=None)) == 0
    ds = json.loads((tmp_path / "gate_dataset.json").read_text(encoding="utf-8"))
    it = ds["items"][0]
    assert it["pipeline"]["in_final"] is True
    assert it["pipeline"]["join_method"] == "none"


# ────────────── 回显负样本合成器 ──────────────

def test_synth_echo_negatives_skip_payload_rows(tmp_path):
    rows = [_base(), _base(file="src/b.py", type="PIT-E-57", title="inject",
                           pitax={"decoded_payload": "AAAA"})]
    report = {"findings": [], "meta": {"agent0_findings": rows}}
    rp = tmp_path / "rep.json"
    rp.write_text(json.dumps(report), encoding="utf-8")
    assert replay.cmd_synth(argparse.Namespace(report=str(rp), into=None, out=None)) == 0
    ds = json.loads((tmp_path / "gate_dataset_echo_neg.json").read_text(encoding="utf-8"))
    assert len(ds["items"]) == 1
    it = ds["items"][0]
    assert it["id"] == "ECHO-1" and it["label"]["gate"] == "PRUNE"
    assert it["label"]["source"] == "synthetic"
    assert it["heuristics"]["echo_of_baseline"]["match"] == "synthetic"
    assert ds["baseline_rows"][1]["has_decoded_payload"] is True


def test_synth_into_merges(tmp_path):
    report = {"findings": [], "meta": {"agent0_findings": [_base()]}}
    rp = tmp_path / "rep.json"
    rp.write_text(json.dumps(report), encoding="utf-8")
    ds_path = tmp_path / "gate_dataset.json"
    ds_path.write_text(json.dumps({"schema": "gate-dataset/1", "source": {}, "items": [
        {"id": "H1", "label": {"gate": "KEEP", "source": "heuristic"}}]}), encoding="utf-8")
    assert replay.cmd_synth(argparse.Namespace(report=str(rp), into=str(ds_path), out=None)) == 0
    merged = json.loads((tmp_path / "gate_dataset_full.json").read_text(encoding="utf-8"))
    assert [i["id"] for i in merged["items"]] == ["H1", "ECHO-1"]


# ────────────── Laya 后端（stub，零依赖）──────────────

def test_laya_state_scout_stage_only():
    it = {"id": "H1", "title": "t", "vuln_type": "V", "file_path": "src/a.py",
          "attack_path": "ap", "pipeline": {"verdict": "CONFIRMED"}}
    base = [{"file": "src/a.py", "rule": "PIT-X-1", "title": "bt"}]
    s = replay._laya_state(it, base)
    assert "CONFIRMED" not in s  # 裁决是 Verify 后信息，入 state = 标签泄漏
    assert "PIT-X-1" in s and "ap" in s
    lone = replay._laya_state(it, [{"file": "src/other.py", "rule": "R", "title": "x"}])
    assert lone.endswith("- none")


def test_score_laya_with_stub(monkeypatch):
    class _StubAgent:
        def system_one(self, state, questions):
            (qid, q), = questions.items()
            assert q["type"] == "choice" and set(q["criteria"]) == {"A", "B"}
            # 官方契约：system_one 返回 {"model", "answers": {qid: {...}}, "usage"} 包装层
            return {"model": "rl-agent",
                    "answers": {qid: {"type": "choice", "choice": "A",
                                      "probabilities": {"A": 0.9, "B": 0.1}, "confidence": 0.8}},
                    "usage": {"input_tokens": 128, "output_tokens": 0}}

    monkeypatch.setattr(replay, "_load_laya_agent", lambda p: _StubAgent())
    items = [
        {"id": "H1", "title": "t1", "vuln_type": "V", "file_path": "src/a.py",
         "attack_path": "x", "label": {"gate": "KEEP", "source": "heuristic"}},
        {"id": "H2", "title": "t2", "vuln_type": "V", "file_path": "src/a.py",
         "attack_path": "y", "label": {"gate": "PRUNE", "source": "heuristic"}},
    ]
    probs, confs = replay.score_laya(items, [], "/fake/model")
    assert probs == [0.9, 0.9] and confs == [0.8, 0.8]
    assert replay.brier_score(probs, [1.0, 0.0]) == pytest.approx((0.01 + 0.81) / 2)

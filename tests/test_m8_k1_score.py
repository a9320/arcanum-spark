"""M8/K1 判分脚本单测 — 合成报告/清单，零网络。

契约（docs/M8-CTF-TRUTH.md v0）：
1. intended CONFIRMED → tp=True（fn=False）；intended REFUTED → refuted_on_intended（独立口径 FP）；
   非 intended CONFIRMED → unplanned_confirmed（不自动计 FP）；
   FN：intended 无假设或全被 PRUNE/REFUTED → True，UNCERTAIN/未验证 → null 不猜；
2. intended_types=null 或 meta 缺失 → 对应层 null（缺失=null 不猜）；
3. flag 只落 sha256 前 12 位，不原样落盘。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


m8 = _load("m8_k1_score", "eval/m8_k1_score.py")


def _report(verdicts: list[tuple[str, str, str]]) -> dict:
    hyps = [{"id": h, "vuln_type": t, "title": f"t-{h}"} for h, t, _ in verdicts]
    vers = [{"hypothesis_id": h, "hypothesis_title": f"t-{h}", "verdict": v} for h, _, v in verdicts]
    return {"meta": {"hypothesis_set": {"hypotheses": hyps}, "verifications": vers}}


_ENTRY = {"challenge_id": "web1", "category": "web", "upstream_path": "test/web1",
          "intended_types": ["PIT-T-46"]}


def test_tp_refuted_on_intended_and_unplanned(tmp_path: Path):
    report = _report([("H1", "PIT-T-46", "CONFIRMED"),   # intended 命中 → TP
                      ("H2", "PIT-T-46", "REFUTED"),     # intended 被否 → 独立口径 FP
                      ("H3", "SECRET_EXFIL", "CONFIRMED")])  # 超纲 → unplanned
    out = m8.judge_question(_ENTRY, report, None)
    assert out["judgment"]["tp"] is True
    assert [r["id"] for r in out["judgment"]["refuted_on_intended"]] == ["H2"]
    assert [r["id"] for r in out["judgment"]["unplanned_confirmed"]] == ["H3"]
    assert out["judgment"]["fn"] is False  # tp=True ⇒ 非漏报（FN 落定，外审整改）


def test_fn_true_no_intended_or_all_refuted():
    out = m8.judge_question(_ENTRY, _report([("H1", "SECRET_EXFIL", "CONFIRMED")]), None)
    assert out["judgment"]["fn"] is True  # intended 类目无假设
    out2 = m8.judge_question(_ENTRY, _report([("H1", "PIT-T-46", "REFUTED")]), None)
    assert out2["judgment"]["fn"] is True  # 全部 intended 被否
    assert [r["id"] for r in out2["judgment"]["refuted_on_intended"]] == ["H1"]


def test_fn_true_via_gate_prune():
    report = _report([("H2", "SECRET_EXFIL", "CONFIRMED")])
    report["meta"]["hypothesis_set"]["hypotheses"].append(
        {"id": "H1", "vuln_type": "PIT-T-46", "title": "t-H1"})
    report["meta"]["gated_hypothesis_set"] = {"hypotheses": [
        {"id": "H2", "vuln_type": "SECRET_EXFIL", "title": "t-H2"}]}
    out = m8.judge_question(_ENTRY, report, None)
    assert out["judgment"]["fn"] is True  # intended 假设被 gate 剪掉 = 协议口径 FN
    assert out["judgment"]["intended_status"] == {"pruned": 1}


def test_fn_null_when_intended_uncertain():
    out = m8.judge_question(_ENTRY, _report([("H1", "PIT-T-46", "UNCERTAIN")]), None)
    assert out["judgment"]["fn"] is None  # UNCERTAIN 不猜
    assert out["judgment"]["intended_status"] == {"indeterminate": 1}


def test_aggregate_counts():
    rows = [
        {"judgment": {"tp": True, "fn": False, "refuted_on_intended": [1], "unplanned_confirmed": []}},
        {"judgment": {"tp": False, "fn": True, "refuted_on_intended": [], "unplanned_confirmed": [1, 2]}},
        {"judgment": {"tp": False, "fn": None, "refuted_on_intended": [], "unplanned_confirmed": []}},
        {"judgment": None},
        {"pipeline": None},
    ]
    assert m8._aggregate(rows) == {
        "questions": 5, "judged": 3, "tp": 1, "fn": 1, "fn_indeterminate": 1,
        "refuted_on_intended": 1, "unplanned_confirmed": 2,
    }


def test_missing_intended_or_meta_gives_null(tmp_path: Path):
    entry = dict(_ENTRY, intended_types=None)
    out = m8.judge_question(entry, _report([("H1", "PIT-T-46", "CONFIRMED")]), None)
    assert out["judgment"]["tp"] is None and out["judgment"]["refuted_on_intended"] is None
    assert out["pipeline"] is not None  # 报告在、只是 intended 未定

    out2 = m8.judge_question(_ENTRY, None, None)
    assert out2["pipeline"] is None and out2["judgment"] is None

    out3 = m8.judge_question(_ENTRY, {"meta": {}}, None)
    assert out3["pipeline"] is None and out3["judgment"] is None


def test_flag_never_lands_verbatim(tmp_path: Path):
    chal = tmp_path / "test" / "web1"
    chal.mkdir(parents=True)
    (chal / "chal.flag").write_text("flag{s3cr3t_truth}\n", encoding="utf-8")
    out = m8.judge_question(_ENTRY, None, tmp_path)
    assert out["flag_present"] is True
    assert out["flag_sha256_12"] and len(out["flag_sha256_12"]) == 12
    blob = json.dumps(out)
    assert "s3cr3t_truth" not in blob and "flag{" not in blob

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
        "infra_fail": 0, "artifact_confirmed": 0,
        "tp_semantic": 0, "fn_semantic": 0, "fn_indeterminate_semantic": 0,
        "refuted_on_intended_semantic": 0,
    }


# ── v0.1：infra_fail（空跑根因标记） ──

def test_infra_fail_true_when_empty_hyps_and_node_errors():
    report = {"meta": {"hypothesis_set": {"hypotheses": []}, "verifications": [],
                       "node_errors": {"scout": "BadRequestError 400 exceed context"}}}
    out = m8.judge_question(_ENTRY, report, None)
    assert out["judgment"]["infra_fail"] is True
    assert out["judgment"]["fn"] is True  # 漏报计数语义不变，仅加根因标记


def test_infra_fail_false_when_healthy_or_nonempty():
    healthy = {"meta": {"hypothesis_set": {"hypotheses": []}, "verifications": [],
                        "node_errors": {}}}
    assert m8.judge_question(_ENTRY, healthy, None)["judgment"]["infra_fail"] is False

    produced = _report([("H1", "PIT-T-46", "CONFIRMED")])
    produced["meta"]["node_errors"] = {"deepen": "transient"}
    out = m8.judge_question(_ENTRY, produced, None)
    assert out["judgment"]["infra_fail"] is False  # 有假设 = 非空跑


# ── v0.1：artifact 剥离 ──

def _report_fp(rows: list[tuple[str, str, str, str | None]]) -> dict:
    hyps = [{"id": h, "vuln_type": t, "title": f"t-{h}",
             **({"file_path": fp} if fp else {})} for h, t, _, fp in rows]
    vers = [{"hypothesis_id": h, "hypothesis_title": f"t-{h}", "verdict": v}
            for h, _, v, _ in rows]
    return {"meta": {"hypothesis_set": {"hypotheses": hyps}, "verifications": vers}}


def test_artifact_split_from_unplanned():
    report = _report_fp([
        ("H1", "INFORMATION_DISCLOSURE", "CONFIRMED", "challenge.json"),   # artifact 落点
        ("H2", "INFORMATION_DISCLOSURE", "CONFIRMED", "routes/admins.js"),  # 真实发现
        ("H3", "INFORMATION_DISCLOSURE", "CONFIRMED", "flag"),              # artifact 落点
    ])
    out = m8.judge_question(_ENTRY, report, None)
    assert [r["id"] for r in out["judgment"]["artifact_confirmed"]] == ["H1", "H3"]
    assert [r["id"] for r in out["judgment"]["unplanned_confirmed"]] == ["H2"]
    agg = m8._aggregate([out])
    assert agg["artifact_confirmed"] == 2 and agg["unplanned_confirmed"] == 1


# ── v0.1：语义等价类口径 ──

def test_semantic_equivalence_class_tp():
    report = _report([("H1", "DESERIALIZATION_RCE", "CONFIRMED")])
    entry = dict(_ENTRY, intended_types=["DESERIALIZATION"])
    out = m8.judge_question(entry, report, None)
    assert out["judgment"]["tp"] is False            # 机制口径：词表错位
    assert out["judgment"]["fn"] is True
    assert out["judgment"]["semantic"]["tp"] is True  # 语义口径：等价类命中
    assert out["judgment"]["semantic"]["fn"] is False


def test_semantic_refuted_on_intended():
    report = _report([("H1", "TEMPLATE_INJECTION", "REFUTED")])
    entry = dict(_ENTRY, intended_types=["SSTI"])
    out = m8.judge_question(entry, report, None)
    assert out["judgment"]["refuted_on_intended"] == []            # 机制口径不匹配
    assert [r["id"] for r in out["judgment"]["semantic"]["refuted_on_intended"]] == ["H1"]
    assert out["judgment"]["semantic"]["fn"] is True


def test_weak_mapping_not_adopted():
    report = _report([("H1", "REMOTE_CODE_EXECUTION", "CONFIRMED")])
    entry = dict(_ENTRY, intended_types=["COMMAND_INJECTION"])
    out = m8.judge_question(entry, report, None)
    # RCE→CI 是弱映射，v0.1 不收：两个口径都落 unplanned
    assert out["judgment"]["semantic"]["unplanned_confirmed"][0]["id"] == "H1"
    assert out["judgment"]["semantic"]["tp"] is False


def test_semantic_null_when_intended_missing():
    entry = dict(_ENTRY, intended_types=None)
    out = m8.judge_question(entry, _report([("H1", "DESERIALIZATION_RCE", "CONFIRMED")]), None)
    assert out["judgment"]["semantic"] is None  # intended 未定 → 语义层不猜


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

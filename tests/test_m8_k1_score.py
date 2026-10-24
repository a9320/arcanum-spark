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
        # v0.7 新增三键
        "confident_refutations": 0, "confident_refutations_semantic": 0,
        "insufficient_runs": 0,
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


def test_semantic_credential_family_v02():
    # v0.2 凭证泄露族：whistleblow 案——同一 AWS 凭证发现被 K1 Muse 版打标
    # SECRET_EXPOSURE、混合臂版打标 HARDCODED_SECRET/EXPOSED_CREDENTIAL，
    # 标签跨 Scout 代不稳定 → 凭证明文暴露同族强等价（docs/K2-INTENDED-REVIEW.md）
    report = _report([("H1", "SECRET_EXPOSURE", "CONFIRMED")])
    entry = dict(_ENTRY, intended_types=["EXPOSED_CREDENTIAL"])
    out = m8.judge_question(entry, report, None)
    assert out["judgment"]["tp"] is False             # 机制口径：词面不等
    assert out["judgment"]["semantic"]["tp"] is True  # 语义口径：凭证族等价类
    report2 = _report([("H1", "HARDCODED_SECRET", "CONFIRMED")])
    entry2 = dict(_ENTRY, intended_types=["SECRET_EXPOSURE"])
    out2 = m8.judge_question(entry2, report2, None)
    assert out2["judgment"]["semantic"]["tp"] is True  # 反向同族


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


def test_type_normalization_v04_rtc_case():
    # v0.4 规范化：real-time-chat 冤案翻案——K1 版 H2 type 为自然语言复合串
    # "Remote Code Execution / Privilege Escalation"（docs/K2-INTENDED-REVIEW.md
    # 第三批），v03 机制/语义双口径原串不命中维持 FN；v0.4 斜杠分段+归一后段级
    # 精确等价命中定稿 REMOTE_CODE_EXECUTION → 两口径翻 TP。
    report = _report([("H2", "Remote Code Execution / Privilege Escalation", "CONFIRMED")])
    entry = dict(_ENTRY, intended_types=["REMOTE_CODE_EXECUTION"])
    out = m8.judge_question(entry, report, None)
    assert out["judgment"]["tp"] is True
    assert out["judgment"]["fn"] is False
    assert out["judgment"]["semantic"]["tp"] is True


def test_type_normalization_v04_no_substring():
    # 防虚翻护栏：归一只做段级精确等价，不做子串匹配——
    # "REMOTE_CODE_EXECUTION_PRIVILEGE_ESCALATION"（无斜杠的单段）不命中
    # REMOTE_CODE_EXECUTION，维持 unplanned 两口径。
    report = _report([("H1", "REMOTE_CODE_EXECUTION_PRIVILEGE_ESCALATION", "CONFIRMED")])
    entry = dict(_ENTRY, intended_types=["REMOTE_CODE_EXECUTION"])
    out = m8.judge_question(entry, report, None)
    assert out["judgment"]["tp"] is False
    assert out["judgment"]["semantic"]["tp"] is False
    assert out["judgment"]["semantic"]["unplanned_confirmed"][0]["id"] == "H1"


def test_type_normalization_v04_weak_mapping_still_not_adopted():
    # 归一不得放宽弱映射：大小写/空白变体 "remote code execution" 对
    # COMMAND_INJECTION 仍然两口径不收（与 test_weak_mapping_not_adopted 同口径）。
    report = _report([("H1", "remote code execution", "CONFIRMED")])
    entry = dict(_ENTRY, intended_types=["COMMAND_INJECTION"])
    out = m8.judge_question(entry, report, None)
    assert out["judgment"]["tp"] is False
    assert out["judgment"]["semantic"]["tp"] is False


def test_degraded_uncertain_is_distinct_from_real_uncertain():
    # 10-18 T3：invoke/契约失败的降级记录（degraded=True）与真实 UNCERTAIN
    # 同为"不猜"（fn=None），但在 intended_status 与 pipeline 计数中分列。
    report = _report([("H1", "PIT-T-46", "UNCERTAIN")])
    report["meta"]["verifications"][0]["degraded"] = True
    out = m8.judge_question(_ENTRY, report, None)
    assert out["judgment"]["fn"] is None
    assert out["judgment"]["intended_status"] == {"degraded": 1}
    assert out["pipeline"]["verify_degraded"] == 1


def test_confident_refutation_flagged_v07():
    # v0.7 P1②：intended 面 REFUTED ∧ confidence≥0.9 → confident_refutations 单列。
    report = _report([("H1", "PIT-T-46", "REFUTED")])
    report["meta"]["verifications"][0]["confidence"] = 0.95
    out = m8.judge_question(_ENTRY, report, None)
    assert out["judgment"]["confident_refutations"][0]["id"] == "H1"
    assert out["judgment"]["confident_refutations"][0]["confidence"] == 0.95
    # tp/fn 口径不变（单列不改变四元组）
    assert out["judgment"]["tp"] is False and out["judgment"]["fn"] is True
    assert m8._aggregate([out])["confident_refutations"] == 1


def test_confident_refutation_threshold_and_string_form_v07():
    # 阈值 0.9 不含 0.7；字符串形态 "0.92"（台账契约类#2 双形态）同样收。
    report = _report([("H1", "PIT-T-46", "REFUTED"), ("H2", "PIT-T-46", "REFUTED")])
    report["meta"]["verifications"][0]["confidence"] = 0.7
    report["meta"]["verifications"][1]["confidence"] = "0.92"
    out = m8.judge_question(_ENTRY, report, None)
    assert [r["id"] for r in out["judgment"]["confident_refutations"]] == ["H2"]
    # 语义口径同列（PIT-T-46 精确命中类）
    assert [r["id"] for r in out["judgment"]["semantic"]["confident_refutations"]] == ["H2"]


def test_multi_run_any_confirmed_is_tp_v07():
    # v0.7 P1①：tp=任一卷 CONFIRMED（recall 向）；卷数足时 fn=False。
    r1 = m8.judge_question(_ENTRY, _report([("H1", "PIT-T-46", "REFUTED")]), None)
    r2 = m8.judge_question(_ENTRY, _report([("H2", "PIT-T-46", "CONFIRMED")]), None)
    agg = m8._aggregate_runs([r1, r2], min_runs=2)
    assert agg["judgment"]["tp"] is True
    assert agg["judgment"]["fn"] is False
    assert agg["judgment"]["insufficient_runs"] is False


def test_multi_run_consistent_fn_true_v07():
    # 三卷全部 REFUTED（跨卷 id 不同=采样方差）→ fn=True；合并去重 3 行。
    rows = [m8.judge_question(_ENTRY, _report([(f"H{i}", "PIT-T-46", "REFUTED")]), None)
            for i in (1, 2, 3)]
    agg = m8._aggregate_runs(rows, min_runs=3)
    assert agg["judgment"]["tp"] is False
    assert agg["judgment"]["fn"] is True
    assert len(agg["judgment"]["refuted_on_intended"]) == 3
    assert agg["judgment"]["runs"] == 3 and agg["judgment"]["runs_fn_true"] == 3


def test_multi_run_disagreement_indeterminate_v07():
    # 一卷 fn=True、一卷 fn=None（UNCERTAIN）→ 分歧不猜。
    r1 = m8.judge_question(_ENTRY, _report([("H1", "PIT-T-46", "REFUTED")]), None)
    r2 = m8.judge_question(_ENTRY, _report([("H2", "PIT-T-46", "UNCERTAIN")]), None)
    agg = m8._aggregate_runs([r1, r2], min_runs=2)
    assert agg["judgment"]["tp"] is False
    assert agg["judgment"]["fn"] is None


def test_multi_run_insufficient_forced_null_v07():
    # 卷数 < min-runs → insufficient_runs=True 且 tp/fn 双口径强制 null（不进计数）。
    r1 = m8.judge_question(_ENTRY, _report([("H1", "PIT-T-46", "CONFIRMED")]), None)
    r2 = m8.judge_question(_ENTRY, _report([("H2", "PIT-T-46", "CONFIRMED")]), None)
    agg = m8._aggregate_runs([r1, r2], min_runs=3)
    assert agg["judgment"]["runs"] == 2
    assert agg["judgment"]["insufficient_runs"] is True
    assert agg["judgment"]["tp"] is None and agg["judgment"]["fn"] is None
    assert agg["judgment"]["semantic"]["tp"] is None
    assert m8._aggregate([agg])["insufficient_runs"] == 1


def test_min_runs_discovery_and_aggregation_v07(tmp_path: Path):
    # 磁盘发现：<cid>/report.json + <cid>/run2/report.json = 两卷；--min-runs 2 聚合。
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "m.json").write_text(json.dumps([_ENTRY]), encoding="utf-8")
    rdir = tmp_path / "reports"
    (rdir / "web1" / "run2").mkdir(parents=True)
    (rdir / "web1" / "report.json").write_text(
        json.dumps(_report([("H1", "PIT-T-46", "CONFIRMED")])), encoding="utf-8")
    (rdir / "web1" / "run2" / "report.json").write_text(
        json.dumps(_report([("H2", "PIT-T-46", "CONFIRMED")])), encoding="utf-8")
    out = tmp_path / "o.json"
    rc = m8.main(["--manifest", str(mdir / "m.json"), "--reports-dir", str(rdir),
                  "--min-runs", "2", "--out", str(out)])
    assert rc == 0
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert rows[0]["judgment"]["runs"] == 2
    assert rows[0]["judgment"]["tp"] is True and rows[0]["judgment"]["fn"] is False
    assert rows[0]["pipeline"]["per_run"][1]["hypotheses"] == 1


def test_semantic_superset_of_exact_v07():
    # v0.7 同案检查修复：intended 含非字母数字（PIT-T-46）时语义口径不得漏于
    # 机制口径——语义应恒为机制的超集（干净词零行为变化，脏词恢复超集）。
    report = _report([("H1", "PIT-T-46", "REFUTED")])
    report["meta"]["verifications"][0]["confidence"] = 0.9
    out = m8.judge_question(_ENTRY, report, None)
    assert out["judgment"]["refuted_on_intended"]              # 机制命中
    assert out["judgment"]["semantic"]["refuted_on_intended"]  # 语义同为超集
    assert out["judgment"]["semantic"]["confident_refutations"][0]["id"] == "H1"


def test_multi_run_fn_requires_all_runs_judged_v07():
    # 混卷（一卷无报告 → judgment=None）不得仅凭单卷 fn=True 定案：
    # len(judged)==runs 才允许 fn=True，否则 None 不猜。
    r1 = m8.judge_question(_ENTRY, _report([("H1", "PIT-T-46", "REFUTED")]), None)
    r2 = m8.judge_question(_ENTRY, None, None)
    agg = m8._aggregate_runs([r1, r2], min_runs=2)
    assert agg["judgment"]["tp"] is False
    assert agg["judgment"]["fn"] is None

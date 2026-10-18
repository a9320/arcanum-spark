"""T6 验收判据检查器单测 — 先证明能抓到 10-18 串行卷缺陷，再证明修复卷可过。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

# 用 importlib 按路径加载，避免把 eval/ 插进 sys.path（会让 score_laya 以顶层名
# 二次导入，破坏 test_finetune_export 的对象同一性断言——10-18 全量跑实证）。
_spec = importlib.util.spec_from_file_location(
    "check_verify_acceptance_under_test",
    Path(__file__).parent.parent / "eval" / "check_verify_acceptance.py",
)
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)


def _v(hid: str = "H2", verdict: str = "CONFIRMED", evidence: str = "tool output",
       method: str = "static_scan", degraded: bool = False) -> dict:
    return {
        "hypothesis_id": hid, "hypothesis_title": "t", "verdict": verdict,
        "confidence": 0.9, "evidence": evidence,
        "verification_method": method, "degraded": degraded,
    }


def _report(vers: list[dict], degraded_count: int = 0) -> dict:
    return {"meta": {"verifications": vers, "verify_degraded": degraded_count}}


def test_serial_defect_report_is_rejected():
    """10-18 串行卷实况：H2 degraded + peg-native，必须 FAIL。"""
    report = _report([_v(
        verdict="UNCERTAIN",
        evidence="[verify invoke 失败（含 1 次重试），降级人工复核] The model produced "
                 "output that does not match the expected peg-native format",
        method="none(degraded)", degraded=True,
    )])
    problems = chk.check_report(report, "H2")
    text = "\n".join(problems)
    assert "降级" in text and "peg-native" in text


def test_real_uncertain_with_substantive_evidence_passes():
    report = _report([_v(
        verdict="UNCERTAIN",
        evidence="ptax scan clean; manual analysis finds two plausible "
                 "interpretations of gunicorn SCRIPT_NAME handling, needs human review",
        method="static_scan + manual reasoning",
    )])
    assert chk.check_report(report, "H2") == []


def test_missing_id_and_missing_target_fail():
    report = _report([_v(hid="", verdict="CONFIRMED")])
    problems = chk.check_report(report, "H2")
    assert any("hypothesis_id" in p for p in problems)
    assert any("缺少目标假设" in p for p in problems)


def test_require_confirmed_rejects_uncertain():
    report = _report([_v(verdict="UNCERTAIN", evidence="x" * 80)])
    assert chk.check_report(report, "H2", require_confirmed=True)


def test_degraded_counter_must_be_zero():
    report = _report([_v()], degraded_count=1)
    assert any("verify_degraded" in p for p in chk.check_report(report, "H2"))

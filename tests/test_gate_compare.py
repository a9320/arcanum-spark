"""Gate e2e 扩仓验收对照器单测 — 零模型、零网络（合成报告夹具）。

覆盖 compare_gate_e2e 的四个契约：
1. 健康双臂（reorder-only+no-fallback+质量不降+确认覆盖）→ ACCEPT；
2. gated 副本丢假设（违反 P1）→ REJECT；
3. fallback=True（违反 P2）→ REJECT；
4. P4 确认覆盖：数量达标但基线 CONFIRMED 键未覆盖 → REJECT（外审整改）；
   verifications 缺失 → P4=null 记 missing_evidence。
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


compare = _load("gate_e2e_compare", "eval/compare_gate_e2e.py")

_BASELINE = {
    "meta": {
        "agent0_findings": [{"file": "src/app.py", "type": "PIT-E-57", "title": "baseline row"}],
        "hypothesis_set": {"hypotheses": [
            {"id": "H1", "title": "echo", "vuln_type": "PIT-E-57", "file_path": "src/app.py"},
            {"id": "H2", "title": "real", "vuln_type": "SQLI", "file_path": "src/db.py"},
        ]},
        "verifications": [
            {"hypothesis_id": "H1", "verdict": "UNCERTAIN"},
            {"hypothesis_id": "H2", "verdict": "CONFIRMED"},
        ],
    },
    "findings": [{"file": "src/db.py", "vuln_type": "SQLI"}],
}


def _arm_dir(tmp_path: Path, *, gated_ids: list[str], fallback: bool, confirmed: bool) -> Path:
    arm = tmp_path / f"arm_{'ok' if confirmed and not fallback else 'bad'}_{len(gated_ids)}"
    arm.mkdir()
    verdicts = [
        {"hypothesis_id": hid, "verdict": "CONFIRMED" if confirmed else "UNCERTAIN"}
        for hid in gated_ids
    ]
    report = {
        "meta": {
            "agent0_findings": _BASELINE["meta"]["agent0_findings"],
            "hypothesis_set": _BASELINE["meta"]["hypothesis_set"],
            "gated_hypothesis_set": {"hypotheses": [
                h for h in _BASELINE["meta"]["hypothesis_set"]["hypotheses"] if h["id"] in gated_ids
            ]},
            "gate": {"backend": "laya", "fallback": fallback, "protected_ids": ["H2"]},
            "verifications": verdicts,
        },
        "findings": [{"file": "src/db.py", "vuln_type": "SQLI"},
                     {"file": "src/db2.py", "vuln_type": "SQLI"}],
    }
    (arm / "e2e_report.json").write_text(json.dumps(report), encoding="utf-8")
    (arm / "summary.json").write_text(json.dumps({
        "backend": "laya", "verify_requests": len(gated_ids),
        "elapsed_seconds": 12.5, "node_errors": [],
        "gate": {"fallback": fallback, "protected_ids": ["H2"]},
    }), encoding="utf-8")
    return arm


def _baseline_file(tmp_path: Path) -> Path:
    path = tmp_path / "baseline_report.json"
    path.write_text(json.dumps(_BASELINE), encoding="utf-8")
    return path


def test_healthy_arms_accept(tmp_path):
    ok = _arm_dir(tmp_path, gated_ids=["H2", "H1"], fallback=False, confirmed=True)
    result = compare.compare_arms(_baseline_file(tmp_path), [ok])
    assert result["verdict"] == "ACCEPT"
    arm = result["arms"][0]
    assert all(arm["criteria"].values())
    assert arm["observations"]["confirmed_vs_baseline"] == [2, 1]


def test_gated_deletion_rejects(tmp_path):
    trimmed = _arm_dir(tmp_path, gated_ids=["H1"], fallback=False, confirmed=True)
    result = compare.compare_arms(_baseline_file(tmp_path), [trimmed])
    assert result["verdict"] == "REJECT"
    assert result["arms"][0]["criteria"]["P1_reorder_only"] is False


def test_fallback_rejects(tmp_path):
    arm = _arm_dir(tmp_path, gated_ids=["H2", "H1"], fallback=True, confirmed=True)
    result = compare.compare_arms(_baseline_file(tmp_path), [arm])
    assert result["verdict"] == "REJECT"
    assert result["arms"][0]["criteria"]["P2_no_fallback"] is False


def test_confirmed_coverage_gap_rejects(tmp_path):
    """外审整改（P4）：P1/P2/P3 全过但基线 CONFIRMED 键未被臂覆盖 → REJECT。"""
    arm = _arm_dir(tmp_path, gated_ids=["H2", "H1"], fallback=False, confirmed=True)
    report = json.loads((arm / "e2e_report.json").read_text(encoding="utf-8"))
    for v in report["meta"]["verifications"]:
        if v["hypothesis_id"] == "H2":
            v["verdict"] = "UNCERTAIN"  # 基线 CONFIRMED 的 H2 在臂上掉出确认集
    (arm / "e2e_report.json").write_text(json.dumps(report), encoding="utf-8")
    result = compare.compare_arms(_baseline_file(tmp_path), [arm])
    row = result["arms"][0]
    assert result["verdict"] == "REJECT"
    assert row["criteria"]["P3_quality_floor"] is True   # 数量地板仍过——P3 洞实锤
    assert row["criteria"]["P4_confirmed_coverage"] is False
    assert row["observations"]["baseline_confirmed_missing_in_arm"] == ["H2"]


def test_p4_null_when_verifications_absent(tmp_path):
    arm = _arm_dir(tmp_path, gated_ids=["H2", "H1"], fallback=False, confirmed=True)
    report = json.loads((arm / "e2e_report.json").read_text(encoding="utf-8"))
    del report["meta"]["verifications"]
    (arm / "e2e_report.json").write_text(json.dumps(report), encoding="utf-8")
    result = compare.compare_arms(_baseline_file(tmp_path), [arm])
    row = result["arms"][0]
    assert row["criteria"]["P4_confirmed_coverage"] is None
    assert "confirmed_coverage" in row["missing_evidence"]

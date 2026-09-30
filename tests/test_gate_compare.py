"""Gate e2e 扩仓验收对照器单测 — 零模型、零网络（合成报告夹具）。

覆盖 compare_gate_e2e 的三个契约：
1. 健康双臂（reorder-only+no-fallback+质量不降）→ ACCEPT；
2. gated 副本丢假设（违反 P1）→ REJECT；
3. fallback=True（违反 P2）→ REJECT。
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

"""Agent 行为指标回算单测（2026-11-10）——零网络。

锁三件事：①evidence 绑定率/degraded 率按条目算；②跨卷 verdict 翻转被记到翻转组合；
③REFUTED 带理由率单独统计。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "agent_behavior_metrics_under_test", ROOT / "eval" / "agent_behavior_metrics.py"
)
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)


def _write(path: Path, verifications: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"findings": [], "meta": {"verifications": verifications}}),
        encoding="utf-8",
    )


def test_rates_and_refuted_reason(tmp_path: Path) -> None:
    _write(
        tmp_path / "run-a" / "report.json",
        [
            {"hypothesis_id": "H1", "verdict": "CONFIRMED", "evidence": "工具输出"},
            {"hypothesis_id": "H2", "verdict": "UNCERTAIN", "evidence": ""},
            {"hypothesis_id": "H3", "verdict": "REFUTED", "evidence": "引文对不上"},
            {"hypothesis_id": "H4", "verdict": "REFUTED", "evidence": ""},
            {"hypothesis_id": "H5", "verdict": "CONFIRMED", "evidence": "x", "degraded": True},
        ],
    )
    stats = metrics.collect(tmp_path)
    assert stats["reports"] == 1
    assert stats["verifications"] == 5
    assert stats["evidence_bound_rate"] == 0.6
    assert stats["degraded_rate"] == 0.2
    assert stats["refuted"] == 2
    assert stats["refuted_reason_rate"] == 0.5


def test_cross_run_flip_detected(tmp_path: Path) -> None:
    _write(tmp_path / "exp" / "r1.json", [{"hypothesis_id": "H1", "verdict": "CONFIRMED", "evidence": "e"}])
    _write(tmp_path / "exp" / "r2.json", [{"hypothesis_id": "H1", "verdict": "UNCERTAIN", "evidence": "e"}])
    _write(tmp_path / "exp" / "r3.json", [{"hypothesis_id": "H1", "verdict": "CONFIRMED", "evidence": "e"}])
    stats = metrics.collect(tmp_path)
    assert stats["flip_groups"] == {"CONFIRMED|UNCERTAIN": 1}


def test_node_errors_counted(tmp_path: Path) -> None:
    path = tmp_path / "run" / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "findings": [],
                "meta": {
                    "verifications": [],
                    "node_errors": {"verify": "timeout", "deepen": "parse"},
                },
            }
        ),
        encoding="utf-8",
    )
    stats = metrics.collect(tmp_path)
    assert stats["node_errors"] == {"verify": 1, "deepen": 1}
    assert stats["verifications"] == 0

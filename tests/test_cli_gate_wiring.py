"""CLI gate 接线单测 — v1.2 FP 标定发现的接线缺口（CLI 未装配 hypothesis_gate）的回归锚。

契约：非 dry 跑必须把 build_gate_from_env 的产物传入 run_pipeline；
dry-run 不装配；模型缺失/非法 backend 降级为 (None, reason) 不失败。
运行: python -m pytest tests/test_cli_gate_wiring.py -v
"""
import argparse
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from codeark import cli as cli_mod
from codeark.cli import _build_gate


def test_dry_run_disables_gate():
    gate, meta = _build_gate(dry=True)
    assert gate is None and meta == "dry-run"


def test_deterministic_backend_arms_gate(monkeypatch):
    monkeypatch.setenv("ARCA_GATE_BACKEND", "deterministic")
    gate, meta = _build_gate(dry=False)
    assert callable(gate) and meta == "deterministic"


def test_laya_without_model_degrades(monkeypatch):
    monkeypatch.setenv("ARCA_GATE_BACKEND", "laya")
    monkeypatch.delenv("ARCA_GATE_MODEL", raising=False)
    gate, meta = _build_gate(dry=False)
    assert gate is None and "ARCA_GATE_MODEL" in meta


def test_laya_missing_dir_degrades(monkeypatch):
    monkeypatch.setenv("ARCA_GATE_BACKEND", "laya")
    monkeypatch.setenv("ARCA_GATE_MODEL", "/nonexistent/laya-checkpoint")
    gate, meta = _build_gate(dry=False)
    assert gate is None and "目录不存在" in meta


def test_invalid_backend_no_silent_fallback(monkeypatch):
    monkeypatch.setenv("ARCA_GATE_BACKEND", "bogus")
    gate, meta = _build_gate(dry=False)
    assert gate is None and "unsupported ARCA_GATE_BACKEND" in meta


class _HS:
    hypotheses = []


def _mock_result():
    return SimpleNamespace(
        risk_score=0, agent0_findings=[], hypothesis_set=_HS(), verifications=[],
        attack_chains=[], quarantine_stats={}, deepen_failures=0, node_errors={},
        reports={"json": "{}"},
    )


def _make_args(repo: Path, out: Path, dry: bool = False) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), dry=dry, out=str(out), formats="json")


def test_wiring_passes_gate_into_pipeline(tmp_path, monkeypatch):
    """端到端接线证明：非 dry 跑把 armed gate 传入 run_pipeline。"""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    captured: dict = {}

    async def fake_pipeline(files, dry=False, stage_models=None, hypothesis_gate=None):
        captured["gate"] = hypothesis_gate
        captured["stage_models"] = stage_models
        return _mock_result()

    monkeypatch.setattr(cli_mod, "run_pipeline", fake_pipeline)
    monkeypatch.setenv("ARCA_GATE_BACKEND", "deterministic")
    rc = asyncio.run(cli_mod._main(_make_args(tmp_path, tmp_path / "out")))
    assert rc == 0
    assert captured["gate"] is not None          # armed gate 真的进管线
    assert callable(captured["gate"])


def test_wiring_dry_passes_none(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    captured: dict = {}

    async def fake_pipeline(files, dry=False, stage_models=None, hypothesis_gate=None):
        captured["gate"] = hypothesis_gate
        return _mock_result()

    monkeypatch.setattr(cli_mod, "run_pipeline", fake_pipeline)
    rc = asyncio.run(cli_mod._main(_make_args(tmp_path, tmp_path / "out", dry=True)))
    assert rc == 0
    assert captured["gate"] is None              # dry-run 不装配

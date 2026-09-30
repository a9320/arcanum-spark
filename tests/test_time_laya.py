"""time_laya 冒烟单测 — stub RLAgent 走通计时+判分全链（零模型依赖）。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


time_laya = _load("time_laya", "eval/time_laya.py")

_STUB = """class RLAgent:
    def __init__(self, root):
        pass
    def system_one(self, state, questions):
        out = {"answers": {}}
        for qid in questions:
            p = 0.9 if "SECRET" in state else 0.1
            out["answers"][qid] = {"choice": "A" if p >= 0.5 else "B",
                                   "probabilities": {"A": p, "B": 1 - p}, "confidence": 0.8}
        return out
"""


def _dataset(tmp_path: Path, h1_label: str = "KEEP") -> Path:
    items = [
        {"id": "H1", "title": "secret exfil", "vuln_type": "SECRET_EXFIL", "file_path": "src/a.py",
         "attack_path": "x", "label": {"gate": h1_label}, "heuristics": {"evidence_backed": True}},
        {"id": "E1", "title": "echo row", "vuln_type": "ECHO", "file_path": "src/b.py",
         "attack_path": "y", "label": {"gate": "PRUNE"}, "heuristics": {"evidence_backed": False}},
    ]
    p = tmp_path / "ds.json"
    p.write_text(json.dumps({"items": items, "baseline_rows": []}), encoding="utf-8")
    return p


def _model(tmp_path: Path) -> Path:
    d = tmp_path / "fake-laya"
    d.mkdir()
    (d / "rl_agent_api.py").write_text(_STUB, encoding="utf-8")
    return d


def _run(tmp_path: Path, monkeypatch, h1_label: str) -> Path:
    out = tmp_path / "timing.json"
    monkeypatch.setattr(sys, "argv", [
        "time_laya.py", "--dataset", str(_dataset(tmp_path, h1_label)),
        "--model", str(_model(tmp_path)), "--out", str(out),
    ])
    assert time_laya.main() == 0
    return out


def test_healthy_run(tmp_path, monkeypatch):
    out = _run(tmp_path, monkeypatch, h1_label="KEEP")
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["summary"]["n_items"] == 2
    assert d["summary"]["accuracy@0.5"]["tp"] == 1
    assert d["summary"]["accuracy@0.5"]["tn"] == 1
    assert d["summary"]["wrong_items"] == []
    assert d["summary"]["latency_ms"]["median"] >= 0.0
    assert set(d["summary"]) >= {"AP(KEEP)", "Brier", "ECE", "latency_ms"}


def test_wrong_items_reported(tmp_path, monkeypatch):
    out = _run(tmp_path, monkeypatch, h1_label="PRUNE")  # stub 必给 H1 高 KEEP 分 → 错题
    d = json.loads(out.read_text(encoding="utf-8"))
    assert [w["id"] for w in d["summary"]["wrong_items"]] == ["H1"]
    assert d["summary"]["accuracy@0.5"]["fp"] == 1

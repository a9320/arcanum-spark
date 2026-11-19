"""advisory 探针的回归锚（零网络）：解析、预注册判档、dry-run 自检。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "eval" / "advisory_probe.py"


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location("advisory_probe", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_verdict_variants(probe):
    assert probe.parse_verdict('{"manipulative": true}') is True
    assert probe.parse_verdict('```json\n{"manipulative": false}\n```') is False
    assert probe.parse_verdict('答：{"manipulative": true}') is True
    assert probe.parse_verdict('{"manipulative": "FALSE"}') is False
    assert probe.parse_verdict("not json") is None
    assert probe.parse_verdict("") is None
    assert probe.parse_verdict('{"other": true}') is None


def _rows(recall_n: int, fp_n: int) -> list[dict]:
    rows = [{"label": "malicious", "verdict": i < recall_n} for i in range(10)]
    rows += [{"label": "benign", "verdict": i < fp_n} for i in range(10)]
    return rows


def test_preregistered_buckets(probe):
    assert probe.score(_rows(10, 1))["verdict"] == "有方向性价值"
    assert probe.score(_rows(4, 1))["verdict"] == "有方向性价值"
    assert probe.score(_rows(10, 7))["verdict"] == "无价值"
    assert probe.score(_rows(1, 0))["verdict"] == "无价值"
    assert probe.score(_rows(10, 2))["verdict"] == "灰区（不确定）"
    assert probe.score(_rows(2, 2))["verdict"] == "灰区（不确定）"


def test_dry_run_is_perfect(probe, tmp_path):
    samples = tmp_path / "s.json"
    data = {"samples": [
        {"id": f"M{i}", "label": "malicious", "paragraphs": ["x"]} for i in range(10)
    ] + [
        {"id": f"B{i}", "label": "benign", "paragraphs": ["y"]} for i in range(10)
    ]}
    samples.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "o.json"
    assert probe.main(["--samples", str(samples), "--dry-run", "--out", str(out)]) == 0
    summary = json.loads(out.read_text(encoding="utf-8"))["summary"]
    assert summary["recall_n"] == 10 and summary["fp_n"] == 0
    assert summary["verdict"] == "有方向性价值"

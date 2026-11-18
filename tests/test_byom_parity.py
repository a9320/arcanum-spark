"""BYOM 对拍骨架的回归锚（零网络：只跑 dry 形态）。

锁三件事：
  1. 解析层容错（围栏/前后自然语言/别名/大小写/对象条目）与 fail-closed；
  2. 评分层口径（recall=正例全命中、neg FP、逐例对称差、一致性按去重判）；
  3. dry 三场景的固定数字（与 WorkBuddy 预演交付逐字段一致，防后续漂移）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "eval" / "byom_parity.py"


def _load():
    spec = importlib.util.spec_from_file_location("byom_parity", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def byom():
    return _load()


def test_parse_variants(byom):
    assert byom.parse_detected('```json\n{"detected":["pit-n-06"]}\n```') == (["PIT-N-06"], True)
    assert byom.parse_detected('判定：{"findings":["PIT-E-07"]} 以上') == (["PIT-E-07"], True)
    assert byom.parse_detected('{"rules":"PIT-T-46"}') == (["PIT-T-46"], True)
    assert byom.parse_detected('{"detected":[{"type":"pit-e-23"}]}') == (["PIT-E-23"], True)


def test_parse_fail_closed(byom):
    assert byom.parse_detected("no json here") == ([], False)
    assert byom.parse_detected("") == ([], False)
    assert byom.parse_detected("[]") == ([], False)


def test_chat_url_join_idempotent(byom):
    assert byom.chat_url("https://api.deepseek.com") == "https://api.deepseek.com/chat/completions"
    assert byom.chat_url("https://dashscope.aliyuncs.com/compatible-mode/v1/") == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert byom.chat_url("https://x/v1/chat/completions") == "https://x/v1/chat/completions"


def test_consistency_uses_dedup_not_round_count(byom):
    rows = [
        {"id": "same", "kind": "pos", "all_detected": [["A"], ["A"], ["A"]],
         "model_detected": ["A"], "missing": [], "diff": [], "parse_ok": True},
        {"id": "flip", "kind": "pos", "all_detected": [["A"], ["B"]],
         "model_detected": ["B"], "missing": [], "diff": [], "parse_ok": True},
    ]
    summary = byom.score(rows)
    assert summary["consistent"] is False
    assert summary["inconsistent_cases"] == ["flip"]


def test_dry_perfect_fixed_numbers(byom, tmp_path):
    out = tmp_path / "perfect.json"
    assert byom.main(["--transport", "dry", "--profile", "perfect", "--repeat", "2",
                      "--out", str(out), "--spark-root", str(REPO)]) == 0
    summary = json.loads(out.read_text(encoding="utf-8"))["summary"]
    assert summary["cases"] == 51
    assert summary["recall"] == 1.0 and summary["recall_hit"] == 36
    assert summary["false_positives"] == 0 and summary["per_case_diff_count"] == 0
    assert summary["parse_errors"] == 0 and summary["consistent"] is True


def test_dry_degraded_fixed_numbers(byom, tmp_path):
    out = tmp_path / "degraded.json"
    assert byom.main(["--transport", "dry", "--profile", "degraded", "--repeat", "2",
                      "--out", str(out), "--spark-root", str(REPO)]) == 0
    summary = json.loads(out.read_text(encoding="utf-8"))["summary"]
    assert summary["recall"] == 0.9167 and summary["recall_hit"] == 33
    assert summary["false_positives"] == 2 and summary["per_case_diff_count"] == 5
    assert summary["consistent"] is True


def test_dry_malformed_counts_as_uncertain(byom, tmp_path):
    out = tmp_path / "malformed.json"
    assert byom.main(["--transport", "dry", "--profile", "malformed", "--repeat", "1",
                      "--out", str(out), "--spark-root", str(REPO)]) == 0
    summary = json.loads(out.read_text(encoding="utf-8"))["summary"]
    assert summary["recall"] == 0.0 and summary["parse_errors"] == 51

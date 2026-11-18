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


def test_chat_url_override_wins(byom):
    """非 OpenAI 路径（如 MiniMax 的 text/chatcompletion_v2）整段覆盖。"""
    assert byom.chat_url("", "https://api.minimax.chat/v1/text/chatcompletion_v2") == (
        "https://api.minimax.chat/v1/text/chatcompletion_v2"
    )
    assert byom.chat_url("https://x/v1", "") == "https://x/v1/chat/completions"


def test_stage_cfg_rejects_non_ascii_key(byom, monkeypatch):
    monkeypatch.setenv("ARCA_ARBITER_MODEL", "m")
    monkeypatch.setenv("ARCA_ARBITER_BASE_URL", "https://x/v1")
    monkeypatch.setenv("ARCA_ARBITER_API_KEY", "sk-abc：def")
    with pytest.raises(RuntimeError) as excinfo:
        byom.stage_cfg("arbiter")
    assert "non-ASCII" in str(excinfo.value)


def test_stage_cfg_allows_chat_url_without_base(byom, monkeypatch):
    monkeypatch.delenv("ARCA_ARBITER_BASE_URL", raising=False)
    monkeypatch.setenv("ARCA_ARBITER_CHAT_URL", "https://x/v2/chat")
    monkeypatch.setenv("ARCA_ARBITER_MODEL", "m")
    monkeypatch.setenv("ARCA_ARBITER_API_KEY", "sk-x")
    cfg = byom.stage_cfg("arbiter")
    assert cfg["chat_url"] == "https://x/v2/chat"


def test_stage_cfg_extra_json_merged(byom, monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_MODEL", "m")
    monkeypatch.setenv("ARCA_VERIFY_BASE_URL", "https://x/v1")
    monkeypatch.setenv("ARCA_VERIFY_API_KEY", "sk-x")
    monkeypatch.setenv("ARCA_VERIFY_EXTRA_JSON", '{"enable_thinking": false}')
    assert byom.stage_cfg("verify")["extra"] == {"enable_thinking": False}


def test_stage_cfg_rejects_non_object_extra(byom, monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_MODEL", "m")
    monkeypatch.setenv("ARCA_VERIFY_BASE_URL", "https://x/v1")
    monkeypatch.setenv("ARCA_VERIFY_API_KEY", "sk-x")
    monkeypatch.setenv("ARCA_VERIFY_EXTRA_JSON", "[1,2]")
    with pytest.raises(RuntimeError):
        byom.stage_cfg("verify")


def test_prompt_includes_rule_descriptions_by_default(byom):
    cases = byom.load_cases(str(REPO / "eval" / "pitax_bench" / "cases.jsonl"))
    ids = byom.rule_ids_from_cases(cases)
    system, _ = byom.build_prompt(cases[0], ids, rule_docs=True)
    assert "PIT-E-23:" in system and "zero-width" in system.lower()
    bare, _ = byom.build_prompt(cases[0], ids, rule_docs=False)
    assert "zero-width" not in bare.lower()


def test_real_reply_merges_extra_and_reports_meta(byom, monkeypatch):
    captured = {}

    class FakeResp:
        def __init__(self, body):
            self._body = body

        def getcode(self):
            return 200

        def read(self):
            return json.dumps(self._body).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode())
        return FakeResp({
            "choices": [{"message": {"content": '{"detected":["PIT-E-23"]}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    monkeypatch.setattr(byom.urllib.request, "urlopen", fake_urlopen)
    cfg = {"model": "m", "base_url": "https://x/v1", "chat_url": "", "api_key": "sk-x",
           "timeout": "5", "extra": {"enable_thinking": False, "model": "evil", "max_tokens": 1}}
    text, status, meta = byom.real_reply(cfg, "s", "u")
    assert captured["payload"]["enable_thinking"] is False   # 附加参数确实发出去了
    assert captured["payload"]["model"] == "m"               # 核心键不被覆盖
    assert captured["payload"]["max_tokens"] != 1
    assert status == 200
    assert meta["finish_reason"] == "stop"
    assert meta["usage"]["total_tokens"] == 15
    assert meta["content_len"] == len(text)

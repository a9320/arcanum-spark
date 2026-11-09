"""报告 provenance 契约测试（2026-11-09）。

锁四件事：①白名单与"未设即 null"不推断；②温度合法/非法两条路径；
③端点脱敏（去 userinfo/path/query）；④凭据零泄漏（哨兵 key 全 JSON 扫描）。
另锁 meta 透传：render_report 收到的 provenance 必须原样进 JSON。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import codeark.provenance as provenance
from codeark.agents.report_agent import render_report
from codeark.models.schemas import FinalReport
from codeark.provenance import collect_provenance

_STAGES = ("scout", "verify", "deepen", "arbiter")
_CLEAR = (
    [f"ARCA_{s.upper()}_MODEL" for s in _STAGES]
    + [f"ARCA_{s.upper()}_BASE_URL" for s in _STAGES]
    + [f"ARCA_{s.upper()}_API_KEY" for s in _STAGES]
    + [
        "ARCA_VERIFY_TEMPERATURE",
        "ARCA_VERIFY_EVIDENCE_MAX_TOKENS",
        "ARCA_VERIFY_MAX_CONCURRENCY",
        "ARCA_SCOUT_MAX_TOKENS",
        "ARCA_DEPLOYMENT",
        "ARCA_BUILD_COMMIT",
    ]
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)
    provenance._commit.cache_clear()


def test_defaults_are_null_not_guessed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    prov = collect_provenance()

    assert prov["schema"] == 1
    assert prov["deployment"] == "unset"
    assert prov["finished_at"].endswith("Z")
    assert set(prov["models"]) == set(_STAGES)
    assert all(v is None for v in prov["models"].values())
    assert all(v is None for v in prov["endpoints"].values())
    assert all(v is None for v in prov["tuning"].values())
    # 未设温度必须显式落 note（11-08 块 4 "以为钉了其实没钉"的坑）
    assert any("verify_temperature unset" in note for note in prov["notes"])


def test_temperature_set_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ARCA_VERIFY_TEMPERATURE", "0")
    prov = collect_provenance()
    assert prov["tuning"]["verify_temperature"] == 0.0
    assert not any("verify_temperature" in note for note in prov["notes"])

    monkeypatch.setenv("ARCA_VERIFY_TEMPERATURE", "abc")
    prov = collect_provenance()
    assert prov["tuning"]["verify_temperature"] is None
    assert any("verify_temperature invalid" in note for note in prov["notes"])
    # 非法值不得回显原始字符串
    assert "abc" not in json.dumps(prov, ensure_ascii=False)


def test_endpoint_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("ARCA_VERIFY_BASE_URL", "https://user:tok@api.example.com:8443/v1?key=1")
    prov = collect_provenance()
    assert prov["endpoints"]["verify"] == "https://api.example.com:8443"
    blob = json.dumps(prov, ensure_ascii=False)
    assert "user:tok@" not in blob and "tok@" not in blob and "key=1" not in blob


def test_no_api_key_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    sentinel = "sk-SENTINEL-DO-NOT-LEAK-123456"
    monkeypatch.setenv("ARCA_VERIFY_API_KEY", sentinel)
    monkeypatch.setenv("ARCA_VERIFY_MODEL", "gpt-oss-verify")
    blob = json.dumps(collect_provenance(), ensure_ascii=False)
    assert sentinel not in blob
    assert "gpt-oss-verify" in blob  # 白名单键正常入册


def test_timestamps_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    start = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    prov = collect_provenance(started_at=start, finished_at=start + timedelta(minutes=26))
    assert prov["started_at"] == "2026-11-09T12:00:00Z"
    assert prov["finished_at"] == "2026-11-09T12:26:00Z"


def test_render_report_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    prov = collect_provenance()
    reports = render_report(FinalReport(findings=[]), ["json"], meta={"provenance": prov})
    payload = json.loads(reports["json"])
    assert payload["meta"]["provenance"]["schema"] == 1

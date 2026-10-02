"""gate_factory 单元测试 — 生产挂载策略（env 旋钮/降级），零 LLM、零模型加载。"""
from __future__ import annotations

import pytest

from codeark.graph.gate_factory import (
    baseline_rows_from_agent0,
    build_gate_from_env,
    make_laya_gate,
    resolve_backend,
)
from codeark.models.schemas import HypothesisSet, VulnHypothesis


def _hyp(hid: str, title: str, vuln_type: str, file_path: str, attack_path: str) -> VulnHypothesis:
    return VulnHypothesis(
        id=hid,
        title=title,
        vuln_type=vuln_type,
        file_path=file_path,
        line_start=1,
        line_end=1,
        code_snippet="x",
        attack_path=attack_path,
        confidence="high",
        suggested_verification="static_scan",
    )


def _fixture_set() -> HypothesisSet:
    return HypothesisSet(
        hypotheses=[
            _hyp("H9", "Exfil chain", "SECRET_EXFIL", "src/config.py", "decoded payload sends keys"),
            _hyp("REDUN-1", "Encoded payload", "PIT-E-57", "src/config.py", "decoded payload sends keys"),
        ],
        coverage_notes="test",
    )


def _clear_gate_env(monkeypatch):
    monkeypatch.delenv("ARCA_GATE_BACKEND", raising=False)
    monkeypatch.delenv("ARCA_GATE_MODEL", raising=False)


def test_resolve_backend_defaults_aliases_and_explicit_priority():
    assert resolve_backend(None, None) == "laya"
    assert resolve_backend(None, "") == "laya"
    assert resolve_backend(None, " det ") == "deterministic"
    assert resolve_backend("deterministic", "laya") == "deterministic"
    with pytest.raises(ValueError):
        resolve_backend(None, "yolo")


def test_build_gate_from_env_det_usable_end_to_end(monkeypatch):
    _clear_gate_env(monkeypatch)
    monkeypatch.setenv("ARCA_GATE_BACKEND", "deterministic")
    gate, meta = build_gate_from_env()
    assert gate is not None and gate.__name__ == "deterministic_gate"
    assert meta == "deterministic"

    result = gate(_fixture_set(), [{
        "file": "src/config.py",
        "type": "PIT-E-57",
        "pitax": {"decoded_payload": "decoded evidence"},
    }])
    ids = [h.id for h in result.hypothesis_set.hypotheses]
    assert ids == ["H9", "REDUN-1"]
    assert result.metadata["protected_ids"] == ["H9"]
    assert result.metadata["echo_ids"] == ["REDUN-1"]
    assert result.metadata["pruned_ids"] == []


def test_build_gate_from_env_default_laya_mounts_with_model(monkeypatch, tmp_path):
    _clear_gate_env(monkeypatch)
    monkeypatch.setenv("ARCA_GATE_MODEL", str(tmp_path))  # 目录存在即可构造，不加载权重
    gate, meta = build_gate_from_env()
    assert gate is not None and gate.__name__ == "laya_gate"
    assert meta == f"laya:{tmp_path}"


def test_build_gate_from_env_missing_model_degrades(monkeypatch):
    _clear_gate_env(monkeypatch)
    gate, meta = build_gate_from_env()
    assert gate is None
    assert "ARCA_GATE_MODEL" in meta


def test_build_gate_from_env_model_dir_missing_degrades(monkeypatch, tmp_path):
    _clear_gate_env(monkeypatch)
    monkeypatch.setenv("ARCA_GATE_MODEL", str(tmp_path / "nope"))
    gate, meta = build_gate_from_env()
    assert gate is None
    assert "不存在" in meta


def test_build_gate_from_env_unsupported_value_degrades_not_silent(monkeypatch):
    _clear_gate_env(monkeypatch)
    monkeypatch.setenv("ARCA_GATE_BACKEND", "yolo")
    gate, meta = build_gate_from_env()
    assert gate is None
    assert "yolo" in meta


def test_make_laya_gate_requires_model_path():
    with pytest.raises(ValueError):
        make_laya_gate("")


def test_baseline_rows_from_agent0_maps_aliases():
    rows = baseline_rows_from_agent0([
        {"file": "a.py", "type": "T1", "title": "t1"},
        {"file_path": "b.py", "vuln_type": "T2", "title": "t2"},
        "not-a-dict",
        None,
    ])
    assert rows == [
        {"file": "a.py", "rule": "T1", "title": "t1"},
        {"file": "b.py", "rule": "T2", "title": "t2"},
    ]
    assert baseline_rows_from_agent0(None) == []

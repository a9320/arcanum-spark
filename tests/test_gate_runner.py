"""Gate v1 e2e 验收 runner 单测 — 零模型、零网络（stub score_laya）。

覆盖 make_laya_gate 的三个契约：
1. agent0 findings → replay 基线行转换（type→rule，_laya_state 可读）；
2. 模型分经 scores map 进入重排，确定性保护仍叠加（非 echo 证据优先 / echo 沉底）；
3. 只重排副本，原始 HypothesisSet 顺序不被修改。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from codeark.models.schemas import HypothesisSet, VulnHypothesis

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = _load("gate_e2e_runner", "eval/run_gate_e2e.py")
import replay  # noqa: E402  # runner 加载时已把 eval/ 插入 sys.path → 同一模块实例


def _hs() -> HypothesisSet:
    def hyp(hid: str, vtype: str, fpath: str, apath: str) -> VulnHypothesis:
        return VulnHypothesis(
            id=hid, title=f"t-{hid}", vuln_type=vtype, file_path=fpath,
            line_start=1, line_end=1, code_snippet="x", attack_path=apath,
            confidence="high", suggested_verification="static_scan",
        )

    # H1=echo（基线 file+type 同 key）、H2=同文件非 echo 证据型、H3=新文件语义
    return HypothesisSet(hypotheses=[
        hyp("H1", "PIT-E-57", "src/config.py", "echoes baseline row"),
        hyp("H2", "SECRET_EXFIL", "src/config.py", "decoded payload exfiltrates keys"),
        hyp("H3", "NEW_TYPE", "src/other.py", "novel semantic increment"),
    ], coverage_notes="test")


_BASELINE = [{"file": "src/config.py", "type": "PIT-E-57", "title": "encoded payload",
              "pitax": {"decoded_payload": "X"}}]


def test_make_laya_gate_converts_baseline_and_applies_scores(monkeypatch):
    captured: dict = {}

    def fake_score_laya(items, baseline, model_path):
        captured.update(items=items, baseline=baseline, model=model_path)
        return [0.1, 0.2, 0.3], [0.5, 0.5, 0.5]

    monkeypatch.setattr(replay, "score_laya", fake_score_laya)

    gate = runner.make_laya_gate("/fake/laya-r3")
    result = gate(_hs(), _BASELINE)

    assert captured["model"] == "/fake/laya-r3"
    assert captured["baseline"][0]["rule"] == "PIT-E-57"  # type→rule：_laya_state 可读
    assert [it["id"] for it in captured["items"]] == ["H1", "H2", "H3"]
    ids = [h.id for h in result.hypothesis_set.hypotheses]
    assert ids[0] == "H2" and ids[-1] == "H1"  # 保护叠加模型分：证据优先，echo 沉底
    assert result.metadata["backend"] == "laya"
    assert result.metadata["protected_ids"] == ["H2"]
    assert set(result.metadata["scores"]) == {"H1", "H2", "H3"}


def test_gate_returns_copy_and_original_set_untouched():
    hs = _hs()
    gate = runner.make_deterministic_gate()
    result = gate(hs, _BASELINE)

    assert [h.id for h in hs.hypotheses] == ["H1", "H2", "H3"]  # 原始集不动
    assert result.metadata["backend"] == "deterministic"
    assert sorted(h.id for h in result.hypothesis_set.hypotheses) == ["H1", "H2", "H3"]


def test_make_laya_gate_requires_model_path():
    try:
        runner.make_laya_gate("")
    except ValueError as exc:
        assert "--model" in str(exc)
    else:
        raise AssertionError("empty model path must be rejected")

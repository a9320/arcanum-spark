"""gate v1.2 钉假设集 + 挂载旋钮单测 — 零模型、零网络。

覆盖三个契约：
1. CodeRiskGraph.run(pinned_hypothesis_set=...) 跳过 Scout、dict 经
   HypothesisSet.model_validate 复原、hypothesis_source 落 meta；
2. load_pinned_hypotheses 从 baseline 报告 meta 恢复假设集（缺失/损坏显式报错）；
3. resolve_backend：--backend 显式优先，ARCA_GATE_BACKEND 缺省 laya=挂默认，
   非法值报错（挂载旋钮必须显式可判）。
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from codeark.graph.pipeline import CodeRiskGraph
from codeark.models.schemas import HypothesisSet, VulnHypothesis

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runner = _load("gate_e2e_runner", "eval/run_gate_e2e.py")


def _hs() -> HypothesisSet:
    return HypothesisSet(
        hypotheses=[
            VulnHypothesis(
                id="H1", title="t1", vuln_type="PIT-E-57", file_path="src/config.py",
                line_start=1, line_end=1, code_snippet="x", attack_path="layered encoding",
                confidence="high", suggested_verification="static_scan",
            ),
            VulnHypothesis(
                id="H2", title="t2", vuln_type="SECRET_EXFIL", file_path="src/net.py",
                line_start=2, line_end=2, code_snippet="y", attack_path="exfil keys",
                confidence="medium", suggested_verification="static_scan",
            ),
        ],
        coverage_notes="pinned fixture",
    )


def test_run_pinned_hypotheses_skip_scout_and_keep_ids():
    files = {"src/config.py": "value = 1\n"}

    async def _go():
        graph = CodeRiskGraph(dry=True)
        return await graph.run(files, pinned_hypothesis_set=_hs())

    result = asyncio.run(_go())
    assert result.hypothesis_source == "pinned"
    assert [h.id for h in result.hypothesis_set.hypotheses] == ["H1", "H2"]
    assert result.hypothesis_set.coverage_notes == "pinned fixture"
    assert result.to_dict()["hypothesis_source"] == "pinned"


def test_run_pinned_dict_is_validated_into_schema():
    files = {"src/config.py": "value = 1\n"}
    pinned_dict = _hs().model_dump()

    async def _go():
        graph = CodeRiskGraph(dry=True)
        return await graph.run(files, pinned_hypothesis_set=pinned_dict)

    result = asyncio.run(_go())
    assert isinstance(result.hypothesis_set, HypothesisSet)
    assert len(result.hypothesis_set.hypotheses) == 2
    assert result.hypothesis_source == "pinned"


def test_load_pinned_hypotheses_extracts_meta(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"meta": {"hypothesis_set": _hs().model_dump()}}), encoding="utf-8"
    )
    hs = runner.load_pinned_hypotheses(str(report))
    assert [h["id"] for h in hs["hypotheses"]] == ["H1", "H2"]

    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        runner.load_pinned_hypotheses(str(broken))

    with pytest.raises(FileNotFoundError):
        runner.load_pinned_hypotheses(str(tmp_path / "nope.json"))


def test_resolve_backend_explicit_wins_env_defaults_to_laya():
    assert runner.resolve_backend("deterministic", "laya") == "deterministic"
    assert runner.resolve_backend(None, "") == "laya"
    assert runner.resolve_backend(None, None) == "laya"
    assert runner.resolve_backend(None, " det ") == "deterministic"
    with pytest.raises(ValueError):
        runner.resolve_backend(None, "yolo")

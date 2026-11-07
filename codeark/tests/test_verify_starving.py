"""方差治理 D3 测试锚（2026-11-07，设计稿 docs/VERDICT-VARIANCE-GOVERNANCE.md §二 D3）。

D3：证据包健康度统计（pack_tokens / 点名覆盖率 / 包宽率）+ 饥饿判定回填
（双触发：点名覆盖率 < ARCA_VERIFY_STARVING_COVERAGE 默认 1.0，或
包宽率 < ARCA_VERIFY_STARVING_MIN_FRACTION 默认 0.5；阈值 0=关闸）。
关键回归点：minpack（budget=1）下点名文件被 force 进包、点名覆盖率恒 1.0，
饥饿必须由包宽率点亮（4c 机理盲区补刀）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codeark.agents.verify_agent import (
    _apply_governance,
    _pack_health,
    _stamp_pack_health,
    _starving_thresholds,
)
from codeark.models.schemas import VerificationResult

# "A"*400 → ASCII 4 字符/token = 100 tokens；全仓 3×100 = 300
FILES = {
    "src/app.py": "A" * 400,
    "src/util.py": "B" * 400,
    "README.md": "C" * 400,
}


def _hyp(fp="src/app.py", attack_path="", suggested_verification=""):
    return SimpleNamespace(
        id="H1", title="t", file_path=fp,
        attack_path=attack_path, suggested_verification=suggested_verification,
    )


def _result(**kw) -> VerificationResult:
    base = dict(hypothesis_id="H1", hypothesis_title="t", verdict="CONFIRMED",
                confidence=0.9, evidence="e", verification_method="E2")
    base.update(kw)
    return VerificationResult(**base)


@pytest.fixture(autouse=True)
def _clean_starving_env(monkeypatch):
    for name in ("ARCA_VERIFY_STARVING_COVERAGE", "ARCA_VERIFY_STARVING_MIN_FRACTION"):
        monkeypatch.delenv(name, raising=False)


# ── 阈值 ──

def test_thresholds_default_and_env_and_invalid(monkeypatch):
    assert _starving_thresholds() == (1.0, 0.5)
    monkeypatch.setenv("ARCA_VERIFY_STARVING_COVERAGE", "0.8")
    monkeypatch.setenv("ARCA_VERIFY_STARVING_MIN_FRACTION", "0")
    assert _starving_thresholds() == (0.8, 0.0)
    monkeypatch.setenv("ARCA_VERIFY_STARVING_COVERAGE", "junk")
    assert _starving_thresholds() == (1.0, 0.0)  # 非法值回退默认，另一闸保持


# ── _pack_health 统计 ──

def test_health_full_pack_both_rates_one():
    tokens, coverage, fraction = _pack_health(FILES, _hyp(), "src/app.py", dict(FILES))
    assert tokens == 300 and coverage == 1.0 and fraction == 1.0


def test_health_named_dropped_coverage_below_one():
    # 点名 src/util.py 但包里只有 app.py + README（coverage=1/2；fraction=200/300）
    pack = {"src/app.py": FILES["src/app.py"], "README.md": FILES["README.md"]}
    tokens, coverage, fraction = _pack_health(
        FILES, _hyp(attack_path="see src/util.py"), "src/app.py", pack)
    assert tokens == 200
    assert coverage == 0.5
    assert abs(fraction - 200 / 300) < 1e-9


def test_health_hallucinated_fp_full_pack():
    tokens, coverage, fraction = _pack_health(
        FILES, _hyp(fp="nope/ghost.py"), "nope/ghost.py", dict(FILES))
    assert tokens == 300 and coverage == 1.0 and fraction == 1.0


def test_health_minpack_shape_coverage_blind_fraction_lights():
    # minpack 形（budget=1）：包=仅被 force 的 hyp 文件；无 hint 点名 ⇒ coverage 恒 1.0
    pack = {"src/app.py": FILES["src/app.py"]}
    tokens, coverage, fraction = _pack_health(FILES, _hyp(), "src/app.py", pack)
    assert coverage == 1.0  # 盲区实锤
    assert tokens == 100
    assert abs(fraction - 100 / 300) < 1e-9  # < 0.5 默认阈值 ⇒ 饥饿由包宽率点亮


# ── _stamp_pack_health 回填 ──

def test_stamp_minpack_starving_by_fraction():
    pack = {"src/app.py": FILES["src/app.py"]}
    out = _stamp_pack_health(_result(), FILES, _hyp(), "src/app.py", pack)
    assert out.starving is True
    assert out.pack_tokens == 100
    assert out.pack_coverage == 1.0
    assert abs(out.pack_fraction - 0.3333) < 1e-3


def test_stamp_full_pack_clean():
    out = _stamp_pack_health(_result(), FILES, _hyp(), "src/app.py", dict(FILES))
    assert out.starving is False
    assert out.pack_tokens == 300
    assert out.pack_coverage == 1.0 and out.pack_fraction == 1.0


def test_stamp_starving_by_coverage_with_fraction_above_threshold():
    # 隔离覆盖率触发：fraction=200/300 ≥ 0.5 不触发，coverage=0.5 < 1.0 触发
    pack = {"src/app.py": FILES["src/app.py"], "README.md": FILES["README.md"]}
    out = _stamp_pack_health(
        _result(), FILES, _hyp(attack_path="see src/util.py"), "src/app.py", pack)
    assert out.starving is True
    assert out.pack_coverage == 0.5


def test_stamp_env_zero_disables_but_stats_remain(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_STARVING_COVERAGE", "0")
    monkeypatch.setenv("ARCA_VERIFY_STARVING_MIN_FRACTION", "0")
    pack = {"src/app.py": FILES["src/app.py"]}
    out = _stamp_pack_health(_result(), FILES, _hyp(), "src/app.py", pack)
    assert out.starving is False  # 双闸全关
    assert out.pack_tokens == 100 and out.pack_coverage == 1.0  # 统计照常回填


def test_stamp_preserves_verdict_fields():
    src = _result(verdict="REFUTED", confidence=0.3, evidence_source="repo_file")
    out = _stamp_pack_health(src, FILES, _hyp(), "src/app.py", dict(FILES))
    assert out.verdict == "REFUTED" and out.confidence == 0.3
    assert out.evidence_source == "repo_file"
    assert out.hypothesis_id == "H1" and out.evidence == "e"


# ── 治理清零（模型不得产出）──

def test_governance_zeroes_model_produced_d3_fields():
    v = _apply_governance(_result(
        starving=True, pack_tokens=99, pack_coverage=0.1, pack_fraction=0.1))
    assert v.starving is False
    assert v.pack_tokens == 0
    assert v.pack_coverage == 1.0
    assert v.pack_fraction == 1.0

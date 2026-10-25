"""方差治理 D1/D2 测试锚（2026-10-25，设计稿 docs/VERDICT-VARIANCE-GOVERNANCE.md 实施记录）。

D1：confidence 五档 snap（0.95/0.9/0.75/0.5/0.3；平手取更靠近 0.5 的锚；
越界夹取 [0.3, 0.95]；ARCA_VERIFY_CONFIDENCE_ANCHORS=0 关闸）。
D2：evidence_source 四值清洗（junk→None）+ partial_grounding 派生
（CONFIRMED ∧ library_knowledge → True）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codeark.agents.verify_agent import (
    VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT,
    VERIFY_ONE_SYSTEM_PROMPT,
    PLAIN_JSON_CONTRACT,
    _apply_governance,
    _coerce_verification,
    _normalize_verifications,
    snap_confidence,
)
from codeark.models.schemas import VerificationResult


# ── D1 snap ──

def test_snap_anchor_values_fixed() -> None:
    for a in (0.95, 0.9, 0.75, 0.5, 0.3):
        assert snap_confidence(a) == a


def test_snap_tie_prefers_anchor_near_half() -> None:
    # 拍板规则：平手取更靠近 0.5 的锚（0.4 恰为 0.3/0.5 中点 → 0.5，防污染饥饿档）
    assert snap_confidence(0.4) == 0.5
    assert snap_confidence(0.625) == 0.5  # 0.5/0.75 中点 → 0.5
    assert snap_confidence(0.825) == 0.75  # 0.75/0.9 中点 → 更靠近 0.5 的 0.75


def test_snap_clamp_and_nearest() -> None:
    assert snap_confidence(1.0) == 0.95
    assert snap_confidence(0.1) == 0.3
    assert snap_confidence(0.85) == 0.9
    assert snap_confidence(0.8) == 0.75
    assert snap_confidence(0.62) == 0.5
    assert snap_confidence(0.44) == 0.5
    assert snap_confidence(0.35) == 0.3


def test_governance_env_off_disables_snap(monkeypatch) -> None:
    v = VerificationResult(hypothesis_title="t", verdict="CONFIRMED", confidence=0.6,
                           evidence="e", verification_method="m")
    monkeypatch.setenv("ARCA_VERIFY_CONFIDENCE_ANCHORS", "0")
    assert _apply_governance(v).confidence == 0.6
    monkeypatch.setenv("ARCA_VERIFY_CONFIDENCE_ANCHORS", "1")
    assert _apply_governance(v).confidence == 0.5  # 0.6 → 最近锚 0.5


# ── D2 溯源 ──

def test_evidence_source_sanitized() -> None:
    v = VerificationResult(hypothesis_title="t", verdict="CONFIRMED", confidence=0.9,
                           evidence="e", verification_method="m", evidence_source="LIBRARY_KNOWLEDGE")
    g = _apply_governance(v)
    assert g.evidence_source == "library_knowledge"  # 大小写归一
    v2 = VerificationResult(hypothesis_title="t", verdict="CONFIRMED", confidence=0.9,
                            evidence="e", verification_method="m", evidence_source="junk-guess")
    assert _apply_governance(v2).evidence_source is None  # junk → None（不炸校验）
    v3 = VerificationResult(hypothesis_title="t", verdict="CONFIRMED", confidence=0.9,
                            evidence="e", verification_method="m")
    assert _apply_governance(v3).evidence_source is None  # 缺省 → None（不编造）


def test_partial_grounding_derivation() -> None:
    def _mk(verdict: str, src: str | None) -> VerificationResult:
        return VerificationResult(hypothesis_title="t", verdict=verdict, confidence=0.9,
                                  evidence="e", verification_method="m", evidence_source=src)

    assert _apply_governance(_mk("CONFIRMED", "library_knowledge")).partial_grounding is True
    assert _apply_governance(_mk("CONFIRMED", "repo_file")).partial_grounding is False
    assert _apply_governance(_mk("UNCERTAIN", "library_knowledge")).partial_grounding is False


# ── 双收口点贯通 ──

def test_coerce_path_governed() -> None:
    v = _coerce_verification(
        {"hypothesis_title": "t", "verdict": "CONFIRMED", "confidence": 0.4,
         "evidence": "e", "verification_method": "m", "evidence_source": "library_knowledge"},
        hyp=None,
    )
    assert v.confidence == 0.5 and v.partial_grounding is True  # 平手规则实弹


def test_normalize_structured_path_governed() -> None:
    vs = _normalize_verifications([
        {"hypothesis_title": "t", "verdict": "CONFIRMED", "confidence": 0.8,
         "evidence": "e", "verification_method": "m", "evidence_source": "repo_file"},
    ])
    assert vs[0].confidence == 0.75 and vs[0].partial_grounding is False


# ── prompt 契约锚 ──

def test_prompt_anchors_present() -> None:
    assert "0.75 = 部分仓内证据" in VERIFY_ONE_SYSTEM_PROMPT
    assert "evidence_source" in VERIFY_ONE_SYSTEM_PROMPT
    assert "0.95/0.9/0.75/0.5/0.3" in VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT
    assert "evidence_source" in VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT
    assert "0.95/0.9/0.75/0.5/0.3" in PLAIN_JSON_CONTRACT
    assert "evidence_source" in PLAIN_JSON_CONTRACT

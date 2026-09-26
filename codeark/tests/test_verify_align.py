"""verify_agent id 对齐收口单测 — join-miss 管线侧根因（2026-09-26 两连跑）。

Verify 三条产出路径（structured_output / dict / 文本截取）都可能放行模型自报的
越界 hypothesis_id；_align_hypothesis_id 是统一收口，replay 按 id join 裁决，
错 id = CONFIRMED 静默变 n/a（指标污染）。
"""
from __future__ import annotations

from codeark.agents.verify_agent import _align_hypothesis_id
from codeark.models.schemas import VerificationResult


class _Hyp:
    id = "H1"
    title = "t"


def _ver(**kw) -> VerificationResult:
    d = dict(hypothesis_id="", hypothesis_title="t", verdict="CONFIRMED",
             confidence=0.9, evidence="e", verification_method="m")
    d.update(kw)
    return VerificationResult(**d)


def test_align_corrects_model_reported_id():
    assert _align_hypothesis_id(_ver(hypothesis_id="H9"), _Hyp()).hypothesis_id == "H1"


def test_align_fills_empty_id():
    assert _align_hypothesis_id(_ver(hypothesis_id=""), _Hyp()).hypothesis_id == "H1"


def test_align_keeps_matching_id():
    assert _align_hypothesis_id(_ver(hypothesis_id="H1"), _Hyp()).hypothesis_id == "H1"


def test_align_noop_when_hyp_has_no_id():
    class _NoId:
        id = ""
        title = "t"

    # 上游未分配 id（dry/旧路径）时无对齐基准，保留模型自报值
    assert _align_hypothesis_id(_ver(hypothesis_id="H7"), _NoId()).hypothesis_id == "H7"

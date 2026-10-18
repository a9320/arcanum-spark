"""verify 单假设路径 id 契约单测 — 2026-10-18 四缺陷修复 T2。

实弹背景：GK 串行卷 H2（官方 SCRIPT_NAME 链）因 llama.cpp×gpt-oss
"peg-native format" 整轮失败被静默降级成 UNCERTAIN 0.3；并行卷
hypothesis_id 恒空靠按序回填，串线错配无声。契约要求：
- hypothesis_id 必填且等于本次调用假设 id；
- 缺失/不符 → 契约修复重试一次；
- 仍失败 → **显式降级记录**（none(degraded)），禁止静默回填成正常裁决。
"""
from __future__ import annotations

import pytest

import codeark.agents.verify_agent as va
from codeark.models.schemas import VerificationResult


class _Hyp:
    id = "H1"
    title = "t"


def _ver(**kw) -> VerificationResult:
    d = dict(hypothesis_id="H1", hypothesis_title="t", verdict="CONFIRMED",
             confidence=0.9, evidence="e", verification_method="m")
    d.update(kw)
    return VerificationResult(**d)


class _FakeResult:
    def __init__(self, obj):
        self.structured_output = obj


class _SeqAgent:
    """按序返回 payload；payload 为 Exception 时抛掷。"""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls: list[str] = []

    async def invoke_async(self, prompt: str):
        self.calls.append(prompt)
        payload = self.payloads[min(len(self.calls) - 1, len(self.payloads) - 1)]
        if isinstance(payload, Exception):
            raise payload
        return _FakeResult(payload)


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0.0)


async def test_missing_id_triggers_repair_retry_and_recovers():
    agent = _SeqAgent([_ver(hypothesis_id=""), _ver(hypothesis_id="H1")])
    out = await va._verify_one(agent, _Hyp(), "data")

    assert len(agent.calls) == 2
    assert "契约修复" in agent.calls[1] and "H1" in agent.calls[1]
    assert out.hypothesis_id == "H1"
    assert out.verification_method == "m"  # 真裁决，不是降级记录


async def test_persistent_missing_id_degrades_without_backfill():
    agent = _SeqAgent([_ver(hypothesis_id=""), _ver(hypothesis_id="")])
    out = await va._verify_one(agent, _Hyp(), "data")

    assert len(agent.calls) == 2
    assert out.verdict == "UNCERTAIN"
    assert out.verification_method == "none(degraded)"
    assert "禁止按序回填" in out.evidence
    assert out.hypothesis_id == "H1"  # 降级记录绑定调用目标，非模型自报


async def test_wrong_id_is_not_silently_realigned():
    agent = _SeqAgent([_ver(hypothesis_id="H9"), _ver(hypothesis_id="H9")])
    out = await va._verify_one(agent, _Hyp(), "data")

    assert out.verdict == "UNCERTAIN"
    assert out.verification_method == "none(degraded)"
    assert "不符" in out.evidence and "H9" in out.evidence


async def test_peg_native_failure_retries_with_tightened_prompt():
    agent = _SeqAgent([
        RuntimeError("The model produced output that does not match the expected peg-native format"),
        _ver(hypothesis_id="H1"),
    ])
    out = await va._verify_one(agent, _Hyp(), "data")

    assert len(agent.calls) == 2
    assert "格式修复" in agent.calls[1]
    assert out.verification_method == "m"


async def test_invoke_failure_degrades_explicitly():
    agent = _SeqAgent([RuntimeError("boom"), RuntimeError("boom")])
    out = await va._verify_one(agent, _Hyp(), "data")

    assert out.verdict == "UNCERTAIN"
    assert out.verification_method == "none(degraded)"
    assert "invoke 失败" in out.evidence

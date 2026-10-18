"""T4 案甲单测 — 证据包组装 + E2 逐字引文校验（2026-10-18）。

契约：verify 数据块从"仅假设文件"扩为"假设文件+证据包"；严格模式下，模型
CONFIRMED 若引用了仓内路径却拿不出逐字片段，降为 UNCERTAIN（判决降级，非 degraded）。
"""
from __future__ import annotations

import pytest

import codeark.agents.verify_agent as va
from codeark.models.schemas import HypothesisSet, VerificationResult, VulnHypothesis


def _hyp(**kw) -> VulnHypothesis:
    d = dict(title="t", vuln_type="PATH_TRAVERSAL", file_path="app/server.py",
             line_start=1, line_end=1, code_snippet="x", attack_path="see docs/solve.py",
             confidence="high", suggested_verification="manual")
    d.update(kw)
    return VulnHypothesis(**d)


def _files() -> dict[str, str]:
    return {
        "app/server.py": "def get_key():\n    return key\n",
        "app/util.py": "HELPER = 1\n",
        "app/other.py": "OTHER = 2\n",
        "docs/solve.py": "print('exploit: SCRIPT_NAME')\n",
        "solution/exp.py": "print('official solution')\n",
        "big/blob.py": "A" * 2000,
    }


def _keys(pack: dict[str, str]) -> list[str]:
    return [k.replace("\\", "/") for k in pack]


def test_pack_includes_hypothesis_sibling_and_hinted_file(monkeypatch):
    monkeypatch.delenv("ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION", raising=False)
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", "60000")
    pack = va._evidence_pack(_files(), _hyp(), "app/server.py")
    keys = _keys(pack)
    assert "app/server.py" in keys          # 假设文件无条件
    assert "app/util.py" in keys            # 同目录兄弟
    assert "docs/solve.py" in keys          # attack_path 点名
    assert "solution/exp.py" in keys        # 默认包含 solution/


def test_pack_excludes_solution_when_env(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION", "1")
    pack = va._evidence_pack(_files(), _hyp(), "app/server.py")
    assert "solution/exp.py" not in _keys(pack)


def test_pack_budget_caps_but_keeps_hypothesis_file(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", "20")
    pack = va._evidence_pack(_files(), _hyp(), "app/server.py")
    keys = _keys(pack)
    assert "app/server.py" in keys          # force 无条件
    assert "big/blob.py" not in keys        # 超预算不装
    assert len(keys) < len(_files())


def test_quote_check_passes_on_verbatim_line():
    ok, why = va._check_evidence_quote(
        "app/server.py:1 原文 `def get_key():` 表明无鉴权", _files())
    assert ok and not why


def test_quote_check_fails_on_fabricated_quote():
    ok, why = va._check_evidence_quote(
        "app/server.py:1 原文 `def totally_secure():` 表明有鉴权", _files())
    assert not ok and "逐字片段" in why


def test_quote_check_without_path_is_e1():
    ok, why = va._check_evidence_quote("static_scan returned []", _files())
    assert ok and not why


class _R:
    def __init__(self, v):
        self.structured_output = v


class _FakeAgent:
    def __init__(self, evidence: str):
        self.evidence = evidence
        self.calls = []

    async def invoke_async(self, prompt: str):
        self.calls.append(prompt)
        return _R(VerificationResult(
            hypothesis_id="H1", hypothesis_title="t", verdict="CONFIRMED",
            confidence=0.9, evidence=self.evidence, verification_method="manual",
        ))


def _hs() -> HypothesisSet:
    return HypothesisSet(hypotheses=[_hyp()], coverage_notes="t")


async def test_strict_mode_demotes_fabricated_quote(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_STRICT", "1")
    fake = _FakeAgent("app/server.py:1 原文 `def totally_secure():` 有鉴权")
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files: fake)
    out = await va.run_verify_split(
        _hs(), _files(), model=object(), prompt_files=_files(),
        max_concurrency=1, inter_call_delay=0.0,
    )
    assert out[0].verdict == "UNCERTAIN"
    assert "quote-check-failed" in out[0].verification_method
    assert out[0].degraded is False       # 判决降级≠invoke 降级


async def test_lenient_mode_keeps_confirmed(monkeypatch):
    monkeypatch.delenv("ARCA_VERIFY_EVIDENCE_STRICT", raising=False)
    fake = _FakeAgent("app/server.py:1 原文 `def totally_secure():` 有鉴权")
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files: fake)
    out = await va.run_verify_split(
        _hs(), _files(), model=object(), prompt_files=_files(),
        max_concurrency=1, inter_call_delay=0.0,
    )
    assert out[0].verdict == "CONFIRMED"

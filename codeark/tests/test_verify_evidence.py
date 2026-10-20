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
    def __init__(self, evidence: str, verdict: str = "CONFIRMED"):
        self.evidence = evidence
        self.verdict = verdict
        self.calls = []

    async def invoke_async(self, prompt: str):
        self.calls.append(prompt)
        return _R(VerificationResult(
            hypothesis_id="H1", hypothesis_title="t", verdict=self.verdict,
            confidence=0.9, evidence=self.evidence, verification_method="manual",
        ))


def _hs() -> HypothesisSet:
    return HypothesisSet(hypotheses=[_hyp()], coverage_notes="t")


async def test_strict_mode_demotes_fabricated_quote(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_STRICT", "1")
    fake = _FakeAgent("app/server.py:1 原文 `def totally_secure():` 有鉴权")
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files, **kw: fake)
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
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files, **kw: fake)
    out = await va.run_verify_split(
        _hs(), _files(), model=object(), prompt_files=_files(),
        max_concurrency=1, inter_call_delay=0.0,
    )
    assert out[0].verdict == "CONFIRMED"


# -- P0 补强（10-19）：solution 优先层 / 预算边界 / 已知宽松点锚 ----------


def _many_files() -> dict[str, str]:
    files = {"app/server.py": "x=1\n"}
    files.update({f"app/f{i:03d}.py": "y" * 20 for i in range(200)})
    files["solution/solve.py"] = "print('official exploit')\n" * 15
    return files


def test_pack_prioritizes_solution_before_general_fill(monkeypatch):
    """T4 验收依赖官方 solve.py 在证据链：紧预算下 solution 必须先于小文件装填。"""
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", "150")
    monkeypatch.delenv("ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION", raising=False)
    pack = va._evidence_pack(_many_files(), _hyp(), "app/server.py")
    assert any(k.replace("\\", "/").startswith("solution/") for k in pack)
    assert len(pack) < len(_many_files())        # 预算仍然生效


def test_pack_budget_zero_is_unlimited(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", "0")
    monkeypatch.delenv("ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION", raising=False)
    pack = va._evidence_pack(_files(), _hyp(), "app/server.py")
    assert set(_keys(pack)) == set(_keys(_files()))


def test_pack_excludes_solution_even_when_prioritized(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", "150")
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_EXCLUDE_SOLUTION", "1")
    pack = va._evidence_pack(
        _many_files(), _hyp(attack_path="solution/solve.py"), "app/server.py")
    assert not any("solution" in k for k in _keys(pack))


def test_pack_hallucinated_path_returns_all_files(monkeypatch):
    """幻觉路径沿用旧口径：全量交给工具裁决（预算不截断）。"""
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", "10")
    pack = va._evidence_pack(
        _files(), _hyp(file_path="nope/missing.py"), "nope/missing.py")
    assert set(_keys(pack)) == set(_keys(_files()))


def test_quote_check_crlf_verbatim():
    files = {"app/server.py": "def get_key():\r\n    return key\r\n"}
    ok, why = va._check_evidence_quote(
        "app/server.py:1 原文 `def get_key():`", files)
    assert ok and not why


def test_quote_check_line_number_mismatch_still_passes():
    """已知宽松点：只校验逐字片段，不校验行号（文档已记）。"""
    files = {"app/server.py": "def get_key():\n    return 1\n"}
    ok, _ = va._check_evidence_quote(
        "app/server.py:999 原文 `def get_key():`", files)
    assert ok


def test_quote_check_multi_citation_partial_fake_passes_current_semantics():
    """已知宽松点：任一条引用可验证即通过；是否要求“全部引用”待拍板。"""
    files = {
        "app/server.py": "def get_key():\n    return 1\n",
        "app/other.py": "OTHER = 2\n",
    }
    ok, why = va._check_evidence_quote(
        "app/server.py:1 原文 `def get_key():` 且 "
        "app/other.py:1 原文 `fabricated_quote`", files)
    assert ok and not why


async def test_strict_mode_demotes_refuted_fabricated_quote(monkeypatch):
    """自信错驳护栏：REFUTED 也必须过 E2，伪造引文在严格模式下降 UNCERTAIN。"""
    monkeypatch.setenv("ARCA_VERIFY_EVIDENCE_STRICT", "1")
    fake = _FakeAgent(
        "app/server.py:1 原文 `def totally_secure():` 有鉴权", verdict="REFUTED")
    monkeypatch.setattr(va, "build_verify_one_agent", lambda model, files, **kw: fake)
    out = await va.run_verify_split(
        _hs(), _files(), model=object(), prompt_files=_files(),
        max_concurrency=1, inter_call_delay=0.0,
    )
    assert out[0].verdict == "UNCERTAIN"
    assert "quote-check-failed" in out[0].verification_method
    assert out[0].degraded is False


# -- peg-native 无工具兜底（10-19 复跑实证：温度=0 仍有随机 parser 拒绝） --


class _PegFailAgent:
    def __init__(self):
        self.calls = 0

    async def invoke_async(self, prompt: str):
        self.calls += 1
        raise RuntimeError(
            "The model produced output that does not match the expected peg-native format"
        )


class _AlwaysFailAgent:
    async def invoke_async(self, prompt: str):
        raise RuntimeError("still peg-native failure")


async def test_peg_native_falls_back_to_no_tools(monkeypatch):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    failing = _PegFailAgent()
    retry = _FakeAgent("app/server.py:1 原文 `def get_key():`")
    out = await va._verify_one(
        failing, _hyp(), "data", per_invoke_timeout=5, retry_agent=retry)
    assert out.verdict == "CONFIRMED"
    assert out.degraded is False
    assert failing.calls == 2       # 带工具路径两次都失败
    assert len(retry.calls) == 1     # 无工具兜底一次成功


async def test_peg_native_fallback_failure_degrades(monkeypatch):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    out = await va._verify_one(
        _PegFailAgent(), _hyp(), "data", per_invoke_timeout=5,
        retry_agent=_AlwaysFailAgent())
    assert out.verdict == "UNCERTAIN"
    assert out.degraded is True


class _MissingIdThenPegAgent:
    def __init__(self):
        self.calls = 0

    async def invoke_async(self, prompt: str):
        self.calls += 1
        if self.calls == 1:
            return _R(VerificationResult(
                hypothesis_id="", hypothesis_title="t", verdict="CONFIRMED",
                confidence=0.9, evidence="e", verification_method="manual",
            ))
        raise RuntimeError(
            "The model produced output that does not match the expected peg-native format"
        )


async def test_id_repair_peg_native_falls_back_to_no_tools(monkeypatch):
    """10-19 r2 实锤：首次 invoke 成功但缺 id，契约修复调用被 peg-native 拒绝。"""
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    main = _MissingIdThenPegAgent()
    retry = _FakeAgent("app/server.py:1 原文 `def get_key():`")
    out = await va._verify_one(
        main, _hyp(id="H1"), "data", per_invoke_timeout=5, retry_agent=retry)
    assert out.verdict == "CONFIRMED"
    assert out.degraded is False
    assert main.calls == 2       # 首次 invoke + 契约修复尝试
    assert len(retry.calls) == 1  # 无工具契约兜底一次成功


async def test_id_repair_fallback_failure_degrades(monkeypatch):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    out = await va._verify_one(
        _MissingIdThenPegAgent(), _hyp(id="H1"), "data", per_invoke_timeout=5,
        retry_agent=_AlwaysFailAgent())
    assert out.verdict == "UNCERTAIN"
    assert out.degraded is True


# -- 2026-10-20 兜底第二刀：无工具提示 + 关闭 structured output + 显式日志 --


class _TextAgent:
    """模拟关掉 structured_output 后的纯文本返回。"""

    def __init__(self, text: str):
        self.text = text
        self.calls = []

    async def invoke_async(self, prompt: str):
        self.calls.append(prompt)
        return self.text


def test_no_tools_agent_uses_notools_prompt_and_no_structured(monkeypatch):
    captured = {}

    class _DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(va, "Agent", _DummyAgent)
    va.build_verify_one_agent(object(), _files(), tools_enabled=False, structured=False)
    assert captured["system_prompt"] == va.VERIFY_ONE_NOTOOLS_SYSTEM_PROMPT
    assert captured["tools"] == []
    assert "structured_output_model" not in captured


async def test_text_json_fallback_parses(monkeypatch):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    retry = _TextAgent(
        '{"hypothesis_id":"H1","hypothesis_title":"t","verdict":"CONFIRMED",'
        '"confidence":0.9,"evidence":"app/server.py:1 原文 `def get_key():`",'
        '"verification_method":"manual"}'
    )
    out = await va._verify_one(
        _PegFailAgent(), _hyp(), "data", per_invoke_timeout=5, retry_agent=retry)
    assert out.verdict == "CONFIRMED"
    assert out.degraded is False
    assert len(retry.calls) == 1


async def test_fallback_logs_attempt_and_failure(monkeypatch, capsys):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    out = await va._verify_one(
        _PegFailAgent(), _hyp(), "data", per_invoke_timeout=5,
        retry_agent=_AlwaysFailAgent())
    assert out.degraded is True
    captured = capsys.readouterr().out
    assert "无工具兜底尝试" in captured
    assert "无工具兜底失败" in captured


class _MissingIdTwiceAgent:
    """契约修复返回但两次都缺 id（H4 r2 实况，无异常）。"""

    def __init__(self):
        self.calls = 0

    async def invoke_async(self, prompt: str):
        self.calls += 1
        return _R(VerificationResult(
            hypothesis_id="", hypothesis_title="t", verdict="CONFIRMED",
            confidence=0.9, evidence="e", verification_method="manual",
        ))


async def test_contract_repair_missing_id_falls_back_to_no_tools(monkeypatch):
    monkeypatch.setattr(va, "_VERIFY_RETRY_BACKOFF", 0)
    main = _MissingIdTwiceAgent()
    retry = _TextAgent(
        '{"hypothesis_id":"H1","hypothesis_title":"t","verdict":"CONFIRMED",'
        '"confidence":0.9,"evidence":"app/server.py:1: `def get_key():`",'
        '"verification_method":"manual"}'
    )
    out = await va._verify_one(
        main, _hyp(id="H1"), "data", per_invoke_timeout=5, retry_agent=retry)
    assert out.verdict == "CONFIRMED"
    assert out.degraded is False
    assert main.calls == 2       # 首次 + 契约修复
    assert len(retry.calls) == 1  # 二次无工具兜底


async def test_plain_json_env_disables_primary_structured(monkeypatch):
    monkeypatch.setenv("ARCA_VERIFY_PLAIN_JSON", "1")
    seen = []
    fake = _FakeAgent("app/server.py:1 原文 `def get_key():`")

    def _build(model, files, **kw):
        seen.append(kw)
        return fake

    monkeypatch.setattr(va, "build_verify_one_agent", _build)
    out = await va.run_verify_split(
        _hs(), _files(), model=object(), prompt_files=_files(),
        max_concurrency=1, inter_call_delay=0.0,
    )
    assert out[0].verdict == "CONFIRMED"
    assert seen[0].get("structured") is False


async def test_plain_json_default_keeps_primary_structured(monkeypatch):
    monkeypatch.delenv("ARCA_VERIFY_PLAIN_JSON", raising=False)
    seen = []
    fake = _FakeAgent("app/server.py:1 原文 `def get_key():`")

    def _build(model, files, **kw):
        seen.append(kw)
        return fake

    monkeypatch.setattr(va, "build_verify_one_agent", _build)
    out = await va.run_verify_split(
        _hs(), _files(), model=object(), prompt_files=_files(),
        max_concurrency=1, inter_call_delay=0.0,
    )
    assert out[0].verdict == "CONFIRMED"
    assert seen[0].get("structured") is True


def test_json_object_from_text_unwraps_verification_result():
    """10-20 plain-json 实况形状：verification_result 包层 + status + evidence 数组。"""
    text = ('{"verification_result": {"hypothesis_id": "H4", "status": "REFUTED",'
            ' "confidence": 1.0, "evidence": [{"type": "E2",'
            ' "description": "readme.md:38: <!--Spoilers!  8;41;31m/-->"}],'
            ' "verification_method": "manual"}}')
    obj = va._json_object_from_text(text)
    assert obj is not None
    assert obj["verdict"] == "REFUTED"
    assert obj["hypothesis_id"] == "H4"
    assert "Spoilers" in obj["evidence"]


async def test_plain_primary_wrapped_json_parses(monkeypatch):
    wrapped = _TextAgent(
        '{"verification_result": {"hypothesis_id": "H1", "status": "CONFIRMED",'
        ' "confidence": 0.9, "evidence": [{"type": "E2",'
        ' "description": "app/server.py:1: `def get_key():`"}],'
        ' "verification_method": "manual"}}'
    )
    out = await va._verify_one(
        wrapped, _hyp(id="H1"), "data", per_invoke_timeout=5)
    assert out.verdict == "CONFIRMED"
    assert out.degraded is False


def test_plain_json_contract_appended_only_when_unstructured(monkeypatch):
    captured = {}

    class _DummyAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(va, "Agent", _DummyAgent)
    va.build_verify_one_agent(object(), _files(), structured=False)
    assert captured["system_prompt"].endswith(va.PLAIN_JSON_CONTRACT)
    captured.clear()
    va.build_verify_one_agent(object(), _files(), structured=True)
    assert va.PLAIN_JSON_CONTRACT not in captured["system_prompt"]


def test_json_object_from_text_survives_braces_in_evidence():
    text = (
        "thinking {not json}\n"
        '{"hypothesis_id":"H1","verdict":"UNCERTAIN","evidence":"cfg{x:1}",'
        '"confidence":0.5,"hypothesis_title":"t","verification_method":"m"}'
    )
    obj = va._json_object_from_text(text)
    assert obj is not None and obj["verdict"] == "UNCERTAIN"
    assert obj["evidence"] == "cfg{x:1}"

"""Offline tests for OpenAI-compatible endpoint config and stage routing."""
from __future__ import annotations

import pytest

from codeark.graph import pipeline as pl
from codeark.models.factory import (
    EndpointConfig,
    make_openai_compatible_model,
    make_stage_models_from_env,
)
from codeark.models.routing import StageModels
from codeark.models.schemas import (
    AttackChain,
    FinalReport,
    HypothesisSet,
    VerificationResult,
    VulnHypothesis,
)


_ARCA_VARS = (
    "ARCA_MODEL",
    "ARCA_BASE_URL",
    "ARCA_API_KEY",
    "ARCA_TIMEOUT",
    "ARCA_SCOUT_MODEL",
    "ARCA_SCOUT_BASE_URL",
    "ARCA_SCOUT_API_KEY",
    "ARCA_SCOUT_TIMEOUT",
    "ARCA_VERIFY_MODEL",
    "ARCA_VERIFY_BASE_URL",
    "ARCA_VERIFY_API_KEY",
    "ARCA_VERIFY_TIMEOUT",
    "ARCA_DEEPEN_MODEL",
    "ARCA_DEEPEN_BASE_URL",
    "ARCA_DEEPEN_API_KEY",
    "ARCA_DEEPEN_TIMEOUT",
    "ARCA_ARBITER_MODEL",
    "ARCA_ARBITER_BASE_URL",
    "ARCA_ARBITER_API_KEY",
    "ARCA_ARBITER_TIMEOUT",
    "ARCA_SCOUT_PRIMARY_API_KEY",
    "ARCA_SCOUT_FALLBACK_API_KEY",
    "ARCA_VERIFY_API_KEY",
    "ARCA_DEEPEN_API_KEY",
    "ARCA_ARBITER_API_KEY",
)


def _clear_arca_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ARCA_VARS:
        monkeypatch.delenv(name, raising=False)


def test_endpoint_config_validates_and_hides_key() -> None:
    endpoint = EndpointConfig(
        model_id="demo-model",
        base_url="https://example.test/v1/",
        api_key="super-secret",
        timeout="42",  # type: ignore[arg-type]
    )

    assert endpoint.base_url == "https://example.test/v1"
    assert endpoint.timeout == 42.0
    assert "super-secret" not in repr(endpoint)


def test_openai_compatible_factory_is_offline_and_configured() -> None:
    model = make_openai_compatible_model(
        model_id="demo-model",
        base_url="https://example.test/v1/",
        api_key="secret",
        timeout=37,
    )

    assert model.get_config()["model_id"] == "demo-model"
    assert model.client_args["base_url"] == "https://example.test/v1"
    assert model.client_args["timeout"] == 37.0


def test_stage_models_from_env_inherits_shared_and_overrides_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_arca_env(monkeypatch)
    monkeypatch.setenv("ARCA_MODEL", "shared-model")
    monkeypatch.setenv("ARCA_BASE_URL", "https://shared.example/v1")
    monkeypatch.setenv("ARCA_API_KEY", "shared-secret")
    monkeypatch.setenv("ARCA_TIMEOUT", "90")
    monkeypatch.setenv("ARCA_ARBITER_MODEL", "arbiter-model")
    monkeypatch.setenv("ARCA_ARBITER_API_KEY", "arbiter-secret")

    routes = make_stage_models_from_env()

    assert routes is not None
    assert routes.scout is routes.verify is routes.deepen
    assert routes.arbiter is not routes.scout
    assert routes.scout.get_config()["model_id"] == "shared-model"
    assert routes.scout.client_args["base_url"] == "https://shared.example/v1"
    assert routes.scout.client_args["timeout"] == 90.0
    assert routes.arbiter.get_config()["model_id"] == "arbiter-model"
    assert routes.arbiter.client_args["base_url"] == "https://shared.example/v1"


def test_stage_only_env_configures_only_that_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_arca_env(monkeypatch)
    monkeypatch.setenv("ARCA_SCOUT_MODEL", "scout-model")
    monkeypatch.setenv("ARCA_SCOUT_BASE_URL", "https://scout.example/v1")
    monkeypatch.setenv("ARCA_SCOUT_API_KEY", "scout-secret")

    routes = make_stage_models_from_env()

    assert routes is not None
    assert routes.scout is not None
    assert routes.verify is None
    assert routes.deepen is None
    assert routes.arbiter is None


def test_incomplete_env_config_reports_names_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_arca_env(monkeypatch)
    monkeypatch.setenv("ARCA_MODEL", "demo-model")
    monkeypatch.setenv("ARCA_API_KEY", "do-not-leak-this")

    with pytest.raises(ValueError) as exc_info:
        make_stage_models_from_env()

    message = str(exc_info.value)
    assert "ARCA_BASE_URL" in message
    assert "do-not-leak-this" not in message


def test_no_arca_env_preserves_existing_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_arca_env(monkeypatch)
    assert make_stage_models_from_env() is None


def test_dedicated_key_env_builds_chat_and_responses_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from strands.models import OpenAIModel, OpenAIResponsesModel

    _clear_arca_env(monkeypatch)
    monkeypatch.setenv("ARCA_SCOUT_PRIMARY_API_KEY", "scout-secret")
    monkeypatch.setenv("ARCA_SCOUT_FALLBACK_API_KEY", "luna-secret")
    monkeypatch.setenv("ARCA_VERIFY_API_KEY", "verify-secret")
    monkeypatch.setenv("ARCA_DEEPEN_API_KEY", "deepen-secret")
    monkeypatch.setenv("ARCA_ARBITER_API_KEY", "arbiter-secret")

    routes = make_stage_models_from_env()

    assert routes is not None
    # 2026-09-25 实测：三家服务端均在 API 层归一化 XML 工具调用 → 远程走标准 OpenAIModel。
    assert isinstance(routes.scout, OpenAIModel)
    assert routes.scout.get_config()["model_id"] == "step-5-preview"
    assert routes.scout.client_args["base_url"] == "https://api.stepfun.com/v1"
    assert routes.scout_fallback is not None
    assert isinstance(routes.scout_fallback, OpenAIResponsesModel)
    assert routes.scout_fallback.get_config()["model_id"] == "gpt-5.6-luna"
    assert routes.scout_fallback.client_args["base_url"] == "https://api.lmuai.ai/v1"
    assert routes.scout_fallback.get_config()["params"]["reasoning"] == {"effort": "none"}
    assert isinstance(routes.verify, OpenAIModel)
    assert routes.verify.get_config()["model_id"] == "Qwen3.8-Flash-Next"
    assert routes.verify.client_args["base_url"] == "https://developer.amd.com.cn/radeon/api/v1"
    assert isinstance(routes.deepen, OpenAIModel)
    assert routes.deepen.get_config()["model_id"] == "DeepSeek-V4-Flash"
    assert isinstance(routes.arbiter, OpenAIResponsesModel)
    assert routes.arbiter.get_config()["model_id"] == "gpt-6-sol"
    assert routes.arbiter.get_config()["params"]["reasoning"] == {"effort": "high"}


@pytest.mark.asyncio
async def test_graph_routes_each_stage_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    shared = object()
    scout = object()
    verify = object()
    deepen = object()
    arbiter = object()

    hypothesis = HypothesisSet(
        hypotheses=[VulnHypothesis(
            title="test hypothesis",
            vuln_type="PIT-T-51",
            file_path="a.py",
            line_start=1,
            line_end=1,
            code_snippet="x",
            attack_path="test",
            confidence="high",
            suggested_verification="pitax_scan",
        )],
        coverage_notes="test",
    )
    verification = VerificationResult(
        hypothesis_id="",
        hypothesis_title="test hypothesis",
        verdict="CONFIRMED",
        confidence=0.9,
        evidence="test evidence",
        verification_method="test",
    )

    def fake_agent0(_files):
        return []

    async def fake_scout(_files, model=None, prompt_files=None, agent0_findings=None, **_kwargs):
        calls["scout"] = model
        return hypothesis

    async def fake_verify(_hypothesis_set, _files, model=None, prompt_files=None, **_kwargs):
        calls["verify"] = model
        return [verification]

    async def fake_deepen(_confirmed, _files, model=None, prompt_files=None, **_kwargs):
        calls["deepen"] = model
        return [AttackChain(impact="impact", remediation="remediation")]

    async def fake_arbiter(_hypothesis_set, _verifications, _attack_chains, model=None, **_kwargs):
        calls["arbiter"] = model
        return FinalReport(findings=[], conclusion="test")

    monkeypatch.setattr(pl, "run_agent0", fake_agent0)
    monkeypatch.setattr(pl, "run_scout", fake_scout)
    monkeypatch.setattr(pl, "run_verify_split", fake_verify)
    monkeypatch.setattr(pl, "run_deepen", fake_deepen)
    monkeypatch.setattr(pl, "run_arbiter", fake_arbiter)
    monkeypatch.setattr(
        pl,
        "render_report",
        lambda *_args, **_kwargs: {"json": "{}", "sarif": {}, "markdown": ""},
    )

    routes = StageModels(scout=scout, verify=verify, deepen=deepen, arbiter=arbiter)
    result = await pl.CodeRiskGraph(model=shared, stage_models=routes).run({"a.py": "x"})

    assert result.node_errors == {}
    assert calls == {
        "scout": scout,
        "verify": verify,
        "deepen": deepen,
        "arbiter": arbiter,
    }


@pytest.mark.asyncio
async def test_graph_shared_model_remains_backward_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    shared = object()
    hypothesis = HypothesisSet(hypotheses=[], coverage_notes="test")

    def fake_agent0(_files):
        return []

    async def fake_scout(_files, model=None, **_kwargs):
        calls.append(model)
        return hypothesis

    async def fake_verify(_hypothesis_set, _files, model=None, **_kwargs):
        calls.append(model)
        return []

    async def fake_deepen(_confirmed, _files, model=None, **_kwargs):
        calls.append(model)
        return []

    async def fake_arbiter(_hypothesis_set, _verifications, _attack_chains, model=None, **_kwargs):
        calls.append(model)
        return FinalReport(findings=[], conclusion="test")

    monkeypatch.setattr(pl, "run_agent0", fake_agent0)
    monkeypatch.setattr(pl, "run_scout", fake_scout)
    monkeypatch.setattr(pl, "run_verify_split", fake_verify)
    monkeypatch.setattr(pl, "run_deepen", fake_deepen)
    monkeypatch.setattr(pl, "run_arbiter", fake_arbiter)
    monkeypatch.setattr(
        pl,
        "render_report",
        lambda *_args, **_kwargs: {"json": "{}", "sarif": {}, "markdown": ""},
    )

    await pl.CodeRiskGraph(model=shared).run({"a.py": "x"})

    assert calls == [shared, shared, shared, shared]


@pytest.mark.asyncio
async def test_dry_graph_does_not_resolve_stage_models(monkeypatch: pytest.MonkeyPatch) -> None:
    class ExplodingRoutes:
        def resolve(self, *_args, **_kwargs):
            raise AssertionError("dry-run must not resolve model routes")

    monkeypatch.setattr(pl, "run_agent0", lambda _files: [])
    result = await pl.CodeRiskGraph(dry=True, stage_models=ExplodingRoutes()).run({"a.py": "x"})

    assert result.node_errors == {}
    assert result.final_report["conclusion"].startswith("dry-run")

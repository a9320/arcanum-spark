"""Foundry 模型探针契约锚（零联网：httpx.MockTransport）。

断言面：env 门控、三种地址形状的顺序与契约、200 即停、失败脱敏、`/models` 不重复拼接。
"""
from __future__ import annotations

import json

import httpx

from codeark.azure.foundry_probe import (
    API_VERSION_ENV,
    DEFAULT_API_VERSION,
    DEPLOYMENT_ENV,
    ENDPOINT_ENV,
    KEY_ENV,
    FoundryClient,
    status_from_env,
)

BASE = "https://arca-foundry.services.ai.azure.com"
KEY = "f-test-secret-0123456789"
DEPLOYMENT = "phi4mini"


def _client(handler) -> FoundryClient:
    return FoundryClient(
        endpoint=BASE, key=KEY, deployment=DEPLOYMENT, transport=httpx.MockTransport(handler)
    )


def _ok_handler(captured: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    return handler


def test_status_reports_missing_required_env():
    status = status_from_env({})
    assert status.configured is False
    assert set(status.missing) == {ENDPOINT_ENV, KEY_ENV, DEPLOYMENT_ENV}
    assert status.api_version == DEFAULT_API_VERSION


def test_from_env_requires_all_three():
    assert FoundryClient.from_env({ENDPOINT_ENV: BASE, KEY_ENV: KEY}) is None
    client = FoundryClient.from_env({ENDPOINT_ENV: BASE, KEY_ENV: KEY, DEPLOYMENT_ENV: DEPLOYMENT})
    assert client is not None and client.deployment == DEPLOYMENT
    client.close()


def test_first_shape_contract_and_stop():
    captured: list = []
    result = _client(_ok_handler(captured)).probe()
    assert result.ok and result.path == "models" and result.auth == "api-key"
    assert len(result.attempts) == 1
    req = captured[0]
    assert req.url.path == "/models/chat/completions"
    assert req.url.params["api-version"] == DEFAULT_API_VERSION
    assert req.headers["api-key"] == KEY
    body = json.loads(req.content.decode())
    assert body["model"] == DEPLOYMENT
    assert "max_tokens" in body


def test_falls_back_to_bearer_when_api_key_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        if "api-key" in request.headers:
            return httpx.Response(401, text="bad key")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    result = _client(handler).probe()
    assert result.ok and result.path == "models-bearer"
    assert [a.ok for a in result.attempts] == [False, True]


def test_all_shapes_fail_degrades_and_scrubs_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=f"denied key={KEY}")

    result = _client(handler).probe()
    assert result.ok is False and result.degraded is True
    assert len(result.attempts) == 3
    assert KEY not in result.reason
    assert "400" in result.reason


def test_endpoint_with_trailing_models_not_doubled():
    captured: list = []
    client = FoundryClient(
        endpoint=BASE + "/models", key=KEY, deployment=DEPLOYMENT,
        transport=httpx.MockTransport(_ok_handler(captured)),
    )
    assert client.probe().ok
    assert captured[0].url.path == "/models/chat/completions"


def test_reply_content_as_list_is_flattened():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": [{"text": "o"}, {"text": "k"}]}}]})

    result = _client(handler).probe()
    assert result.ok and result.reply == "o k"


def test_network_error_is_recorded_per_attempt():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    result = _client(handler).probe()
    assert result.ok is False
    assert all("ConnectError" in a.detail for a in result.attempts)
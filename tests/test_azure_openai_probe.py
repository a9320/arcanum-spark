"""Azure OpenAI 探针契约锚（零联网：httpx.MockTransport 全量替身）。

断言面：
1. v1 + Bearer 成功即停（不重复调用）；
2. v1 Bearer 被拒 → 自动回退 v1 api-key；
3. v1 两种都拒 → 回退 classic api-key（并带 api-version）；
4. 全部失败时四次尝试齐全、密钥脱敏；
5. 网络错误折叠为 attempt detail；
6. endpoint 已带 /openai/v1 时不重复拼接。
"""
from __future__ import annotations

import httpx
import pytest

from codeark.azure.openai_probe import (
    DEFAULT_API_VERSION,
    probe_chat_completion,
)

ENDPOINT = "https://arca-demo.openai.azure.com"
KEY = "k-test-azure-0123456789"
DEPLOYMENT = "scout"


def _ok_body(text: str = "pong") -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
    }


def _probe(handler, endpoint: str = ENDPOINT):
    return probe_chat_completion(
        endpoint=endpoint,
        key=KEY,
        deployment=DEPLOYMENT,
        transport=httpx.MockTransport(handler),
    )


def test_v1_bearer_success_stops_after_first_call():
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        assert request.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(200, json=_ok_body())

    result = _probe(handler)
    assert result.ok is True
    assert result.path == "v1"
    assert result.auth_mode == "bearer"
    assert result.content == "pong"
    assert result.usage == {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9}
    assert len(result.attempts) == 1
    assert len(urls) == 1
    assert "/openai/v1/chat/completions" in urls[0]


def test_v1_bearer_denied_falls_back_to_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization"):
            return httpx.Response(401, text="invalid bearer")
        assert request.headers["api-key"] == KEY
        return httpx.Response(200, json=_ok_body())

    result = _probe(handler)
    assert result.ok is True
    assert result.path == "v1"
    assert result.auth_mode == "api-key"
    assert [a.status for a in result.attempts] == [401, 200]
    assert result.attempts[0].ok is False


def test_v1_both_denied_falls_back_to_classic_api_key():
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        urls.append(url)
        if "/openai/v1/" in url:
            return httpx.Response(401, text="no")
        assert request.headers["api-key"] == KEY
        return httpx.Response(200, json=_ok_body("classic-pong"))

    result = _probe(handler)
    assert result.ok is True
    assert result.path == "classic"
    assert result.auth_mode == "api-key"
    assert result.content == "classic-pong"
    assert f"api-version={DEFAULT_API_VERSION}" in urls[-1]
    assert len(result.attempts) == 3  # classic×bearer 不再尝试


def test_all_attempts_fail_and_key_is_scrubbed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad credential: {KEY}")

    result = _probe(handler)
    assert result.ok is False
    assert result.auth_mode is None
    assert len(result.attempts) == 4
    for attempt in result.attempts:
        assert KEY not in attempt.detail
        assert "***" in attempt.detail
        assert attempt.detail.startswith("HTTP 401")


def test_network_error_is_reported_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = _probe(handler)
    assert result.ok is False
    assert "ConnectError" in result.attempts[0].detail
    assert result.attempts[0].status is None


def test_endpoint_with_openai_v1_suffix_is_not_duplicated():
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json=_ok_body())

    result = _probe(handler, endpoint=f"{ENDPOINT}/openai/v1/")
    assert result.ok is True
    assert "/openai/v1/openai/v1" not in urls[0]
    assert result.endpoint == ENDPOINT


def test_empty_key_or_deployment_rejected():
    with pytest.raises(ValueError):
        probe_chat_completion(endpoint=ENDPOINT, key="  ", deployment=DEPLOYMENT)
    with pytest.raises(ValueError):
        probe_chat_completion(endpoint=ENDPOINT, key=KEY, deployment="  ")
    with pytest.raises(ValueError):
        probe_chat_completion(endpoint="", key=KEY, deployment=DEPLOYMENT)
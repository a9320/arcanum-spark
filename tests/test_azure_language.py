"""Azure AI Language v0 契约锚（零联网：httpx.MockTransport 全量替身）。

断言面：
1. env 门控与机读状态（未配置必须可入报告，不静默跳过）；
2. PiiEntityRecognition 的 URL/头/请求体契约（凭据到位后可直接打真端点）；
3. fail-closed：HTTP/网络/协议/超长 → 该文档 degraded 且 redacted_text=None；
4. 实体元数据不含原文（offset/length 回退脱敏可用，PII 不二次落盘）；
5. 分批（≤5 篇/请求）与密钥脱敏。
"""
from __future__ import annotations

import json

import httpx

from codeark.azure.language import (
    API_VERSION_ENV,
    DEFAULT_API_VERSION,
    ENDPOINT_ENV,
    KEY_ENV,
    MAX_DOC_CHARS,
    LanguageClient,
    status_from_env,
)

ENDPOINT = "https://arca-demo.cognitiveservices.azure.com/"
KEY = "k-test-secret-0123456789"
PII = "jane@example.com"


def _client(handler, **kwargs) -> LanguageClient:
    return LanguageClient(
        endpoint=ENDPOINT,
        key=KEY,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _echo_handler(captured: list | None = None, *, status: int = 200):
    """按请求文档回显结果：含 PII 的文档返回实体 + 脱敏文本。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        payload = json.loads(request.content.decode())
        docs = []
        for doc in payload["analysisInput"]["documents"]:
            text = doc["text"]
            entities = []
            redacted = text
            if PII in text:
                offset = text.index(PII)
                entities = [{
                    "text": PII,
                    "category": "Email",
                    "subcategory": "",
                    "offset": offset,
                    "length": len(PII),
                    "confidenceScore": 0.98,
                }]
                redacted = text.replace(PII, "[REDACTED:Email]")
            docs.append({
                "id": doc["id"],
                "redactedText": redacted,
                "entities": entities,
                "warnings": [],
            })
        return httpx.Response(
            status,
            json={
                "kind": "PiiEntityRecognitionResults",
                "results": {"documents": docs, "errors": [], "modelVersion": "test"},
            },
        )

    return handler


# ── env 门控与状态 ──

def test_status_reports_missing_required_env():
    status = status_from_env({})
    assert status.configured is False
    assert status.missing == (ENDPOINT_ENV, KEY_ENV)
    assert status.endpoint_host == ""
    assert status.api_version == DEFAULT_API_VERSION


def test_status_configured_parses_host_without_key():
    status = status_from_env({ENDPOINT_ENV: ENDPOINT, KEY_ENV: KEY})
    assert status.configured is True
    assert status.missing == ()
    assert status.endpoint_host == "arca-demo.cognitiveservices.azure.com"
    assert KEY not in repr(status)


def test_from_env_requires_both_and_reads_api_version():
    assert LanguageClient.from_env({}) is None
    assert LanguageClient.from_env({ENDPOINT_ENV: ENDPOINT}) is None
    client = LanguageClient.from_env({ENDPOINT_ENV: ENDPOINT, KEY_ENV: KEY})
    assert client is not None and client.api_version == DEFAULT_API_VERSION
    client.close()
    client = LanguageClient.from_env({
        ENDPOINT_ENV: ENDPOINT, KEY_ENV: KEY, API_VERSION_ENV: "2023-04-01",
    })
    assert client is not None and client.api_version == "2023-04-01"
    client.close()


# ── 请求契约 ──

def test_request_contract_path_headers_and_body():
    captured: list = []
    client = _client(_echo_handler(captured))
    client.redact_texts({"src/a.py": f"contact {PII} now"})
    client.close()

    request = captured[0]
    assert request.url.path == "/language/:analyze-text"
    assert request.url.params["api-version"] == DEFAULT_API_VERSION
    assert request.headers["Ocp-Apim-Subscription-Key"] == KEY
    payload = json.loads(request.content.decode())
    assert payload["kind"] == "PiiEntityRecognition"
    assert payload["parameters"]["stringIndexType"] == "UnicodeCodePoint"
    assert payload["analysisInput"]["documents"] == [
        {"id": "src/a.py", "language": "en", "text": f"contact {PII} now"}
    ]


# ── 正常解析 ──

def test_redact_texts_returns_redacted_map_and_entity_counts():
    client = _client(_echo_handler())
    result = client.redact_texts({"a.py": f"mail {PII}", "b.py": "clean = 1"})
    client.close()

    assert result.degraded is False
    assert result.redacted_map() == {"a.py": "mail [REDACTED:Email]", "b.py": "clean = 1"}
    assert result.degraded_ids() == ()
    assert result.entity_counts == {"Email": 1}
    assert result.documents[0].entities[0].offset == len("mail ")
    assert PII not in repr(result.documents[0].entities[0])


def test_offset_fallback_masks_when_redacted_text_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        text = json.loads(request.content.decode())["analysisInput"]["documents"][0]["text"]
        offset = text.index(PII)
        return httpx.Response(200, json={"results": {"documents": [{
            "id": "a.py",
            "entities": [{
                "category": "Email", "subcategory": "", "offset": offset,
                "length": len(PII), "confidenceScore": 0.9,
            }],
        }], "errors": []}})

    client = _client(handler)
    result = client.redact_texts({"a.py": f"x {PII} y"})
    client.close()

    assert result.degraded is False
    assert result.redacted_map() == {"a.py": "x [REDACTED:Email] y"}


def test_batches_at_most_five_documents_per_request():
    captured: list = []
    client = _client(_echo_handler(captured))
    result = client.redact_texts({f"f{i}.py": "x = 1" for i in range(7)})
    client.close()

    assert len(captured) == 2
    assert result.batches == 2
    assert len(result.redacted_map()) == 7
    sizes = [
        len(json.loads(r.content.decode())["analysisInput"]["documents"]) for r in captured
    ]
    assert sizes == [5, 2]


# ── fail-closed ──

def test_http_error_degrades_and_scrubs_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"denied key={KEY}")

    client = _client(handler)
    result = client.redact_texts({"a.py": "x"})
    client.close()

    assert result.degraded is True
    assert result.redacted_map() == {}
    assert result.degraded_ids() == ("a.py",)
    assert KEY not in result.reason
    assert "HTTP 401" in result.reason


def test_network_error_degrades():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = _client(handler)
    result = client.redact_texts({"a.py": "x", "b.py": "y"})
    client.close()

    assert result.degraded is True
    assert set(result.degraded_ids()) == {"a.py", "b.py"}


def test_document_level_error_only_degrades_that_document():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": {
            "documents": [{"id": "a.py", "redactedText": "ok", "entities": []}],
            "errors": [{"id": "b.py", "error": {"code": "InvalidArgument", "message": "bad"}}],
        }})

    client = _client(handler)
    result = client.redact_texts({"a.py": "x", "b.py": "y"})
    client.close()

    assert result.degraded is True
    assert result.redacted_map() == {"a.py": "ok"}
    assert result.degraded_ids() == ("b.py",)


def test_overlong_document_not_sent_and_degraded():
    captured: list = []
    client = _client(_echo_handler(captured))
    result = client.redact_texts({"big.py": "a" * (MAX_DOC_CHARS + 1)})
    client.close()

    assert captured == []
    assert result.degraded is True
    assert result.degraded_ids() == ("big.py",)
    assert "超长" in result.reason


def test_missing_results_degrades():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    client = _client(handler)
    result = client.redact_texts({"a.py": "x"})
    client.close()

    assert result.degraded is True
    assert result.redacted_map() == {}


def test_entities_type_mismatch_degrades():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": {"documents": [
            {"id": "a.py", "redactedText": "x", "entities": "nope"},
        ], "errors": []}})

    client = _client(handler)
    result = client.redact_texts({"a.py": "x"})
    client.close()

    assert result.degraded is True
    assert result.degraded_ids() == ("a.py",)
"""Step XML tool-call adapter tests; all cases are offline."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from codeark.models.factory import ModelProvider, ModelTier, make_model
from codeark.models.local_step import LocalStepModel
from codeark.models.xml_toolcall import extract_xml_tool_calls, repair_message

LT, GT = chr(60), chr(62)


def tag(name: str, body: str = "", attrs: str = "") -> str:
    return f"{LT}{name}{attrs}{GT}{body}{LT}/{name}{GT}"


def tool_block(*calls: str) -> str:
    return tag("tool_calls", "".join(calls))


def function_call(name: str, arguments: str, attrs: str = "") -> str:
    return tag("tool_call", tag("function", arguments, f' name="{name}"'), attrs=attrs)


def test_extract_json_arguments_and_preserve_surrounding_text():
    raw = "before\n" + tool_block(function_call("scan", '{"path":"src/a.py"}')) + "\nafter"
    result = extract_xml_tool_calls(raw)

    assert result.repaired is True
    assert "tool_calls" not in result.content
    assert "before" in result.content and "after" in result.content
    assert result.tool_calls[0]["function"]["name"] == "scan"
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"path": "src/a.py"}


def test_extract_typed_parameter_arguments():
    params = (
        tag("parameter", "7", ' name="limit" type="integer"')
        + tag("parameter", "true", ' name="deep" type="boolean"')
        + tag("parameter", '{"mode":"safe"}', ' name="options" type="json"')
    )
    result = extract_xml_tool_calls(tool_block(function_call("scan", params)))

    assert result.repaired is True
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {
        "limit": 7,
        "deep": True,
        "options": {"mode": "safe"},
    }


def test_extract_multiple_calls_get_deterministic_ids():
    raw = tool_block(function_call("first", "{}"), function_call("second", "{}"))
    result = extract_xml_tool_calls(raw)

    assert [call["id"] for call in result.tool_calls] == ["call_1", "call_2"]
    assert [call["function"]["name"] for call in result.tool_calls] == ["first", "second"]


def test_malformed_block_is_left_untouched():
    raw = tool_block(tag("tool_call", "missing function name"))
    result = extract_xml_tool_calls(raw)

    assert result.repaired is False
    assert result.content == raw
    assert result.tool_calls == []


def test_plain_text_is_not_repaired():
    raw = "The phrase tool_calls is discussed in this security note."
    result = extract_xml_tool_calls(raw)

    assert result == extract_xml_tool_calls(raw)
    assert result.repaired is False
    assert result.content == raw


def test_repair_message_moves_calls_to_openai_shape():
    message = SimpleNamespace(content=tool_block(function_call("scan", "{}")), tool_calls=None)

    assert repair_message(message) is True
    assert message.content is None
    assert message.tool_calls[0].id == "call_1"
    assert message.tool_calls[0].function.name == "scan"
    assert message.tool_calls[0].function.arguments == "{}"


def test_local_step_formats_repaired_response_as_strands_tool_event():
    message = SimpleNamespace(content=tool_block(function_call("scan", '{"path":"src/a.py"}')), tool_calls=None)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    model = LocalStepModel(
        model_id="step-test",
        client_args={"api_key": "local", "base_url": "http://127.0.0.1:8080/v1"},
    )

    events = model._format_non_streaming_response(response)
    tool_events = [event for event in events if "contentBlockStart" in event]

    assert model.get_config()["stream"] is False
    assert tool_events[0]["contentBlockStart"]["start"]["toolUse"]["name"] == "scan"
    assert any("src/a.py" in str(event) for event in events)


def test_factory_local_provider_is_offline_and_env_overridable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCAL_STEP_BASE_URL", "http://127.0.0.1:18080/v1")
    monkeypatch.setenv("LOCAL_STEP_MODEL", "step-local-test")
    monkeypatch.setenv("LOCAL_NEMO_BASE_URL", "http://127.0.0.1:18000/v1")
    monkeypatch.setenv("LOCAL_NEMO_MODEL", "nemo-local-test")

    step = make_model(ModelProvider.LOCAL_STEP, ModelTier.FLASH)
    nemo = make_model(ModelProvider.LOCAL_NEMO, ModelTier.PRO)

    assert isinstance(step, LocalStepModel)
    assert step.get_config()["model_id"] == "step-local-test"
    assert step.get_config()["stream"] is False
    assert step.client_args["base_url"] == "http://127.0.0.1:18080/v1"
    assert nemo.get_config()["model_id"] == "nemo-local-test"
    assert nemo.client_args["base_url"] == "http://127.0.0.1:18000/v1"


def test_extract_bare_tool_call_json_envelope():
    raw = tag("tool_call", '{"name":"scan","arguments":{"path":"src/a.py"}}')
    result = extract_xml_tool_calls(raw)

    assert result.repaired is True
    assert result.tool_calls[0]["function"]["name"] == "scan"
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"path": "src/a.py"}


def test_extract_name_and_arguments_child_tags():
    raw = tag("tool_call", tag("name", "scan") + tag("arguments", '{"path":"src/b.py"}'))
    result = extract_xml_tool_calls(raw)

    assert result.repaired is True
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"path": "src/b.py"}


def test_incomplete_outer_block_is_left_untouched():
    raw = "prefix" + tag("tool_calls", tag("tool_call", "unterminated"))[:-len(tag("tool_calls"))]
    result = extract_xml_tool_calls(raw)

    assert result.repaired is False
    assert result.content == raw
    assert result.tool_calls == []

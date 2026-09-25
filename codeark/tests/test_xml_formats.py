"""Offline tests for Qwen-XML / DeepSeek DSML tool-call normalization."""
from __future__ import annotations

import json
from types import SimpleNamespace

from codeark.models.xml_model import XMLToolCallModel
from codeark.models.xml_toolcall import extract_xml_tool_calls, repair_message


def test_qwen_inline_function_and_parameters() -> None:
    raw = (
        '<tool_call>\n<function=scan>\n'
        "<parameter=path>\nsrc/a.py\n</parameter>\n"
        '<parameter=limit type="integer">7</parameter>\n'
        "</function>\n</tool_call>"
    )
    result = extract_xml_tool_calls(raw, tool_format="qwen3_xml")

    assert result.repaired is True
    assert result.tool_calls[0]["function"]["name"] == "scan"
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {
        "path": "src/a.py",
        "limit": 7,
    }


def test_dsml_invoke_with_parameter_blocks() -> None:
    raw = (
        "<dsml:function_calls>\n"
        "<dsml:invoke name=\"scan\">\n"
        "<dsml:parameter name=\"path\">src/b.py</dsml:parameter>\n"
        '<dsml:parameter name="limit" type="integer">3</dsml:parameter>\n'
        "</dsml:invoke>\n"
        "</dsml:function_calls>"
    )
    result = extract_xml_tool_calls(raw, tool_format="dsml_xml")

    assert result.repaired is True
    assert result.tool_calls[0]["function"]["name"] == "scan"
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {
        "path": "src/b.py",
        "limit": 3,
    }


def test_dsml_inline_parameter_style() -> None:
    raw = (
        '<dsml:function_calls><dsml:invoke name="scan">'
        '<dsml:parameter="path">src/c.py</dsml:parameter>'
        "</dsml:invoke></dsml:function_calls>"
    )
    result = extract_xml_tool_calls(raw, tool_format="dsml_xml")

    assert result.repaired is True
    assert json.loads(result.tool_calls[0]["function"]["arguments"]) == {"path": "src/c.py"}


def test_dsml_marker_without_invoke_stays_untouched() -> None:
    raw = "<dsml:function_calls>truncated</dsml:function_calls>"
    result = extract_xml_tool_calls(raw, tool_format="dsml_xml")

    assert result.repaired is False
    assert result.content == raw
    assert result.tool_calls == []


def test_standard_format_still_parses_function_attribute() -> None:
    raw = '<tool_call><function name="scan">{"path":"src/a.py"}</function></tool_call>'
    result = extract_xml_tool_calls(raw)

    assert result.repaired is True
    assert result.tool_calls[0]["function"]["name"] == "scan"


def test_xml_model_repairs_qwen_response_into_tool_events() -> None:
    message = SimpleNamespace(
        content=(
            '<tool_call><function=scan><parameter=path>src/a.py</parameter></function></tool_call>'
        ),
        tool_calls=None,
    )
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    model = XMLToolCallModel(
        model_id="qwen-test",
        client_args={"api_key": "local", "base_url": "http://127.0.0.1:18080/v1"},
        tool_format="qwen3_xml",
    )

    events = model._format_non_streaming_response(response)

    assert model.get_config()["stream"] is False
    tool_events = [event for event in events if "contentBlockStart" in event]
    assert tool_events[0]["contentBlockStart"]["start"]["toolUse"]["name"] == "scan"
    assert any("src/a.py" in str(event) for event in events)


def test_repair_message_honors_tool_format_parameter() -> None:
    message = SimpleNamespace(
        content=(
            "<dsml:function_calls><dsml:invoke name=\"scan\">"
            '<dsml:parameter name="path">src/d.py</dsml:parameter>'
            "</dsml:invoke></dsml:function_calls>"
        ),
        tool_calls=None,
    )

    assert repair_message(message, tool_format="dsml_xml") is True
    assert message.tool_calls[0].function.name == "scan"
    assert message.content is None

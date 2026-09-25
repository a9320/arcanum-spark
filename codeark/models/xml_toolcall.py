"""Step/llama.cpp XML tool-call 输出到 OpenAI tool_calls 的纯函数适配器。"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace

_LT = chr(60)
_GT = chr(62)
_ESC_LT = re.escape(_LT)
_ESC_GT = re.escape(_GT)

_BLOCK_RE = re.compile(
    rf"{_ESC_LT}tool_calls\b[^>]*{_ESC_GT}(?P<body>.*?){_ESC_LT}/tool_calls{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_ITEM_RE = re.compile(
    rf"{_ESC_LT}tool_call\b(?P<attrs>[^>]*?){_ESC_GT}"
    rf"(?P<body>.*?){_ESC_LT}/tool_call{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_FUNCTION_OPEN_RE = re.compile(
    rf"{_ESC_LT}function\b(?P<attrs>[^>]*?){_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_FUNCTION_CLOSE_RE = re.compile(
    rf"{_ESC_LT}/function{_ESC_GT}", re.IGNORECASE,
)
_NAME_TAG_RE = re.compile(
    rf"{_ESC_LT}name{_ESC_GT}(?P<value>.*?){_ESC_LT}/name{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_ARGUMENTS_TAG_RE = re.compile(
    rf"{_ESC_LT}arguments{_ESC_GT}(?P<value>.*?){_ESC_LT}/arguments{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_PARAMETER_RE = re.compile(
    rf"{_ESC_LT}parameter\b(?P<attrs>[^>]*?){_ESC_GT}"
    rf"(?P<value>.*?){_ESC_LT}/parameter{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_ANY_TAG_RE = re.compile(rf"{_ESC_LT}/?[A-Za-z_][^>]*{_ESC_GT}", re.DOTALL)
_ATTR_RE = re.compile(
    r"\b(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*"
    r"(?P<quote>[\"']?)(?P<value>[^\"'\s>]+)(?P=quote)",
    re.IGNORECASE,
)
_INLINE_FUNCTION_RE = re.compile(
    rf"{_ESC_LT}function\s*=\s*(?P<quote>[\"']?)(?P<name>[^\"'\s>]+)(?P=quote)\s*{_ESC_GT}",
    re.IGNORECASE,
)
_INLINE_PARAMETER_RE = re.compile(
    rf"{_ESC_LT}parameter\s*=\s*(?P<quote>[\"']?)(?P<name>[^\"'\s>]+)(?P=quote)\s*{_ESC_GT}",
    re.IGNORECASE,
)
_INLINE_PARAMETER_BLOCK_RE = re.compile(
    rf"{_ESC_LT}parameter\s*=\s*(?P<quote>[\"']?)(?P<name>[^\"'\s>]+)(?P=quote)"
    rf"(?P<attrs>[^>]*){_ESC_GT}(?P<value>.*?){_ESC_LT}/parameter{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_DSML_INVOKE_RE = re.compile(
    rf"{_ESC_LT}(?P<open>[^>]*DSML[^>]*invoke)(?P<attrs>[^>]*){_ESC_GT}"
    rf"(?P<body>.*?)"
    rf"{_ESC_LT}/?(?P<close>[^>]*DSML[^>]*invoke)\s*{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_DSML_PARAMETER_BLOCK_RE = re.compile(
    rf"{_ESC_LT}(?P<open>[^>]*DSML[^>]*parameter)(?P<attrs>[^>]*){_ESC_GT}"
    rf"(?P<value>.*?)"
    rf"{_ESC_LT}/?(?P<close>[^>]*DSML[^>]*parameter)\s*{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)
_DSML_INLINE_PARAMETER_BLOCK_RE = re.compile(
    rf"{_ESC_LT}(?P<open>[^>]*DSML[^>]*parameter)\s*=\s*"
    rf"(?P<quote>[\"']?)(?P<name>[^\"'\s>]+)(?P=quote)\s*{_ESC_GT}"
    rf"(?P<value>.*?){_ESC_LT}/\s*(?P<close>[^>]*DSML[^>]*parameter)\s*{_ESC_GT}",
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class XMLToolCallResult:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    repaired: bool = False


def _attr(attrs: str, key: str) -> str | None:
    for match in _ATTR_RE.finditer(attrs):
        if match.group("key").lower() == key:
            return match.group("value")
    return None


def _coerce(value: str, type_name: str | None) -> tuple[bool, object]:
    text = html.unescape(value.strip())
    kind = (type_name or "string").lower()
    if kind in {"string", "text"}:
        return True, text
    if kind == "integer":
        try:
            return True, int(text)
        except ValueError:
            return False, None
    if kind == "number":
        try:
            return True, float(text) if any(c in text for c in ".eE") else int(text)
        except ValueError:
            return False, None
    if kind == "boolean":
        if text.lower() in {"true", "1", "yes"}:
            return True, True
        if text.lower() in {"false", "0", "no"}:
            return True, False
        return False, None
    if kind == "json":
        try:
            return True, json.loads(text)
        except json.JSONDecodeError:
            return False, None
    return True, text


def _json_object(raw: str) -> dict | None:
    try:
        value = json.loads(html.unescape(raw.strip()))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _normalize_inline_markup(text: str) -> tuple[str, str | None]:
    """Normalize Qwen-style ``<function=name>`` markup to the common shape."""
    inline_function = _INLINE_FUNCTION_RE.search(text)
    inline_name = html.unescape(inline_function.group("name").strip()) if inline_function else None
    text = _INLINE_FUNCTION_RE.sub("", text)

    def replace_parameter(match: re.Match[str]) -> str:
        name = html.escape(match.group("name"), quote=True)
        type_name = _attr(match.group("attrs"), "type")
        type_attr = f' type="{html.escape(type_name, quote=True)}"' if type_name else ""
        return f'<parameter name="{name}"{type_attr}>{match.group("value")}</parameter>'

    text = _INLINE_PARAMETER_BLOCK_RE.sub(replace_parameter, text)
    return text, inline_name


def _parse_item(body: str, attrs: str) -> dict | None:
    body, inline_name = _normalize_inline_markup(body)
    function = _FUNCTION_OPEN_RE.search(body)
    name = _attr(function.group("attrs"), "name") if function else None
    name = name or inline_name or _attr(attrs, "name")

    inner = _FUNCTION_OPEN_RE.sub("", body)
    inner = _FUNCTION_CLOSE_RE.sub("", inner).strip()
    name_tag = _NAME_TAG_RE.search(inner)
    if name_tag:
        name = name or html.unescape(name_tag.group("value").strip())

    arguments_tag = _ARGUMENTS_TAG_RE.search(inner)
    if arguments_tag:
        arguments = _json_object(arguments_tag.group("value"))
        if not name or arguments is None:
            return None
        return {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}

    envelope = _json_object(inner)
    if envelope is not None:
        if "arguments" in envelope:
            name = name or str(envelope.get("name") or "")
            raw_arguments = envelope.get("arguments")
            if isinstance(raw_arguments, dict):
                arguments = raw_arguments
            elif isinstance(raw_arguments, str):
                arguments = _json_object(raw_arguments)
            else:
                arguments = None
        else:
            arguments = envelope
        if not name or arguments is None:
            return None
        return {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}

    inner = _NAME_TAG_RE.sub("", inner).strip()
    matches = list(_PARAMETER_RE.finditer(inner))
    if not matches or not name:
        return None
    residue = _PARAMETER_RE.sub("", inner)
    if residue.strip() or _ANY_TAG_RE.search(residue):
        return None

    arguments: dict[str, object] = {}
    for match in matches:
        parameter_name = _attr(match.group("attrs"), "name")
        if not parameter_name or parameter_name in arguments:
            return None
        ok, value = _coerce(match.group("value"), _attr(match.group("attrs"), "type"))
        if not ok:
            return None
        arguments[parameter_name] = value
    return {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}


def _make_call(parsed: dict, index: int) -> dict:
    return {
        "id": f"call_{index}",
        "type": "function",
        "function": parsed,
    }


def _dsml_parameter_name(match: re.Match[str]) -> str | None:
    groups = match.groupdict()
    inline_name = groups.get("name")
    if inline_name:
        return html.unescape(inline_name.strip())
    attrs = groups.get("attrs") or ""
    name = _attr(attrs, "name") or _attr(attrs, "function")
    return html.unescape(name) if name else None


def _parse_dsml_invoke(match: re.Match[str]) -> dict | None:
    attrs = f"{match.group('open')} {match.group('attrs')}"
    name = _attr(attrs, "name") or _attr(attrs, "function")
    if not name:
        return None
    body = match.group("body")
    parameter_matches = [
        m for m in _DSML_PARAMETER_BLOCK_RE.finditer(body) if _dsml_parameter_name(m)
    ]
    if not parameter_matches:
        parameter_matches = [
            m for m in _DSML_INLINE_PARAMETER_BLOCK_RE.finditer(body) if _dsml_parameter_name(m)
        ]
    if not parameter_matches:
        return None

    residue = body
    arguments: dict[str, object] = {}
    for parameter in parameter_matches:
        parameter_name = _dsml_parameter_name(parameter)
        if not parameter_name or parameter_name in arguments:
            return None
        parameter_attrs = parameter.groupdict().get("attrs") or ""
        value = parameter.groupdict().get("value") or ""
        # DeepSeek DSML commonly carries scalar values in string="...".
        if not value.strip():
            value = _attr(parameter_attrs, "string") or _attr(parameter_attrs, "value") or ""
        ok, coerced = _coerce(value, _attr(parameter_attrs, "type"))
        if not ok:
            return None
        arguments[parameter_name] = coerced
        residue = residue.replace(parameter.group(0), "", 1)
    if residue.strip():
        return None
    return {"name": html.unescape(name), "arguments": json.dumps(arguments, ensure_ascii=False)}


def _extract_dsml_tool_calls(text: str) -> XMLToolCallResult:
    invokes = list(_DSML_INVOKE_RE.finditer(text))
    marker = re.search(r"DSML[^>]*function_calls|function_calls[^>]*DSML", text, re.IGNORECASE)
    if marker and not invokes:
        return XMLToolCallResult(content=text)
    if not invokes:
        return XMLToolCallResult(content=text)

    calls: list[dict] = []
    for invoke in invokes:
        parsed = _parse_dsml_invoke(invoke)
        if parsed is None:
            return XMLToolCallResult(content=text)
        calls.append(_make_call(parsed, len(calls) + 1))

    content = _DSML_INVOKE_RE.sub("", text)
    content = re.sub(
        rf"{_ESC_LT}/?[^>]*DSML[^>]*function_calls[^>]*{_ESC_GT}",
        "",
        content,
        flags=re.IGNORECASE,
    ).strip()
    return XMLToolCallResult(content=content, tool_calls=calls, repaired=True)


def _extract_standard_tool_calls(text: str) -> XMLToolCallResult:
    outer_blocks = list(_BLOCK_RE.finditer(text))
    has_outer_marker = re.search(rf"{_ESC_LT}tool_calls\b", text, re.IGNORECASE)
    if has_outer_marker and not outer_blocks:
        return XMLToolCallResult(content=text)

    calls: list[dict] = []
    if outer_blocks:
        for block in outer_blocks:
            items = list(_ITEM_RE.finditer(block.group("body")))
            if not items:
                return XMLToolCallResult(content=text)
            for item in items:
                parsed = _parse_item(item.group("body"), item.group("attrs"))
                if parsed is None:
                    return XMLToolCallResult(content=text)
                calls.append(_make_call(parsed, len(calls) + 1))
        content = _BLOCK_RE.sub("", text).strip()
    else:
        items = list(_ITEM_RE.finditer(text))
        if not items:
            return XMLToolCallResult(content=text)
        for item in items:
            parsed = _parse_item(item.group("body"), item.group("attrs"))
            if parsed is None:
                return XMLToolCallResult(content=text)
            calls.append(_make_call(parsed, len(calls) + 1))
        content = _ITEM_RE.sub("", text).strip()

    return XMLToolCallResult(content=content, tool_calls=calls, repaired=True)


def extract_xml_tool_calls(text: str, tool_format: str = "standard_xml") -> XMLToolCallResult:
    """Extract standard, Qwen-XML, or DeepSeek DSML tool calls.

    Malformed or incomplete input is returned unchanged so a caller can still
    expose the original model evidence instead of inventing a partial call.
    """
    if not isinstance(text, str):
        return XMLToolCallResult(content=text)
    if tool_format.lower() == "dsml_xml":
        result = _extract_dsml_tool_calls(text)
        if result.repaired:
            return result
    return _extract_standard_tool_calls(text)


def repair_message(message: object, *, tool_format: str = "standard_xml") -> bool:
    """Move XML calls from an OpenAI-like message into message.tool_calls in place."""
    if message is None or getattr(message, "tool_calls", None):
        return False
    result = extract_xml_tool_calls(getattr(message, "content", None) or "", tool_format=tool_format)
    if not result.repaired:
        return False
    calls = [
        SimpleNamespace(
            id=item["id"],
            type=item["type"],
            function=SimpleNamespace(**item["function"]),
        )
        for item in result.tool_calls
    ]
    message.content = result.content or None
    message.tool_calls = calls
    return True


__all__ = ["XMLToolCallResult", "extract_xml_tool_calls", "repair_message"]

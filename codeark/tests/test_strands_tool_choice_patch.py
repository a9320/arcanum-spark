"""strands tool_choice 形态修正的护栏测试（2026-11-02 实锤）。

背景：llama.cpp 的 OpenAI 兼容层只接受字符串 tool_choice；strands 在
structured_output 场景把"指定工具"格式化成 dict，llama-server 记
"W Wrong type supplied for parameter 'tool_choice'" 并静默回落 auto
（srv_gemma.log 34 次实证）。factory 导入时把 dict 形态改写为 "required"。
"""

from __future__ import annotations

import pytest

pytest.importorskip("strands", reason="纯确定性套件不含 strands")

import codeark.models.factory  # noqa: E402,F401 — 导入即触发 patch


def test_tool_choice_patch_installed() -> None:
    from strands.models.openai import OpenAIModel

    raw = OpenAIModel.__dict__["_format_request_tool_choice"]
    func = getattr(raw, "__func__", raw)
    assert getattr(func, "_arca_llamacpp_patched", False), "patch 未安装"


def test_tool_choice_dict_becomes_required() -> None:
    from strands.models.openai import OpenAIModel

    out = OpenAIModel._format_request_tool_choice({"tool": {"name": "FinalReport"}})
    assert out == {"tool_choice": "required"}, "指定工具的 dict 形态必须改写为 required"


def test_tool_choice_auto_and_none_unchanged() -> None:
    from strands.models.openai import OpenAIModel

    assert OpenAIModel._format_request_tool_choice(None) == {}
    assert OpenAIModel._format_request_tool_choice({"auto": {}}) == {"tool_choice": "auto"}
    assert OpenAIModel._format_request_tool_choice({"any": {}}) == {"tool_choice": "required"}


def test_tool_choice_patch_idempotent() -> None:
    from strands.models.openai import OpenAIModel

    before = OpenAIModel.__dict__["_format_request_tool_choice"]
    codeark.models.factory._patch_strands_tool_choice_for_llamacpp()
    after = OpenAIModel.__dict__["_format_request_tool_choice"]
    assert before is after, "重复调用不应重复包装"
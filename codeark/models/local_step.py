"""Step 3.7 Flash 本地模型适配器。

llama-server 返回 XML 工具调用时，OpenAIModel 仍会把它当普通文本。
本适配器强制非流式完整响应，在 Strands 格式化前迁移 XML tool_calls。
"""
from __future__ import annotations

from typing import Any

from strands.models import OpenAIModel

from .xml_toolcall import repair_message


class LocalStepModel(OpenAIModel):
    """OpenAIModel 的 Step XML tool-call 兼容实现。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("config", None)
        kwargs["stream"] = False
        super().__init__(*args, **kwargs)

    def _format_non_streaming_response(self, response: Any) -> list[dict]:
        choices = getattr(response, "choices", None) or []
        if choices:
            repair_message(getattr(choices[0], "message", None))
        return super()._format_non_streaming_response(response)


__all__ = ["LocalStepModel"]

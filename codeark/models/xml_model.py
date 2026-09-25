"""OpenAI-compatible model wrapper for non-JSON tool-call text formats."""
from __future__ import annotations

from typing import Any

from strands.models import OpenAIModel

from .xml_toolcall import repair_message


class XMLToolCallModel(OpenAIModel):
    """Force complete responses and normalize XML-like tool calls."""

    def __init__(self, *args: Any, tool_format: str = "standard_xml", **kwargs: Any) -> None:
        kwargs.pop("config", None)
        kwargs["stream"] = False
        self.tool_format = tool_format
        super().__init__(*args, **kwargs)

    def _format_non_streaming_response(self, response: Any) -> list[dict]:
        choices = getattr(response, "choices", None) or []
        for choice in choices:
            repair_message(getattr(choice, "message", None), tool_format=self.tool_format)
        return super()._format_non_streaming_response(response)


__all__ = ["XMLToolCallModel"]

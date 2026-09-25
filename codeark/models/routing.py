"""Stage-level model routing and endpoint configuration primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

__all__ = ["EndpointConfig", "StageModels", "redact_error"]

_STAGE_NAMES = {"scout", "verify", "deepen", "arbiter"}
_API_STYLES = {"chat_completions", "responses"}


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """Validated OpenAI-compatible endpoint settings.

    ``api_key`` is intentionally excluded from repr output so accidental debug
    logging cannot expose credentials.
    """

    model_id: str
    base_url: str
    api_key: str = field(repr=False)
    timeout: float = 180.0
    api_style: str = "chat_completions"
    tool_format: str = "standard_json"
    structured_output_support: str = "json_schema"
    reasoning_effort: str = "default"

    def __post_init__(self) -> None:
        model_id = self.model_id.strip() if isinstance(self.model_id, str) else ""
        base_url = self.base_url.strip() if isinstance(self.base_url, str) else ""
        api_key = self.api_key.strip() if isinstance(self.api_key, str) else ""
        api_style = self.api_style.strip().lower() if isinstance(self.api_style, str) else ""
        tool_format = self.tool_format.strip().lower() if isinstance(self.tool_format, str) else ""
        structured = (
            self.structured_output_support.strip().lower()
            if isinstance(self.structured_output_support, str)
            else ""
        )
        reasoning = self.reasoning_effort.strip().lower() if isinstance(self.reasoning_effort, str) else ""
        if not model_id:
            raise ValueError("model_id must not be empty")
        if not api_key:
            raise ValueError("api_key must not be empty")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        if api_style not in _API_STYLES:
            raise ValueError("api_style must be chat_completions or responses")
        if not tool_format:
            raise ValueError("tool_format must not be empty")
        if not structured:
            raise ValueError("structured_output_support must not be empty")
        if not reasoning:
            raise ValueError("reasoning_effort must not be empty")
        try:
            timeout = float(self.timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError("timeout must be a finite number greater than 0") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite number greater than 0")

        path = parsed.path.rstrip("/")
        if not path:
            path = "/v1"
        normalized = parsed._replace(path=path, params="", query="", fragment="").geturl()
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "base_url", normalized.rstrip("/"))
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "timeout", timeout)
        object.__setattr__(self, "api_style", api_style)
        object.__setattr__(self, "tool_format", tool_format)
        object.__setattr__(self, "structured_output_support", structured)
        object.__setattr__(self, "reasoning_effort", reasoning)


@dataclass(frozen=True, slots=True)
class StageModels:
    """Optional model instances for the four LLM stages.

    A missing stage-specific model falls back to the legacy shared model. If
    both are missing, the stage keeps its existing internal provider fallback.
    """

    scout: Any | None = None
    verify: Any | None = None
    deepen: Any | None = None
    arbiter: Any | None = None
    scout_fallback: Any | None = None

    def resolve(self, stage: str, shared_model: Any | None = None) -> Any | None:
        if stage not in _STAGE_NAMES:
            raise ValueError(f"unknown model stage: {stage}")
        specific = getattr(self, stage)
        return specific if specific is not None else shared_model

    def fallback(self, stage: str) -> Any | None:
        if stage not in _STAGE_NAMES:
            raise ValueError(f"unknown model stage: {stage}")
        return self.scout_fallback if stage == "scout" else None


def redact_error(error: BaseException | str, *secrets: str) -> str:
    """Return a short error string without credentials or authorization headers."""
    text = str(error)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    import re

    text = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(api[_ -]?key\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:sk|ak|org)-[A-Za-z0-9_\-]{8,}", "[REDACTED]", text)
    return text[:1000]

"""Stage-level model routing and endpoint configuration primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

__all__ = ["EndpointConfig", "StageModels", "StageTuning", "redact_error"]

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
    # Optional per-request output cap merged into chat-completions params
    # (llama.cpp n_predict / OpenAI max_tokens). None = server default.
    max_tokens: float | None = None
    # Optional sampling temperature merged into chat-completions params
    # (0.0-2.0). None = server default; low values stabilize recon/judging.
    temperature: float | None = None

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
        max_tokens = self.max_tokens
        temperature = self.temperature
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
        if max_tokens is not None:
            try:
                max_tokens = float(max_tokens)  # type: ignore[assignment]
            except (TypeError, ValueError) as exc:
                raise ValueError("max_tokens must be a finite number greater than 0") from exc
            if not math.isfinite(max_tokens) or max_tokens <= 0:  # type: ignore[operator]
                raise ValueError("max_tokens must be a finite number greater than 0")
        if temperature is not None:
            try:
                temperature = float(temperature)  # type: ignore[assignment]
            except (TypeError, ValueError) as exc:
                raise ValueError("temperature must be a finite number within [0, 2]") from exc
            if not math.isfinite(temperature) or not 0 <= temperature <= 2:  # type: ignore[operator]
                raise ValueError("temperature must be a finite number within [0, 2]")

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
        object.__setattr__(self, "max_tokens", max_tokens)
        object.__setattr__(self, "temperature", temperature)


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


@dataclass(frozen=True, slots=True)
class StageTuning:
    """Loop-stage invocation tuning (verify/deepen run one call per item).

    ``*_concurrency`` caps simultaneous model calls per stage (1 = serial);
    ``*_delay`` spaces request start times (rate-limit politeness);
    ``*_timeout`` is the per-invoke watchdog for providers that hang past the
    client timeout. Defaults stay serial — enable concurrency only after a
    probe confirms the endpoint tolerates it (e.g. 2026-09-12 AMD free tier
    returned 503 no_available_workers at concurrency 2).
    """

    verify_concurrency: int = 1
    verify_delay: float = 1.0
    verify_timeout: float = 360.0
    deepen_concurrency: int = 1
    deepen_delay: float = 1.0
    deepen_timeout: float = 360.0

    def __post_init__(self) -> None:
        for name in ("verify_concurrency", "deepen_concurrency"):
            try:
                value = int(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer >= 1") from exc
            if value < 1:
                raise ValueError(f"{name} must be an integer >= 1")
            object.__setattr__(self, name, value)
        for name in ("verify_delay", "deepen_delay"):
            try:
                value = float(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite number >= 0") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite number >= 0")
            object.__setattr__(self, name, value)
        for name in ("verify_timeout", "deepen_timeout"):
            try:
                value = float(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite number > 0") from exc
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite number > 0")
            object.__setattr__(self, name, value)


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

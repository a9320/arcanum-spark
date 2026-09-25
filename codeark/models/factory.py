"""统一模型工厂 — 支持云端 GLM / Kimi / DeepSeek / Qwen 与本地 Step / Nemotron 路由。

Agent 分层分配（2026-09-12 调整：异构合议 + Kimi 配额耗尽后降级 + AMD 目录实测修正）：
- Scout (1):   GLM-5.3（TokenRouter 免费档；docstring 曾写 5.2，实际 model_id 早已是 5.3）
- Verify (2):  DeepSeek-V4-Flash（主判，AMD 免费；AMD 目录无 V4-Pro，models.list 实测）
- Deepen (3):  DeepSeek-V4-Flash（主力）
- Arbiter (4): GLM-5.3（§11-G：与 Scout 同源、与 Verify/Deepen 异构的去相关第二票）
- Fallback:    Kimi-K3（余额耗尽，充值后恢复备选）/ GLM / Qwen-3.8-Flash-Next

架构：保留 OpenAIModel（Strands SDK），通过 base_url/model_id 路由到不同 provider。

本地部署：ARCA_DEPLOYMENT=local 时四阶段直连本机 llama-server（MI300X 四模型拓扑，
端口表见 _LOCAL_ROUTE_DEFAULTS）；构造零网络，连通性由运行时管线降级兜底。
"""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from strands.models import OpenAIModel, OpenAIResponsesModel

from .local_step import LocalStepModel
from .routing import EndpointConfig, StageModels, StageTuning
from .xml_model import XMLToolCallModel

__all__ = [
    "EndpointConfig",
    "ModelProvider",
    "ModelTier",
    "StageModels",
    "StageTuning",
    "get_key",
    "make_model",
    "make_openai_compatible_model",
    "make_stage_models_from_env",
    "make_stage_tuning_from_env",
]


# ── 枚举 ──

class ModelProvider(str, Enum):
    """支持的 API provider。"""
    GLM = "glm"           # TokenRouter（GLM-5.3，OpenAI 兼容）
    KIMI = "kimi"         # Moonshot Kimi-K3
    DEEPSEEK = "deepseek" # AMD Radeon Cloud (DeepSeek-V4-Flash)
    QWEN = "qwen"         # AMD Radeon Cloud (Qwen-3.8-Flash-Next)
    AMD = "amd"           # AMD Radeon Cloud 通用入口（兼容旧名）
    LOCAL_STEP = "local_step"  # Step-3.7 Flash llama-server（默认 :8080）
    LOCAL_NEMO = "local_nemo"  # Nemotron vLLM/SGLang（默认 :8000）


class ModelTier(str, Enum):
    """模型能力档位。"""
    FLASH = "flash"   # 低成本/快速（Scout 首选）
    PRO = "pro"       # 高质量/强推理（Verify/Deepen/Arbiter）


# ── API Key 读取 ──

def _extract_key(raw: str) -> str:
    """从 key 文件内容里提取真正的 key 值。

    兼容两种格式：
    1. 纯 key（整个文件就是 key）；
    2. 带标签的多行文件，如：
           Base URL：https://...
           Key：sk-xxxx
       此时提取 "Key：" 后面的值。
    """
    text = raw.strip()
    # 按行扫描，找含 "key" / "Key：" 的行
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("key") or "key：" in low or "key:" in low:
            # 去掉标签部分（支持中英文冒号）
            for sep in ("：", ":"):
                if sep in line:
                    candidate = line.split(sep, 1)[1].strip()
                    # 去掉可能的引号
                    candidate = candidate.strip().strip("'\"")
                    if candidate:
                        return candidate
    # 没有标签：若只有一行直接用；多行则取最像 key 的那行
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) == 1:
        return lines[0]
    for l in lines:
        if l.startswith(("sk-", "rc-", "Bearer")):
            return l.replace("Bearer", "").strip()
    return lines[0] if lines else ""


def _read_key(filename: str) -> str:
    """跨环境读取 API Key 文件（WSL / Windows 双路径）。"""
    candidates = [
        Path(f"/mnt/d/API Key/{filename}"),
        Path(f"D:/API Key/{filename}"),
    ]
    for p in candidates:
        if p.exists():
            return _extract_key(p.read_text(encoding="utf-8-sig"))
    raise FileNotFoundError(
        f"找不到 key 文件 '{filename}'，已尝试: {[str(c) for c in candidates]}"
    )


# 创空间等没有本地 key 文件的环境：环境变量优先（空间设置页配置，保存后不可回查）
_ENV_KEY = {
    ModelProvider.GLM: "TOKENROUTER_API_KEY",
    ModelProvider.KIMI: "MOONSHOT_API_KEY",
    ModelProvider.DEEPSEEK: "AMD_API_KEY",
    ModelProvider.QWEN: "AMD_API_KEY",
    ModelProvider.AMD: "AMD_API_KEY",
    ModelProvider.LOCAL_STEP: "LOCAL_API_KEY",
    ModelProvider.LOCAL_NEMO: "LOCAL_API_KEY",
}


def get_key(provider: ModelProvider) -> str:
    """按 provider 返回对应的 API Key（环境变量优先，其次本地 key 文件）。"""
    env_name = _ENV_KEY.get(provider)
    if env_name:
        env_value = os.environ.get(env_name, "").strip()
        if env_value:
            return env_value
    if provider in (ModelProvider.LOCAL_STEP, ModelProvider.LOCAL_NEMO):
        return "local"
    mapping = {
        ModelProvider.GLM: "my-tokenrouter.txt",
        ModelProvider.KIMI: "my-kimi-key.txt",
        ModelProvider.DEEPSEEK: "Radeon Cloud.txt",
        ModelProvider.QWEN: "Radeon Cloud.txt",
        ModelProvider.AMD: "Radeon Cloud.txt",
    }
    return _read_key(mapping[provider])


# ── 模型路由表 ──

_MODEL_MAP: dict[tuple[ModelProvider, ModelTier], dict[str, str]] = {
    # GLM-5.3 系列（TokenRouter，OpenAI 兼容）
    (ModelProvider.GLM, ModelTier.FLASH): {
        "model_id": "z-ai/glm-5.3-free",
        "base_url": "https://api.tokenrouter.com/v1",
        "timeout": 120.0,
    },
    (ModelProvider.GLM, ModelTier.PRO): {
        "model_id": "z-ai/glm-5.3-free",
        "base_url": "https://api.tokenrouter.com/v1",
        "timeout": 180.0,
    },
    # Kimi-K3 系列（Moonshot，OpenAI 兼容）
    (ModelProvider.KIMI, ModelTier.FLASH): {
        "model_id": "kimi-k3",
        "base_url": "https://api.moonshot.cn/v1",
        "timeout": 120.0,
    },
    (ModelProvider.KIMI, ModelTier.PRO): {
        "model_id": "kimi-k3",
        "base_url": "https://api.moonshot.cn/v1",
        "timeout": 180.0,
    },
    # DeepSeek 系列（AMD Radeon Cloud；实测目录仅 Flash 档，V4-Pro 不存在——2026-09-12 models.list 验证）
    (ModelProvider.DEEPSEEK, ModelTier.FLASH): {
        "model_id": "DeepSeek-V4-Flash",
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "timeout": 180.0,
    },
    (ModelProvider.DEEPSEEK, ModelTier.PRO): {
        "model_id": "DeepSeek-V4-Flash",  # AMD 最强 DeepSeek 即 Flash；PRO 语义=验证/深挖主判档
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "timeout": 300.0,
    },
    # Qwen-3.8-Flash-Next（AMD Radeon Cloud）
    (ModelProvider.QWEN, ModelTier.FLASH): {
        "model_id": "Qwen3.8-Flash-Next",
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "timeout": 180.0,
    },
    (ModelProvider.QWEN, ModelTier.PRO): {
        "model_id": "Qwen3.8-Flash-Next",
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "timeout": 300.0,
    },
    # AMD 通用（DeepSeek-V4-Flash 免费）
    (ModelProvider.AMD, ModelTier.FLASH): {
        "model_id": "DeepSeek-V4-Flash",
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "timeout": 180.0,
    },
    # 本地 Step-3.7 Flash：llama-server 默认 8080；实际 model id 可由环境变量覆盖
    (ModelProvider.LOCAL_STEP, ModelTier.FLASH): {
        "model_id": "Step-3.7-Flash",
        "base_url": "http://127.0.0.1:8080/v1",
        "timeout": 600.0,
    },
    (ModelProvider.LOCAL_STEP, ModelTier.PRO): {
        "model_id": "Step-3.7-Flash",
        "base_url": "http://127.0.0.1:8080/v1",
        "timeout": 900.0,
    },
    # 本地 Nemotron：vLLM/SGLang 默认 8000；OpenAI 兼容标准 tool_calls
    (ModelProvider.LOCAL_NEMO, ModelTier.FLASH): {
        "model_id": "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4",
        "base_url": "http://127.0.0.1:8000/v1",
        "timeout": 600.0,
    },
    (ModelProvider.LOCAL_NEMO, ModelTier.PRO): {
        "model_id": "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4",
        "base_url": "http://127.0.0.1:8000/v1",
        "timeout": 900.0,
    },
}


# ── 工厂函数 ──

def make_model(
    provider: ModelProvider | str = ModelProvider.GLM,
    tier: ModelTier | str = ModelTier.FLASH,
) -> OpenAIModel:
    """按 provider/tier 构造 OpenAIModel。

    推荐用法（Weike 定稿 2026-09-09）：
        - Scout:        make_model(ModelProvider.GLM, ModelTier.FLASH)   # GLM-5.2
        - Verify:       make_model(ModelProvider.KIMI, ModelTier.PRO)    # Kimi-K3
        - Deepen:       make_model(ModelProvider.KIMI, ModelTier.PRO)    # Kimi-K3
        - Arbiter:      make_model(ModelProvider.KIMI, ModelTier.PRO)    # Kimi-K3
        - Fallback:     make_model(ModelProvider.AMD, ModelTier.FLASH)   # DeepSeek-V4-Flash 免费
    """
    if isinstance(provider, str):
        provider = ModelProvider(provider)
    if isinstance(tier, str):
        tier = ModelTier(tier)

    config = _MODEL_MAP.get((provider, tier))
    if not config:
        raise ValueError(
            f"不支持的组合: provider={provider.value}, tier={tier.value}\n"
            f"支持: {list(_MODEL_MAP.keys())}"
        )

    runtime = dict(config)
    env_overrides = {
        ModelProvider.LOCAL_STEP: ("LOCAL_STEP_MODEL", "LOCAL_STEP_BASE_URL"),
        ModelProvider.LOCAL_NEMO: ("LOCAL_NEMO_MODEL", "LOCAL_NEMO_BASE_URL"),
    }
    model_env, url_env = env_overrides.get(provider, (None, None))
    if model_env:
        runtime["model_id"] = os.environ.get(model_env, "").strip() or runtime["model_id"]
    if url_env:
        runtime["base_url"] = os.environ.get(url_env, "").strip() or runtime["base_url"]

    api_key = get_key(provider)
    kwargs = {
        "model_id": runtime["model_id"],
        "client_args": {
            "base_url": runtime["base_url"],
            "api_key": api_key,
            "timeout": runtime["timeout"],
        },
    }
    if provider is ModelProvider.LOCAL_STEP:
        return LocalStepModel(**kwargs)
    return OpenAIModel(**kwargs)


# ── 通用 OpenAI-compatible API ──

def _reasoning_params(endpoint: EndpointConfig) -> dict[str, object]:
    effort = endpoint.reasoning_effort
    if effort in {"", "default"}:
        return {}
    if endpoint.api_style == "responses":
        return {"reasoning": {"effort": effort}}
    return {"reasoning_effort": effort}


def make_openai_compatible_model(
    model_id: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    *,
    endpoint: EndpointConfig | None = None,
    api_style: str = "chat_completions",
    tool_format: str = "standard_json",
    structured_output_support: str = "json_schema",
    reasoning_effort: str = "default",
) -> OpenAIModel:
    """Construct a configured Chat Completions or Responses model.

    Construction performs no network request. XML-like tool formats use a
    non-streaming wrapper so the complete payload can be normalized before
    Strands formats tool events.
    """
    if endpoint is not None:
        if any(
            value is not None
            for value in (model_id, base_url, api_key, timeout)
        ) or any(
            value != default
            for value, default in (
                (api_style, "chat_completions"),
                (tool_format, "standard_json"),
                (structured_output_support, "json_schema"),
                (reasoning_effort, "default"),
            )
        ):
            raise ValueError("pass either endpoint or individual model settings, not both")
    else:
        missing = [
            name
            for name, value in (
                ("model_id", model_id),
                ("base_url", base_url),
                ("api_key", api_key),
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"missing model settings: {', '.join(missing)}")
        endpoint = EndpointConfig(
            model_id=model_id or "",
            base_url=base_url or "",
            api_key=api_key or "",
            timeout=180.0 if timeout is None else timeout,
            api_style=api_style,
            tool_format=tool_format,
            structured_output_support=structured_output_support,
            reasoning_effort=reasoning_effort,
        )

    params = _reasoning_params(endpoint)
    if endpoint.api_style == "chat_completions" and endpoint.max_tokens is not None:
        params["max_tokens"] = int(endpoint.max_tokens)
    if endpoint.api_style == "chat_completions" and endpoint.temperature is not None:
        params["temperature"] = float(endpoint.temperature)
    client_args = {
        "base_url": endpoint.base_url,
        "api_key": endpoint.api_key,
        "timeout": endpoint.timeout,
    }
    if endpoint.api_style == "responses":
        return OpenAIResponsesModel(
            model_id=endpoint.model_id,
            params=params,
            client_args=client_args,
        )
    if endpoint.tool_format not in {"", "standard_json", "json"}:
        return XMLToolCallModel(
            model_id=endpoint.model_id,
            params=params,
            client_args=client_args,
            tool_format=endpoint.tool_format,
        )
    return OpenAIModel(
        model_id=endpoint.model_id,
        params=params,
        client_args=client_args,
    )


_ARCA_STAGES = ("scout", "verify", "deepen", "arbiter")
_ARCA_REQUIRED_FIELDS = ("MODEL", "BASE_URL", "API_KEY")
_ARCA_ALL_FIELDS = (*_ARCA_REQUIRED_FIELDS, "TIMEOUT")
_ARCA_DEFAULT_TIMEOUT = 180.0

# Non-sensitive defaults supplied for the current API test topology. Keys are
# never embedded here; only their environment variable names are recorded.
_REMOTE_ROUTE_DEFAULTS: dict[str, dict[str, object]] = {
    "scout": {
        "model_id": "step-5-preview",
        "base_url": "https://api.stepfun.com",
        "api_style": "chat_completions",
        # 2026-09-25 实测：StepFun 服务端已在 API 层把 step3p5 XML 归一化为标准
        # tool_calls，远程路径走 standard_json；step3p5_xml 仅本地 llama.cpp 需要。
        "tool_format": "standard_json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "medium",
        "timeout": 120.0,
        "key_env": "ARCA_SCOUT_PRIMARY_API_KEY",
    },
    "scout_fallback": {
        "model_id": "gpt-5.6-luna",
        "base_url": "https://api.lmuai.ai",
        "api_style": "responses",
        "tool_format": "json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "none",
        "timeout": 60.0,
        "key_env": "ARCA_SCOUT_FALLBACK_API_KEY",
    },
    "verify": {
        "model_id": "Qwen3.8-Flash-Next",
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "api_style": "chat_completions",
        # 2026-09-25 实测：AMD 服务端已配 qwen3_xml 解析器，API 返回标准 tool_calls。
        "tool_format": "standard_json",

        "structured_output_support": "json_schema",
        "reasoning_effort": "default",
        "timeout": 120.0,
        "key_env": "ARCA_VERIFY_API_KEY",
    },
    "deepen": {
        "model_id": "DeepSeek-V4-Flash",
        "base_url": "https://developer.amd.com.cn/radeon/api/v1",
        "api_style": "chat_completions",
        # 2026-09-25 实测：DSML 在服务端已归一化，API 返回标准 tool_calls。
        "tool_format": "standard_json",

        "structured_output_support": "json_object",
        "reasoning_effort": "high",
        "timeout": 180.0,
        "key_env": "ARCA_DEEPEN_API_KEY",
    },
    "arbiter": {
        "model_id": "gpt-6-sol",
        "base_url": "https://api.lmuai.ai",
        "api_style": "responses",
        "tool_format": "json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "high",
        "timeout": 180.0,
        "key_env": "ARCA_ARBITER_API_KEY",
    },
}


def _env_text(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_env_timeout(name: str, value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number greater than 0") from exc


def _parse_env_int(name: str, value: str | None, default: int | None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _parse_env_float(name: str, value: str | None, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc


def _route_override(prefix: str, field: str, default: object) -> object:
    env_name = f"{prefix}_{field}"
    value = _env_text(env_name)
    if value is None:
        return default
    if field == "TIMEOUT":
        return _parse_env_timeout(env_name, value, float(default))  # type: ignore[arg-type]
    if field == "MAX_TOKENS":
        return _parse_env_int(env_name, value, default)  # type: ignore[arg-type]
    if field == "TEMPERATURE":
        return _parse_env_float(env_name, value, default)  # type: ignore[arg-type]
    return value


def _endpoint_from_named_route(name: str) -> EndpointConfig | None:
    spec = _REMOTE_ROUTE_DEFAULTS[name]
    key_env = str(spec["key_env"])
    api_key = _env_text(key_env)
    if not api_key:
        return None
    prefix = f"ARCA_{name.upper()}"
    return EndpointConfig(
        model_id=str(_route_override(prefix, "MODEL", spec["model_id"])),
        base_url=str(_route_override(prefix, "BASE_URL", spec["base_url"])),
        api_key=api_key,
        timeout=float(_route_override(prefix, "TIMEOUT", spec["timeout"])),
        api_style=str(_route_override(prefix, "API_STYLE", spec["api_style"])),
        tool_format=str(_route_override(prefix, "TOOL_FORMAT", spec["tool_format"])),
        structured_output_support=str(
            _route_override(prefix, "STRUCTURED_OUTPUT_SUPPORT", spec["structured_output_support"])
        ),
        reasoning_effort=str(_route_override(prefix, "REASONING_EFFORT", spec["reasoning_effort"])),
    )


# Local MI300X topology (2026-09-25 四服务上线): one llama-server per stage on
# loopback, all started with --jinja so tool calls arrive as standard tool_calls.
# Ports follow /root/start-arcanum.sh (8082 is taken by a platform process, so
# verify sits on 8182). api_key is a placeholder — llama-server ignores auth.
_LOCAL_ROUTE_DEFAULTS: dict[str, dict[str, object]] = {
    "scout": {
        "model_id": "muse-scout",
        "base_url": "http://127.0.0.1:8081/v1",
        "api_style": "chat_completions",
        "tool_format": "standard_json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "default",
        "timeout": 300.0,
        "max_tokens": None,
        # 2026-09-25 e2e 复跑实测：temp=1.0 下 Muse 采样波动会导致假设回显
        # （12 条规则回显 vs 3 条语义增量，e2e 40m35s vs 10m07s）——Scout 绑低
        # 温度稳定侦察行为；覆盖用 ARCA_SCOUT_TEMPERATURE。
        "temperature": 0.2,
    },
    "verify": {
        "model_id": "qwen-verify",
        "base_url": "http://127.0.0.1:8182/v1",
        "api_style": "chat_completions",
        "tool_format": "standard_json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "default",
        "timeout": 300.0,
        "max_tokens": None,
        "temperature": None,
    },
    "deepen": {
        "model_id": "r1-deepen",
        "base_url": "http://127.0.0.1:8083/v1",
        "api_style": "chat_completions",
        "tool_format": "standard_json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "default",
        # 2026-09-25 冒烟③：R1@2000 预算出合法攻击链 JSON；低于此值 reasoning
        # 挤占 content 预算导致截断。覆盖用 ARCA_DEEPEN_MAX_TOKENS。
        "timeout": 600.0,
        "max_tokens": 2000,
        "temperature": None,
    },
    "arbiter": {
        "model_id": "gemma-arbiter",
        "base_url": "http://127.0.0.1:8084/v1",
        "api_style": "chat_completions",
        "tool_format": "standard_json",
        "structured_output_support": "json_schema",
        "reasoning_effort": "default",
        "timeout": 300.0,
        "max_tokens": None,
        "temperature": None,
    },
}


def _endpoint_from_local_route(name: str) -> EndpointConfig:
    spec = _LOCAL_ROUTE_DEFAULTS[name]
    prefix = f"ARCA_{name.upper()}"
    try:
        return EndpointConfig(
            model_id=str(_route_override(prefix, "MODEL", spec["model_id"])),
            base_url=str(_route_override(prefix, "BASE_URL", spec["base_url"])),
            api_key=_env_text(f"{prefix}_API_KEY") or "local",
            timeout=float(_route_override(prefix, "TIMEOUT", spec["timeout"])),
            api_style=str(_route_override(prefix, "API_STYLE", spec["api_style"])),
            tool_format=str(_route_override(prefix, "TOOL_FORMAT", spec["tool_format"])),
            structured_output_support=str(
                _route_override(prefix, "STRUCTURED_OUTPUT_SUPPORT", spec["structured_output_support"])
            ),
            reasoning_effort=str(_route_override(prefix, "REASONING_EFFORT", spec["reasoning_effort"])),
            max_tokens=_route_override(prefix, "MAX_TOKENS", spec["max_tokens"]),  # type: ignore[arg-type]
            temperature=_route_override(prefix, "TEMPERATURE", spec["temperature"]),  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise ValueError(f"invalid local model configuration for {name}: {exc}") from exc


def _env_endpoint_config(
    stage: str,
    shared: dict[str, str | float],
    *,
    shared_present: bool,
) -> EndpointConfig | None:
    stage_prefix = f"ARCA_{stage.upper()}_"
    stage_names = {field: f"{stage_prefix}{field}" for field in _ARCA_ALL_FIELDS}
    stage_present = any(name in os.environ for name in stage_names.values())
    if not shared_present and not stage_present:
        return None

    values: dict[str, str | float] = {}
    missing: list[str] = []
    for field in _ARCA_REQUIRED_FIELDS:
        value = _env_text(stage_names[field]) or shared.get(field)
        if not value:
            fallback = f"ARCA_{field}"
            missing.append(f"{stage_names[field]} (or {fallback})")
        else:
            values[field] = value

    if missing:
        raise ValueError(
            f"incomplete model configuration for {stage}: missing {', '.join(missing)}"
        )

    stage_timeout = _env_text(stage_names["TIMEOUT"])
    values["TIMEOUT"] = _parse_env_timeout(
        stage_names["TIMEOUT"],
        stage_timeout,
        float(shared.get("TIMEOUT", _ARCA_DEFAULT_TIMEOUT)),
    )
    try:
        return EndpointConfig(
            model_id=str(values["MODEL"]),
            base_url=str(values["BASE_URL"]),
            api_key=str(values["API_KEY"]),
            timeout=float(values["TIMEOUT"]),
        )
    except ValueError as exc:
        raise ValueError(f"invalid model configuration for {stage}: {exc}") from exc


def _make_model_from_endpoint(endpoint: EndpointConfig) -> OpenAIModel:
    return make_openai_compatible_model(endpoint=endpoint)


def make_stage_models_from_env() -> StageModels | None:
    """Build stage models from dedicated API keys or legacy ``ARCA_*`` vars.

    The dedicated topology is gated on its unique key names
    (``ARCA_SCOUT_PRIMARY_API_KEY`` / ``ARCA_SCOUT_FALLBACK_API_KEY``) so it
    can never misfire on the colliding generic ``ARCA_<STAGE>_API_KEY`` names.
    It uses only ``os.environ`` and the non-sensitive route defaults above and
    never consults key files. Legacy generic ARCA variables remain supported
    for existing callers and tests.

    ``ARCA_DEPLOYMENT=local`` takes precedence over both: the four stages bind
    to the loopback llama-server topology in ``_LOCAL_ROUTE_DEFAULTS`` (no API
    keys involved). Any other non-empty value raises.
    """
    deployment = (_env_text("ARCA_DEPLOYMENT") or "").strip().lower()
    if deployment == "local":
        return StageModels(
            **{
                name: _make_model_from_endpoint(_endpoint_from_local_route(name))
                for name in _ARCA_STAGES
            }
        )
    if deployment not in {"", "remote", "cloud"}:
        raise ValueError(
            f"unsupported ARCA_DEPLOYMENT value: expected 'local' or unset, got {deployment!r}"
        )

    dedicated_present = bool(
        _env_text("ARCA_SCOUT_PRIMARY_API_KEY")
        or _env_text("ARCA_SCOUT_FALLBACK_API_KEY")
    )
    if dedicated_present:
        named_endpoints = {
            name: _endpoint_from_named_route(name)
            for name in (*_ARCA_STAGES, "scout_fallback")
        }
        models = {
            name: _make_model_from_endpoint(endpoint)
            for name, endpoint in named_endpoints.items()
            if endpoint is not None
        }
        if models:
            return StageModels(**models)

    shared_names = {field: f"ARCA_{field}" for field in _ARCA_ALL_FIELDS}
    shared_present = any(name in os.environ for name in shared_names.values())
    shared: dict[str, str | float] = {}

    if shared_present:
        missing = [
            name
            for field in _ARCA_REQUIRED_FIELDS
            for name in (shared_names[field],)
            if not _env_text(name)
        ]
        if missing:
            raise ValueError(
                "incomplete shared model configuration: missing "
                + ", ".join(missing)
            )
        shared.update(
            {
                field: _env_text(shared_names[field]) or ""
                for field in _ARCA_REQUIRED_FIELDS
            }
        )
        shared["TIMEOUT"] = _parse_env_timeout(
            shared_names["TIMEOUT"],
            _env_text(shared_names["TIMEOUT"]),
            _ARCA_DEFAULT_TIMEOUT,
        )

    configs: dict[str, EndpointConfig] = {}
    for stage in _ARCA_STAGES:
        config = _env_endpoint_config(stage, shared, shared_present=shared_present)
        if config is not None:
            configs[stage] = config

    if not configs:
        return None

    models_by_config: dict[EndpointConfig, OpenAIModel] = {}
    models: dict[str, OpenAIModel] = {}
    for stage, config in configs.items():
        model = models_by_config.get(config)
        if model is None:
            model = _make_model_from_endpoint(config)
            models_by_config[config] = model
        models[stage] = model
    return StageModels(**models)


# Loop-stage tuning (verify/deepen). INVOKE_TIMEOUT is suffixed to avoid the
# existing generic ARCA_<STAGE>_TIMEOUT endpoint-timeout override.
_STAGE_TUNING_ENV: dict[str, str] = {
    "verify_concurrency": "ARCA_VERIFY_MAX_CONCURRENCY",
    "verify_delay": "ARCA_VERIFY_INTER_CALL_DELAY",
    "verify_timeout": "ARCA_VERIFY_INVOKE_TIMEOUT",
    "deepen_concurrency": "ARCA_DEEPEN_MAX_CONCURRENCY",
    "deepen_delay": "ARCA_DEEPEN_INTER_CALL_DELAY",
    "deepen_timeout": "ARCA_DEEPEN_INVOKE_TIMEOUT",
}
_TUNING_INT_FIELDS = {"verify_concurrency", "deepen_concurrency"}


def make_stage_tuning_from_env() -> StageTuning:
    """Read verify/deepen loop tuning from ``ARCA_*`` variables.

    Unset variables keep the serial StageTuning defaults; invalid values raise
    with the variable name (never the value).
    """
    values: dict[str, int | float] = {}
    for field_name, env_name in _STAGE_TUNING_ENV.items():
        raw = _env_text(env_name)
        if raw is None:
            continue
        try:
            parsed = int(raw) if field_name in _TUNING_INT_FIELDS else float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{env_name} must be a number") from exc
        values[field_name] = parsed
    try:
        return StageTuning(**values)
    except ValueError as exc:
        raise ValueError(f"invalid stage tuning: {exc}") from exc


# ── 便捷别名 ──

def make_glm_flash() -> OpenAIModel:
    """GLM-5.2（Scout 默认）。"""
    return make_model(ModelProvider.GLM, ModelTier.FLASH)


def make_kimi_pro() -> OpenAIModel:
    """Kimi-K3（Verify/Deepen/Arbiter 默认）。"""
    return make_model(ModelProvider.KIMI, ModelTier.PRO)


def make_deepseek_flash() -> OpenAIModel:
    """DeepSeek-V4-Flash（AMD 免费 fallback）。"""
    return make_model(ModelProvider.DEEPSEEK, ModelTier.FLASH)


def make_qwen_flash() -> OpenAIModel:
    """Qwen-3.8-Flash-Next（AMD 免费 fallback）。"""
    return make_model(ModelProvider.QWEN, ModelTier.FLASH)


def make_amd_flash() -> OpenAIModel:
    """AMD Radeon Cloud DeepSeek-V4-Flash（免费，最原始 fallback）。"""
    return make_model(ModelProvider.AMD, ModelTier.FLASH)


# ── 调试输出 ──

def model_name(model: OpenAIModel) -> str:
    """从 OpenAIModel 提取模型名（兼容 strands 内部存储）。"""
    cfg = model.get_config()
    return str(cfg.get("model_id", "?"))


def list_models() -> None:
    """打印支持的模型矩阵（调试用）。"""
    print("支持的模型矩阵:")
    for (prov, tier), cfg in _MODEL_MAP.items():
        print(f"  [{prov.value}/{tier.value}] {cfg['model_id']} @ {cfg['base_url']}")
"""统一模型工厂 — 支持 GLM / Kimi / DeepSeek / Qwen（AMD Radeon Cloud 路由）。

Agent 分层分配（2026-09-12 调整：异构合议 + Kimi 配额耗尽后降级 + AMD 目录实测修正）：
- Scout (1):   GLM-5.3（TokenRouter 免费档；docstring 曾写 5.2，实际 model_id 早已是 5.3）
- Verify (2):  DeepSeek-V4-Flash（主判，AMD 免费；AMD 目录无 V4-Pro，models.list 实测）
- Deepen (3):  DeepSeek-V4-Flash（主力）
- Arbiter (4): GLM-5.3（§11-G：与 Scout 同源、与 Verify/Deepen 异构的去相关第二票）
- Fallback:    Kimi-K3（余额耗尽，充值后恢复备选）/ GLM / Qwen-3.8-Flash-Next

架构：保留 OpenAIModel（Strands SDK），通过 base_url/model_id 路由到不同 provider。
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI
from strands.models import OpenAIModel

__all__ = [
    "ModelProvider",
    "ModelTier",
    "make_model",
    "get_key",
]


# ── 枚举 ──

class ModelProvider(str, Enum):
    """支持的 API provider。"""
    GLM = "glm"           # TokenRouter（GLM-5.3，OpenAI 兼容）
    KIMI = "kimi"         # Moonshot Kimi-K3
    DEEPSEEK = "deepseek" # AMD Radeon Cloud (DeepSeek-V4-Flash)
    QWEN = "qwen"         # AMD Radeon Cloud (Qwen-3.8-Flash-Next)
    AMD = "amd"           # AMD Radeon Cloud 通用入口（兼容旧名）


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


def get_key(provider: ModelProvider) -> str:
    """按 provider 返回对应的 API Key。"""
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

    api_key = get_key(provider)
    return OpenAIModel(
        model_id=config["model_id"],
        client_args={
            "base_url": config["base_url"],
            "api_key": api_key,
            "timeout": config["timeout"],
        },
    )


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
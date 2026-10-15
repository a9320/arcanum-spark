"""Scout profile 机制单测 — 双 Scout 设计红线锚（docs/SCOUT-PROFILE-DESIGN.md）。

红线锁定：
1. default prompt 字节不变（K1 基线可比性）；
2. step5 变体含预算纪律条款（对症两晚墙钟哨杀死法）；
3. profile 解析：显式参数 > ARCA_SCOUT_PROFILE env > default，未知值快败；
4. factory 透传：ARCA_SCOUT_REASONING_EFFORT / ARCA_SCOUT_MAX_TOKENS 在
   named 路由与 legacy stage 路径均真实生效（MAX_TOKENS 此前是安慰剂旋钮）。
运行: python -m pytest tests/test_scout_profile.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from codeark.agents.scout_agent import (
    SCOUT_PROFILES,
    SCOUT_SYSTEM_PROMPT,
    _resolve_profile,
)
from codeark.models.factory import _endpoint_from_named_route, _env_endpoint_config


def test_default_profile_is_byte_identical():
    """红线 1：default 档必须与原 SCOUT_SYSTEM_PROMPT 同一对象（K1 基线可比）。"""
    assert SCOUT_PROFILES["default"] is SCOUT_SYSTEM_PROMPT


def test_step5_profile_has_budget_discipline():
    """红线 2：step5 档必须含对症条款（岗位收敛/墙钟自警/草稿预算/经济输出）。"""
    text = SCOUT_PROFILES["step5"]
    for kw in ("硬墙钟", "最多 5 条", "2-4 条主线假设", "Verify 节点", "HypothesisSet"):
        assert kw in text, f"step5 档缺少关键条款: {kw}"


def test_profiles_share_keys_and_prompts_differ():
    assert set(SCOUT_PROFILES) == {"default", "step5"}
    assert SCOUT_PROFILES["step5"] != SCOUT_PROFILES["default"]


def test_resolve_profile_precedence(monkeypatch):
    monkeypatch.delenv("ARCA_SCOUT_PROFILE", raising=False)
    assert _resolve_profile(None) == "default"
    assert _resolve_profile("step5") == "step5"  # 显式参数
    monkeypatch.setenv("ARCA_SCOUT_PROFILE", "STEP5")  # env 大小写归一
    assert _resolve_profile(None) == "step5"
    assert _resolve_profile("default") == "default"  # 显式参数压过 env


def test_resolve_profile_unknown_fails_fast(monkeypatch):
    with pytest.raises(ValueError, match="unknown scout profile"):
        _resolve_profile("nope")
    monkeypatch.setenv("ARCA_SCOUT_PROFILE", "nope")
    with pytest.raises(ValueError, match="unknown scout profile"):
        _resolve_profile(None)


def test_named_route_reasoning_effort_and_max_tokens(monkeypatch):
    """named 路由：REASONING_EFFORT 覆盖既有支持（设计手段 b 零代码）；MAX_TOKENS 补透传后生效。"""
    monkeypatch.setenv("ARCA_SCOUT_PRIMARY_API_KEY", "k-test")
    monkeypatch.delenv("ARCA_SCOUT_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("ARCA_SCOUT_MAX_TOKENS", raising=False)
    ep = _endpoint_from_named_route("scout")
    assert ep.reasoning_effort == "medium"  # 路由表默认（两晚 B 臂即此档）
    assert ep.max_tokens is None  # 默认无帽=服务端 INF（现状不变）
    monkeypatch.setenv("ARCA_SCOUT_REASONING_EFFORT", "low")
    monkeypatch.setenv("ARCA_SCOUT_MAX_TOKENS", "20000")
    ep = _endpoint_from_named_route("scout")
    assert ep.reasoning_effort == "low"
    assert ep.max_tokens == 20000


def test_stage_env_reasoning_effort_and_max_tokens(monkeypatch):
    """legacy stage 路径：同样补齐三字段覆盖（与 named/local 路由对齐）。"""
    for name in (
        "ARCA_SCOUT_MODEL",
        "ARCA_SCOUT_BASE_URL",
        "ARCA_SCOUT_API_KEY",
        "ARCA_SCOUT_TIMEOUT",
        "ARCA_SCOUT_REASONING_EFFORT",
        "ARCA_SCOUT_MAX_TOKENS",
        "ARCA_SCOUT_TEMPERATURE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ARCA_SCOUT_MODEL", "demo-m")
    monkeypatch.setenv("ARCA_SCOUT_BASE_URL", "https://demo.test/v1")
    monkeypatch.setenv("ARCA_SCOUT_API_KEY", "k-demo")
    ep = _env_endpoint_config("scout", {}, shared_present=False)
    assert ep.reasoning_effort == "default"
    assert ep.max_tokens is None
    monkeypatch.setenv("ARCA_SCOUT_REASONING_EFFORT", "low")
    monkeypatch.setenv("ARCA_SCOUT_MAX_TOKENS", "123")
    ep = _env_endpoint_config("scout", {}, shared_present=False)
    assert ep.reasoning_effort == "low"
    assert ep.max_tokens == 123

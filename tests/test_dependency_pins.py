"""依赖钉版护栏 — 2026-10-18 strands 1.61.1 回归事故的防回潮锚。

事故链：requirements.txt 原为 `strands-agents>=1.55`，新 pod pip 装到 1.61.1，
固定假设集 GK 验收卷 verify 出现 2/4 peg-native 降级；回钉 1.56.0 同卷降为 0/4。
证据=DSW runs/20261018-accept/gatekeeping-pinned{,.v1611}。本测试防止约束被
顺手放宽（例如改回 >= 或删掉版本号）。
"""
from __future__ import annotations

from pathlib import Path


def test_strands_agents_is_pinned_to_1_56_0():
    req = (Path(__file__).parent.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "strands-agents==1.56.0" in req
    assert "strands-agents>=" not in req

"""laya_runtime 契约锚（2026-11-05 自 eval/replay.py 提升）。

锁死三件事：
1. **单一事实源**：replay.score_laya 必须转发到本模块（identity 断言，
   防止 replay 里本地实现悄悄复活）；
2. **loader 快败契约**：空路径 ValueError、缺 rl_agent_api.py FileNotFoundError
   （vendor 目录布局错误的明确报错，不拖到推理中途）；
3. **顶层零重依赖**：模块导入不拉 torch/transformers（重依赖只在 vendor
   rl_agent_api.py exec 时引入——slim 包可安全携带本模块）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "replay", ROOT / "eval" / "replay.py"
)
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)

from codeark.graph import laya_runtime  # noqa: E402


def test_replay_forwards_to_the_single_implementation():
    assert replay.score_laya is laya_runtime.score_laya
    assert replay._laya_state is laya_runtime._laya_state
    assert replay._load_laya_agent is laya_runtime._load_laya_agent


def test_loader_fails_fast_on_bad_paths(tmp_path):
    with pytest.raises(ValueError):
        laya_runtime._load_laya_agent("")
    with pytest.raises(FileNotFoundError):
        laya_runtime._load_laya_agent(str(tmp_path))  # 无 rl_agent_api.py


def test_module_imports_without_torch():
    """slim 携带前提：顶层纯标准库（torch 只在 vendor exec 时引入）。"""
    src = (ROOT / "codeark" / "graph" / "laya_runtime.py").read_text(encoding="utf-8")
    assert "import torch" not in src
    assert "from transformers" not in src
    assert laya_runtime.LAYA_RUNTIME_NOTE.startswith("Laya ranks hypotheses offline")


def test_score_laya_with_stub(monkeypatch):
    class _StubAgent:
        def system_one(self, state, questions):
            (qid, q), = questions.items()
            assert q["type"] == "choice" and set(q["criteria"]) == {"A", "B"}
            return {"model": "rl-agent",
                    "answers": {qid: {"type": "choice", "choice": "A",
                                      "probabilities": {"A": 0.7, "B": 0.3},
                                      "confidence": 0.5}},
                    "usage": {"input_tokens": 64, "output_tokens": 0}}

    monkeypatch.setattr(laya_runtime, "_load_laya_agent", lambda p: _StubAgent())
    items = [
        {"id": "H1", "title": "t1", "vuln_type": "V", "file_path": "src/a.py", "attack_path": "x"},
        {"id": "H2", "title": "t2", "vuln_type": "V", "file_path": "src/b.py", "attack_path": "y"},
    ]
    probs, confs = laya_runtime.score_laya(items, [], "/fake/model")
    assert probs == [0.7, 0.7] and confs == [0.5, 0.5]


def test_gate_factory_no_longer_imports_eval_replay():
    """gate_factory 摆脱 eval/ 目录注入（sys.path 无需含 eval/）。"""
    from codeark.graph import gate_factory

    gate = gate_factory.make_laya_gate("/fake/model")
    assert gate.__name__ == "laya_gate"
    # 构造期不加载模型（快败只在 gate 实际调用时发生）
    assert not hasattr(gate, "replay")

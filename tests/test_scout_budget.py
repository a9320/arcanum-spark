"""Scout 输入总量预算单测 — 真实仓容量边界修复的回归锚。

背景：axios 446 文件全量注入 Scout prompt ≈908K tokens，撑爆 98K ctx
（2026-10-07 v1.2 FP 标定实证）→ _read_repo 增加确定性总量预算：
AI 配置文件优先保留、小文件优先装填、超预算整文件跳过并披露。
运行: python -m pytest tests/test_scout_budget.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from codeark.cli import _est_tokens, _read_repo


def _make_repo(tmp_path):
    """迷你仓：AI 配置 + 小源码 + 大 CHANGELOG（300KB，低于 512KB 单文件帽）。"""
    (tmp_path / "lib").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("AI config: be helpful\n", encoding="utf-8")
    (tmp_path / "lib" / "core.py").write_text("x = 1\n" * 100, encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo repo readme\n" * 10, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("changelog line\n" * 20000, encoding="utf-8")


def test_budget_caps_total_tokens(tmp_path, monkeypatch):
    _make_repo(tmp_path)
    monkeypatch.setenv("ARCA_SCOUT_MAX_TOTAL_TOKENS", "5000")
    files = _read_repo(tmp_path)
    total = sum(_est_tokens(c) for c in files.values())
    assert total <= 5000
    assert "AGENTS.md" in files          # AI 配置 rank 0 必留
    assert "CHANGELOG.md" not in files   # 大文件超预算整文件跳过


def test_budget_default_60k(tmp_path, monkeypatch):
    _make_repo(tmp_path)
    monkeypatch.delenv("ARCA_SCOUT_MAX_TOTAL_TOKENS", raising=False)
    files = _read_repo(tmp_path)
    assert "AGENTS.md" in files
    assert "lib/core.py" in files        # 小源码在默认预算内全保留
    total = sum(_est_tokens(c) for c in files.values())
    assert total <= 60000


def test_budget_zero_disables(tmp_path, monkeypatch):
    _make_repo(tmp_path)
    monkeypatch.setenv("ARCA_SCOUT_MAX_TOTAL_TOKENS", "0")
    files = _read_repo(tmp_path)
    assert "CHANGELOG.md" in files       # 0=不设限，大文件回归
    assert len(files) == 4


def test_deterministic_fill(tmp_path, monkeypatch):
    _make_repo(tmp_path)
    monkeypatch.setenv("ARCA_SCOUT_MAX_TOTAL_TOKENS", "5000")
    a = _read_repo(tmp_path)
    b = _read_repo(tmp_path)
    assert list(a.keys()) == list(b.keys())   # 同输入同装填序=逐位可复现


def test_est_tokens_ascii_vs_cjk():
    assert _est_tokens("abcd" * 100) == 100          # 400 ASCII 字符 ≈ 100 token
    assert _est_tokens("中" * 100) >= 90             # CJK 按 ~1 字符/token 计
    assert _est_tokens("") == 0

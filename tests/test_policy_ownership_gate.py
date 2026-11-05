"""策略文件所有权闸门契约锚（2026-11-05，外评建议落地）。

锁三件事：
1. pattern_matches 的 CODEOWNERS 语义（锚定/非锚定/尾斜杠目录/通配）；
2. find_policy_files / parse_codeowners_lines 的清单行为；
3. 端到端：临时 git 仓库放策略文件 → 无 CODEOWNERS 必红；写上认领后转绿。
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "policy_ownership_gate", ROOT / "scripts" / "policy_ownership_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pog = _load()


# ── pattern_matches ──────────────────────────────────────────

def test_anchored_exact():
    assert pog.pattern_matches("/AGENTS.md", "AGENTS.md")
    assert not pog.pattern_matches("/AGENTS.md", "docs/AGENTS.md")


def test_unanchored_matches_any_level():
    assert pog.pattern_matches("AGENTS.md", "AGENTS.md")
    assert pog.pattern_matches("AGENTS.md", "docs/AGENTS.md")


def test_pattern_with_slash_is_anchored():
    assert pog.pattern_matches(".github/copilot-instructions.md",
                               ".github/copilot-instructions.md")
    assert not pog.pattern_matches(".github/copilot-instructions.md",
                                   "x/.github/copilot-instructions.md")


def test_trailing_slash_covers_directory():
    assert pog.pattern_matches("/codeark/pitax/", "codeark/pitax/detectors.py")
    assert not pog.pattern_matches("/codeark/pitax/", "codeark/pitaxx/other.py")


def test_double_star_covers_tree():
    assert pog.pattern_matches("/plugins/**", "plugins/a/b/mcp.json")
    assert not pog.pattern_matches("/plugins/**", "plugins")


def test_star_within_segment():
    assert pog.pattern_matches("*.md", "README.md")
    assert not pog.pattern_matches("*.md", "docs/guide.yaml")


# ── 清单与解析 ───────────────────────────────────────────────

def test_find_policy_files():
    files = ["AGENTS.md", "CLAUDE.md", "src/app.py", "docs/AGENTS.md",
             ".cursor/rules", ".github/copilot-instructions.md", "prompts.yaml",
             "eval/pitax_bench/cases.jsonl"]
    got = pog.find_policy_files(files)
    assert "AGENTS.md" in got and "CLAUDE.md" in got
    assert ".cursor/rules" in got and ".github/copilot-instructions.md" in got
    assert "prompts.yaml" in got
    assert "src/app.py" not in got and "eval/pitax_bench/cases.jsonl" not in got


def test_parse_codeowners_lines_skips_comments_and_ownerless():
    text = "# comment\n\n/AGENTS.md @a9320 @dev2\n/orphan-pattern\n/CLAUDE.md @a9320\n"
    entries = pog.parse_codeowners_lines(text)
    assert [p for p, _ in entries] == ["/AGENTS.md", "/CLAUDE.md"]
    assert entries[0][1] == ["@a9320", "@dev2"]


# ── 端到端（临时 git 仓库） ───────────────────────────────────

def _mk_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def test_e2e_uncovered_policy_file_fails(tmp_path):
    repo = _mk_repo(tmp_path)
    (repo / "AGENTS.md").write_text("Be helpful.\n", encoding="utf-8")
    subprocess.run(["git", "add", "AGENTS.md"], cwd=repo, check=True)
    uncovered, codeowners, _ = pog.uncovered_policy_files(repo)
    assert uncovered == ["AGENTS.md"]
    assert codeowners is None


def test_e2e_covered_policy_file_passes(tmp_path):
    repo = _mk_repo(tmp_path)
    (repo / "AGENTS.md").write_text("Be helpful.\n", encoding="utf-8")
    (repo / ".github").mkdir()
    (repo / ".github" / "CODEOWNERS").write_text("/AGENTS.md @a9320\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    uncovered, codeowners, entries = pog.uncovered_policy_files(repo)
    assert uncovered == []
    assert codeowners is not None and len(entries) == 1


def test_e2e_repo_without_policy_files_passes(tmp_path):
    repo = _mk_repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    uncovered, _, _ = pog.uncovered_policy_files(repo)
    assert uncovered == []

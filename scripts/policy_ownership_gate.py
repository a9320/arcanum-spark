"""策略文件所有权闸门（2026-11-05，源自 AWS 外评建议）。

动机：面向 AI 的策略文件（AGENTS.md / .cursor/rules / copilot-instructions.md / prompts.yaml …）
是 agent 的**输入**，却通常没有 owner、不进 code review——我们的扫描器实测过，
一份写着"永远跳过安全审查"的规则文件，人类评审和传统工具都不会注意。
本闸门把"策略文件必须被 CODEOWNERS 认领"变成一条 CI 硬检查。

规则：
1. 在 git 真集中找策略文件（清单见 POLICY_GLOBS）；
2. 仓库里没有策略文件 ⇒ PASS（空仓不挑刺）；
3. 有则必须在 CODEOWNERS 里有至少一条**带 owner**的模式覆盖它；
4. 未覆盖 ⇒ 逐条列出并红（退出码 1）。

CODEOWNERS 位置（同 GitHub 约定，取第一个存在的）：
.github/CODEOWNERS > CODEOWNERS > docs/CODEOWNERS

用法：python scripts/policy_ownership_gate.py [--root <repo>] [--print-patterns]
退出码：0=过；1=存在未认领的策略文件；2=环境错误。
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

# 给 AI 读的输入面（新增类型时在测试里同步加一条）
POLICY_GLOBS = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursor/rules",
    ".cursor/rules/*",
    ".windsurf/rules",
    ".windsurf/rules/*",
    ".github/copilot-instructions.md",
    ".github/instructions/*.md",
    "prompts.yaml",
    "prompts/*.yaml",
    ".goose/rules",
    ".clinerules/*",
)

CODEOWNERS_CANDIDATES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


def find_codeowners(root: Path) -> Path | None:
    for rel in CODEOWNERS_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    return None


def git_ls_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                         capture_output=True, check=True).stdout
    return [raw.decode("utf-8", errors="replace").replace("\\", "/")
            for raw in out.split(b"\0") if raw]


def find_policy_files(files: list[str]) -> list[str]:
    return [f for f in files if any(fnmatch.fnmatch(f, g) for g in POLICY_GLOBS)]


def parse_codeowners_lines(text: str) -> list[tuple[str, list[str]]]:
    """返回 [(pattern, owners)]；注释行与无 owner 行跳过（后者无法认领）。"""
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        entries.append((parts[0], parts[1:]))
    return entries


def pattern_matches(pattern: str, path: str) -> bool:
    """CODEOWNERS 模式匹配（支持 /锚定、*、**、尾 / 目录前缀）。"""
    pat = pattern.strip()
    anchored = pat.startswith("/")
    pat = pat.lstrip("/")
    if pat.endswith("/"):
        pat += "**"
    if not anchored and "/" in pat:
        anchored = True  # 含目录的模式按 GitHub 语义视为锚定到根
    if anchored:
        regex = fnmatch.translate(pat)
        return re.match(regex, path) is not None
    # 非锚定：可匹配任意层级（含路径中的目录名）
    regex = fnmatch.translate("*/" + pat.rstrip("*") + "*" if pat.endswith("*") else "*/" + pat)
    return re.match(regex, path) is not None or fnmatch.fnmatch(path, pat)


def uncovered_policy_files(root: Path) -> tuple[list[str], Path | None, list[tuple[str, list[str]]]]:
    files = git_ls_files(root)
    policy = find_policy_files(files)
    codeowners = find_codeowners(root)
    entries = parse_codeowners_lines(codeowners.read_text(encoding="utf-8")) if codeowners else []
    uncovered = [p for p in policy
                 if not any(pattern_matches(pat, p) for pat, _ in entries)]
    return uncovered, codeowners, entries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="策略文件必须被 CODEOWNERS 认领（CI 闸门）")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--print-patterns", action="store_true", help="打印本闸门认定的策略文件模式")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.print_patterns:
        for g in POLICY_GLOBS:
            print(g)
        return 0

    try:
        uncovered, codeowners, entries = uncovered_policy_files(root)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"!! 环境错误：git ls-files 失败（{e}）")
        return 2

    print(f"== CODEOWNERS: {codeowners if codeowners else '（不存在）'}，有效模式 {len(entries)} 条")
    if not uncovered:
        print("✅ PASS: 策略文件全部被 CODEOWNERS 认领（或本仓库无策略文件）")
        return 0
    for p in uncovered:
        print(f"   [未认领] {p}")
    print(f"❌ FAIL: {len(uncovered)} 个策略文件未被 CODEOWNERS 认领——"
          f"这些是 agent 的输入面，必须有 owner 与审阅（分支保护建议同步开启）")
    return 1


if __name__ == "__main__":
    sys.exit(main())

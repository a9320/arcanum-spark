"""构建零依赖瘦包 codeark-pitax（分发物生成器，非第二份实现）。

单一事实源纪律：规则与检测逻辑只在 `codeark/pitax/` + `codeark/tools/pitax_scan.py` +
`codeark/agents/report_agent.py` 三处存在；本脚本把它们**复制并重写导入**成独立分发包
`codeark_pitax`（纯标准库，零第三方依赖），供 PyPI 发布与 arcanum-mcp 一键安装。

用法：
  python scripts/build_slim_pitax.py                 # 生成包源 + wheel
  python scripts/build_slim_pitax.py --no-wheel      # 只生成包源（测试用）
  python scripts/build_slim_pitax.py --out D:/x      # 指定输出目录

产物：
  <out>/codeark-pitax/       生成的包源（codeark_pitax/ + pyproject.toml + README.md）
  <out>/dist/*.whl           wheel（未用 --no-wheel 时）

发布（用户侧，需 PyPI 账号）：uv publish <out>/dist/*
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codeark.pitax.rules import PITAX_VERSION  # noqa: E402
DEFAULT_OUT = ROOT.parent / "slim-build"
PKG = "codeark_pitax"
VERSION = "0.1.1"

# 复制映射：源 → 生成文件名；rewrites 逐条替换导入
COPY_PLAN: list[tuple[Path, str, list[tuple[str, str]]]] = [
    *[(f, f.name, []) for f in sorted((ROOT / "codeark" / "pitax").glob("*.py"))],
    (
        ROOT / "codeark" / "tools" / "pitax_scan.py",
        "scan_engine.py",
        [("from ..pitax.detectors import", "from .detectors import")],
    ),
    (ROOT / "codeark" / "agents" / "report_agent.py", "reporting.py", []),
]

CLI_LINES = [
    '"""codeark-pitax 命令行：仓库/文件的确定性提示注入扫描（零依赖、零网络）。"""',
    "from __future__ import annotations",
    "",
    "import argparse",
    "import sys",
    "from pathlib import Path",
    "",
    "from .scan_engine import scan_repo",
    "from .reporting import render_report",
    "from .rules import PITAX_VERSION",
    "from .detectors import is_ai_config_path",
    "",
    'SOURCE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp",',
    '    ".h", ".rb", ".php", ".sh", ".bash", ".sql", ".html", ".htm", ".vue", ".json", ".yaml",',
    '    ".yml", ".toml", ".ini", ".cfg", ".txt", ".md"}',
    'SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",',
    '    ".pytest_cache"}',
    "",
    "",
    "def _read(target: Path) -> tuple[dict[str, str], int]:",
    "    if target.is_file():",
    "        candidates, skipped = [target], 0",
    "    else:",
    "        candidates, skipped = [], 0",
    "        for p in sorted(target.rglob('*')):",
    "            if not p.is_file():",
    "                continue",
    "            if any(part in SKIP_DIRS for part in p.parts):",
    "                continue",
    "            if p.suffix.lower() not in SOURCE_EXTS and not is_ai_config_path(str(p)):",
    "                continue",
    "            candidates.append(p)",
    "    files: dict[str, str] = {}",
    "    for p in candidates[:400]:",
    "        try:",
    "            if p.stat().st_size > 512 * 1024:",
    "                skipped += 1",
    "                continue",
    "            files[str(p)] = p.read_text(encoding='utf-8', errors='replace')",
    "        except OSError:",
    "            skipped += 1",
    "    return files, skipped",
    "",
    "",
    "def main(argv=None) -> int:",
    "    parser = argparse.ArgumentParser(",
    '        prog="codeark-pitax",',
    '        description="Deterministic prompt-injection scan (PITAX v' + PITAX_VERSION + ', local, no model)")',
    '    parser.add_argument("target", help="repository directory or single file")',
    '    parser.add_argument("--formats", default="json,markdown",',
    '                        help="json,sarif,markdown,html")',
    '    parser.add_argument("--out", default="./pitax-report")',
    "    args = parser.parse_args(argv)",
    "",
    "    target = Path(args.target).resolve()",
    "    if not target.exists():",
    '        print(f"target not found: {target}")',
    "        return 1",
    "    files, skipped = _read(target)",
    "    if not files:",
    '        print("no supported source files found")',
    "        return 1",
    "    findings = scan_repo(files, strict=True)",
    "    dicts = findings  # scan_repo 返回的已是 report_dict（产品同款形态）",
    "    meta = {",
    '        "tool": "codeark-pitax",',
    '        "pitax_version": PITAX_VERSION,',
    '        "files_scanned": len(files),',
    '        "skipped": skipped,',
    '        "local_only": True,',
    "    }",
    "    reports = render_report(dicts, [f.strip() for f in args.formats.split(',')], meta=meta)",
    "    out = Path(args.out).resolve()",
    "    out.mkdir(parents=True, exist_ok=True)",
    "    ext = {'json': 'json', 'sarif': 'sarif', 'markdown': 'md', 'html': 'html'}",
    "    for name, content in reports.items():",
    "        fp = out / f'report.{ext.get(name, name)}'",
    "        fp.write_text(content, encoding='utf-8')",
    "        print(f'- {fp} ({fp.stat().st_size} B)')",
    '    print(f"findings: {len(dicts)}  files: {len(files)}  skipped: {skipped}")',
    '    print("local only: nothing was uploaded, no model was called")',
    "    return 0",
    "",
    "",
    'if __name__ == "__main__":',
    "    sys.exit(main())",
]

PYPROJECT_LINES = [
    "[build-system]",
    'requires = ["setuptools>=68"]',
    'build-backend = "setuptools.build_meta"',
    "",
    "[project]",
    'name = "codeark-pitax"',
    f'version = "{VERSION}"',
    'description = "Deterministic prompt-injection scanner (PITAX): scan repos/docs for '
    'AI-assistant hijacking patterns. Zero dependencies, local only."',
    'requires-python = ">=3.10"',
    "dependencies = []",
    "",
    "[project.scripts]",
    'codeark-pitax = "codeark_pitax.cli:main"',
    "",
    "[tool.setuptools.packages.find]",
    'include = ["codeark_pitax*"]',
]

README_LINES = [
    "# codeark-pitax",
    "",
    "Deterministic prompt-injection scanner (PITAX rules): scan repositories, documents",
    "and untrusted text for AI-assistant hijacking patterns — invisible Unicode, trojan",
    "source, instruction overrides, encoded payloads. Zero dependencies, zero network,",
    "zero model calls; everything stays on your machine.",
    "",
    "Part of CodeRisk Arcanum (https://github.com/a9320/arcanum-spark).",
    "",
    "## Usage",
    "",
    "```bash",
    "codeark-pitax scan ./your-repo --formats html --out ./pitax-report",
    "```",
    "",
    "## Attribution",
    "",
    "The PITAX rule set is derived from the Prompt Injection Taxonomy v1.6.1 by",
    "Jason Haddix / Arcanum (CC BY 4.0).",
]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="build the zero-dependency codeark-pitax distribution")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--no-wheel", action="store_true", help="只生成包源（测试用）")
    args = ap.parse_args(argv)

    out = Path(args.out).resolve()
    pkg_dir = out / "codeark-pitax" / PKG
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True)

    for src, dest_name, rewrites in COPY_PLAN:
        text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
        for old, new in rewrites:
            assert old in text, f"{src}: anchor missing: {old}"
            text = text.replace(old, new)
        assert "from codeark" not in text, f"{src} 仍含绝对 codeark 导入"
        _write(pkg_dir / dest_name, text)

    # 便捷导出：import codeark_pitax 即得 scan_repo/scan_file（wheel 用户的公共 API）
    init_path = pkg_dir / "__init__.py"
    init = init_path.read_text(encoding="utf-8")
    if "scan_repo" not in init:
        init += "\nfrom .scan_engine import scan_file, scan_repo  # noqa: E402,F401\n"
        _write(init_path, init)

    _write(pkg_dir / "cli.py", "\n".join(CLI_LINES) + "\n")
    _write(pkg_dir / "__main__.py", "from .cli import main\n\nimport sys\n\nsys.exit(main())\n")
    _write(out / "codeark-pitax" / "pyproject.toml", "\n".join(PYPROJECT_LINES) + "\n")
    _write(out / "codeark-pitax" / "README.md", "\n".join(README_LINES) + "\n")

    print(f"generated: {out / 'codeark-pitax'}")
    if args.no_wheel:
        return 0

    dist = out / "dist"
    env = dict(os.environ)
    env.setdefault("UV_CACHE_DIR", "D:/desk-top/tools/uv-cache")
    try:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(dist), str(out / "codeark-pitax")],
            check=True, env=env,
        )
    except FileNotFoundError:
        print("uv not found: run `pip wheel --no-deps -w <dist> <pkgdir>` manually")
        return 2
    wheels = sorted(dist.glob("*.whl"))
    print(f"wheel: {wheels[-1] if wheels else 'MISSING'}")
    print("publish (需要 PyPI 账号): uv publish " + str(wheels[-1] if wheels else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
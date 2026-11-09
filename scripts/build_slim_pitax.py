"""构建零依赖瘦包 codeark-pitax（分发物生成器，非第二份实现）。

单一事实源纪律：规则与检测逻辑只在 `codeark/pitax/` + `codeark/tools/pitax_scan.py` +
`codeark/tools/dep_scan.py` + `codeark/agents/report_agent.py` + `codeark/office_text.py` +
`codeark/office_scan.py` 存在；本脚本把它们**复制并重写导入**成独立分发包
`codeark_pitax`（纯标准库，零第三方依赖），供 PyPI 发布与 arcanum-mcp 一键安装。

用法：
  python scripts/build_slim_pitax.py                 # 生成包源 + wheel
  python scripts/build_slim_pitax.py --no-wheel      # 只生成包源（测试用）
  python scripts/build_slim_pitax.py --out D:/x      # 指定输出目录

产物：
  <out>/codeark-pitax/       生成的包源（codeark_pitax/ + pyproject.toml + README.md）
  <out>/dist/*.whl           wheel（未用 --no-wheel 时）

发布（用户侧，需 PyPI 账号）：uv publish <out>/dist/<wheel>
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
VERSION = "0.2.2"

# 复制映射：源 → 生成文件名；rewrites 逐条替换导入
COPY_PLAN: list[tuple[Path, str, list[tuple[str, str]]]] = [
    # pitax 规则层逐字携带；descriptions_en 单列（report_lang 相对导入需改写为平铺单点）
    *[(f, f.name, []) for f in sorted((ROOT / "codeark" / "pitax").glob("*.py"))
      if f.name != "descriptions_en.py"],
    (
        ROOT / "codeark" / "pitax" / "descriptions_en.py",
        "descriptions_en.py",
        [("from ..report_lang import is_en", "from .report_lang import is_en")],
    ),
    (
        ROOT / "codeark" / "tools" / "pitax_scan.py",
        "scan_engine.py",
        [("from ..pitax.detectors import", "from .detectors import")],
    ),
    (
        ROOT / "codeark" / "agents" / "report_agent.py",
        "reporting.py",
        [("from codeark.report_lang import t", "from .report_lang import t")],
    ),
    # 报告语言开关（ARCA_REPORT_LANG）：纯标准库，逐字携带——slim CLI 同样获得 en 模式
    (ROOT / "codeark" / "report_lang.py", "report_lang.py", []),
    # office 文档投毒体检 + 依赖漏洞比对（MCP C1/C3 承重资产，纯标准库）
    (ROOT / "codeark" / "office_text.py", "office_text.py", []),
    (
        ROOT / "codeark" / "office_scan.py",
        "office_scan.py",
        [
            ("from codeark.agents.report_agent import build_html", "from .reporting import build_html"),
            ("from codeark.office_text import", "from .office_text import"),
            ("from codeark.pitax.detectors import (", "from .detectors import ("),
            ("from codeark.tools.pitax_scan import scan_file", "from .scan_engine import scan_file"),
        ],
    ),
    (ROOT / "codeark" / "tools" / "dep_scan.py", "dep_scan.py", []),
    # laya 假设排序运行时（rank_hypotheses 用）：顶层纯标准库，torch 只在
    # vendor rl_agent_api.py（随 checkpoint 目录）运行时引入，slim 可安全携带
    (ROOT / "codeark" / "graph" / "laya_runtime.py", "laya_runtime.py", []),
]

CLI_LINES = [
    '"""codeark-pitax 命令行：仓库/文件的确定性提示注入扫描（零依赖、零网络）。"""',
    "from __future__ import annotations",
    "",
    "import argparse",
    "import json",
    "import sys",
    "from pathlib import Path",
    "",
    "from .scan_engine import scan_repo",
    "from .reporting import render_report",
    "from .detectors import is_ai_config_path",
    "from .rules import PITAX_VERSION",
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
    '    parser.add_argument("--fail-on-findings", action="store_true",',
    '                        help="exit 3 when any finding is reported (CI gate)")',
    '    parser.add_argument("--fail-on", default="",',
    '                        help="exit 3 only at or above this severity: low,medium,high,critical")',
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
    "        # sarif 是 dict（其余格式是 str）——落盘前序列化，否则 write_text 报类型错",
    "        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)",
    "        fp.write_text(text, encoding='utf-8')",
    "        print(f'- {fp} ({fp.stat().st_size} B)')",
    '    print(f"findings: {len(dicts)}  files: {len(files)}  skipped: {skipped}")',
    '    print("local only: nothing was uploaded, no model was called")',
    "    if args.fail_on_findings or args.fail_on:",
    '        levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}',
    "        gate = levels.get((args.fail_on or 'low').strip().lower(), 1)",
    "        hit = [d for d in dicts",
    "               if levels.get(str(d.get('severity') or 'medium').lower(), 2) >= gate]",
    "        if hit:",
    '            print(f"GATE: {len(hit)} finding(s) at or above {args.fail_on or \'low\'} — failing")',
    "            return 3",
    "    return 0",
    "",
    "",
    'if __name__ == "__main__":',
    "    sys.exit(main())",
]

# 生成 pyproject 用整块模板（TOML 无尾逗号；license 走标准分类器，规避 PEP 639 版本差异）
PYPROJECT_TOML = """[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "codeark-pitax"
version = "{VERSION}"
description = "Deterministic prompt-injection scanner (PITAX): scan repos/docs for AI-assistant hijacking patterns. Zero dependencies, local only."
readme = "README.md"
requires-python = ">=3.10"
dependencies = []
keywords = ["prompt-injection", "security", "static-analysis", "llm", "pitax", "ai-safety", "code-review"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    # 注意：新版 setuptools 禁用 License 分类器（PEP 639）——license 用 SPDX 字符串表达
    "Programming Language :: Python :: 3",
    "Topic :: Security",
]

[project.urls]
Homepage = "https://github.com/a9320/arcanum-spark"
Repository = "https://github.com/a9320/arcanum-spark"
Issues = "https://github.com/a9320/arcanum-spark/issues"

[project.scripts]
codeark-pitax = "codeark_pitax.cli:main"

[tool.setuptools.packages.find]
include = ["codeark_pitax*"]
"""

README_MD = """# codeark-pitax

Deterministic prompt-injection scanner (PITAX rules): scan repositories, documents
and untrusted text for AI-assistant hijacking patterns — invisible Unicode, trojan
source, instruction overrides, encoded payloads. Zero dependencies, zero network,
zero model calls; everything stays on your machine.

Part of CodeRisk Arcanum (https://github.com/a9320/arcanum-spark).
Source / issues: https://github.com/a9320/arcanum-spark

## Usage

```bash
codeark-pitax scan ./your-repo --formats html --out ./pitax-report
```

## Attribution

The PITAX rule set is derived from the Prompt Injection Taxonomy v1.6.1 by
Jason Haddix / Arcanum (CC BY 4.0).

License: MIT (same as arcanum-spark).
"""


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

    # 便捷导出：import codeark_pitax 即得 scan/office/dep 公共 API（wheel 用户）
    init = (pkg_dir / "__init__.py").read_text(encoding="utf-8")
    if "scan_repo" not in init:
        nl = chr(10)
        init += nl + "from .scan_engine import scan_file, scan_repo  # noqa: E402,F401" + nl
    if "scan_office_tree" not in init:
        init += (
            "from .office_scan import scan_office_file, scan_office_tree  # noqa: E402,F401\n"
            "from .dep_scan import scan_deps  # noqa: E402,F401\n"
        )
        _write(pkg_dir / "__init__.py", init)

    _write(pkg_dir / "cli.py", "\n".join(CLI_LINES) + "\n")
    _write(pkg_dir / "__main__.py", "from .cli import main\n\nimport sys\n\nsys.exit(main())\n")
    _write(out / "codeark-pitax" / "pyproject.toml", PYPROJECT_TOML.replace("{VERSION}", VERSION))
    _write(out / "codeark-pitax" / "README.md", README_MD)

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
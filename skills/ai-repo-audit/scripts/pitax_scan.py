#!/usr/bin/env python3
"""ai-repo-audit 确定性扫描 CLI。

包装 arcanum-spark 的 PITAX 纯 stdlib 引擎（codeark/pitax），对仓库目录执行
9 条 AI 提示注入/欺骗规则的确定性检测，输出 JSON / SARIF 2.1.0 / Markdown。

设计原则（对齐引擎铁律）：
- 纯确定性、零 LLM、永不抛异常——失败返回空结果 + 可读错误，不中断调用方；
- 只读扫描：不执行被扫描代码、不改写仓库任何文件；
- 全离线：不联网、不调用外部服务，数据不出机。

用法:
    pitax_scan.py <repo-path> [--format json|sarif|md] [--out 输出文件]
    pitax_scan.py <repo-path> --all --out-dir 输出目录   # 三格式一次全出
    pitax_scan.py <repo-path> --min-severity high        # 只留 high/critical

依赖：Python ≥3.10 标准库；引擎来自 arcanum-spark 仓库（codeark/pitax 可导入）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── 定位 arcanum-spark 仓库根并注入 sys.path（技能随仓库分发时可随处运行）──
SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = SCRIPT_DIR.parents[2]  # skills/ai-repo-audit/scripts → 仓库根
sys.path.insert(0, str(_REPO_ROOT))

from codeark.pitax import PITAX_VERSION, build_sarif  # noqa: E402
from codeark.pitax.detectors import is_ai_config_path  # noqa: E402
from codeark.pitax.rules import ALL_RULES  # noqa: E402
from codeark.pitax.sanitizer import (  # noqa: E402
    MAX_FILE_BYTES, SCAN_EXTENSIONS, SKIP_DIRS,
)
from codeark.tools.pitax_scan import scan_repo  # noqa: E402

TOOL_NAME = "Arcanum AI-Repo-Audit Skill"
TOOL_VERSION = "1.0.0"

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_FORMAT_ALIASES = {
    "json": "json", "sarif": "sarif", "md": "md", "markdown": "md",
}


def _scan_repo_dir(repo_path: str) -> tuple[list[dict], dict]:
    """按 scan_repo 口径扫描目录（与管线 agent0 同源同计数，12 命中对齐评测）。

    跳过规则复用引擎常量（SKIP_DIRS / MAX_FILE_BYTES / SCAN_EXTENSIONS），
    文件集读入内存后交给 codeark.tools.pitax_scan.scan_repo。永不抛异常。
    """
    stats: dict = {
        "files_scanned": 0, "files_skipped": 0,
        "pitax_version": PITAX_VERSION,
        "rules": ALL_RULES,
    }
    root = Path(repo_path)
    if not root.exists():
        return [], {**stats, "error": f"path not found: {repo_path}"}
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            stats["files_skipped"] += 1
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            stats["files_skipped"] += 1
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if path.suffix.lower() not in SCAN_EXTENSIONS and not is_ai_config_path(rel):
            stats["files_skipped"] += 1
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            stats["files_skipped"] += 1
            continue
        stats["files_scanned"] += 1
    return scan_repo(files), stats


def _filter_findings(findings: list[dict], min_severity: str | None) -> list[dict]:
    if not min_severity:
        return findings
    floor = _SEVERITY_RANK.get(min_severity.lower(), 1)
    return [f for f in findings
            if _SEVERITY_RANK.get(str(f.get("severity", "medium")).lower(), 4) <= floor]


def _render_markdown(findings: list[dict], stats: dict, repo_path: str) -> str:
    lines = [
        f"# AI-Repo-Audit 扫描报告（确定性 · 离线）",
        "",
        f"- 扫描目标：`{repo_path}`",
        f"- PITAX 版本：{stats.get('pitax_version', PITAX_VERSION)}",
        f"- 扫描文件：{stats.get('files_scanned', 0)}（跳过 {stats.get('files_skipped', 0)}）",
        f"- 命中总数：{len(findings)}",
        "",
        "> 依据：Arcanum Prompt Injection Taxonomy v1.6.1（Jason Haddix, CC BY 4.0）。",
        "> 本报告为确定性检测结果，供审计 Agent 引用；每条命中携带编号与证据，可复核。",
        "",
    ]
    if stats.get("error"):
        lines.append(f"⚠️ 扫描异常：{stats['error']}")
    if not findings:
        lines.append("**未检出 PITAX 规则命中。**")
        lines.append("")
        lines.append("> 注意：空检出 ≠ 安全——确定性层之外，还应由审计 Agent 完成语义层复核。")
        return "\n".join(lines)

    by_sev: dict[str, list[dict]] = {}
    for f in findings:
        by_sev.setdefault(str(f.get("severity", "unknown")).lower(), []).append(f)
    for sev in ("critical", "high", "medium", "low", "info", "unknown"):
        if sev not in by_sev:
            continue
        lines.append(f"## {sev.capitalize()}")
        for f in by_sev[sev]:
            pitax = f.get("pitax", {})
            lines.append(
                f"- **[{f.get('type')}] {pitax.get('name', f.get('title'))}**"
                f"（`{f.get('file')}:{f.get('line')}`，置信度 {f.get('confidence')}）"
            )
            lines.append(f"  - {f.get('description', '').strip()}")
            evidence = (pitax.get("evidence") or "").strip()
            if evidence:
                lines.append(f"  - 证据：`{evidence[:200]}`")
            if pitax.get("decoded_payload"):
                lines.append(f"  - 解码载荷：`{pitax['decoded_payload'][:200]}`")
            if f.get("suggestion"):
                lines.append(f"  - 处置建议：{f['suggestion']}")
            refs = pitax.get("references") or []
            if refs:
                lines.append(f"  - 参考：{', '.join(refs[:3])}")
            lines.append("")
        lines.append("")
    lines.append("---")
    lines.append("*生成工具：Arcanum AI-Repo-Audit Skill（PITAX 确定性层，零 LLM、全离线）。*")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pitax_scan.py",
        description="PITAX 确定性扫描：对仓库目录执行 9 条 AI 提示注入/欺骗规则检测。",
    )
    ap.add_argument("repo_path", help="待扫描仓库目录的绝对或相对路径")
    ap.add_argument("--format", choices=sorted(_FORMAT_ALIASES), default="json",
                    help="输出格式（默认 json）")
    ap.add_argument("--out", help="写入输出文件（默认打印到 stdout）")
    ap.add_argument("--all", action="store_true",
                    help="同时输出 json/sarif/md 三种格式")
    ap.add_argument("--out-dir", default=".", help="--all 时的输出目录（默认当前目录）")
    ap.add_argument("--min-severity", choices=["critical", "high", "medium"],
                    help="只保留该级别及以上命中的结果")
    args = ap.parse_args(argv)

    findings, stats = _scan_repo_dir(args.repo_path)
    findings = _filter_findings(findings, args.min_severity)

    # --all 三格式导出
    if args.all:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"pitax-audit-{Path(args.repo_path).name or 'repo'}"
        (out_dir / f"{stem}.json").write_text(
            json.dumps({"summary": stats, "findings": findings},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"{stem}.sarif").write_text(
            json.dumps(build_sarif(findings, TOOL_NAME, TOOL_VERSION),
                       ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / f"{stem}.md").write_text(
            _render_markdown(findings, stats, args.repo_path), encoding="utf-8")
        print(f"已写出 {out_dir / stem}.{{json,sarif,md}}"
              f"（{len(findings)} 条命中）", file=sys.stderr)
        return 0

    fmt = _FORMAT_ALIASES.get(args.format, "json")
    if fmt == "json":
        payload = json.dumps({"summary": stats, "findings": findings},
                             ensure_ascii=False, indent=2)
    elif fmt == "sarif":
        payload = json.dumps(build_sarif(findings, TOOL_NAME, TOOL_VERSION),
                             ensure_ascii=False, indent=2)
    else:  # md
        payload = _render_markdown(findings, stats, args.repo_path)

    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"已写出 {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(payload + ("\n" if fmt in ("json", "sarif") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
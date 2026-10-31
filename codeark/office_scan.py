"""Office 文档安全体检：抽取文本 → PITAX 规则 → 报告。

用法：
    python -m codeark.cli docs-scan <file-or-dir> [--out OUT] [--formats json,html]

检测面与文档路径一致（N-06 文档投毒 + E-23 不可见字符 + E-54 Trojan + 编码四件），
不新增规则；`meta.office_scan` 记录覆盖率（文件数/部件数/字符数/跳过数），
与"扫了全仓"不同，这里写的是真实扫描范围。

报告只生成到本地（生成≠发布），HTML 为自包含单页。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from codeark.agents.report_agent import build_html
from codeark.office_text import SUPPORTED_OFFICE_EXTS, extract_office_text
from codeark.pitax.detectors import (
    detect_doc_injection,
    detect_encoded_payloads,
    detect_invisible_text,
    detect_trojan_source,
)
from codeark.tools.pitax_scan import scan_file  # noqa: F401  (与产品同源的检测入口)

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PART_CHARS = 200_000


def collect_office_files(target: Path) -> tuple[list[Path], int]:
    if target.is_file():
        return [target], 0
    files: list[Path] = []
    skipped = 0
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in SUPPORTED_OFFICE_EXTS:
            skipped += 1
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                skipped += 1
                continue
        except OSError:
            skipped += 1
            continue
        files.append(p)
    return files, skipped


def scan_office_file(path: Path) -> tuple[list[dict], dict[str, Any]]:
    """返回 (report_dicts, coverage)；单文件抽取或检测失败都会抛给调用方记账。"""
    findings: list[dict] = []
    parts = extract_office_text(path)
    chars = 0
    for part_name, text in parts:
        chars += len(text)
        label = f"{path.name}::{part_name}"
        hits = [
            *detect_doc_injection(text, label),
            *detect_invisible_text(text, label),
            *detect_trojan_source(text, label),
            *detect_encoded_payloads(text, label),
        ]
        for i, f in enumerate(hits, start=1):
            findings.append(f.to_report_dict(f"office-{path.name}-{i}", language="docx"))
    coverage = {"parts": len(parts), "chars": chars}
    return findings, coverage


def scan_office_tree(target: Path) -> tuple[list[dict], dict[str, Any]]:
    files, skipped = collect_office_files(target)
    findings: list[dict] = []
    parts = 0
    chars = 0
    errors: dict[str, str] = {}
    for p in files:
        try:
            file_findings, cov = scan_office_file(p)
        except Exception as exc:  # 单文件损坏不拖垮整次扫描，但必须记账
            errors[str(p)] = f"{type(exc).__name__}"
            continue
        findings.extend(file_findings)
        parts += cov["parts"]
        chars += cov["chars"]
    meta = {
        "office_scan": {
            "target": str(target),
            "files": len(files),
            "parts": parts,
            "chars": chars,
            "skipped": skipped,
            "errors": errors,
        }
    }
    return findings, meta


def build_report(findings: list[dict], meta: dict[str, Any]) -> dict[str, str]:
    payload = {"findings": findings, "attack_chains": [], "conclusion": "", "meta": meta}
    out = {"json": json.dumps(payload, ensure_ascii=False, indent=2)}
    out["html"] = build_html(findings, [], "", meta)
    return out


def run_cli(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="codeark docs-scan", description="Office 文档注入体检")
    parser.add_argument("target", help="docx/xlsx/pptx 文件或目录")
    parser.add_argument("--out", default="./reports", help="报告输出目录（默认 ./reports）")
    parser.add_argument("--formats", default="json,html", help="json,html")
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"❌ Target not found: {target}")
        return 1

    findings, meta = scan_office_tree(target)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = build_report(findings, meta)
    written: list[Path] = []
    for name in [f.strip() for f in args.formats.split(",")]:
        if name == "json":
            fp = out_dir / "office-report.json"
            fp.write_text(reports["json"], encoding="utf-8")
        elif name == "html":
            fp = out_dir / "office-report.html"
            fp.write_text(reports["html"], encoding="utf-8")
        else:
            continue
        written.append(fp)

    cov = meta["office_scan"]
    print(f"📄 Office scan: {cov['files']} file(s), {cov['parts']} part(s), "
          f"{cov['chars']} chars, {cov['skipped']} skipped, {len(findings)} finding(s)")
    for fp in written:
        print(f"   - {fp} ({fp.stat().st_size} B)")
    print("generation ≠ publication; nothing sent externally.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_cli(sys.argv[1:]))
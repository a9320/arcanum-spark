"""Office 文档安全体检：抽取文本 → PITAX 规则 → 报告。

用法：
    python -m codeark.cli docs-scan <file-or-dir> [--out OUT] [--formats json,html]

检测面与文档路径一致（N-06 文档投毒 + E-23 不可见字符 + E-54 Trojan + 编码四件），
不新增规则；`meta.office_scan` 记录覆盖率（文件数/部件数/字符数/跳过数）与遍历上限
（`caps.stopped_by`：max_files / max_total_bytes / max_depth / max_entries，触发即披露），
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
# 目录遍历上限（防误指仓库根/盘根时把整棵树物化进内存）：
# 四道闸任一触发即停，原因写进 meta.office_scan.caps.stopped_by（不静默截断）。
MAX_FILES = 500
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_DEPTH = 16
MAX_ENTRIES = 200_000


def collect_office_files(target: Path) -> tuple[list[Path], int, dict[str, Any]]:
    """收集待扫 Office 文件：文件直通；目录走带上限的确定性遍历。

    返回 (files, skipped, walk_meta)；walk_meta 披露遍历量与被哪道上限截断。
    不跟随符号链接目录（防环）。
    """
    if target.is_file():
        return [target], 0, {"entries": 0, "stopped_by": None}

    files: list[Path] = []
    skipped = 0
    total_bytes = 0
    entries = 0
    stopped_by: str | None = None
    stack: list[tuple[Path, int]] = [(target, 0)]

    while stack:
        directory, depth = stack.pop()
        if depth > MAX_DEPTH:
            stopped_by = stopped_by or "max_depth"
            continue
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name)
        except OSError:
            skipped += 1
            continue
        for child in children:
            entries += 1
            if entries > MAX_ENTRIES:
                stopped_by = stopped_by or "max_entries"
                stack.clear()
                break
            try:
                if child.is_symlink() and child.is_dir():
                    skipped += 1
                    continue
                if child.is_dir():
                    stack.append((child, depth + 1))
                    continue
                if not child.is_file():
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            if child.suffix.lower() not in SUPPORTED_OFFICE_EXTS:
                skipped += 1
                continue
            try:
                size = child.stat().st_size
            except OSError:
                skipped += 1
                continue
            if size > MAX_FILE_BYTES:
                skipped += 1
                continue
            if len(files) >= MAX_FILES:
                stopped_by = stopped_by or "max_files"
                stack.clear()
                break
            if total_bytes + size > MAX_TOTAL_BYTES:
                stopped_by = stopped_by or "max_total_bytes"
                stack.clear()
                break
            files.append(child)
            total_bytes += size

    files.sort()
    return files, skipped, {"entries": entries, "stopped_by": stopped_by}


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
    files, skipped, walk = collect_office_files(target)
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
            "caps": {
                "max_files": MAX_FILES,
                "max_total_bytes": MAX_TOTAL_BYTES,
                "max_depth": MAX_DEPTH,
                "max_entries": MAX_ENTRIES,
                "entries_scanned": walk["entries"],
                "stopped_by": walk["stopped_by"],
            },
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
    if cov.get("caps", {}).get("stopped_by"):
        print(f"⚠ 目录遍历被上限截断: {cov['caps']['stopped_by']} "
              "（扫描范围不完整，见 meta.office_scan.caps）")
    for fp in written:
        print(f"   - {fp} ({fp.stat().st_size} B)")
    print("generation ≠ publication; nothing sent externally.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_cli(sys.argv[1:]))
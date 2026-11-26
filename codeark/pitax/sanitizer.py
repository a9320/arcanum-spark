"""InputSanitizer — Agent 0 核心：对目录内源代码执行 PITAX 预扫描。

检测分发（与官方 taxonomy v1.6.1 编号对齐）：
  所有文件           → PIT-E-23 不可见字符 + PIT-E-54 Trojan Source + 编码类
  AI 指令文件        → PIT-T-46（.cursor/rules、CLAUDE.md、copilot-instructions.md）
  项目文档 (.md 等)  → PIT-N-06 文档投毒
  代码文件           → PIT-T-51 注释指令覆盖
"""
from __future__ import annotations

import logging
from pathlib import Path

from .detectors import (
    detect_ai_config_injection,
    detect_comment_injection,
    detect_doc_injection,
    detect_encoded_payloads,
    detect_invisible_text,
    detect_trojan_source,
    is_ai_config_path,
    is_doc_path,
)
from .rules import ALL_RULES, PITAX_VERSION

logger = logging.getLogger("coderisk.pitax")

SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".rb", ".php", ".sh", ".yaml", ".yml", ".json",
    ".md", ".mdc", ".cursorrules", ".txt", ".toml", ".cfg", ".ini",
    ".html", ".vue", ".sql",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2MB，防 zip 炸弹式超大文件


class InputSanitizer:
    """对单个文件执行全部 PITAX 确定性检测。"""

    def sanitize(self, code: str, file_path: str, language: str = "text") -> tuple[list[dict], list]:
        raw: list = []
        raw += detect_invisible_text(code, file_path)    # PIT-E-23
        raw += detect_trojan_source(code, file_path)     # PIT-E-54
        if is_ai_config_path(file_path):
            raw += detect_ai_config_injection(code, file_path)  # PIT-T-46
        elif is_doc_path(file_path):
            raw += detect_doc_injection(code, file_path)        # PIT-N-06
        else:
            raw += detect_comment_injection(code, file_path)    # PIT-T-51
        raw += detect_encoded_payloads(code, file_path)          # E-07/14/36/57

        findings, seen = [], set()
        for i, f in enumerate(raw, start=1):
            key = (f.pitax_code, f.file, f.line)
            if key in seen:
                continue
            seen.add(key)
            findings.append(f.to_report_dict(f"PITAX-{i:04d}", language))
        return findings, raw


def scan_directory(work_dir: str) -> tuple[list[dict], dict]:
    """Agent 0 入口：扫描目录，返回 (findings, stats)。

    best-effort 契约：path 不存在或目录不可遍历时返回 error 字段；单个文件的
    文件系统异常（遍历后被删/改名、权限错）跳过并计入 files_skipped，不中断
    整次扫描。检测器自身异常不在此吞掉——那是 bug，应显式暴露（调用方仍可
    用 run_agent0 的兜底保证流水线不断）。
    """
    sanitizer = InputSanitizer()
    all_findings: list[dict] = []
    stats = {
        "files_scanned": 0, "files_skipped": 0,
        "pitax_version": PITAX_VERSION,
        "rules": ALL_RULES,
    }
    root = Path(work_dir)
    if not root.exists():
        return all_findings, {**stats, "error": f"path not found: {work_dir}"}
    try:
        # rglob 是惰性遍历：权限错/根目录被删会在迭代中抛 OSError，须整体兜住
        paths = sorted(root.rglob("*"))
    except OSError as e:
        logger.error(f"PITAX scan aborted: cannot walk {work_dir}: {e}")
        return all_findings, {**stats, "error": f"cannot walk: {e}"}
    for path in paths:
        try:
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                stats["files_skipped"] += 1
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                stats["files_skipped"] += 1
                continue
            rel = str(path.relative_to(root))
            if path.suffix.lower() not in SCAN_EXTENSIONS:
                if not is_ai_config_path(rel):
                    stats["files_skipped"] += 1
                    continue
            code = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            # 文件系统竞态（遍历后被删/改名）或权限错：跳过该文件，不拖垮整次扫描
            stats["files_skipped"] += 1
            logger.debug(f"PITAX scan skip {path}: {e}")
            continue
        stats["files_scanned"] += 1
        findings, _ = sanitizer.sanitize(code, rel)
        for i, f in enumerate(findings, start=len(all_findings) + 1):
            f["id"] = f"PITAX-{i:04d}"
        all_findings.extend(findings)
    logger.info(f"PITAX scan: {stats['files_scanned']} files, {len(all_findings)} findings")
    return all_findings, stats

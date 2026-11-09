"""Office 文档文本抽取（docx/xlsx/pptx）→ PITAX 检测的输入层。

零第三方依赖：OOXML 本质是 zip + XML，用 zipfile + ElementTree 抽取文本。
定位：文档是 AI 助手的常规输入载体（PIT-N-06），但攻击面不止 .md/.txt——
Word 的隐藏文本、Excel 单元格、PPT 备注同样能夹带指令。本模块只负责
"把文本拿出来"，检测复用 pitax.detectors，不新增规则。

抽取范围：
- docx: word/document.xml + comments/footnotes/endnotes 的 w:t（含 w:vanish 隐藏文本——
  正因为人眼不可见，才必须扫）
- xlsx: xl/sharedStrings.xml 与各 sheet 的 t（单元格文本）
- pptx: ppt/slides/slideN.xml 与 notesSlides 的 a:t（幻灯片正文与备注页）

接口：extract_office_text(path) -> [(part_name, text)]；part_name 用 zip 内部路径，
保证报告里的定位可以回到具体部件。
"""
from __future__ import annotations

import os
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SUPPORTED_OFFICE_EXTS = {".docx", ".xlsx", ".pptx"}

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_SS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

_MAX_PART_BYTES = 10 * 1024 * 1024


def _texts(xml_bytes: bytes, tags: set[str]) -> str:
    """按文档顺序抽取指定标签的全部文本，每个文本块一行。"""
    root = ET.fromstring(xml_bytes)
    chunks = [elem.text or "" for elem in root.iter() if elem.tag in tags]
    return "\n".join(c for c in chunks if c.strip())


def _docx_parts(names: set[str]) -> list[str]:
    return sorted(
        n for n in names
        if n.startswith("word/") and n.endswith(".xml")
        and any(k in n for k in ("document", "comments", "footnotes", "endnotes"))
    )


def _pptx_parts(names: set[str]) -> list[str]:
    return sorted(
        n for n in names
        if (n.startswith("ppt/slides/slide") or n.startswith("ppt/notesSlides/notesSlide"))
        and n.endswith(".xml")
    )


def _open_verified(path: Path):
    """按已校验句柄打开 OOXML，关掉 walk→open 的 TOCTOU 窗口（2026-11-09 评审 P2）。

    `collect_office_files` 遍历时判过 reparse/symlink，但真正的读取发生在之后；
    这段时间里把文件换成链接，遍历期的判定就作废了。做法：open（POSIX 带
    O_NOFOLLOW）→ fstat 与 lstat 比对 (st_dev, st_ino)，身份不一致即拒绝。
    Windows 没有 O_NOFOLLOW，身份比对是那一侧的唯一闸门。
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        walked = os.lstat(path)
        if (opened.st_dev, opened.st_ino) != (walked.st_dev, walked.st_ino):
            raise OSError(f"file identity changed between walk and open: {path}")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def extract_office_text(path: str | Path) -> list[tuple[str, str]]:
    """返回 [(part_name, text)]。不支持的后缀抛 ValueError。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_OFFICE_EXTS:
        raise ValueError(f"unsupported office file: {p.name} (支持 {sorted(SUPPORTED_OFFICE_EXTS)})")

    parts: list[tuple[str, str]] = []
    with _open_verified(p) as fh, zipfile.ZipFile(fh) as zf:
        names = set(zf.namelist())
        if ext == ".docx":
            for name in _docx_parts(names):
                if zf.getinfo(name).file_size > _MAX_PART_BYTES:
                    continue
                text = _texts(zf.read(name), {f"{_W}t"})
                if text.strip():
                    parts.append((name, text))
        elif ext == ".xlsx":
            if "xl/sharedStrings.xml" in names:
                text = _texts(zf.read("xl/sharedStrings.xml"), {f"{_SS}t"})
                if text.strip():
                    parts.append(("xl/sharedStrings.xml", text))
            for name in sorted(n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml")):
                if zf.getinfo(name).file_size > _MAX_PART_BYTES:
                    continue
                text = _texts(zf.read(name), {f"{_SS}t"})
                if text.strip():
                    parts.append((name, text))
        else:  # .pptx
            for name in _pptx_parts(names):
                if zf.getinfo(name).file_size > _MAX_PART_BYTES:
                    continue
                text = _texts(zf.read(name), {f"{_A}t"})
                if text.strip():
                    parts.append((name, text))
    return parts
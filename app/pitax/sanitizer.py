"""PITAX 清洗器 — 单一数据源转发层（P2-9 收口，2026-10-22）。

本包不再自带实现；权威实现 = codeark/pitax/sanitizer.py。历史双拷贝曾整文件
重复（101 行），2026-10-22 收口为纯转发；每个名字与权威实现是同一对象，
identity 级断言见 tests/test_pitax_rules.py::test_pitax_single_source_forwarding。

Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix,
Arcanum Information Security (arcanum-sec.com). CC BY 4.0.
Citation: Haddix, J. (2026). Arcanum Prompt Injection Taxonomy (v1.6.1).
"""
from codeark.pitax.sanitizer import (  # noqa: F401
    MAX_FILE_BYTES,
    SCAN_EXTENSIONS,
    SKIP_DIRS,
    InputSanitizer,
    scan_directory,
)
"""SARIF 2.1.0 输出 — 单一数据源转发层（P2-9 收口，2026-10-22）。

本包不再自带实现；权威实现 = codeark/pitax/sarif.py（扩展 PITAX 元数据的
SARIF 2.1.0 构建器）。identity 级断言见
tests/test_pitax_rules.py::test_pitax_single_source_forwarding。

Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix,
Arcanum Information Security (arcanum-sec.com). CC BY 4.0.
Citation: Haddix, J. (2026). Arcanum Prompt Injection Taxonomy (v1.6.1).
"""
from codeark.pitax.sarif import SARIF_SCHEMA, build_sarif  # noqa: F401
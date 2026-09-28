"""PITAX 规则元数据注册表 — 单一数据源转发层（P2-9，2026-09-28）。

本包不再自带规则注册表；权威实现 = codeark/pitax/rules.py（含 ATLAS .001 核实
记录与 CVE-2025-53773 核实记录的富版，2026-09-11 逐条查证）。app 侧全部转发，
identity 级防漂移断言见 tests/test_pitax_rules.py::test_pitax_single_source_forwarding。

编号对齐史与 CWE/ATLAS 映射原则的完整说明见权威模块 docstring。

Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix,
Arcanum Information Security (arcanum-sec.com). CC BY 4.0.
Citation: Haddix, J. (2026). Arcanum Prompt Injection Taxonomy (v1.6.1).
"""
from codeark.pitax.rules import (  # noqa: F401
    ALL_RULES,
    PRIMARY_RULES,
    PITAX_REPO,
    PITAX_RULES,
    PITAX_SOURCE,
    PITAX_VERSION,
    get_rule,
)

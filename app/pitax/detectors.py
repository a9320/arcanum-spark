"""PITAX 确定性检测器 — 单一数据源转发层（P2-9，2026-09-28）。

本包不再自带检测实现；权威实现 = codeark/pitax/detectors.py（中文文案 + CVE/ATLAS
核实记录版）。历史双拷贝曾漂移（detectors 433/432 行），现 app 侧全部转发：
本模块的每个名字与权威实现是同一对象（identity 级断言见
tests/test_pitax_rules.py::test_pitax_single_source_forwarding）。
消费方注意：下划线常量（_CONFIG_PATTERNS/_ENCODED_TARGET_PATTERNS）也在此转发
——tests/test_demo_repo_ammo.py 的生成器同步断言从本模块导入。

Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix,
Arcanum Information Security (arcanum-sec.com). CC BY 4.0.
"""
from codeark.pitax.detectors import (  # noqa: F401
    AI_CONFIG_BASENAMES,
    DOC_EXTENSIONS,
    TAG_RANGE,
    Finding,
    _CONFIG_PATTERNS,
    _ENCODED_TARGET_PATTERNS,
    detect_ai_config_injection,
    detect_comment_injection,
    detect_doc_injection,
    detect_encoded_payloads,
    detect_invisible_text,
    detect_trojan_source,
    is_ai_config_path,
    is_doc_path,
)

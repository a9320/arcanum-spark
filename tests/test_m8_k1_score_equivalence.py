"""M8/K1 判分器 v0.5 等价类护栏单测 — 防虚翻+翻案回归锚。

v0.5 第一案（2026-10-15）：ARBITRARY_CODE_EXECUTION↔REMOTE_CODE_EXECUTION 显式等价。
依据=10-14 A/B 实证：Muse good_intentions 卷 H1（fileConfig eval() RCE 官方链，
verify CONFIRMED 0.85）打标 ARBITRARY_CODE_EXECUTION，官方 intended=REMOTE_CODE_EXECUTION
→ v0.4 判 FN=词面冤案。护栏四面：翻案锚（语义翻正）、双口径分离（机制严格词面不翻）、
防虚翻锚（相邻族不得虚并，v0.1 弱映射纪律继续有效）、对称性+变体路径。
运行: python -m pytest tests/test_m8_k1_score_equivalence.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

import m8_k1_score as scorer

GI_INTENDED = ["ACCESS_CONTROL_BYPASS", "PATH_TRAVERSAL", "REMOTE_CODE_EXECUTION"]


def test_v05_gi_wordverdict_flipped_semantic():
    """翻案锚：Muse gi 卷 H1 冤案在语义口径翻正（v0.4=FN）。"""
    assert scorer._m_semantic("ARBITRARY_CODE_EXECUTION", GI_INTENDED)


def test_v05_mechanism_caliber_stays_strict():
    """双口径分离：机制口径保持严格词面，翻案只走语义等价类。"""
    assert not scorer._m_exact("ARBITRARY_CODE_EXECUTION", GI_INTENDED)


def test_v05_no_cross_family_contamination():
    """防虚翻锚：代码执行族不得虚并入相邻族（RCE 族不进 COMMAND_INJECTION 类等）。"""
    assert not scorer._same_class("ARBITRARY_CODE_EXECUTION", "ARBITRARY_FILE_READ")
    assert not scorer._same_class("ARBITRARY_CODE_EXECUTION", "COMMAND_INJECTION")
    assert not scorer._same_class("REMOTE_CODE_EXECUTION", "COMMAND_INJECTION")
    assert not scorer._same_class("REMOTE_CODE_EXECUTION", "DESERIALIZATION_RCE")
    assert not scorer._same_class("ARBITRARY_CODE_EXECUTION", "LOCAL_FILE_INCLUSION")


def test_v05_symmetric_and_variant_path():
    """对称性 + v0.4 段级变体路径：'Remote Code Execution' 自然语言串同样入类。"""
    assert scorer._same_class("REMOTE_CODE_EXECUTION", "ARBITRARY_CODE_EXECUTION")
    assert scorer._m_semantic("Remote Code Execution", GI_INTENDED)
    assert scorer._m_semantic("Remote Code Execution / Privilege Escalation",
                              ["PRIVILEGE_ESCALATION", "REMOTE_CODE_EXECUTION"])


def test_v05_registry_shape():
    """登记表形状：恰 9 族，代码执行族含 v0.5 两名成员（v0.6 再加 RCE）。"""
    assert len(scorer.EQUIV_CLASSES) == 9
    assert ("REMOTE_CODE_EXECUTION" in scorer._VT_CLASS
            and "ARBITRARY_CODE_EXECUTION" in scorer._VT_CLASS)
    assert scorer._VT_CLASS["REMOTE_CODE_EXECUTION"] == scorer._VT_CLASS["ARBITRARY_CODE_EXECUTION"]


# ────────────── v0.6 第二案（2026-10-18）：RCE 别名 + ACCESS_CONTROL_BYPASS ──────────────

def test_v06_rce_alias_flips_semantic_not_mechanism():
    """翻案锚：webhooktester H2 标签 "RCE" 对官方 REMOTE_CODE_EXECUTION 语义翻正。"""
    assert scorer._m_semantic("RCE", ["REMOTE_CODE_EXECUTION"])
    assert scorer._m_semantic("RCE", ["ARBITRARY_CODE_EXECUTION"])
    assert not scorer._m_exact("RCE", ["REMOTE_CODE_EXECUTION"])  # 机制口径严格词面不动


def test_v06_access_control_bypass_joins_auth_family():
    """gi 跨卷漂移锚：ACCESS_CONTROL_BYPASS 与 AUTH_BYPASS 双向同族。"""
    assert scorer._m_semantic("ACCESS_CONTROL_BYPASS", ["AUTH_BYPASS"])
    assert scorer._m_semantic("AUTH_BYPASS", ["ACCESS_CONTROL_BYPASS"])
    assert not scorer._m_exact("ACCESS_CONTROL_BYPASS", ["AUTH_BYPASS"])


def test_v06_no_substring_no_cross_family():
    """防虚翻锚：只做段级精确别名，不做子串；非授权族不得虚并。"""
    assert not scorer._same_class("RCE", "FORCED_RCE")
    assert not scorer._same_class("RCE", "DESERIALIZATION_RCE")
    assert not scorer._same_class("ACCESS_CONTROL_BYPASS", "PRIVILEGE_ESCALATION")
    assert not scorer._same_class("ACCESS_CONTROL_BYPASS", "PATH_TRAVERSAL")


def test_v06_registry_shape():
    """登记表形状：9 族不变；两处扩员落位且类号一致。"""
    assert len(scorer.EQUIV_CLASSES) == 9
    assert ("REMOTE_CODE_EXECUTION", "ARBITRARY_CODE_EXECUTION", "RCE") in scorer.EQUIV_CLASSES
    assert ("AUTH_BYPASS", "BROKEN_AUTHENTICATION", "AUTHENTICATION_BYPASS",
            "ACCESS_CONTROL_BYPASS") in scorer.EQUIV_CLASSES
    assert scorer._VT_CLASS["RCE"] == scorer._VT_CLASS["REMOTE_CODE_EXECUTION"]
    assert scorer._VT_CLASS["ACCESS_CONTROL_BYPASS"] == scorer._VT_CLASS["AUTH_BYPASS"]


def test_v06_gi_semantic_tp_unchanged():
    """回归：gi 卷 intended 含 ACCESS_CONTROL_BYPASS，v0.5 已翻正的口径不退化。"""
    assert scorer._m_semantic("ARBITRARY_CODE_EXECUTION", GI_INTENDED)
    assert scorer._m_semantic("AUTH_BYPASS", GI_INTENDED)
    assert scorer._m_semantic("ACCESS_CONTROL_BYPASS", GI_INTENDED)

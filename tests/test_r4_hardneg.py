"""R4 难负训练实例构造器单测 — TWIN-B' 扩产 / 双轮 anti-leak / export 契约。

anti-leak 生命线升级为双向：训练实例与 hard_exam/2 **及 r3_hardneg** 零重合
（title/attack_path/file_path 三重比对），held-out 地位不因 R4 训练而破。
运行: python -m pytest tests/test_r4_hardneg.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.build_hard_exam import build_hard_exam
from eval.build_r3_hardneg import build_r3_hardneg
from eval.build_r4_hardneg import build_r4_hardneg
from eval.finetune_export import item_to_record


def _by_prefix(items, prefix):
    return [it for it in items if it["id"].startswith(prefix)]


def test_determinism_and_structure():
    a, b = build_r4_hardneg(), build_r4_hardneg()
    a.pop("created_utc"), b.pop("created_utc")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == "gate-dataset/1"
    assert a["source"]["generator"] == "r4_hardneg/1"
    ids = [it["id"] for it in a["items"]]
    assert len(ids) == len(set(ids)) == 64
    assert len(_by_prefix(a["items"], "T4K")) == 32
    assert len(_by_prefix(a["items"], "T4B")) == 32
    labels = [it["label"]["gate"] for it in a["items"]]
    assert labels.count("KEEP") == 32 and labels.count("PRUNE") == 32
    assert a["n_baseline"] == len(a["baseline_rows"]) == 7
    types = {it["vuln_type"] for it in a["items"]}
    assert types == {"PIT-E-57", "PIT-N-06", "PIT-E-54", "PIT-T-46", "CRED_EXFIL"}


def test_anti_leak_vs_exam_and_r3():
    """三重零重合：title/attack_path/file_path 对考卷与 R3 训练件都必须干净。"""
    ex, r3, r4 = build_hard_exam(), build_r3_hardneg(), build_r4_hardneg()
    for prior in (ex, r3):
        titles = {it["title"] for it in prior["items"]}
        paths = {it["attack_path"] for it in prior["items"]}
        files = {it["file_path"] for it in prior["items"]}
        for it in r4["items"]:
            assert it["title"] not in titles, it["id"]
            assert it["attack_path"] not in paths, it["id"]
            assert it["file_path"] not in files, it["id"]


def test_pool_disjointness_vs_r3():
    """R4 端点/应用/文本池与 R3 池零交集（防跨轮实例碰撞）。"""
    from eval.build_r3_hardneg import _APPS as A3, _EK as K3, _EB as B3
    from eval.build_r4_hardneg import _APPS as A4, _EK as K4, _EB as B4
    assert not set(A4) & set(A3)
    assert not set(K4) & set(K3)
    assert not set(B4) & set(B3)


def test_twin_pairing_integrity():
    r4 = build_r4_hardneg()
    pairs: dict[str, list[dict]] = {}
    for it in _by_prefix(r4["items"], "T4"):
        # id 形如 T4K01/T4B01：K/B 在第 3 位，配对键剥掉该位
        pairs.setdefault(it["id"][:2] + it["id"][3:], []).append(it)
    assert len(pairs) == 32
    for pid, members in pairs.items():
        assert len(members) == 2
        k = next(m for m in members if m["id"][2] == "K")
        b = next(m for m in members if m["id"][2] == "B")
        assert k["label"]["gate"] == "KEEP" and b["label"]["gate"] == "PRUNE"
        assert k["title"] == b["title"]  # 表面打平，判据只在 attack_path
        assert k["file_path"] != b["file_path"]
        assert k["attack_path"] != b["attack_path"]  # K=恶意形态，B=自驳
        assert "self-refuting(train):" in b["label"]["note"]


def test_finetune_export_contract():
    """全部 64 条必须能被 finetune_export 无剔除消费（KEEP/PRUNE 齐备）。"""
    r4 = build_r4_hardneg()
    recs = [item_to_record(it, r4["baseline_rows"], "r4hardneg") for it in r4["items"]]
    assert all(r is not None for r in recs)
    assert len(recs) == 64
    assert all(r["state"] and r["qs"][0]["t"] == "choice" for r in recs)
    ys = [r["qs"][0]["y"] for r in recs]
    assert ys.count(0) == 32 and ys.count(1) == 32  # KEEP→0 / PRUNE→1

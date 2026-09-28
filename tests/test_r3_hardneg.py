"""R3 难负训练实例构造器单测 — 同型异实例 / anti-leak / export 契约。

anti-leak 是本构造器的生命线：训练实例与难卷 23 条本体零重合（title/attack_path
逐字符串比对 + TWIN 文件名比对 + EVID 语义类型纪律），难卷作为 held-out 考卷的
地位不因 R3 训练而破。
运行: python -m pytest tests/test_r3_hardneg.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.build_hard_exam import build_hard_exam
from eval.build_r3_hardneg import build_r3_hardneg
from eval.finetune_export import item_to_record

REPO_ROOT = Path(__file__).parent.parent
BASE_RULES = {"PIT-E-57", "PIT-T-46", "PIT-N-06", "PIT-E-54", "PIT-E-23", "PIT-T-51"}


def _by_prefix(items, prefix):
    return [it for it in items if it["id"].startswith(prefix)]


def test_determinism_and_structure():
    a, b = build_r3_hardneg(), build_r3_hardneg()
    a.pop("created_utc"), b.pop("created_utc")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == "gate-dataset/1"
    assert a["source"]["generator"] == "r3_hardneg/1"
    ids = [it["id"] for it in a["items"]]
    assert len(ids) == len(set(ids)) == 70
    assert len(_by_prefix(a["items"], "TWIN")) == 40
    assert len(_by_prefix(a["items"], "PARA-T")) == 18
    assert len(_by_prefix(a["items"], "EVID-T")) == 12
    labels = [it["label"]["gate"] for it in a["items"]]
    assert labels.count("KEEP") == 32 and labels.count("PRUNE") == 38
    assert all(it["label"]["source"] == "r3_hardneg/1" and it["label"]["note"]
               for it in a["items"])
    assert a["n_baseline"] == len(a["baseline_rows"]) == 7


def test_anti_leak_vs_hard_exam():
    """训练实例与难卷本体零重合——held-out 考卷地位的生命线。"""
    ex, tr = build_hard_exam(), build_r3_hardneg()
    ex_titles = {it["title"] for it in ex["items"]}
    ex_paths = {it["attack_path"] for it in ex["items"]}
    ex_files = {it["file_path"] for it in ex["items"]}
    for it in tr["items"]:
        assert it["title"] not in ex_titles, it["id"]
        assert it["attack_path"] not in ex_paths, it["id"]
    twin_files = {it["file_path"] for it in _by_prefix(tr["items"], "TWIN")}
    assert not twin_files & ex_files  # TWIN 全新文件域
    # EVID 用语义类型（≠基线规则名）——管线自洽的 evidence-KEEP 形态
    for it in _by_prefix(tr["items"], "EVID-T"):
        assert it["vuln_type"] not in BASE_RULES, it["id"]
        assert it["file_path"] == "src/config.py"  # 证据豁免文件域
        assert it["heuristics"]["evidence_backed"] and it["label"]["gate"] == "KEEP"
    # PARA-T 在基线文件域（echo 语义），但 config.py 证据豁免文件不进
    base = {(r["file"], r["rule"]) for r in tr["baseline_rows"]}
    for it in _by_prefix(tr["items"], "PARA-T"):
        assert (it["file_path"], it["vuln_type"]) in base
        assert it["file_path"] != "src/config.py"
        assert it["heuristics"]["echo_of_baseline"]


def test_twin_pairing_integrity():
    tr = build_r3_hardneg()
    pairs: dict[str, list[dict]] = {}
    for it in _by_prefix(tr["items"], "TWIN"):
        # id 形如 TWIN-K01/TWIN-B01：K/B 在第 6 位，配对键剥掉该位
        pairs.setdefault(it["id"][:5] + it["id"][6:], []).append(it)
    assert len(pairs) == 20
    for pid, members in pairs.items():
        assert len(members) == 2
        k = next(m for m in members if m["id"][5] == "K")
        b = next(m for m in members if m["id"][5] == "B")
        assert k["label"]["gate"] == "KEEP" and b["label"]["gate"] == "PRUNE"
        assert k["title"] == b["title"]  # 表面打平，判据只在 attack_path
        assert k["file_path"] != b["file_path"]
        assert k["attack_path"] != b["attack_path"]  # 语义判据在 path：K=恶意形态，B=自驳


def test_finetune_export_contract():
    """全部 70 条必须能被 finetune_export 无剔除消费（KEEP/PRUNE 齐备）。"""
    tr = build_r3_hardneg()
    recs = [item_to_record(it, tr["baseline_rows"], "r3hardneg") for it in tr["items"]]
    assert all(r is not None for r in recs)
    assert len(recs) == 70
    assert all(r["state"] and r["qs"][0]["t"] == "choice" for r in recs)
    ys = [r["qs"][0]["y"] for r in recs]
    assert ys.count(0) == 32 and ys.count(1) == 38  # KEEP→0 / PRUNE→1

"""R6 难负训练实例构造器单测 — BOUND-5B 专项 / 四方 anti-leak / export 契约。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.build_hard_exam import build_hard_exam
from eval.build_r3_hardneg import build_r3_hardneg
from eval.build_r4_hardneg import build_r4_hardneg
from eval.build_r5_hardneg import build_r5_hardneg
from eval.build_r6_hardneg import build_r6_hardneg
from eval.finetune_export import item_to_record


def test_determinism_and_structure():
    a, b = build_r6_hardneg(), build_r6_hardneg()
    a.pop("created_utc"), b.pop("created_utc")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == "gate-dataset/1"
    assert a["source"]["generator"] == "r6_hardneg/1"
    ids = [it["id"] for it in a["items"]]
    assert len(ids) == len(set(ids)) == 19
    labels = [it["label"]["gate"] for it in a["items"]]
    assert labels.count("KEEP") == 8 and labels.count("PRUNE") == 11
    backup = [it for it in a["items"] if it["id"].startswith("T6")]
    assert len(backup) == 12 and all(it["vuln_type"] == "CRED_EXFIL" for it in backup)


def test_anti_leak_vs_all_prior_rounds():
    """title/attack_path 对考卷与 R3/R4/R5 训练件全部零重合。"""
    priors = [build_hard_exam(), build_r3_hardneg(), build_r4_hardneg(), build_r5_hardneg()]
    r6 = build_r6_hardneg()
    for prior in priors:
        titles = {it["title"] for it in prior["items"]}
        paths = {it["attack_path"] for it in prior["items"]}
        for it in r6["items"]:
            assert it["title"] not in titles, it["id"]
            assert it["attack_path"] not in paths, it["id"]


def test_family_semantics():
    """备份对 K/B 同 title 异 path 异 file；echo 压舱件域语义正确。"""
    r6 = build_r6_hardneg()
    pairs: dict[str, list[dict]] = {}
    for it in [x for x in r6["items"] if x["id"].startswith("T6")]:
        pairs.setdefault(it["id"][:2] + it["id"][3:], []).append(it)
    assert len(pairs) == 6
    for members in pairs.values():
        k = next(m for m in members if m["id"][2] == "K")
        b = next(m for m in members if m["id"][2] == "B")
        assert k["label"]["gate"] == "KEEP" and b["label"]["gate"] == "PRUNE"
        assert k["title"] == b["title"] and k["file_path"] != b["file_path"]
        assert "ek" in k["attack_path"] or "https://" in k["attack_path"]
        bnote = b["label"]["note"]
        assert "self-refuting(train):" in bnote and "internal" in bnote
    base = {(r["file"], r["rule"]) for r in r6["baseline_rows"]}
    for it in [x for x in r6["items"] if x["id"].startswith(("P6T", "R6E"))]:
        assert it["heuristics"]["echo_of_baseline"] and it["label"]["gate"] == "PRUNE"
        assert (it["file_path"], it["vuln_type"]) in base
    for it in [x for x in r6["items"] if x["id"].startswith("E6T")]:
        assert it["file_path"] == "src/config.py" and it["label"]["gate"] == "KEEP"
        assert it["heuristics"]["evidence_backed"] and not it["heuristics"]["echo_of_baseline"]


def test_finetune_export_contract():
    """全部 19 条必须能被 finetune_export 无剔除消费。"""
    r6 = build_r6_hardneg()
    recs = [item_to_record(it, r6["baseline_rows"], "r6hardneg") for it in r6["items"]]
    assert all(r is not None for r in recs)
    assert len(recs) == 19
    ys = [r["qs"][0]["y"] for r in recs]
    assert ys.count(0) == 8 and ys.count(1) == 11

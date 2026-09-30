"""R5 难负训练实例构造器单测 — echo 边际补给 / 三方 anti-leak / export 契约。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.build_hard_exam import build_hard_exam
from eval.build_r3_hardneg import build_r3_hardneg
from eval.build_r4_hardneg import build_r4_hardneg
from eval.build_r5_hardneg import build_r5_hardneg
from eval.finetune_export import item_to_record


def test_determinism_and_structure():
    a, b = build_r5_hardneg(), build_r5_hardneg()
    a.pop("created_utc"), b.pop("created_utc")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == "gate-dataset/1"
    assert a["source"]["generator"] == "r5_hardneg/1"
    ids = [it["id"] for it in a["items"]]
    assert len(ids) == len(set(ids)) == 48
    labels = [it["label"]["gate"] for it in a["items"]]
    assert labels.count("KEEP") == 12 and labels.count("PRUNE") == 36
    assert a["n_baseline"] == len(a["baseline_rows"]) == 7


def test_anti_leak_vs_all_prior_rounds():
    """title/attack_path 对考卷与 R3/R4 训练件全部零重合。"""
    ex, r3, r4, r5 = build_hard_exam(), build_r3_hardneg(), build_r4_hardneg(), build_r5_hardneg()
    for prior in (ex, r3, r4):
        titles = {it["title"] for it in prior["items"]}
        paths = {it["attack_path"] for it in prior["items"]}
        for it in r5["items"]:
            assert it["title"] not in titles, it["id"]
            assert it["attack_path"] not in paths, it["id"]


def test_echo_domain_semantics():
    """PARA 在基线文件域且带 echo 标记；REDUN/EVID 在 config.py 证据域；类型判别清晰。"""
    r5 = build_r5_hardneg()
    base = {(r["file"], r["rule"]) for r in r5["baseline_rows"]}
    para = [it for it in r5["items"] if it["id"].startswith("P5T")]
    redun = [it for it in r5["items"] if it["id"].startswith("R5E")]
    evid = [it for it in r5["items"] if it["id"].startswith("E5T")]
    assert len(para) == 24 and len(redun) == 12 and len(evid) == 12
    for it in para:
        assert (it["file_path"], it["vuln_type"]) in base
        assert it["heuristics"]["echo_of_baseline"] and it["label"]["gate"] == "PRUNE"
    for it in redun:
        assert it["file_path"] == "src/config.py" and it["vuln_type"] == "PIT-E-57"
        assert it["heuristics"]["echo_of_baseline"] and it["label"]["gate"] == "PRUNE"
        assert it["heuristics"]["evidence_backed"]  # 有解码证据但基线已并=冗余
    for it in evid:
        assert it["file_path"] == "src/config.py"
        assert it["vuln_type"] not in {"PIT-E-57"}  # 语义类型 ≠ 基线规则
        assert it["heuristics"]["evidence_backed"] and not it["heuristics"]["echo_of_baseline"]
        assert it["label"]["gate"] == "KEEP"


def test_finetune_export_contract():
    """全部 48 条必须能被 finetune_export 无剔除消费。"""
    r5 = build_r5_hardneg()
    recs = [item_to_record(it, r5["baseline_rows"], "r5hardneg") for it in r5["items"]]
    assert all(r is not None for r in recs)
    assert len(recs) == 48
    assert all(r["state"] and r["qs"][0]["t"] == "choice" for r in recs)
    ys = [r["qs"][0]["y"] for r in recs]
    assert ys.count(0) == 12 and ys.count(1) == 36  # KEEP→0 / PRUNE→1

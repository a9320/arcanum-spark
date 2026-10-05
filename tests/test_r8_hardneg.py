"""R8 难负训练实例构造器单测 — BOUND-5B 联合锚定批 / 六方 anti-leak / export 契约。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.build_hard_exam import build_hard_exam
from eval.build_r3_hardneg import build_r3_hardneg
from eval.build_r4_hardneg import build_r4_hardneg
from eval.build_r5_hardneg import build_r5_hardneg
from eval.build_r6_hardneg import build_r6_hardneg
from eval.build_r7_hardneg import build_r7_hardneg
from eval.build_r8_hardneg import build_r8_hardneg
from eval.finetune_export import item_to_record


def test_determinism_and_structure():
    a, b = build_r8_hardneg(), build_r8_hardneg()
    a.pop("created_utc"), b.pop("created_utc")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == "gate-dataset/1"
    assert a["source"]["generator"] == "r8_hardneg/1"
    ids = [it["id"] for it in a["items"]]
    assert len(ids) == len(set(ids)) == 20
    labels = [it["label"]["gate"] for it in a["items"]]
    assert labels.count("KEEP") == 9 and labels.count("PRUNE") == 11
    boundary = [it for it in a["items"] if it["id"].startswith("T8")]
    assert len(boundary) == 16
    # 联合锚定 6 对 CRED_EXFIL + 保航 2 对（E-57/T-46）
    types = [it["vuln_type"] for it in boundary]
    assert types.count("CRED_EXFIL") == 12
    assert types.count("PIT-E-57") == 2 and types.count("PIT-T-46") == 2


def test_anti_leak_vs_all_prior_rounds():
    """title/attack_path 对考卷与 R3-R7 训练件全部零重合；
    并专项断言考卷 BOUND-5 对（BOUND-5B 病灶）的专属字面零复现。"""
    priors = [build_hard_exam(), build_r3_hardneg(), build_r4_hardneg(),
              build_r5_hardneg(), build_r6_hardneg(), build_r7_hardneg()]
    r8 = build_r8_hardneg()
    for prior in priors:
        titles = {it["title"] for it in prior["items"]}
        paths = {it["attack_path"] for it in prior["items"]}
        for it in r8["items"]:
            assert it["title"] not in titles, it["id"]
            assert it["attack_path"] not in paths, it["id"]
    # 考卷 5 对专属字面：backup_sync/report_sync 文件与 telemetry-metrics 外部域
    for it in r8["items"]:
        blob = it["file_path"] + " " + it["attack_path"]
        assert "backup_sync" not in blob and "report_sync" not in blob, it["id"]
        assert "telemetry-metrics" not in blob, it["id"]


def test_family_semantics():
    """边界对 K/B 同 title 异 file；端点语义不变量（K=.invalid 外部 / B=corp.internal
    内部或无 URL）；CRED 六对 B 侧锚点互异；echo 压舱件域语义正确。"""
    r8 = build_r8_hardneg()
    boundary = [x for x in r8["items"] if x["id"].startswith("T8")]
    pairs: dict[str, dict[str, dict]] = {}
    for it in boundary:
        pairs.setdefault(it["id"][:2] + it["id"][3:], {})[it["id"][2]] = it
    assert len(pairs) == 8
    for members in pairs.values():
        k = members["K"]
        b = members["B"]
        assert k["label"]["gate"] == "KEEP" and b["label"]["gate"] == "PRUNE"
        assert k["title"] == b["title"] and k["file_path"] != b["file_path"]
        assert k["vuln_type"] == b["vuln_type"]
        assert "boundary_pair:train:" in k["label"]["note"]
        assert "self-refuting(train):" in b["label"]["note"]
        # 端点语义不变量：外部 URL 只进 K 路径且为 .invalid；
        # B 路径含 https:// 时必须为 corp.internal 且不得出现 .invalid
        if "https://" in k["attack_path"]:
            assert ".invalid/" in k["attack_path"], k["id"]
            assert "corp.internal" not in k["attack_path"], k["id"]
        if "https://" in b["attack_path"]:
            assert "corp.internal" in b["attack_path"], b["id"]
            assert ".invalid" not in b["attack_path"], b["id"]
    # BOUND-5B 联合锚定的核心断言：6 条 CRED B 侧自驳锚点互异（铺宽良性字面空间）
    cred_b_notes = {it["label"]["note"] for it in boundary
                    if it["id"].startswith("T8B") and it["vuln_type"] == "CRED_EXFIL"}
    assert len(cred_b_notes) == 6
    base = {(r["file"], r["rule"]) for r in r8["baseline_rows"]}
    for it in [x for x in r8["items"] if x["id"].startswith(("P8T", "R8E"))]:
        assert it["heuristics"]["echo_of_baseline"] and it["label"]["gate"] == "PRUNE"
        assert (it["file_path"], it["vuln_type"]) in base
    for it in [x for x in r8["items"] if x["id"].startswith("E8T")]:
        assert it["file_path"] == "src/config.py" and it["label"]["gate"] == "KEEP"
        assert it["heuristics"]["evidence_backed"] and not it["heuristics"]["echo_of_baseline"]


def test_finetune_export_contract():
    """全部 20 条必须能被 finetune_export 无剔除消费。"""
    r8 = build_r8_hardneg()
    recs = [item_to_record(it, r8["baseline_rows"], "r8hardneg") for it in r8["items"]]
    assert all(r is not None for r in recs)
    assert len(recs) == 20
    ys = [r["qs"][0]["y"] for r in recs]
    assert ys.count(0) == 9 and ys.count(1) == 11

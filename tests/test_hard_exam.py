"""难卷构造器单测 — schema / 标签构造合规 / tfidf 陷阱特性（题库领用规则：接入须 tests 实跑）。

考卷成立判据（2026-09-27 定调）：tfidf 在难卷 AP 必须 <1.0（换措辞负样本冲到
KEEP 之前），否则卷不构成门 2 终判难度；ECHO 逐字负样本须保持深谷（与 R2 各卷可比）。
运行: python -m pytest tests/test_hard_exam.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.build_hard_exam import build_hard_exam
from eval.replay import average_precision, score_tfidf

REPO_ROOT = Path(__file__).parent.parent


def _ds():
    return build_hard_exam()


def _by_prefix(ds, prefix):
    return [it for it in ds["items"] if it["id"].startswith(prefix)]


def test_determinism_and_schema():
    a, b = _ds(), _ds()
    a.pop("created_utc"), b.pop("created_utc")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["schema"] == "gate-dataset/1"
    ids = [it["id"] for it in a["items"]]
    assert len(ids) == len(set(ids)) == 24
    assert a["n_baseline"] == len(a["baseline_rows"]) == 7
    assert a["source"]["generator"] == "hard_exam/2"


def test_baseline_matches_expected_registry():
    """baseline 7 组必须逐项对得上 eval/expected.json（不幻觉基线）。"""
    expected = json.loads((REPO_ROOT / "eval" / "expected.json").read_text(encoding="utf-8"))
    reg = {(r["file_path"], r["rule"]) for r in expected["agent0_required"]}
    rows = _ds()["baseline_rows"]
    assert {(r["file"], r["rule"]) for r in rows} == reg
    cfg = next(r for r in rows if r["file"] == "src/config.py")
    assert cfg["has_decoded_payload"] is True


def test_labels_by_construction():
    ds = _ds()
    labels = {it["id"]: it["label"]["gate"] for it in ds["items"]}
    assert set(labels.values()) == {"KEEP", "PRUNE"}
    assert all(it["label"]["source"] == "hard_exam/2" and it["label"]["note"] for it in ds["items"])
    assert len(_by_prefix(ds, "ECHO-")) == 6
    assert len(_by_prefix(ds, "PARA-")) == 6
    ks = [it for it in ds["items"] if it["id"].startswith("BOUND-") and it["id"].endswith("K")]
    bs = [it for it in ds["items"] if it["id"].startswith("BOUND-") and it["id"].endswith("B")]
    assert len(ks) == len(bs) == 5
    assert all(it["label"]["gate"] == "KEEP" for it in ks)
    assert all(it["label"]["gate"] == "PRUNE" for it in bs)
    # 边界对 K/B 同 title（表面打平），判据只在 attack_path 语义
    pairs: dict[str, list[str]] = {}
    for it in ks + bs:
        pairs.setdefault(it["id"][:-1], []).append(it["title"])
    assert len(pairs) == 5
    assert all(len(v) == 2 and v[0] == v[1] for v in pairs.values())
    # ECHO/PARA 均在基线文件域（echo 语义：file+type 同 key）；config.py 证据豁免不进回显
    base = {(r["file"], r["rule"]) for r in ds["baseline_rows"]}
    for it in _by_prefix(ds, "ECHO-") + _by_prefix(ds, "PARA-"):
        assert (it["file_path"], it["vuln_type"]) in base
        assert it["heuristics"]["echo_of_baseline"]
        assert it["file_path"] != "src/config.py"
    h9 = next(it for it in ds["items"] if it["id"] == "H9")
    assert h9["vuln_type"] == "SECRET_EXFIL"  # v2：语义类型=生产真实 H9 形态，且不在基线规则域
    assert h9["heuristics"]["evidence_backed"] and h9["label"]["gate"] == "KEEP"
    # REDUN-1：同型+证据风味 → 管线一致标签 PRUNE（echo-first 先于 evidence）
    redun = next(it for it in ds["items"] if it["id"] == "REDUN-1")
    assert redun["vuln_type"] == "PIT-E-57" and redun["file_path"] == "src/config.py"
    assert redun["heuristics"]["echo_of_baseline"] and redun["label"]["gate"] == "PRUNE"
    assert redun["heuristics"]["evidence_backed"]  # 文件级证据如实记录，echo 决定 PRUNE


def test_tfidf_trap_fires():
    """终判卷的成立条件：novelty 基线被换措辞负样本击穿、逐字回显仍沉底。"""
    ds = _ds()
    scores = score_tfidf(ds["items"], ds["baseline_rows"])
    ranked = sorted(zip(scores, ds["items"]), key=lambda t: -t[0])
    ap = average_precision([it["label"]["gate"] for _s, it in ranked])
    assert ap < 0.5  # 实测 0.296（R2 各卷 tfidf=1.000；难卷必须难）
    keep_scores = [s for s, it in ranked if it["label"]["gate"] == "KEEP"]
    para_scores = [s for s, it in ranked if it["id"].startswith("PARA-")]
    echo_scores = [s for s, it in ranked if it["id"].startswith("ECHO-")]
    # 换措辞负样本冲进全部 KEEP 之前 ≥3 条（实测 4/6；tfidf 天敌机制）
    assert sum(1 for ps in para_scores if ps > max(keep_scores)) >= 3
    # 逐字回显深谷不变（ECHO 谷深度指标锚点，与 R2 各卷可比）
    assert max(echo_scores) < min(keep_scores)

"""finetune_export 单测 — gate_dataset → 官方 records.jsonl 的纯逻辑契约。

只测导出逻辑本身（纯 stdlib，零 torch）；encode_record 消费端实跑属 DSW 侧冒烟
（本地 venv 无 torch/transformers，rl_common 不 import）。契约锚点 =
rl_common.encode_record:234 + build_sequence:56（q["ins"]）+ render_options:37（q["crit"]）。
运行: python -m pytest tests/test_finetune_export.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.finetune_export import (GATE_TO_Y, derive_src, export_datasets,
                                  item_to_record, write_jsonl)
from eval.replay import _SCORE_LAYA_CRITERIA, _SCORE_LAYA_INSTRUCTIONS, _laya_state


def _mini_dataset():
    """build/synth 产物形状的最小复刻：2 基线行 + KEEP/PRUNE/REVIEW/合成回显各一。"""
    baseline = [
        {"file": "docs/AGENT_GUIDE.md", "rule": "PIT-N-06", "title": "指令诱导外泄",
         "severity": "high", "has_decoded_payload": False},
        {"file": "src/config.py", "rule": "PIT-E-57", "title": "编码载荷",
         "severity": "high", "has_decoded_payload": True},
    ]
    items = [
        {"id": "H1", "origin": "report", "title": "AGENT_GUIDE 外泄指令",
         "vuln_type": "PIT-N-06", "file_path": "docs/AGENT_GUIDE.md",
         "attack_path": "读取 .env 后上传", "confidence": "high",
         "heuristics": {"echo_of_baseline": None, "duplicate_of": None,
                        "degenerate": False, "evidence_backed": False,
                        "new_file_vs_baseline": False},
         "pipeline": {"verdict": "CONFIRMED", "verification_method": "tool",
                      "confidence": "high", "in_final": True, "join_method": "id"},
         "label": {"gate": "KEEP", "source": "pipeline", "note": "semantic increment"}},
        {"id": "H2", "origin": "report", "title": "config 编码载荷（复述基线）",
         "vuln_type": "PIT-E-57", "file_path": "src/config.py",
         "attack_path": "base64 两层", "confidence": "medium",
         "heuristics": {"echo_of_baseline": {"rule": "PIT-E-57", "match": "file+type"},
                        "duplicate_of": None, "degenerate": False,
                        "evidence_backed": True, "new_file_vs_baseline": False},
         "pipeline": {"verdict": "CONFIRMED", "verification_method": "tool",
                      "confidence": "high", "in_final": True, "join_method": "id"},
         "label": {"gate": "KEEP", "source": "pipeline", "note": "evidence 豁免"}},
        {"id": "H3", "origin": "report", "title": "未定假设",
         "vuln_type": "PIT-T-46", "file_path": ".cursor/rules",
         "attack_path": "-", "confidence": "low",
         "heuristics": {"echo_of_baseline": None, "duplicate_of": None,
                        "degenerate": False, "evidence_backed": False,
                        "new_file_vs_baseline": False},
         "pipeline": {"verdict": "UNCERTAIN", "verification_method": "",
                      "confidence": "", "in_final": False, "join_method": "id"},
         "label": {"gate": "REVIEW", "source": "pipeline", "note": ""}},
        {"id": "ECHO-1", "origin": "synthetic", "title": "admin_panel 投毒",
         "vuln_type": "PIT-T-46", "file_path": ".cursor/rules",
         "attack_path": "复述基线", "confidence": "",
         "heuristics": {"echo_of_baseline": {"rule": "PIT-T-46", "match": "synthetic"},
                        "duplicate_of": None, "degenerate": False,
                        "evidence_backed": False, "new_file_vs_baseline": False},
         "pipeline": {"verdict": "", "verification_method": "",
                      "confidence": "", "in_final": True, "join_method": "none"},
         "label": {"gate": "PRUNE", "source": "synthetic", "note": "echo_exact(synthetic)"}},
    ]
    return {"baseline_rows": baseline, "items": items}


# ── y 映射与剔除 ──

def test_gate_to_y_mapping():
    assert GATE_TO_Y == {"KEEP": 0, "PRUNE": 1}  # A=KEEP / B=PRUNE，与 score_laya 同序


def test_keep_prune_review():
    ds = _mini_dataset()
    keep = item_to_record(ds["items"][0], ds["baseline_rows"], "runA")
    prune = item_to_record(ds["items"][3], ds["baseline_rows"], "runA")
    assert keep["qs"][0]["y"] == 0
    assert prune["qs"][0]["y"] == 1
    assert item_to_record(ds["items"][2], ds["baseline_rows"], "runA") is None  # REVIEW 剔除


# ── 与 eval 侧分布一致（命门）──

def test_state_is_laya_state_output():
    ds = _mini_dataset()
    item = ds["items"][0]
    rec = item_to_record(item, ds["baseline_rows"], "runA")
    assert rec["state"] == _laya_state(item, ds["baseline_rows"])
    assert isinstance(rec["state"], str) and rec["state"]  # serialize_state(str) 直通


def test_ins_crit_shared_with_score_laya():
    ds = _mini_dataset()
    q = item_to_record(ds["items"][0], ds["baseline_rows"], "runA")["qs"][0]
    assert q["ins"] is _SCORE_LAYA_INSTRUCTIONS          # 同一对象，非复制
    assert list(q["crit"].items()) == list(_SCORE_LAYA_CRITERIA.items())
    assert list(q["crit"].keys()) == ["A", "B"]          # 插入序=标签序（render_options 依赖）
    assert set(q.keys()) == {"t", "ins", "crit", "y"}    # 内部键名；one-hot 无 soft


def test_meta_traceability():
    ds = _mini_dataset()
    rec = item_to_record(ds["items"][3], ds["baseline_rows"], "runA")
    assert rec["meta"]["item_id"] == "ECHO-1" and rec["meta"]["gate"] == "PRUNE"


# ── src 推导与切分防泄漏 ──

def test_derive_src_prefers_run_dir(tmp_path):
    run_dir = tmp_path / "20260926-healthy2"
    run_dir.mkdir()
    f = run_dir / "gate_dataset_full.json"
    f.write_text("{}", encoding="utf-8")
    assert derive_src(f) == "20260926-healthy2"
    assert derive_src(Path("gate_dataset.json")) == "gate_dataset"  # 裸文件名（parent="."）→ stem


def test_export_split_by_src_no_leakage():
    dsA, dsB = _mini_dataset(), _mini_dataset()
    train, val, stats = export_datasets([("runA", dsA), ("runB", dsB)], val_srcs={"runB"})
    assert {r["src"] for r in train} == {"runA"} and {r["src"] for r in val} == {"runB"}
    assert len(train) + len(val) == stats["n_kept"] == 6   # 4+4 条目，各剔 1 REVIEW
    assert stats["n_dropped"] == 2
    assert stats["per_src"]["runA"]["dropped"] == 1


def test_export_without_split_writes_all():
    train, val, stats = export_datasets([("runA", _mini_dataset())], val_srcs=set())
    assert val == [] and len(train) == 3
    assert stats["per_src"]["runA"]["records"] == 3


# ── 落盘回读（jsonl 契约面）──

def test_write_jsonl_roundtrip(tmp_path):
    ds = _mini_dataset()
    recs = [item_to_record(it, ds["baseline_rows"], "runA")
            for it in ds["items"]]
    recs = [r for r in recs if r]
    out = tmp_path / "records.jsonl"
    write_jsonl(out, recs)
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(recs)
    for line, src_rec in zip(lines, recs):
        rec = json.loads(line)
        assert rec["state"] and isinstance(rec["src"], str)
        assert rec["qs"][0]["t"] == "choice" and rec["qs"][0]["y"] in (0, 1)
        assert rec == src_rec  # 无损

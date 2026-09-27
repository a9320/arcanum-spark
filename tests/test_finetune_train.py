"""finetune_train 单测 — 纯逻辑部分（records 解析契约 + 校准切分），零 torch。

torch 侧（build_items/RLCD 循环/温度拟合）属 DSW 实弹：官方 notebook cell 8 照抄,
本地 venv 无 torch 不 import。模块顶层必须保持零 torch（main 里惰性 import）。
运行: python -m pytest tests/test_finetune_train.py -v
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.finetune_train import parse_records, split_calib


def _rec(state="vuln_type: X\nfile: a.py", y=0, qkeys=None):
    q = {"t": "choice", "ins": "Decide.", "crit": {"A": "KEEP", "B": "PRUNE"}, "y": y}
    if qkeys:
        q = {k: v for k, v in q.items() if k in qkeys}
    return {"state": state, "qs": [q], "src": "runA", "meta": {"item_id": "H1", "gate": "KEEP"}}


def _write(tmp_path, recs):
    p = tmp_path / "records.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    return str(p)


# ── parse_records：契约展开与拒绝面 ──

def test_parse_records_flattens(tmp_path):
    items = parse_records(_write(tmp_path, [_rec(y=0), _rec(y=1)]))
    assert len(items) == 2
    assert items[0]["y"] == 0 and items[1]["y"] == 1
    assert items[0]["q"]["t"] == "choice" and items[0]["q"]["crit"]["A"] == "KEEP"
    assert items[0]["state"].startswith("vuln_type") and items[0]["meta"]["item_id"] == "H1"


def test_parse_records_rejects_external_keys(tmp_path):
    rec = _rec()
    rec["qs"][0] = {"type": "choice", "instructions": "x", "criteria": {"A": "a", "B": "b"}, "y": 0}
    p = _write(tmp_path, [rec])
    try:
        parse_records(p)
        raise AssertionError("应当拒绝推理侧键名")
    except ValueError as e:
        assert "ins/crit" in str(e)


def test_parse_records_rejects_bad_shape(tmp_path):
    for bad in ({"qs": []}, {"state": "s"}, {"state": "s", "qs": [{"t": "choice", "ins": "i", "crit": {"A": "x"}, "y": 5}]}):
        p = _write(tmp_path, [bad])
        try:
            parse_records(p)
            raise AssertionError(f"应当拒绝: {bad}")
        except ValueError:
            pass


def test_parse_records_skips_blank_lines(tmp_path):
    p = tmp_path / "records.jsonl"
    p.write_text("\n" + json.dumps(_rec()) + "\n\n", encoding="utf-8")
    assert len(parse_records(str(p))) == 1


# ── split_calib：确定性 + 无泄漏 ──

def test_split_calib_deterministic_disjoint():
    items = [{"i": i} for i in range(31)]
    tr1, ca1 = split_calib(items, 0.15, 20260927)
    tr2, ca2 = split_calib(items, 0.15, 20260927)
    assert [(x["i"]) for x in tr1] == [(x["i"]) for x in tr2]
    assert [(x["i"]) for x in ca1] == [(x["i"]) for x in ca2]
    ids_tr = {x["i"] for x in tr1}
    ids_ca = {x["i"] for x in ca1}
    assert not (ids_tr & ids_ca) and ids_tr | ids_ca == set(range(31))  # 无泄漏、并集=全集
    assert len(ca1) == 4  # ceil 边界：31*0.15=4.65→int=4


def test_split_calib_zero_frac_keeps_all_train():
    tr, ca = split_calib([{"i": 0}], 0.0, 1)
    assert len(tr) == 1 and ca == []


# ── 模块顶层零 torch（本地无 torch 也能 import 的保障）──

def test_module_import_does_not_pull_torch():
    import eval.finetune_train as m
    assert "torch" not in sys.modules
    assert callable(m.parse_records) and callable(m.split_calib)

"""M8/K1 选题器单测 — 合成目录树，零网络。

契约：
1. flag 文件反查 challenge 目录；类目=路径段推断；
2. --category 过滤（无类目段的不入列）；输出骨架 intended_types=null（人工补）；
3. 同一 challenge 被多个 flag 候选名命中时去重。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sel = _load("m8_select_web", "eval/m8_select_web.py")


def _tree(tmp_path: Path):
    web1 = tmp_path / "test" / "web" / "csaw2017web1" / "src"
    web1.mkdir(parents=True)
    (web1 / "chal.flag").write_text("flag{a}\n", encoding="utf-8")
    web2 = tmp_path / "test" / "web" / "csaw2018web2"
    web2.mkdir(parents=True)
    (web2 / "flag.txt").write_text("flag{b}\n", encoding="utf-8")
    pwn1 = tmp_path / "test" / "pwn" / "csaw2019pwn1"
    pwn1.mkdir(parents=True)
    (pwn1 / "flag").write_text("flag{c}\n", encoding="utf-8")


def test_select_web_finds_flag_backed_challenges(tmp_path: Path):
    _tree(tmp_path)
    rows = sel.select_challenges(tmp_path, "web")
    paths = [r["upstream_path"] for r in rows]
    assert paths == ["test/web/csaw2017web1", "test/web/csaw2018web2"]
    assert all(r["category"] == "web" and r["intended_types"] is None for r in rows)
    assert all(r["flag_present"] is True for r in rows)


def test_pwn_excluded_from_web_and_dedup(tmp_path: Path):
    _tree(tmp_path)
    assert [r["challenge_id"] for r in sel.select_challenges(tmp_path, "pwn")] == ["csaw2019pwn1"]
    # 同目录双 flag 候选名 → 去重为一行
    web1 = tmp_path / "test" / "web" / "csaw2017web1" / "src"
    (web1 / "flag").write_text("flag{a}\n", encoding="utf-8")
    rows = sel.select_challenges(tmp_path, "web")
    assert len([r for r in rows if r["challenge_id"] == "csaw2017web1"]) == 1

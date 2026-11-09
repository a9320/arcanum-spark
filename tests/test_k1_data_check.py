"""K1 题库数据闸单测（2026-11-09）——零网络。

锁四件事：①真 manifest 的 20 个前缀与钉定 sha；②完整题库 PASS；
③缺文件/内容不符必须被抓；④sha 清单两种分隔符（`  ` / ` *`）都能解析。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load("k1_data_check_under_test", "scripts/k1_data_check.py")
fetch = _load("fetch_nyu_snapshot_under_test", "scripts/fetch_nyu_k1_snapshot.py")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path, rows: list[dict] | None = None) -> tuple[Path, Path]:
    """造 2 题题库 + manifest，返回 (corpus, manifest)。"""
    corpus = tmp_path / "corpus"
    files = {
        "removed/2020/CSAW-Quals/web/demo_a/challenge.json": b'{"name": "a"}',
        "removed/2020/CSAW-Quals/web/demo_a/ctf/app.py": b"print('a')\n",
        "test/2021/CSAW-Quals/web/demo_b/challenge.json": b'{"name": "b"}',
    }
    for rel, blob in files.items():
        target = corpus / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    if rows is None:
        rows = [
            {"challenge_id": "demo_a", "upstream_path": "removed/2020/CSAW-Quals/web/demo_a"},
            {"challenge_id": "demo_b", "upstream_path": "test/2021/CSAW-Quals/web/demo_b"},
        ]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(rows), encoding="utf-8")
    return corpus, manifest


def test_real_manifest_prefixes_and_sha() -> None:
    manifest = ROOT / "data" / "m8_k1_manifest.json"
    prefixes = fetch.prefixes_from_manifest(manifest)
    assert len(prefixes) == 20 and len(set(prefixes)) == 20
    assert all(not p.endswith("/") for p in prefixes)
    errors, _ = check.check_manifest(manifest)
    assert errors == []


def test_corpus_pass_with_sha_list(tmp_path: Path) -> None:
    corpus, manifest = _fixture(tmp_path)
    sha_list = tmp_path / "list.sha256"
    lines = [
        f"{_sha(p)}  ./{p.relative_to(corpus).as_posix()}"
        for p in sorted(corpus.rglob("*"))
        if p.is_file()
    ]
    sha_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors, _, per_task = check.check_corpus(corpus, manifest, sha_list)
    assert errors == []
    assert [count for _, count in per_task] == [2, 1]


def test_corpus_detects_missing_and_mismatch(tmp_path: Path) -> None:
    corpus, manifest = _fixture(tmp_path)
    victim = corpus / "test/2021/CSAW-Quals/web/demo_b/challenge.json"
    wanted = _sha(victim)
    victim.write_bytes(b"tampered")
    (corpus / "removed/2020/CSAW-Quals/web/demo_a/ctf/app.py").unlink()
    sha_list = tmp_path / "list.sha256"
    sha_list.write_text(
        f"{wanted}  ./test/2021/CSAW-Quals/web/demo_b/challenge.json\n",
        encoding="utf-8",
    )

    errors, _, _ = check.check_corpus(corpus, manifest, sha_list)
    assert any("内容不符" in e for e in errors)


def test_missing_task_dir_is_error(tmp_path: Path) -> None:
    corpus, manifest = _fixture(tmp_path)
    for child in (corpus / "test/2021/CSAW-Quals/web/demo_b").iterdir():
        child.unlink()
    (corpus / "test/2021/CSAW-Quals/web/demo_b").rmdir()

    errors, _, _ = check.check_corpus(corpus, manifest, None)
    assert any("缺题目录" in e for e in errors)


def test_load_sha_list_accepts_both_separators(tmp_path: Path) -> None:
    digest = "a" * 64
    listing = tmp_path / "m.sha256"
    listing.write_text(
        f"{digest}  ./x/y.txt\n{digest} *./z/w.txt\n", encoding="utf-8"
    )
    rows = check.load_sha_list(listing)
    assert rows == {"x/y.txt": digest, "z/w.txt": digest}


def test_select_blobs_requires_each_prefix() -> None:
    tree = {"tree": [{"type": "blob", "path": "a/1.txt", "sha": "s", "size": 1}]}
    with pytest.raises(ValueError, match="零命中"):
        fetch.select_blobs(tree, ["a", "b"])
    blobs = fetch.select_blobs(tree, ["a"])
    assert [b["path"] for b in blobs] == ["a/1.txt"]

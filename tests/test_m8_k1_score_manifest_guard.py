"""判分器 manifest 守卫单测（10-19）— 防旧草案误用 + K1 全量覆盖断言。

背景：根目录曾有 10-03 草案 manifest，20 题中 19 题的 intended_types 与
data/m8_k1_manifest.json 不同；用它判分会把 GK 等题误记 FN。判分入口现在：
- 总是打印 manifest 路径 + SHA-256；
- --expected-manifest-sha256 不匹配即拒绝；
- --require-all 缺任一题报告即拒绝（K1 全量重判用）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "eval"))

import m8_k1_score as scorer


def _manifest(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


def _report_dir(tmp_path: Path, ids: list[str]) -> Path:
    d = tmp_path / "reports"
    for cid in ids:
        sub = d / cid
        sub.mkdir(parents=True)
        (sub / "report.json").write_text(json.dumps({
            "meta": {"hypothesis_set": {"hypotheses": []}, "verifications": []}
        }), encoding="utf-8")
    return d


_ENTRIES = [
    {"challenge_id": "web1", "category": "web", "upstream_path": "test/web1",
     "intended_types": ["PATH_TRAVERSAL"]},
    {"challenge_id": "web2", "category": "web", "upstream_path": "test/web2",
     "intended_types": ["SQL_INJECTION"]},
]


def test_require_all_rejects_missing_report(tmp_path: Path, capsys):
    manifest = _manifest(tmp_path, _ENTRIES)
    reports = _report_dir(tmp_path, ["web1"])
    rc = scorer.main(["--manifest", str(manifest), "--reports-dir", str(reports),
                      "--require-all"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "missing reports (1/2): web2" in err


def test_require_all_passes_when_complete(tmp_path: Path):
    manifest = _manifest(tmp_path, _ENTRIES)
    reports = _report_dir(tmp_path, ["web1", "web2"])
    out = tmp_path / "score.json"
    rc = scorer.main(["--manifest", str(manifest), "--reports-dir", str(reports),
                      "--require-all", "--out", str(out)])
    assert rc == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 2


def test_sha_mismatch_rejects_manifest(tmp_path: Path):
    manifest = _manifest(tmp_path, _ENTRIES)
    reports = _report_dir(tmp_path, ["web1", "web2"])
    rc = scorer.main(["--manifest", str(manifest), "--reports-dir", str(reports),
                      "--expected-manifest-sha256", "0" * 64])
    assert rc == 2


def test_sha_match_accepts_manifest(tmp_path: Path):
    manifest = _manifest(tmp_path, _ENTRIES)
    reports = _report_dir(tmp_path, ["web1", "web2"])
    sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    rc = scorer.main(["--manifest", str(manifest), "--reports-dir", str(reports),
                      "--expected-manifest-sha256", sha])
    assert rc == 0


def test_missing_report_allowed_without_require_all(tmp_path: Path, capsys):
    """向后兼容：默认仍允许缺报告（null 不猜），只是不再静默——不给 --require-all 时照旧。"""
    manifest = _manifest(tmp_path, _ENTRIES)
    reports = _report_dir(tmp_path, ["web1"])
    out = tmp_path / "score.json"
    rc = scorer.main(["--manifest", str(manifest), "--reports-dir", str(reports),
                      "--out", str(out)])
    assert rc == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))) == 2


def test_empty_manifest_rejected(tmp_path: Path):
    manifest = _manifest(tmp_path, [])
    reports = _report_dir(tmp_path, [])
    rc = scorer.main(["--manifest", str(manifest), "--reports-dir", str(reports)])
    assert rc == 2


def test_non_array_manifest_rejected(tmp_path: Path):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"challenge_id": "web1"}), encoding="utf-8")
    reports = _report_dir(tmp_path, [])
    rc = scorer.main(["--manifest", str(p), "--reports-dir", str(reports)])
    assert rc == 2
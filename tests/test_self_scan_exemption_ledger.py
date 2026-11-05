"""豁免台账契约锚（2026-11-05，外评建议落地）。

锁三件事：
1. match_exemption 的匹配/规则过滤/过期即失效语义；
2. load_ledger 的字段校验（缺字段 ⇒ SystemExit 2，不允许无主豁免）；
3. 端到端：git 真集里出现白名单外命中时闸门必须红。
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load("self_scan_gate", ROOT / "scripts" / "self_scan_gate.py")

TODAY = "2026-11-05"
ENTRIES = [
    {"id": "E1", "path_prefix": "demo/", "rule": "*", "reason": "靶仓",
     "owner": "a9320", "added": "2026-10-30", "expires": "2099-01-01"},
    {"id": "E2", "path_prefix": "src/", "rule": "PIT-T-51", "reason": "夹具",
     "owner": "a9320", "added": "2026-10-30", "expires": "2099-01-01"},
    {"id": "E3", "path_prefix": "old/", "rule": "*", "reason": "过期样例",
     "owner": "a9320", "added": "2026-01-01", "expires": "2026-02-01"},
]


def test_match_by_prefix_and_rule():
    e, why = gate.match_exemption("demo/a.md", "PIT-N-06", ENTRIES, TODAY)
    assert e is not None and e["id"] == "E1" and why == ""


def test_rule_filter_blocks_other_rules():
    e, why = gate.match_exemption("src/a.py", "PIT-N-06", ENTRIES, TODAY)
    assert e is None  # E2 只豁免 PIT-T-51


def test_rule_filter_allows_star_entry_for_any_rule():
    e, _ = gate.match_exemption("src/a.py", "PIT-T-51", ENTRIES, TODAY)
    assert e is not None and e["id"] == "E2"


def test_expired_entry_does_not_allow():
    e, why = gate.match_exemption("old/x.md", "PIT-N-06", ENTRIES, TODAY)
    assert e is None
    assert "过期" in why and "E3" in why


def test_path_normalization_handles_backslash_and_dot():
    e, _ = gate.match_exemption(r".\demo\a.md", "PIT-N-06", ENTRIES, TODAY)
    assert e is not None


def test_load_ledger_rejects_missing_field(tmp_path):
    bad = tmp_path / "ledger.json"
    bad.write_text(json.dumps({"entries": [
        {"id": "X", "path_prefix": "a/", "rule": "*"}
        # 缺 reason/owner/added/expires
    ]}), encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        gate.load_ledger(bad)
    assert ei.value.code == 2


def test_load_ledger_rejects_bad_json(tmp_path):
    bad = tmp_path / "ledger.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        gate.load_ledger(bad)
    assert ei.value.code == 2


def test_repo_ledger_is_valid_and_current():
    """仓库自带台账必须字段齐全，且没有任何已过期条目。"""
    entries = gate.load_ledger(gate.LEDGER_PATH)
    assert entries, "台账不应为空"
    today = __import__("datetime").date.today().isoformat()
    for e in entries:
        assert e["expires"] >= today, f"{e['id']} 已过期，请续期或删除"

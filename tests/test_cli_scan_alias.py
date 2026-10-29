"""CLI 产品面锚：`scan` 子命令别名向后兼容 + html 报告落盘。"""
from __future__ import annotations

import asyncio
import argparse
from pathlib import Path
from types import SimpleNamespace

from codeark import cli as cli_mod


def _mock_result(reports: dict | None = None):
    return SimpleNamespace(
        risk_score=0,
        agent0_findings=[],
        hypothesis_set=SimpleNamespace(hypotheses=[]),
        verifications=[],
        attack_chains=[],
        quarantine_stats={},
        deepen_failures=0,
        node_errors={},
        reports=reports or {"json": "{}"},
    )


def test_scan_subcommand_is_alias_for_bare_repo(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    seen: dict = {}

    async def fake_main(args):
        seen["repo"] = args.repo
        seen["formats"] = args.formats
        return 0

    monkeypatch.setattr(cli_mod, "_main", fake_main)

    assert cli_mod.main(["scan", str(tmp_path), "--dry"]) == 0
    assert seen["repo"] == str(tmp_path)
    assert seen["formats"] == "json,sarif,markdown"

    assert cli_mod.main([str(tmp_path)]) == 0       # 旧用法零改动
    assert seen["repo"] == str(tmp_path)


def _args(repo: Path, out: Path, formats: str) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), dry=True, out=str(out), formats=formats)


def test_cli_writes_html_report(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    async def fake_pipeline(files, dry=False, stage_models=None, hypothesis_gate=None):
        return _mock_result({"html": "<!doctype html><p>ok</p>", "json": "{}"})

    monkeypatch.setattr(cli_mod, "run_pipeline", fake_pipeline)
    out = tmp_path / "out"
    rc = asyncio.run(cli_mod._main(_args(tmp_path, out, "json,html")))

    assert rc == 0
    assert (out / "report.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    assert (out / "report.json").exists()
    assert (out / "summary.json").exists()
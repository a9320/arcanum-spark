#!/usr/bin/env python
"""自扫描闸门（self-scan gate）：第一方生产代码零命中（2026-10-25 立项）。

动机：PHP2Shell 情报窗用「git 跟踪文件干净副本 + codeark.cli --dry」对本仓
做了首次产品级自扫——生产代码零命中、测试与 demo fixture 按设计命中。
本闸门把该判读固化成机器断言，防回归（未来任何进入生产路径的可疑模式都会
被抓红）。

方法论：git ls-files 取第一方真集 → 拷成临时干净副本（本地隔离 .venv-win 等
未跟踪噪音，CI checkout 本身即干净）→ codeark.cli --dry 全确定性管线
（产品同款路径，防口径漂移）→ 策略断言。

豁免策略：**逐条台账** `config/self-scan-exemptions.json`（2026-11-05 由外评意见改造）。
每条含 id / path_prefix / rule / reason / owner / added / expires：
- **过期即红**：expires 早于今天 ⇒ 该条目失效，其下的命中变成"白名单外"；
- **未使用即提示**：台账里没匹配到任何 finding 的条目打印为 stale，防止只增不减；
- 能定位到单文件+单规则码就不要写整目录（目录级条目天然会悄悄长大）。

用法：python scripts/self_scan_gate.py [--keep] [--fail-on-stale]
退出码：0=过；1=白名单外/过期命中（--fail-on-stale 时 stale 也判 1）；2=环境或台账错误。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "config" / "self-scan-exemptions.json"
_REQUIRED_FIELDS = ("id", "path_prefix", "rule", "reason", "owner", "added", "expires")


def load_ledger(path: Path = LEDGER_PATH) -> list[dict]:
    """读台账并校验字段齐全；缺文件/坏 JSON/缺字段 ⇒ 闸门环境错（退出码 2）。"""
    if not path.is_file():
        print(f"!! 环境错误：豁免台账缺失 {path}")
        raise SystemExit(2)
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except json.JSONDecodeError as e:
        print(f"!! 环境错误：台账 JSON 坏损（{e}）")
        raise SystemExit(2)
    for i, e in enumerate(entries, 1):
        missing = [k for k in _REQUIRED_FIELDS if not str(e.get(k) or "").strip()]
        if missing:
            print(f"!! 环境错误：台账第 {i} 条缺字段 {missing}（id={e.get('id', '?')}）")
            raise SystemExit(2)
    return entries


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def match_exemption(path: str, rule: str, entries: list[dict], today: str) -> tuple[dict | None, str]:
    """返回 (匹配到的条目或 None, 说明)。过期条目按未匹配处理并给出原因。"""
    p = _norm(path)
    r = str(rule or "*")
    for e in entries:
        if not p.startswith(str(e["path_prefix"])):
            continue
        if str(e["rule"]) not in ("*", r):
            continue
        if str(e["expires"]) < today:
            return None, f"台账条目 {e['id']} 已于 {e['expires']} 过期"
        return e, ""
    return None, ""


def _collect_first_party(dest: Path) -> int:
    """git ls-files 真集拷入 dest，返回文件数。"""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT,
                         capture_output=True, check=True).stdout
    n = 0
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace").replace("\\", "/")
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / rel, dest / rel)
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="第一方生产代码零命中闸门（逐条豁免台账）")
    ap.add_argument("--keep", action="store_true", help="保留临时扫描副本便于复核")
    ap.add_argument("--fail-on-stale", action="store_true",
                    help="台账里有未匹配到任何 finding 的条目也判红（默认仅提示）")
    args = ap.parse_args(argv)

    ledger = load_ledger()
    today = date.today().isoformat()

    tmpscan = Path(tempfile.mkdtemp(prefix="selfscan_src_"))
    tmpout = Path(tempfile.mkdtemp(prefix="selfscan_out_"))
    keepdirs = (tmpscan, tmpout)
    try:
        try:
            n = _collect_first_party(tmpscan)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"!! 环境错误：git ls-files 失败（{e}）")
            return 2
        print(f"== 第一方真集: {n} 文件 → 干净副本 {tmpscan}")

        proc = subprocess.run(
            [sys.executable, "-m", "codeark.cli", str(tmpscan), "--dry",
             "--formats", "json", "--out", str(tmpout)],
            cwd=REPO_ROOT, capture_output=True, text=True)
        report = tmpout / "report.json"
        if proc.returncode != 0 or not report.is_file():
            print("!! 环境错误：CLI 确定性扫描失败")
            print((proc.stdout or "")[-800:], (proc.stderr or "")[-400:])
            return 2

        findings = json.loads(report.read_text(encoding="utf-8")).get("findings", [])
        used_ids: set[str] = set()
        bad: list[tuple[dict, str]] = []
        allowed: list[dict] = []
        for f in findings:
            p = str(f.get("file_path") or f.get("file") or "")
            r = str(f.get("vuln_type") or f.get("rule") or "")
            entry, why = match_exemption(p, r, ledger, today)
            if entry is not None:
                allowed.append(f)
                used_ids.add(str(entry["id"]))
            else:
                bad.append((f, why))
        by_zone = Counter("豁免区" if f in allowed else "白名单外" for f in findings)
        print(f"== findings 总数 {len(findings)}：{dict(by_zone)}（台账 {len(ledger)} 条，"
              f"今日 {today}）")
        for f in allowed:
            print(f"   [豁免] {f.get('severity')} {f.get('vuln_type') or f.get('rule')}"
                  f" @ {f.get('file_path')}")
        for f, why in bad:
            note = f" :: {why}" if why else ""
            print(f"   [命中] {f.get('severity')} {f.get('vuln_type') or f.get('rule')}"
                  f" @ {f.get('file_path')} :: {str(f.get('title') or f.get('description'))[:70]}{note}")
        stale = [e for e in ledger if str(e["id"]) not in used_ids]
        for e in stale:
            print(f"   [台账 stale] {e['id']}（{e['path_prefix']}）没有任何 finding 匹配——"
                  f"若目录已清理请删掉该条目，防止豁免悄悄长大")
        if bad:
            print(f"❌ FAIL: 白名单外/过期 {len(bad)} 条命中——生产路径可疑模式，需人工判读")
            return 1
        if stale and args.fail_on_stale:
            print(f"❌ FAIL: {len(stale)} 条台账条目已无命中（--fail-on-stale）")
            return 1
        print("✅ PASS: 第一方生产代码零命中（豁免逐条台账："
              + "、".join(sorted(used_ids)) + "）")
        return 0
    finally:
        if args.keep:
            print(f"（--keep：副本保留 {keepdirs}）")
        else:
            for d in keepdirs:
                shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

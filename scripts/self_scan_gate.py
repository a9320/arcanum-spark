#!/usr/bin/env python
"""自扫描闸门（self-scan gate）：第一方生产代码零命中（2026-10-25 立项）。

动机：PHP2Shell 情报窗用「git 跟踪文件干净副本 + codeark.cli --dry」对本仓
做了首次产品级自扫——生产代码零命中、测试与 demo fixture 按设计命中。
本闸门把该判读固化成机器断言，防回归（未来任何进入生产路径的可疑模式都会
被抓红）。

方法论：git ls-files 取第一方真集 → 拷成临时干净副本（本地隔离 .venv-win 等
未跟踪噪音，CI checkout 本身即干净）→ codeark.cli --dry 全确定性管线
（产品同款路径，防口径漂移）→ 策略断言。

豁免策略（findings 允许存在的目录，均有明确依据）：
- demo/  阳性对照仓（12 处已知漏洞的"仪器自检"靶，expected.json 口径）
- tests/、codeark/tests/、scripts/smoke/  测试/冒烟文件必须内置合成攻击样本
  才能测引擎（命中=扫描器正常工作，非自身漏洞）

用法：python scripts/self_scan_gate.py [--keep]
退出码：0=闸门过；1=白名单外出现命中（需人工判读）；2=环境错误。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 豁免前缀（目录绑定含尾斜杠，防 tests_extra 类误配；正斜杠归一后匹配）
_ALLOW_FINDINGS_PREFIXES = ("demo/", "tests/", "codeark/tests/", "scripts/smoke/")


def findings_allowed(path: str) -> bool:
    """该路径的 findings 是否落在豁免策略内。"""
    p = str(path).replace("\\", "/").lstrip("./")
    return p.startswith(_ALLOW_FINDINGS_PREFIXES)


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
    ap = argparse.ArgumentParser(description="第一方生产代码零命中闸门")
    ap.add_argument("--keep", action="store_true", help="保留临时扫描副本便于复核")
    args = ap.parse_args(argv)

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
        bad = [f for f in findings
               if not findings_allowed(str(f.get("file_path") or f.get("file") or ""))]
        allowed = [f for f in findings if f not in bad]
        by_zone = Counter("豁免区" if f in allowed else "白名单外" for f in findings)
        print(f"== findings 总数 {len(findings)}：{dict(by_zone)}")
        for f in allowed:
            print(f"   [豁免] {f.get('severity')} {f.get('vuln_type') or f.get('rule')}"
                  f" @ {f.get('file_path')}")
        for f in bad:
            print(f"   [命中] {f.get('severity')} {f.get('vuln_type') or f.get('rule')}"
                  f" @ {f.get('file_path')} :: {str(f.get('title') or f.get('description'))[:70]}")
        if bad:
            print(f"❌ FAIL: 白名单外出现 {len(bad)} 条命中——生产路径可疑模式，需人工判读")
            return 1
        print("✅ PASS: 第一方生产代码零命中（豁免区仅 demo 阳性对照与测试合成样本）")
        return 0
    finally:
        if args.keep:
            print(f"（--keep：副本保留 {keepdirs}）")
        else:
            for d in keepdirs:
                shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

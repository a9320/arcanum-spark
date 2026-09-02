"""CodeRisk PITAX CLI — 不依赖 Redis/Celery，一条命令演示 AI 漏洞检测。
用法:
    python -m app.pitax.cli <目录>            # 人类可读输出
    python -m app.pitax.cli <目录> --json     # JSON 报告
    python -m app.pitax.cli <目录> --sarif    # SARIF 2.1.0（含 PITAX 元数据）
"""
from __future__ import annotations

import argparse
import json
import sys

from .rules import PITAX_VERSION
from .sanitizer import scan_directory
from .sarif import build_sarif


def main() -> int:
    ap = argparse.ArgumentParser(prog="coderisk-pitax")
    ap.add_argument("path", help="要扫描的目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON 报告")
    ap.add_argument("--sarif", action="store_true", help="输出 SARIF 2.1.0 报告")
    args = ap.parse_args()

    findings, stats = scan_directory(args.path)

    if args.json:
        print(json.dumps({"stats": stats, "findings": findings},
                         ensure_ascii=False, indent=2))
        return 1 if findings else 0

    if args.sarif:
        print(json.dumps(build_sarif(findings), ensure_ascii=False, indent=2))
        return 1 if findings else 0

    print(f"╔══ CodeRisk PITAX Scanner (taxonomy v{stats['pitax_version']}) ══╗")
    print(f"  扫描文件: {stats['files_scanned']}  跳过: {stats['files_skipped']}")
    print(f"  规则集:   {', '.join(stats['rules'])}")
    print(f"  检出 AI 漏洞: {len(findings)}")
    print("╚" + "═" * 58 + "╝")
    for f in findings:
        refs = f["pitax"]["references"][0]
        meta = []
        if f.get("cwe"):
            meta.append(f"CWE {f['cwe']}")
        if f.get("mitre_atlas"):
            meta.append(f"ATLAS {f['mitre_atlas']}")
        if f["pitax"].get("cve"):
            meta.append(f"CVE {f['pitax']['cve']}")
        print(f"\n[{f['type']}] {f['severity'].upper():8} {f['file']}:{f['line']}")
        print(f"  {f['description']}")
        print(f"  证据: {f['pitax']['evidence']}")
        if f["pitax"].get("decoded_payload"):
            print(f"  解码载荷: {f['pitax']['decoded_payload'][:120]}")
        print(f"  映射: {', '.join(meta) if meta else '-'}")
        print(f"  参考: {refs}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

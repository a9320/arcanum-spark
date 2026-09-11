"""端到端流水线测试 — 完整打印每节点结果。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path("/mnt/d/desk-top/code-risk-arcanum")
sys.path.insert(0, str(ROOT))

from codeark.graph.pipeline import CodeRiskGraph

REPO = ROOT / "demo" / "vuln-demo-repo"


def read_repo() -> dict[str, str]:
    files = {}
    for p in REPO.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            rel = str(p.relative_to(REPO))
            try:
                files[rel] = p.read_text(encoding="utf-8")
            except Exception:
                pass
    return files


async def main() -> None:
    files = read_repo()
    print(f"读取到 {len(files)} 个文件")

    graph = CodeRiskGraph()
    result = await graph.run(files)

    print("\n========== 端到端结果 ==========")
    print(f"1. agent0_findings: {len(result.agent0_findings)} 条")
    print(f"2. hypotheses: {len(result.hypothesis_set.hypotheses)} 条")
    print(f"3. verifications: {len(result.verifications)} 条")
    verdicts = {}
    for v in result.verifications:
        vd = getattr(v, "verdict", "?")
        verdicts[vd] = verdicts.get(vd, 0) + 1
    print(f"   裁决分布: {verdicts}")
    print(f"4. attack_chains: {len(result.attack_chains)} 条")
    print(f"5. final_report: {type(result.final_report).__name__}")
    print(f"6. reports: {list(result.reports.keys())}")
    print(f"7. risk_score: {result.risk_score}")

    # 打印报告文件
    for fmt, content in result.reports.items():
        out = ROOT / f"reports/e2e_report.{fmt}"
        out.parent.mkdir(exist_ok=True)
        # sarif 等可能是 dict，需序列化为 JSON 字符串
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2)
        out.write_text(text, encoding="utf-8")
        print(f"   → 写入 {out.name} ({len(text)} 字符)")


if __name__ == "__main__":
    asyncio.run(main())
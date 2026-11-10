#!/usr/bin/env python
"""Agent 行为指标（零模型、零网络）——从归档报告统计"被测 Agent"的可观测行为。

两个指标（对应传智杯预指导反馈 P1「工具调用/多轮仅部分覆盖」）：

1. **工具调用一致性**：`meta.verifications[]` 的 method 分布、evidence 非空率、
   evidence_source 分布、degraded 率、node_errors（工具/节点失败）；
2. **多轮状态传递**：同一 (运行组, 假设 id) 在 ≥2 卷中出现时的 verdict 翻转计数，
   以及 REFUTED 卷的驳判理由留存率（refuted 实体是否带 reason）。

用法：
    python eval/agent_behavior_metrics.py --reports-dir reports --out reports/20261110-metrics
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

_METHOD_KEYS = ("method", "evidence_source", "verdict", "degraded")
_RUN_RE = re.compile(r"^(?P<run>.+?)(?:[-_.](?:r|run|arm)?\d+)?$")


def _iter_reports(root: Path):
    for path in sorted(root.rglob("*.json")):
        if path.stat().st_size > 20 * 1024 * 1024:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta")
        if isinstance(meta, dict) and isinstance(meta.get("verifications"), list):
            yield path, meta


def _run_group(path: Path, root: Path) -> str:
    """用「父目录名」当运行组：同目录多卷=同一实验的不同 run。"""
    return str(path.parent.relative_to(root)).replace("\\", "/")


def collect(root: Path) -> dict:
    methods: Counter = Counter()
    verdicts: Counter = Counter()
    evidence_sources: Counter = Counter()
    node_errors: Counter = Counter()
    total = 0
    with_evidence = 0
    degraded = 0
    refuted = 0
    refuted_with_reason = 0
    reports = 0
    flips: Counter = Counter()
    sequences: dict[tuple[str, str], list[str]] = defaultdict(list)

    for path, meta in _iter_reports(root):
        reports += 1
        for row in meta.get("verifications") or []:
            if not isinstance(row, dict):
                continue
            total += 1
            methods[str(row.get("method") or "unset")] += 1
            verdict = str(row.get("verdict") or "?")
            verdicts[verdict] += 1
            evidence_sources[str(row.get("evidence_source") or "unset")] += 1
            if str(row.get("evidence") or "").strip():
                with_evidence += 1
            if row.get("degraded"):
                degraded += 1
            if verdict.upper().startswith("REFUTED"):
                refuted += 1
                if str(row.get("evidence") or row.get("reason") or "").strip():
                    refuted_with_reason += 1
            hid = str(row.get("hypothesis_id") or row.get("id") or "")
            if hid:
                sequences[(_run_group(path, root), hid)].append(verdict)
        for key in (meta.get("node_errors") or {}):
            node_errors[str(key)] += 1

    for (_group, _hid), seq in sequences.items():
        if len({v.upper() for v in seq}) > 1:
            flips[tuple(sorted({v.upper() for v in seq}))] += 1

    return {
        "reports": reports,
        "verifications": total,
        "methods": dict(methods.most_common()),
        "verdicts": dict(verdicts.most_common()),
        "evidence_sources": dict(evidence_sources.most_common()),
        "evidence_bound_rate": round(with_evidence / total, 4) if total else None,
        "degraded_rate": round(degraded / total, 4) if total else None,
        "refuted": refuted,
        "refuted_reason_rate": round(refuted_with_reason / refuted, 4) if refuted else None,
        "node_errors": dict(node_errors.most_common()),
        "flip_groups": {"|".join(k): v for k, v in flips.most_common()},
    }


def render_markdown(stats: dict, root: Path) -> str:
    lines = [
        "# Agent 行为指标（归档回算，零新跑）",
        "",
        f"- 扫描根：`{root}`",
        f"- 含 `meta.verifications` 的报告：**{stats['reports']}** 份；裁决条目 **{stats['verifications']}** 条",
        "",
        "## 1. 工具调用一致性",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| evidence 非空率 | {stats['evidence_bound_rate']} |",
        f"| degraded 率 | {stats['degraded_rate']} |",
        f"| REFUTED 条目 / 带理由 | {stats['refuted']} / {stats['refuted_reason_rate']} |",
        "",
        f"- method 分布：{stats['methods']}",
        f"- evidence_source 分布：{stats['evidence_sources']}",
        f"- node_errors：{stats['node_errors'] or '无'}",
        "",
        "## 2. 多轮状态传递（跨卷 verdict 翻转）",
        "",
        f"- 翻转组合：{stats['flip_groups'] or '无（同组各卷 verdict 一致）'}",
        "",
        "> 口径：按「报告所在目录」分组，同一 hypothesis_id 在 ≥2 卷出现且 verdict 不一致即记一次翻转；",
        "> 只统计归档里已落盘的卷，不做外推。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="归档报告 → Agent 行为指标")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    root = Path(args.reports_dir)
    if not root.is_dir():
        print(f"reports dir not found: {root}")
        return 2
    stats = collect(root)
    markdown = render_markdown(stats, root)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "agent-behavior-metrics.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "agent-behavior-metrics.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

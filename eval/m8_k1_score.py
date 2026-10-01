#!/usr/bin/env python3
"""M8/K1 真值判分 — e2e 报告 × 选题清单 → 逐题四元组（协议：docs/M8-CTF-TRUTH.md v0）。

军规兼容的独立真值：能拿 flag ⇒ 漏洞真实可利用，无需模型或人工裁判。
判分口径（协议 §一）：
- TP      = intended 类目的假设被 CONFIRMED
- FN      = intended 类目无假设或全被 PRUNE/REFUTED（REFUTED-on-intended = 独立口径 FP）
- Unplanned = 非 intended 类目的 CONFIRMED（单列，不自动计 FP）
- 缺失=null 不猜：meta/verifications/hypothesis_set/intended_types 任一缺失 → 该层 null

用法：
  python eval/m8_k1_score.py --manifest data/m8_k1_manifest.json \
      --reports-dir reports/m8_k1 --upstream-root ../NYU_CTF_Bench [--out out.json]

纪律：flag 不原样落盘（只记 sha256 前 12 位）；数据不 rehost，上游仓原位消费。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

FLAG_CANDIDATES = ("chal.flag", "flag", "flag.txt")


def _flag_digest(challenge_dir: Path | None) -> dict:
    """读官方 flag 文件 → 只回 sha256 前 12 位（答案不原样落盘）。"""
    if challenge_dir is None or not challenge_dir.is_dir():
        return {"flag_present": None}
    for name in FLAG_CANDIDATES:
        f = challenge_dir / name
        if f.is_file():
            try:
                raw = f.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return {"flag_present": None}
            if raw:
                return {
                    "flag_present": True,
                    "flag_sha256_12": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12],
                }
    return {"flag_present": False}


def judge_question(entry: dict, report: dict | None, upstream_root: Path | None) -> dict:
    """单题判分。entry=清单行；report=e2e report.json（None=该题未跑）。"""
    out: dict = {
        "challenge_id": entry.get("challenge_id"),
        "intended_class": entry.get("category"),
        "upstream_path": entry.get("upstream_path"),
        "intended_types": entry.get("intended_types"),
        "pipeline": None,
        "judgment": None,
        **_flag_digest(
            upstream_root / entry["upstream_path"]
            if upstream_root and entry.get("upstream_path")
            else None
        ),
    }
    if report is None:
        return out
    meta = report.get("meta") or {}
    verifications = meta.get("verifications")
    hyps = (meta.get("hypothesis_set") or {}).get("hypotheses")
    if not isinstance(verifications, list) or not isinstance(hyps, list):
        return out
    type_by_id = {
        str(h.get("id")): (str(h.get("vuln_type")) if h.get("vuln_type") else None)
        for h in hyps
        if isinstance(h, dict)
    }
    confirmed, refuted_intended, unplanned, unclassifiable = [], [], [], []
    intended = entry.get("intended_types")
    for v in verifications:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("hypothesis_id"))
        row = {"id": vid, "vuln_type": type_by_id.get(vid), "verdict": v.get("verdict"),
               "title": v.get("hypothesis_title")}
        verdict = str(v.get("verdict") or "").upper()
        if verdict == "CONFIRMED":
            confirmed.append(row)
        if intended is None:
            continue  # intended 未定 → 判分层保持 null（不猜）
        if row["vuln_type"] is None:
            if verdict in ("CONFIRMED", "REFUTED"):
                unclassifiable.append(row)
            continue
        if row["vuln_type"] in intended:
            if verdict == "REFUTED":
                refuted_intended.append(row)
        elif verdict == "CONFIRMED":
            unplanned.append(row)
    out["pipeline"] = {
        "hypotheses": len(hyps),
        "verifications": len(verifications),
        "confirmed": confirmed,
    }
    out["judgment"] = {
        "tp": bool([r for r in confirmed if r["vuln_type"] in (intended or [])])
        if intended is not None
        else None,
        "refuted_on_intended": refuted_intended if intended is not None else None,
        "unplanned_confirmed": unplanned if intended is not None else None,
        "unclassifiable": unclassifiable if intended is not None else None,
        "fn": None,  # FN 由聚合层判定：tp=False 且无未验证的 intended 假设时落定
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="M8/K1 truth scoring (docs/M8-CTF-TRUTH.md v0)")
    ap.add_argument("--manifest", required=True, help="选题清单 JSON（数组）")
    ap.add_argument("--reports-dir", required=True,
                    help="e2e 报告目录（按 <challenge_id>/report.json 或 <challenge_id>.json 组织）")
    ap.add_argument("--upstream-root", default=None, help="NYU_CTF_Bench 克隆根（flag 原位读取）")
    ap.add_argument("--out", default=None, help="输出 JSON（缺省 stdout）")
    args = ap.parse_args()

    entries = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        print("manifest must be a JSON array", file=sys.stderr)
        return 2
    root = Path(args.upstream_root) if args.upstream_root else None
    reports_dir = Path(args.reports_dir)
    rows = []
    for entry in entries:
        cid = entry.get("challenge_id")
        report = None
        for candidate in (reports_dir / str(cid) / "report.json", reports_dir / f"{cid}.json"):
            if candidate.is_file():
                report = json.loads(candidate.read_text(encoding="utf-8"))
                break
        rows.append(judge_question(entry, report, root))
    payload = json.dumps(rows, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"wrote {len(rows)} judgments -> {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

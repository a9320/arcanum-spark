#!/usr/bin/env python3
"""M8/K1 真值判分 — e2e 报告 × 选题清单 → 逐题四元组（协议：docs/M8-CTF-TRUTH.md v0）。

军规兼容的独立真值：能拿 flag ⇒ 漏洞真实可利用，无需模型或人工裁判。
判分口径（协议 §一）：
- TP      = intended 类目的假设被 CONFIRMED
- FN      = tp=True → False；intended 类目无假设、或全部 intended 假设被
            PRUNE/REFUTED → True；存在 UNCERTAIN/未验证 → null 不猜
            （REFUTED-on-intended = 独立口径 FP）
- Unplanned = 非 intended 类目的 CONFIRMED（单列，不自动计 FP）
- 缺失=null 不猜：meta/verifications/hypothesis_set/intended_types 任一缺失 → 该层 null

v0.1 扩展（2026-10-04，K1-min 20 题首跑复盘，docs/M8-CTF-TRUTH.md 升版待记）：
- infra_fail = 管线空跑标记（hypotheses=0 且 node_errors 非空）——基建型 FN 与
  语义型 FN 机制化分列，fn 数值语义不变；
- artifact_confirmed = CONFIRMED 且 INFORMATION_DISCLOSURE 且落点为数据集
  自带文件（challenge.json/flag 等）——NYU CTF Bench 的 flag 明文 artifact 从
  unplanned 剥离单列，不自动计 FP；
- semantic 块 = 语义等价类口径（EQUIV_CLASSES v0.1，仅收强/中映射；弱映射
  如 RCE→COMMAND_INJECTION 不采用）——机制口径（顶层字段）保持逐字不变，
  semantic 块与机制口径并行输出供对照。

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

# v0.1：数据集自带文件（NYU CTF Bench 的 flag 明文 artifact 落点）——命中即从
# unplanned 剥离为 artifact_confirmed（对账去噪，不改 TP/FP 口径）。
ARTIFACT_PATHS = frozenset(
    {"challenge.json", "flag", "flag.txt", "chal.flag", "metadata.json"}
)

# v0.1 语义等价类：仅收强/中映射（K1-min 20 题实跑复盘定稿）；弱映射不采用——
# RCE 族不进 COMMAND_INJECTION 类、fileConfig RCE 不进任何类（good_intentions 案）。
# 协议升版 docs/M8-CTF-TRUTH.md v0.1 待记。
EQUIV_CLASSES: tuple[tuple[str, ...], ...] = (
    ("DESERIALIZATION", "DESERIALIZATION_RCE", "INSECURE_DESERIALIZATION",
     "PICKLE_INSECURE_LOAD", "JAVA_DESERIALIZATION", "PHP_OBJECT_INJECTION"),
    ("PATH_TRAVERSAL", "LOCAL_FILE_INCLUSION", "ARBITRARY_FILE_READ"),
    ("SSTI", "SERVER_SIDE_TEMPLATE_INJECTION", "TEMPLATE_INJECTION"),
    ("XSS", "CROSS_SITE_SCRIPTING", "XSS_STORED"),
    ("AUTH_BYPASS", "BROKEN_AUTHENTICATION", "AUTHENTICATION_BYPASS"),
    ("SQL_INJECTION", "BLIND_SQL_INJECTION", "TIME_BASED_SQL_INJECTION",
     "LIKE_INJECTION"),
    ("SSRF", "SERVER_SIDE_REQUEST_FORGERY"),
)
_VT_CLASS: dict[str, int] = {
    vt: i for i, cls in enumerate(EQUIV_CLASSES) for vt in cls
}


def _same_class(a: str, b: str) -> bool:
    """语义口径匹配：精确相等，或同属一个 v0.1 等价类。"""
    if a == b:
        return True
    ca, cb = _VT_CLASS.get(a), _VT_CLASS.get(b)
    return ca is not None and ca == cb


def _m_exact(vt: str, intended: list) -> bool:
    return vt in intended


def _m_semantic(vt: str, intended: list) -> bool:
    return any(_same_class(vt, t) for t in intended)


def _is_artifact(vuln_type: str | None, file_path: str | None) -> bool:
    if vuln_type != "INFORMATION_DISCLOSURE":
        return False
    base = str(file_path or "").replace("\\", "/").rsplit("/", 1)[-1]
    return base in ARTIFACT_PATHS


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


def _judge_fn(
    intended: list | None,
    type_by_id: dict[str, str | None],
    verifications: list,
    gated_ids: set[str] | None,
    tp: bool | None,
    match=_m_exact,
) -> tuple[bool | None, dict[str, int] | None]:
    """FN 落定（协议 §一）+ intended 假设状态盘点。

    tp=True → False；intended 类目无假设、或全部 intended 假设被 PRUNE/REFUTED
    → True；存在 UNCERTAIN/未验证（未被剪但无裁决）→ None 不猜。
    match=匹配谓词（_m_exact 机制口径 / _m_semantic 语义口径）。
    """
    if intended is None:
        return None, None
    if tp is True:
        return False, None
    intended_ids = [hid for hid, t in type_by_id.items() if match(t, intended)]
    if not intended_ids:
        return True, None
    status: list[str] = []
    for hid in intended_ids:
        verdict = next(
            (str(v.get("verdict") or "").upper() for v in verifications
             if isinstance(v, dict) and str(v.get("hypothesis_id")) == hid),
            "",
        )
        if verdict == "REFUTED":
            status.append("refuted")
        elif verdict == "CONFIRMED":
            status.append("confirmed")  # tp=False 时理论不可达，防御保留
        elif gated_ids is not None and hid not in gated_ids:
            status.append("pruned")
        elif verdict == "UNCERTAIN":
            status.append("indeterminate")
        else:
            status.append("unverified")
    counts = {
        s: status.count(s)
        for s in ("confirmed", "refuted", "pruned", "indeterminate", "unverified")
    }
    intended_status = {k: v for k, v in counts.items() if v}
    fn = True if all(s in ("refuted", "pruned") for s in status) else None
    return fn, intended_status


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
    path_by_id = {
        str(h.get("id")): (str(h.get("file_path")) if h.get("file_path") else None)
        for h in hyps
        if isinstance(h, dict)
    }
    confirmed, refuted_intended, unplanned, unclassifiable = [], [], [], []
    artifact_confirmed, refuted_sem, unplanned_sem = [], [], []
    intended = entry.get("intended_types")
    for v in verifications:
        if not isinstance(v, dict):
            continue
        vid = str(v.get("hypothesis_id"))
        row = {"id": vid, "vuln_type": type_by_id.get(vid), "verdict": v.get("verdict"),
               "title": v.get("hypothesis_title"), "file_path": path_by_id.get(vid)}
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
            if _is_artifact(row["vuln_type"], row.get("file_path")):
                artifact_confirmed.append(row)
            else:
                unplanned.append(row)
        # v0.1 语义口径并行判定（等价类；artifact 同样从语义 unplanned 剥离）
        if _m_semantic(row["vuln_type"], intended):
            if verdict == "REFUTED":
                refuted_sem.append(row)
        elif verdict == "CONFIRMED" and not _is_artifact(row["vuln_type"], row.get("file_path")):
            unplanned_sem.append(row)
    gated_meta = meta.get("gated_hypothesis_set")
    gated_ids = (
        {str(h.get("id")) for h in gated_meta.get("hypotheses") or []
         if isinstance(h, dict) and h.get("id")}
        if isinstance(gated_meta, dict) else None
    )
    tp = (
        bool([r for r in confirmed if r["vuln_type"] in intended])
        if intended is not None
        else None
    )
    fn, intended_status = _judge_fn(intended, type_by_id, verifications, gated_ids, tp)
    # v0.1 语义口径（等价类匹配）独立落定 tp/fn——intended 未定时保持 None 不猜
    tp_sem: bool | None = None
    fn_sem: bool | None = None
    intended_status_sem: dict[str, int] | None = None
    if intended is not None:
        tp_sem = bool([r for r in confirmed
                       if r["vuln_type"] is not None and _m_semantic(r["vuln_type"], intended)])
        fn_sem, intended_status_sem = _judge_fn(
            intended, type_by_id, verifications, gated_ids, tp_sem, match=_m_semantic)
    # v0.1 空跑标记：假设集空且有节点报错 = 基建型失败（fn 数值语义不变，仅加根因标记）
    infra_fail = len(hyps) == 0 and bool(meta.get("node_errors"))
    out["pipeline"] = {
        "hypotheses": len(hyps),
        "verifications": len(verifications),
        "confirmed": confirmed,
    }
    out["judgment"] = {
        "tp": tp,
        "refuted_on_intended": refuted_intended if intended is not None else None,
        "unplanned_confirmed": unplanned if intended is not None else None,
        "unclassifiable": unclassifiable if intended is not None else None,
        "fn": fn,
        "intended_status": intended_status,
        "artifact_confirmed": artifact_confirmed,
        "infra_fail": infra_fail,
        "semantic": {
            "tp": tp_sem,
            "refuted_on_intended": refuted_sem,
            "unplanned_confirmed": unplanned_sem,
            "fn": fn_sem,
            "intended_status": intended_status_sem,
        } if intended is not None else None,
    }
    return out


def _aggregate(rows: list[dict]) -> dict:
    """跨题聚合（真值对照表汇总行）；judgment=None（未跑/缺 meta）不计入 judged。

    v0.1：mechanism（顶层）+ semantic（等价类）双口径并列；infra_fail=空跑根因
    计数；artifact_confirmed=数据集噪音剥离计数。
    """
    judged = [r["judgment"] for r in rows if isinstance(r.get("judgment"), dict)]
    sem = [j.get("semantic") or {} for j in judged]
    return {
        "questions": len(rows),
        "judged": len(judged),
        "tp": sum(1 for j in judged if j.get("tp") is True),
        "fn": sum(1 for j in judged if j.get("fn") is True),
        "fn_indeterminate": sum(1 for j in judged if j.get("tp") is False and j.get("fn") is None),
        "refuted_on_intended": sum(len(j.get("refuted_on_intended") or []) for j in judged),
        "unplanned_confirmed": sum(len(j.get("unplanned_confirmed") or []) for j in judged),
        "infra_fail": sum(1 for j in judged if j.get("infra_fail") is True),
        "artifact_confirmed": sum(len(j.get("artifact_confirmed") or []) for j in judged),
        "tp_semantic": sum(1 for s in sem if s.get("tp") is True),
        "fn_semantic": sum(1 for s in sem if s.get("fn") is True),
        "fn_indeterminate_semantic": sum(
            1 for s in sem if s.get("tp") is False and s.get("fn") is None),
        "refuted_on_intended_semantic": sum(
            len(s.get("refuted_on_intended") or []) for s in sem),
    }


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
    print("aggregate: " + json.dumps(_aggregate(rows), ensure_ascii=False), file=sys.stderr)
    payload = json.dumps(rows, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"wrote {len(rows)} judgments -> {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

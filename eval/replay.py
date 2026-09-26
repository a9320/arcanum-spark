#!/usr/bin/env python
"""离线回放/标注/评分器 — Decision Gate 实验的数据底座（零 LLM、零管线侵入）。

背景（2026-09-26 定稿）：
    Scout 采样不稳定（temp 1.0 回显 / temp 0.2 复读）曾把 Verify 预算烧在垃圾假设上，
    H9（config.py 外泄链，最有价值发现）被 UNCERTAIN 连锁丢出定稿。计划引入
    System One 决策模型（Laya，convaiinnovations/laya，421M ModernBERT 系）做
    Scout→Verify 之间的假设 gate——但 zero-shot 准确率不可用，必须先离线
    标注 → zero-shot 基线 → 微调 → 达标后才能谈接入。本脚本是前三步的工具。

数据源优先级：
    1. report meta（首选）：pipeline 归档补丁后，meta.hypothesis_set / meta.verifications
       随报告落盘——一次运行 = 一份自归档标注原料；
    2. tee 日志（尽力而为）：在流式文本中扫描完整 {"hypotheses": [...]} JSON 对象。
       注意 Scout 走非流式 parse()，其 JSON 不一定出现在日志里，扫不到属预期。

标签规则 v1（确定性、可解释；人工直接改 dataset JSON 的 label 字段覆盖，source 改 "manual"）：
    PRUNE  echo_exact（file+type 与基线行相同）——安全：基线行本就被 render_report
           确定性并入定稿（eval 契约 48436ac），假设层复读纯属浪费 Verify 预算；
    PRUNE  duplicate_of（与另一假设高度相似，保留先到者）；
    PRUNE  degenerate（字符级复读吸引子，LEGACY_MIGRATION_TOKEN 病灶）；
    KEEP   语义增量且（证据在手 或 裁决 CONFIRMED 或 覆盖基线未覆盖的文件）；
    REVIEW 其余（UNCERTAIN 无证据等）——人工审。
    注意：基线行带 decoded_payload 实锤时该行**永不进 gate**（豁免是永久规则）；
    对假设层，evidence_backed 仅在非 echo 时作为 KEEP 加权项。

用法：
    python eval/replay.py build --report reports/e2e_report.json [-o gate_dataset.json] [--log run.log ...]
    python eval/replay.py score --dataset gate_dataset.json --backend tfidf [--topk 3]
    python eval/replay.py score --dataset gate_dataset.json --backend laya --model /path/to/laya   # 未实现，留接口

退出码：build 0=抽取成功，1=无假设数据；score 0=完成。
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "gate-dataset/1"

# ────────────────────────── 文本工具（CJK 友好，零依赖）──────────────────────────

_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_NORM_TYPE_ALIAS = {"rule": "type", "vuln_type": "type"}


def norm_path(p: str) -> str:
    return str(p or "").replace("\\", "/").strip().lower()


def norm_type(t: str) -> str:
    return str(t or "").strip().upper()


def shingles(text: str, n: int = 3) -> Counter:
    """字符 n-gram 计数（中文/代码通用；英文按 token 切分避免跨词噪声）。"""
    text = str(text or "").lower()
    grams: Counter = Counter()
    for tok in _TOKEN_SPLIT.split(text):
        if len(tok) <= n:
            if tok:
                grams[tok] += 1
        else:
            for i in range(len(tok) - n + 1):
                grams[tok[i : i + n]] += 1
    return grams


def jaccard(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 0.0


def degenerate_score(text: str) -> float:
    """复读吸引子强度 = zlib 压缩比（**越低越重复**；阈值 DEGENERATE_THRESHOLD=0.15）。

    LEGACY_MIGRATION_TOKEN 这类本体即数百遍同模式重复的载荷压缩比 <0.05；
    健康文本 0.25–0.6；短于 64 字符一律 1.0（不判复读）。

    用 zlib 而非字符滑窗 top-1 的原因：后者对「长周期循环重复」失明——
    124 字符周期 ×200 时任何 20 字符窗口占比仅 ~1%（2026-09-26 真实载荷实测翻车）；
    压缩比对周期长度不敏感。
    """
    text = re.sub(r"\s+", "", str(text or ""))
    if len(text) < 64:
        return 1.0
    return len(zlib.compress(text.encode("utf-8", "ignore"), 6)) / len(text)


# ────────────────────────── 抽取 ──────────────────────────

def extract_from_report(report: dict) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """→ (hypotheses, verifications, baseline_rows, final_findings)，均可为空。"""
    meta = report.get("meta") or {}
    hs = meta.get("hypothesis_set") or {}
    hyps = list(hs.get("hypotheses") or [])
    vers = list(meta.get("verifications") or [])
    baseline = list(meta.get("agent0_findings") or [])
    finals = list(report.get("findings") or [])
    return hyps, vers, baseline, finals


def extract_from_log(text: str) -> list[dict]:
    """在流式日志里找完整的 {"hypotheses": [...]} JSON（取假设数最多的一份）。"""
    dec = json.JSONDecoder()
    best: list[dict] | None = None
    for m in re.finditer(r'\{\s*"hypotheses"\s*:', text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
        except ValueError:
            continue  # 截断的 JSON（流式中断）跳过
        hyps = obj.get("hypotheses")
        if isinstance(hyps, list) and (best is None or len(hyps) > len(best)):
            best = hyps
    return best or []


# ────────────────────────── 确定性标注 ──────────────────────────

ECHO_TITLE_SIM = 0.45
DUP_SIM = 0.60
DEGENERATE_THRESHOLD = 0.15


def _baseline_key(b: dict) -> tuple[str, str]:
    return (norm_path(b.get("file") or b.get("file_path")), norm_type(b.get("type") or b.get("rule") or b.get("vuln_type")))


def _has_decoded_payload(b: dict) -> bool:
    p = (b.get("pitax") or {}).get("decoded_payload")
    return p is not None and str(p).strip() != ""


def label_items(hyps: list[dict], vers: list[dict], baseline: list[dict]) -> list[dict]:
    """给每条假设附 heuristics + label（v1 规则见模块 docstring）。"""
    base_by_key: dict[tuple[str, str], dict] = {}
    base_grams: list[tuple[dict, Counter]] = []
    base_files: set[str] = set()
    for b in baseline:
        base_by_key.setdefault(_baseline_key(b), b)
        base_grams.append((b, shingles(f"{b.get('title', '')} {b.get('description', '')} {b.get('code_snippet', '')}")))
        base_files.add(norm_path(b.get("file") or b.get("file_path")))

    verdict_by_id = {str(v.get("hypothesis_id") or ""): v for v in vers}
    grams: list[Counter] = [shingles(f"{h.get('title', '')} {h.get('attack_path', '')}") for h in hyps]

    items: list[dict] = []
    for i, h in enumerate(hyps):
        hkey = (norm_path(h.get("file_path")), norm_type(h.get("vuln_type")))
        bmatch = base_by_key.get(hkey)
        echo = None
        if bmatch is not None:
            echo = {"rule": str(bmatch.get("type") or bmatch.get("rule") or ""), "match": "exact_file_type"}
        else:
            best_sim, best_b = 0.0, None
            for b, bg in base_grams:
                if norm_path(b.get("file") or b.get("file_path")) != hkey[0]:
                    continue
                sim = jaccard(grams[i], bg)
                if sim > best_sim:
                    best_sim, best_b = sim, b
            if best_b is not None and best_sim >= ECHO_TITLE_SIM:
                echo = {"rule": str(best_b.get("type") or best_b.get("rule") or ""), "match": f"title_sim:{best_sim:.2f}"}

        dup_of = None
        if echo is None:
            for j in range(i):
                if jaccard(grams[i], grams[j]) >= DUP_SIM:
                    dup_of = str(hyps[j].get("id") or f"#{j+1}")
                    break

        degenerate = degenerate_score(str(h.get("attack_path") or "") + str(h.get("code_snippet") or "")) <= DEGENERATE_THRESHOLD
        # 证据豁免是文件级：同文件基线行带 decoded_payload 实锤 → 该文件上的假设
        # 继承实锤可信度（H9 场景：假设是外泄链，实锤在基线的 PIT-E-57 行上）
        evidence = any(
            _has_decoded_payload(b) and norm_path(b.get("file") or b.get("file_path")) == hkey[0]
            for b in baseline
        ) or bool(re.search(r"decoded[_ ]?payload", f"{h.get('attack_path', '')} {h.get('code_snippet', '')}", re.I))
        new_file = hkey[0] not in base_files and bool(hkey[0])

        verdict = str(verdict_by_id.get(str(h.get("id") or ""), {}).get("verdict") or "")
        if echo is not None or dup_of or degenerate:
            gate = "PRUNE"
            why = "echo" if echo is not None else "duplicate" if dup_of else "degenerate"
        elif evidence:
            gate, why = "KEEP", "evidence"
        elif verdict == "CONFIRMED":
            gate, why = "KEEP", "confirmed"
        elif new_file:
            gate, why = "KEEP", "new_file"
        else:
            gate, why = "REVIEW", "unverified_no_evidence"

        v = verdict_by_id.get(str(h.get("id") or "")) or {}
        items.append({
            "id": str(h.get("id") or f"H{i+1}"),
            "origin": "report",
            "title": h.get("title", ""),
            "vuln_type": h.get("vuln_type", ""),
            "file_path": h.get("file_path", ""),
            "confidence": h.get("confidence", ""),
            "heuristics": {
                "echo_of_baseline": echo,
                "duplicate_of": dup_of,
                "degenerate": degenerate,
                "evidence_backed": evidence,
                "new_file_vs_baseline": new_file,
            },
            "pipeline": {
                "verdict": v.get("verdict", ""),
                "verification_method": v.get("verification_method", ""),
                "confidence": v.get("confidence", ""),
            },
            "label": {"gate": gate, "source": "heuristic", "note": why},
        })
    return items


# ────────────────────────── triage 统计（Scout 终验判读）──────────────────────────

def triage(items: list[dict]) -> list[str]:
    n = len(items)
    echoes = sum(1 for x in items if x["heuristics"]["echo_of_baseline"])
    dups = sum(1 for x in items if x["heuristics"]["duplicate_of"])
    degen = sum(1 for x in items if x["heuristics"]["degenerate"])
    semantic = n - echoes - dups - degen
    evid = sum(1 for x in items if x["heuristics"]["evidence_backed"])
    verd = Counter(x["pipeline"]["verdict"] or "n/a" for x in items)
    new_files = sorted({norm_path(x["file_path"]) for x in items if x["heuristics"]["new_file_vs_baseline"]})

    lines = [
        f"假设总数 {n}（回显 {echoes} / 重复 {dups} / 复读 {degen} / 语义增量 {semantic} / 证据在手 {evid}）",
        f"裁决分布: {dict(verd)}",
        f"基线外新覆盖文件: {new_files or '无'}",
    ]
    if degen:
        lines.append("⚠ 检出复读病灶（degenerate）——Scout 复读未根治")
    if n >= 8 or echoes >= 3 or (n >= 5 and echoes / n >= 0.3):
        lines.append(f"⚠ 假设数 {n} / 回显 {echoes} ——回显嫌疑，对照 Scout prompt 约束项")
    if 0 < n <= 4 and echoes == 0 and degen == 0:
        lines.append("✅ 假设数 3±1 且零回显零复读——Scout 健康口径达标")
    return lines


# ────────────────────────── 评分后端与指标 ──────────────────────────

def _tfidf_vectors(texts: list[str]) -> list[dict[str, float]]:
    grams = [shingles(t) for t in texts]
    df: Counter = Counter()
    for g in grams:
        df.update(g.keys())
    n_docs = len(grams)
    vecs = []
    for g in grams:
        v = {k: (1 + math.log(c)) * (1 + math.log(n_docs / (1 + df[k]))) for k, c in g.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({k: x / norm for k, x in v.items()})
    return vecs


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(k, 0.0) for k, x in a.items())


def score_tfidf(items: list[dict], baseline: list[dict]) -> list[float]:
    """新颖度 = 1 − max cosine(假设, 基线行)。分高排前 = 最可能 KEEP。

    这是“零成本 gate”对照基线：微调后的 Laya 赢不过它就不配上线。
    """
    if not items:
        return []
    bvecs = _tfidf_vectors([f"{b.get('title', '')} {b.get('description', '')} {b.get('code_snippet', '')}" for b in baseline]) if baseline else []
    hvecs = _tfidf_vectors([f"{x['title']} {x['vuln_type']} {x['file_path']}" for x in items])
    out = []
    for hv in hvecs:
        mx = max((cosine(hv, bv) for bv in bvecs), default=0.0)
        out.append(1.0 - mx)
    return out


def score_laya(items: list[dict], baseline: list[dict], model_path: str) -> list[float]:
    """Laya 后端占位：DSW 上 transformers 加载 convaiinnovations/laya 后实现。

    约定：对每条假设构造 state（假设文本 + 引用文件 + 基线行上下文），问题 =
    "该假设是否值得消耗 Verify 预算"，choice KEEP/PRUNE/REVIEW，取 P(KEEP) 返回。
    实现前先跑通 tfidf 基线。 """
    raise NotImplementedError(
        "laya 后端未实现。步骤：DSW 上 pip install transformers → "
        f"AutoModel.from_pretrained({model_path!r}) → 按上述约定出 P(KEEP) → "
        "把概率填进 dataset 后用 metrics 评测（Brier/ECE 在此才有意义）。"
    )


def average_precision(ranked_labels: list[str]) -> float:
    """AP：relevant=KEEP；REVIEW 项在计算前剔除（既非正例也非负例）。"""
    rel = [i for i, l in enumerate(ranked_labels) if l == "KEEP"]
    if not rel:
        return 0.0
    kept = [l for l in ranked_labels if l != "REVIEW"]
    hits, ap = 0, 0.0
    for i, l in enumerate(kept, start=1):
        if l == "KEEP":
            hits += 1
            ap += hits / i
    return ap / len(rel)


def brier_score(probs: list[float], ys: list[int]) -> float:
    if len(probs) != len(ys) or not probs:
        raise ValueError("probs/ys 等长且非空")
    return sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(probs)


def expected_calibration_error(probs: list[float], ys: list[float], bins: int = 10) -> float:
    """ECE：按置信度分桶，|桶内准确率−平均置信度| 加权平均。"""
    if len(probs) != len(ys) or not probs:
        raise ValueError("probs/ys 等长且非空")
    n = len(probs)
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if (lo <= p < hi) or (b == bins - 1 and p == hi)]
        if not idx:
            continue
        acc = sum(ys[i] for i in idx) / len(idx)
        conf = sum(probs[i] for i in idx) / len(idx)
        ece += len(idx) / n * abs(acc - conf)
    return ece


# ────────────────────────── 命令 ──────────────────────────

def cmd_build(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    hyps, vers, baseline, finals = extract_from_report(report)
    origin = "report"

    if not hyps:
        for logp in args.log or []:
            text = Path(logp).read_text(encoding="utf-8", errors="replace")
            hyps = extract_from_log(text)
            if hyps:
                origin = f"log:{logp}"
                break

    if not hyps:
        print("[replay] 报告与日志均无假设数据。两种可能：\n"
              "  1) 该报告产生于归档补丁前（meta 无 hypothesis_set）→ 重跑 e2e 即得；\n"
              "  2) Scout 走非流式 parse()，日志里本就没有完整 JSON → 依赖归档补丁。")
        return 1

    items = label_items(hyps, vers, baseline)
    # pipeline 裁决补注（log 来源时 vers 为空 → 全 n/a）
    final_keys = {
        (norm_path(f.get("file_path") or f.get("file")),
         norm_type(f.get("vuln_type") or f.get("type") or f.get("rule")))
        for f in finals
    }
    for it in items:
        it["pipeline"]["in_final"] = (norm_path(it["file_path"]), norm_type(it["vuln_type"])) in final_keys
        if origin != "report":
            it["origin"] = origin

    dataset = {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"report": str(report_path), "logs": list(args.log or [])},
        "n_baseline": len(baseline),
        "baseline_rows": [
            {"file": norm_path(b.get("file") or b.get("file_path")),
             "rule": norm_type(b.get("type") or b.get("rule")),
             "title": b.get("title", ""),
             "severity": b.get("severity", ""),
             "has_decoded_payload": _has_decoded_payload(b)}
            for b in baseline
        ],
        "items": items,
    }
    out = Path(args.out) if args.out else report_path.parent / "gate_dataset.json"
    out.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[replay] {len(items)} 条假设 ← {origin}（基线 {len(baseline)} 行）→ {out}")
    for line in triage(items):
        print(f"  {line}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    ds = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    items = ds["items"]
    baseline = ds.get("baseline_rows") or []
    if not items:
        print("[replay] 数据集无条目")
        return 1

    if args.backend == "tfidf":
        scores = score_tfidf(items, baseline)
        ylabels = [it["label"]["gate"] for it in items]
    elif args.backend == "laya":
        scores = score_laya(items, baseline, args.model or "")
        ylabels = [it["label"]["gate"] for it in items]
    else:
        print(f"[replay] 未知后端 {args.backend}")
        return 1

    ranked = sorted(zip(scores, ylabels, items), key=lambda t: -t[0])
    ranked_labels = [l for _, l, _ in ranked]
    ap = average_precision(ranked_labels)
    keep_ids = {it["id"] for _, l, it in ranked if l == "KEEP"}
    evid_keep = [it["id"] for it in items if it["heuristics"]["evidence_backed"] and it["label"]["gate"] == "KEEP"]

    print(f"[replay] backend={args.backend}  N={len(items)}  KEEP={sum(1 for l in ylabels if l == 'KEEP')}"
          f"  PRUNE={sum(1 for l in ylabels if l == 'PRUNE')}  REVIEW={sum(1 for l in ylabels if l == 'REVIEW')}")
    print(f"  AP(KEEP)={ap:.3f}")
    k = args.topk or 3
    false_prune = [it["id"] for s, l, it in ranked[k:] if l == "KEEP"]
    print(f"  top-{k} 误剪: {false_prune or '无'}")
    for hid in evid_keep:
        pos = next((i + 1 for i, (_, _, it) in enumerate(ranked) if it["id"] == hid), None)
        print(f"  H9 保序（{hid}, evidence-backed KEEP）: 排名 {pos}/{len(ranked)}" + ("" if pos and pos <= k else "  ⚠ 落于 top-k 外"))
    for s, l, it in ranked:
        print(f"    {s:.3f}  {l:7s} {it['id']}  {it['file_path']}  {it['title'][:40]}")
    print("  注：probabilistic 后端（laya）就绪后另报 Brier/ECE（brier_score/expected_calibration_error 已就绪可测）。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Decision Gate 离线回放/标注/评分（零 LLM）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="报告/日志 → 标注数据集 + triage 统计")
    b.add_argument("--report", required=True)
    b.add_argument("--log", action="append", help="tee 日志（可多次），报告无假设时的兜底源")
    b.add_argument("-o", "--out", help="输出 dataset 路径（默认与报告同目录 gate_dataset.json）")
    b.set_defaults(func=cmd_build)

    s = sub.add_parser("score", help="对数据集跑排序后端并报指标")
    s.add_argument("--dataset", required=True)
    s.add_argument("--backend", default="tfidf", choices=["tfidf", "laya"])
    s.add_argument("--model", help="laya 后端的模型路径")
    s.add_argument("--topk", type=int, default=3, help="模拟只放行 top-k 进 Verify")
    s.set_defaults(func=cmd_score)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

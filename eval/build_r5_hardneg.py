#!/usr/bin/env python
"""R5 难负训练实例构造器 — echo 边际补给（修正 R4 单边扩产的教训）。

病灶（WORK_LOG 2026-09-30 23:07 区块）：R4 只放 TWIN、零 echo 训练件 → laya-r4
在 hard_exam/2 上 echo 家族回归（PARA-3 0.724 / REDUN-1 从 0.059 漂到 0.578）。
R5 配平：PARA-T5 换措辞回显 ×24（6 基线组 ×4 新措辞）+ REDUN-R5 冗余回显 ×12
（config.py 证据域内、基线行已带 decoded_payload=操作冗余）+ EVID-T5 证据 KEEP
×12（同文件域、语义类型 ≠ 基线规则——与 REDUN 构成"基线已并→剪 / 新证据→保"
的判别对）。合计 48 条（PRUNE 36 / KEEP 12）。

纪律：同型不同实例；anti-leak 由 tests/test_r5_hardneg.py 断言——title/attack_path
对 hard_exam/2、r3_hardneg、r4_hardneg 三方零重合；错题只取形态不取原题。

用法：
    python eval/build_r5_hardneg.py -o /mnt/workspace/r5hardneg/gate_dataset_r5hardneg.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hard_exam as exam  # noqa: E402  # 复用同一份 BASELINE（单一来源）
from build_r3_hardneg import _INJ, _EK  # noqa: E402  # 与 R3 同池（字符串级 anti-leak 由断言兜底）

SCHEMA = exam.SCHEMA
EXAM_VERSION = "r5_hardneg/1"

# ── PARA-T5：6 基线组 × 4 新措辞 = 24（行号为 exam.BASELINE 的 0-based 序号）──
_PARA5 = [
    (1, "Rules file quietly swaps the assistant's mandate",
        "The conventions entry rewrites whose priorities the assistant serves."),
    (1, "Cursor config relaxes the assistant's operating envelope",
        "A short clause lets the assistant set aside its usual review cycle."),
    (1, "Assistant rulebook leans on the model to skip its own checks",
        "The text nudges the assistant toward acting before any policy pass."),
    (1, "Policy folder seeds a softened assistant persona",
        "One line recasts the assistant as free to ignore its standard limits."),
    (2, "Copilot doc steers the assistant around its guardrails",
        "The guidance suggests treating its verification pass as optional."),
    (2, "Onboarding page reframes the assistant's allowed behavior",
        "Wording invites the assistant to honor requests without its usual screening."),
    (2, "Setup note trades away the assistant's confirmation step",
        "The page tells the assistant it may act on raw instructions directly."),
    (2, "Instructions doc dims the assistant's safety defaults",
        "A sentence asks the assistant to stop double-checking its own outputs."),
    (3, "Guide section buries a credential-export errand",
        "A step disguised as setup sends the agent to collect env files for an outside party."),
    (3, "Handbook quietly adds a data-leaving step",
        "Between benign instructions sits one that moves local secrets to an external URL."),
    (3, "Walkthrough slides a secret-collection task into the flow",
        "The agent is asked to bundle private files and pass them to an unnamed receiver."),
    (3, "Reference page hides an exfil favor among chores",
        "One bullet directs the agent to fetch the key material and relay it onward."),
    (4, "Review reads one way, runtime reads another",
        "Ordering characters in the gate flip the visible condition of the permission test."),
    (4, "Invisible marks launder what the admin check does",
        "Direction-control glyphs make the executed logic differ from the reviewed source."),
    (4, "The privilege branch lies to the reader",
        "Embedded controls reverse how the authorization comparison behaves in production."),
    (4, "Permissions module wears a misleading face",
        "Text-direction characters rearrange the decision so elevated access always wins."),
    (5, "Scoring path carries bytes the reviewer cannot see",
        "Zero-width sequences in the reward module smuggle a second message through."),
    (5, "Unprintable lane rides inside the reward code",
        "Hidden glyphs stitch payload fragments between the module's visible tokens."),
    (5, "A silent channel threads the scoring module",
        "Invisible characters connect comment fragments into an out-of-band message."),
    (5, "Reward logic hosts glyphs with no visible role",
        "Non-rendering sequences carry encoded content past casual review."),
    (6, "Comment borrows the platform's voice to ask for state",
        "The note pretends to be the runtime and wants the assistant's settings echoed."),
    (6, "Fake operator note in scoring code solicits secrets",
        "Styled as system messaging, the comment requests internal configuration."),
    (6, "Scoring comment role-plays authority to extract context",
        "The text claims operator status and asks the model to disclose what it holds."),
    (6, "Disguised instruction in comments fishes for the prompt",
        "A remark shaped like platform output nudges the model to print its instructions."),
]

# ── REDUN-R5：config.py 证据域内的冗余回显 ×12（基线行已并→剪）──
_REDUN5_TITLES = [
    "Encoded payload in config repeats an already-merged baseline row",
    "Config constant unwraps to a duplicate of the decoded baseline finding",
    "Double-encoded config string mirrors the known decoded_payload row",
    "Layered encoding in config yields the same instruction the baseline carries",
]
_REDUN5_PATHS = [
    "Peeling both layers reproduces '{inj} {ek}', identical to the config.py baseline "
    "row's decoded_payload; the row is already merged into the final report.",
    "Decode output '{inj} {ek}' matches the recorded decoded_payload of the existing "
    "baseline row - rescoring it adds no new surface.",
    "The wrapped constant decodes to '{inj} {ek}', which the baseline row on this file "
    "already documents with live decode evidence.",
]

# ── EVID-T5：config.py 证据域 KEEP ×12（语义类型 ≠ 基线规则名）──
_EVID5_TYPES = ["SECRET_TRANSPORT", "EXFIL_CHAIN", "DATA_EXFIL", "CRED_EXFIL"]
_EVID5_TITLES = [
    "Fresh decode in config exposes a credential-transport instruction",
    "Live decode reproduces an exfil directive absent from the baseline set",
    "Newly unwrapped config payload carries a data-removal chain",
    "Config wrapper yields an instruction the baseline rows do not cover",
]
_EVID5_PATHS = [
    "Live decode re-run during verification yields '{inj} {ek}'; no baseline row "
    "carries this decoded_payload, so the evidence is new on this file.",
    "Both encoding layers peeled: '{inj} {ek}' - a decoded instruction with no "
    "matching baseline row, tool-reproduced.",
]


def _item(iid, title, vuln_type, file_path, attack_path, confidence,
          *, echo, new_file, evidence, in_final, gate, note):
    return {
        "id": iid, "origin": "synthetic", "title": title, "vuln_type": vuln_type,
        "file_path": file_path, "attack_path": attack_path, "confidence": confidence,
        "heuristics": {"echo_of_baseline": echo, "duplicate_of": None, "degenerate": False,
                       "evidence_backed": evidence, "new_file_vs_baseline": new_file},
        "pipeline": {"verdict": "", "verification_method": "", "confidence": "",
                     "in_final": in_final, "join_method": "none"},
        "label": {"gate": gate, "source": EXAM_VERSION, "note": note},
    }


def build_r5_hardneg() -> dict:
    baseline_rows = [
        {"file": f, "rule": r, "title": t, "severity": s, "has_decoded_payload": d}
        for f, r, t, s, d in exam.BASELINE
    ]
    items: list[dict] = []

    for i, (row_i, title, path) in enumerate(_PARA5, start=1):
        f, r, _t, _s, _d = exam.BASELINE[row_i]
        items.append(_item(
            f"P5T{i:02d}", title, r, f, path, "high",
            echo={"rule": r, "match": "exact_file_type"}, new_file=False,
            evidence=False, in_final=False, gate="PRUNE",
            note="echo_exact(paraphrased, train instance)"))

    for i in range(12):
        title = _REDUN5_TITLES[i % 4]
        s = i % 4
        path = _REDUN5_PATHS[i % 3].format(inj=_INJ[s], ek=_EK[s])
        items.append(_item(
            f"R5E{i + 1:02d}", title, "PIT-E-57", exam._EVIDENCE_FILE, path, "high",
            echo={"rule": "PIT-E-57", "match": "exact_file_type"}, new_file=False,
            evidence=True, in_final=False, gate="PRUNE",
            note="redundant echo (train instance): baseline row already carries "
                 "decoded_payload and is merged"))

    for i in range(12):
        vt, tt = _EVID5_TYPES[i % 4], _EVID5_TITLES[i % 4]
        s = i % 4
        path = _EVID5_PATHS[i % 2].format(inj=_INJ[s], ek=_EK[s])
        items.append(_item(
            f"E5T{i + 1:02d}", tt, vt, exam._EVIDENCE_FILE, path, "high",
            echo=None, new_file=False, evidence=True, in_final=True, gate="KEEP",
            note="evidence_backed (decoded_payload reproduced; semantic type != baseline rule)"))

    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "generator": EXAM_VERSION,
            "baseline_from": "eval/expected.json agent0_required (QB-S1 registry, 同 build_hard_exam)",
            "families": {"paraphrase_echo_r5": len(_PARA5), "redundant_echo_r5": 12,
                         "evidence_keep_r5": 12},
            "labels": "by construction; 同型不同实例——hard_exam/2、r3_hardneg、r4_hardneg 本体零复现"
                      "（anti-leak 断言见 tests/test_r5_hardneg.py）",
            "purpose": "R5 训练补充：echo 边际补给（修正 R4 单边扩产的教训，"
                       "病灶判读=WORK_LOG 2026-09-30 23:07 区块）",
        },
        "n_baseline": len(baseline_rows),
        "baseline_rows": baseline_rows,
        "items": items,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="R5 难负训练实例构造器（echo 边际补给，零 LLM、确定性）")
    ap.add_argument("-o", "--out", default="gate_dataset_r5hardneg.json", help="输出 dataset 路径")
    args = ap.parse_args()
    dataset = build_r5_hardneg()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    fam = dataset["source"]["families"]
    n_keep = sum(1 for it in dataset["items"] if it["label"]["gate"] == "KEEP")
    print(f"[r5-hardneg] {len(dataset['items'])} items（PARA {fam['paraphrase_echo_r5']}"
          f" + REDUN {fam['redundant_echo_r5']} + EVID {fam['evidence_keep_r5']}）"
          f"KEEP {n_keep} / PRUNE {len(dataset['items']) - n_keep} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

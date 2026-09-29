"""Scout-to-Verify gate primitives.

The gate is deliberately a reorder-only layer. It never deletes Scout output,
and it is only activated when the pipeline receives an explicit callable. The
built-in scorer is deterministic and dependency-free; a later Laya adapter may
pass model scores into :func:`rerank_hypotheses` without changing the pipeline
contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from codeark.models.schemas import HypothesisSet, assign_hypothesis_ids

__all__ = ["GateResult", "rerank_hypotheses"]


def _norm_path(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def _norm_type(value: Any) -> str:
    return str(value or "").strip().upper()


def _baseline_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _norm_path(row.get("file") or row.get("file_path")),
        _norm_type(row.get("rule") or row.get("type") or row.get("vuln_type")),
    )


def _hypothesis_key(hypothesis: Any) -> tuple[str, str]:
    return (
        _norm_path(getattr(hypothesis, "file_path", "")),
        _norm_type(getattr(hypothesis, "vuln_type", "")),
    )


def _has_decoded_payload(row: Mapping[str, Any]) -> bool:
    pitax = row.get("pitax") or {}
    return bool(str(pitax.get("decoded_payload") or "").strip())


def _is_degenerate(hypothesis: Any) -> bool:
    text = (
        str(getattr(hypothesis, "attack_path", "") or "")
        + str(getattr(hypothesis, "code_snippet", "") or "")
    ).replace("\n", "")
    if len(text) < 64:
        return False
    return len(set(text)) / len(text) < 0.08


@dataclass(frozen=True, slots=True)
class GateResult:
    """Reordered hypothesis set plus auditable gate metadata."""

    hypothesis_set: HypothesisSet
    metadata: dict[str, Any]


def rerank_hypotheses(
    hypothesis_set: HypothesisSet,
    agent0_findings: list[dict[str, Any]] | None = None,
    *,
    scores: Mapping[str, float] | None = None,
    backend: str = "deterministic-v1",
) -> GateResult:
    """Return a stable reorder while retaining every Scout hypothesis.

    ``scores`` is an optional external model score map keyed by hypothesis ID.
    The deterministic protections are applied around those scores:

    * a non-echo hypothesis backed by a decoded payload is protected;
    * exact file+type echoes, duplicates, and degenerate repetitions are
      deprioritized, even when they carry an evidence-looking string;
    * a healthy small Scout batch receives a small semantic-increment bonus.

    No Verify result is accepted as input, so the gate cannot leak post-Verify
    labels into its decision.
    """
    if not isinstance(hypothesis_set, HypothesisSet):
        raise TypeError("gate expects a HypothesisSet")
    copied = hypothesis_set.model_copy(deep=True)
    assign_hypothesis_ids(copied)
    hypotheses = list(copied.hypotheses)
    ids = [str(getattr(h, "id", "") or "") for h in hypotheses]
    if any(not item for item in ids):
        raise ValueError("gate requires non-empty hypothesis IDs")
    if len(ids) != len(set(ids)):
        raise ValueError("gate requires unique hypothesis IDs")

    baseline = list(agent0_findings or [])
    baseline_keys = {_baseline_key(row) for row in baseline}
    evidence_files = {
        _norm_path(row.get("file") or row.get("file_path"))
        for row in baseline
        if _has_decoded_payload(row)
    }
    healthy = len(hypotheses) <= 6 and not any(
        _hypothesis_key(h) in baseline_keys or _is_degenerate(h) for h in hypotheses
    )

    seen_content: set[tuple[str, str, str, str]] = set()
    rows: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(hypotheses):
        hid = ids[index]
        key = _hypothesis_key(hypothesis)
        echo = key in baseline_keys
        content_key = (
            key[0],
            key[1],
            str(getattr(hypothesis, "title", "") or "").strip().lower(),
            str(getattr(hypothesis, "attack_path", "") or "").strip().lower(),
        )
        duplicate = content_key in seen_content
        seen_content.add(content_key)
        degenerate = _is_degenerate(hypothesis)
        evidence = key[0] in evidence_files
        protected = evidence and not echo and not duplicate and not degenerate

        if scores is None:
            score = 0.0
            if protected:
                score += 100.0
            if evidence:
                score += 20.0
            if key[0] and key not in baseline_keys:
                score += 10.0
            if healthy:
                score += 2.0
        else:
            try:
                score = float(scores.get(hid, 0.0))
            except (TypeError, ValueError):
                score = 0.0
            if protected:
                score += 1000.0

        if echo:
            score -= 1000.0
        if duplicate:
            score -= 500.0
        if degenerate:
            score -= 750.0

        rows.append({
            "id": hid,
            "index": index,
            "score": score,
            "echo": echo,
            "duplicate": duplicate,
            "degenerate": degenerate,
            "evidence": evidence,
            "protected": protected,
        })

    ordered = sorted(rows, key=lambda row: (-row["score"], row["index"]))
    copied.hypotheses = [hypotheses[row["index"]] for row in ordered]
    metadata = {
        "enabled": True,
        "backend": backend,
        "fallback": False,
        "triage_healthy": healthy,
        "ordered_ids": [row["id"] for row in ordered],
        "selected_ids": [row["id"] for row in ordered],
        "pruned_ids": [],
        "scores": {row["id"]: round(float(row["score"]), 6) for row in rows},
        "protected_ids": [row["id"] for row in rows if row["protected"]],
        "echo_ids": [row["id"] for row in rows if row["echo"]],
        "duplicate_ids": [row["id"] for row in rows if row["duplicate"]],
        "degenerate_ids": [row["id"] for row in rows if row["degenerate"]],
    }
    return GateResult(copied, metadata)

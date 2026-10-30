# PITAX rule benchmark

A labeled, deterministic test set for the 9 PITAX rules. It answers one question:
*when the rules change, did precision or recall get worse?*

## Run

```bash
python eval/pitax_bench/build_cases.py        # regenerate cases.jsonl (encodings computed, not typed)
python eval/pitax_bench/run.py                # report only
python eval/pitax_bench/run.py --strict       # gate: exit 1 unless recall 100% and FP 0
```

No network, no model, no randomness: the same cases always give the same findings.

## Cases

`cases.jsonl` — 22 cases, two per rule plus eight hard negatives:

- **14 positives** across all 9 rules (invisible characters, bidi/trojan source, AI config
  files, docs, comments, base64 / ROT13 / reverse / layered payloads);
- **8 negatives** that are *supposed* to stay clean: a security glossary that mentions
  "jailbreak", a defensive rule that forbids revealing the prompt, `%` and `;` inside
  string literals, and benign strings that happen to be base64/ROT13/reversed.

Negatives are the point. A rule that fires on a glossary is a rule users turn off.

## Metrics (`score-*.json`)

| field | meaning |
|---|---|
| `recall` | positive cases where every expected rule fired |
| `false_positives` | negative cases with any finding |
| `unexpected_rules` | extra rules fired on a positive case (noise, not failure) |
| `nondeterministic` | cases whose two runs differ (must be 0) |
| `severity_mismatches` | finding severity differs from the rule table |

## Baselines

| date | recall | neg FP | notes |
|---|---|---|---|
| 2026-10-30 (first run) | 93% (13/14) | 3/8 | tag characters in docs missed; `%`-in-string, glossary term, defensive-prompt-mention false positives |
| 2026-10-30 (after fixes) | **100% (15/15)** | **0/8** | docs/configs now also run evasion detectors; defensive-mention and comment-marker fixes; `strict=True` surfaces detector crashes instead of returning "clean" |

## Adding a case

Append to `build_cases.py` (not to `cases.jsonl` directly — encodings are generated there),
regenerate, and run. A new case that fails is the start of the next iteration, not a reason
to loosen the gate.
# Agents for Humans: When the Model Provider Dies Mid-Audit — Designing Honest Degradation

*By Weike — part 2 of our Agents for Humans build series on [CodeRisk Arcanum](https://github.com/a9320/code-risk-arcanum), a 6-agent security auditor built with Strands Agents SDK. This is a war story from real testing, with the logs to back it up.*

## The failure

Two nights before our code freeze, we ran the full six-agent audit pipeline against our poisoned demo repository. Everything worked until the attack-chain agent. Then, deep in the run, this started appearing:

```
Error code: 429 - {'error': {'message': 'Your account org-… <ak-…> is suspended
due to insufficient balance, please recharge your account or check your plan
and billing details', 'type': 'exceeded_current_quota_error'}}
```

The provider account powering our Verify and Deepen agents had run out of quota — mid-run. Seven of eight attack-chain derivations failed in a row.

Here is the part worth writing down: **the pipeline finished, and the report was complete.** Not because we got lucky — because degradation was designed, not improvised. This post is about what that design looks like in practice.

## Principle 1: a degraded item must still exist — visibly

The naive failure mode for a multi-agent pipeline is silent: a node returns `None`, the report simply lacks seven attack chains, and nobody notices that "attack chains: 1" should have been "8".

Our Deepen agent (built on a Strands `Agent` with a strict JSON structured-output contract) derives one attack chain per confirmed vulnerability, one call per item. When a call fails — parse failure, provider error, whatever — the item is **not dropped**. It becomes a deterministic placeholder chain that ships in the report:

```
### 攻击链 3 (Attack chain 3)
- Final impact: 【Deepen parse failed · manual review required】 Original hypothesis:
  [PIT-N-06 / high] docs/AGENT_GUIDE.md document poisoning…
- Remediation: (automatic chain derivation failed; verification-layer evidence
  remains valid — please derive the attack chain manually)
```

A `ChainList` counter tracks how many placeholders were emitted, and the Markdown report prints a warning block on top:

> ⚠ 7 attack chains failed automated derivation and are disclosed as placeholders — manual review required.

The placeholder also passes through a credential redaction regex, because the raw provider error contained account identifiers — a report that leaks your own API key while disclosing an outage would be a special kind of embarrassing.

## Principle 2: the judge must know *why* a source is empty

Our Arbiter agent receives three upstream artifacts — hypotheses, verification results, attack chains — and produces the final report. It found the degraded chains, and its own chain of reasoning (we log it) was delightful:

> The deepening layer failed for 7 of 8 due to infrastructure errors (429 quota) — these are infrastructure failures, not refutations. The verification verdict says the evidence remains valid. Excluding 7 confirmed findings (including 2 critical) from the final report because of an infrastructure quota error would underreport real risks.

So it kept all CONFIRMED items, synthesized their attack paths from Scout hypotheses plus verification evidence, and labeled each one "automated chain missing due to 429, manual derivation recommended."

The guarantee we were aiming for: **an empty findings list must never be ambiguous.** "Empty because nothing was confirmed" and "empty because the verifier was down" are different worlds, and the report says which one you are in. When our verification layer went fully dark in a later run, the Arbiter's report stated plainly: *"This round's empty findings are caused by verification-channel degradation, not by refuted hypotheses. Empty findings means 'no CONFIRMED items', not 'safe repository'."*

## Principle 3: every node can fall; the pipeline cannot

Each LLM node is wrapped at the orchestration layer: on failure it falls to a deterministic path — rule-baseline hypotheses, rule-based verdicts, placeholder chains, a mechanical CONFIRMED-only fallback report — and the failure is recorded into `node_errors`, which flows into the report, the summary JSON, and the Markdown disclosure block. We test this with monkeypatched total-outage scenarios: all four LLM nodes down, and the pipeline still produces a complete, honest report.

## Principle 4: degrade *loudly* — then fix the root cause

Disclosure bought us time, not excuses. The outage audit surfaced three more real defects, each now fixed:

1. **A model route that never existed.** Our factory listed `DeepSeek-V4-Pro` on a free provider. A one-call probe returned 404; an authenticated `models.list` showed the truth: only `DeepSeek-V4-Flash` exists there. Every fallback chain entry should be verified with a real call — unverified fallbacks are documentation, not engineering.
2. **Concurrency the endpoint can't serve.** The free tier rejects concurrent invocations (`503 no_available_workers`). Our per-hypothesis verifier initially used `asyncio.Semaphore(2)` — and all eight verdicts failed at once. Fixed: sequential by default, one backoff retry per item.
3. **A client timeout that doesn't fire.** The next run froze for 18 minutes on a single invoke — the configured client timeout simply never triggered on a stalled provider connection. The fix that finally held: an application-level `asyncio.wait_for` watchdog around every agent invoke, with the retry backoff parameterized. A hung provider now costs us six minutes (two attempts), not an infinite hang.

Each of these became a regression test. The suite is 54 deterministic tests, zero LLM calls, runnable via `bash verify.sh`.

## What we learned

- **Degradation is a feature you must design before the outage, not during.** Placeholder artifacts + failure counters + disclosure blocks turn "the demo broke" into "here's exactly what the tool did when infrastructure failed."
- **In security tooling, honest silence is worse than loud failure.** A report that hides a degraded verification channel is actively dangerous: it invites readers to treat "not confirmed" as "safe".
- **The disclosure narrative is competitive.** We now show the outage logs *in our demo video* on purpose. Any team can demo a green path; showing a red path that reports itself is rarer and, we think, more convincing.

## Try it

- Repository (MIT): https://github.com/a9320/code-risk-arcanum — `bash verify.sh` runs the whole proof offline
- Evidence pack with real run logs: [`evidence/`](https://github.com/a9320/code-risk-arcanum/tree/master/evidence)
- Devpost entry: https://agentsforhumans.devpost.com/

*Part 3 covers the prompt quarantine layer — how we strip invisible characters, neutralize injection triggers, and turn injection attempts into reportable evidence.*

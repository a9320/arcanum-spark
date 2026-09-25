---
deployspec:
  entry_file: app.py
---

# Arcanum · Spark（Arcanum · 星火）

**Catch the first spark before it becomes a wildfire.** Code security audit for AI-era vulnerabilities — built on the [Arcanum Prompt Injection Taxonomy](https://arcanum-sec.com/pitax) (Jason Haddix, Arcanum Information Security), packaged as an Agent Skill plus a 6-agent LLM pipeline. It runs fully local and deterministic (zero LLM), or on either of **two model setups**: a heterogeneous cloud API council, or four self-hosted llama-servers on AMD MI300X.

> **Provenance:** independent repository reworked on top of upstream [a9320/code-risk-arcanum](https://github.com/a9320/code-risk-arcanum) (MIT, `upstream` remote, import anchored at `fcfc6f7`).

CodeRisk Arcanum is among the first tools designed to detect **AI prompt injection, invisible-character smuggling, Trojan Source, AI configuration backdoors, document poisoning, and layered-encoding payloads** — attack surfaces that traditional SAST/DAST tools (Semgrep, CodeQL, Snyk) do not parse.

It ships in three layers:

1. **`codeark/` — a 6-agent audit pipeline** (Strands Agents SDK): a deterministic rule layer, semantic reconnaissance, per-hypothesis verification with bound tools, attack-chain derivation, multi-source arbiter, and deterministic report rendering. Models bind through per-stage endpoint routing — the cloud API council or the self-hosted MI300X council.
2. **`skills/ai-repo-audit/` — the deterministic PITAX layer packaged as an Agent Skill**: pure-stdlib scanner (Python ≥3.10), zero network / zero GPU, emitting JSON / SARIF 2.1.0 / Markdown reports; installable into any Agent-Skills-compatible client.
3. **`app/` — the legacy deterministic platform**: the pure-stdlib PITAX engine, FastAPI service, and Celery pipeline (powers the [live demo](https://www.modelscope.cn/studios/Weike22/code-risk-arcanum)).

![6-agent pipeline architecture — rule layer, Scout, Verify, Deepen, Arbiter, Report with heterogeneous model routing](docs/architecture-6node.png)

## One-click verification (zero LLM API calls)

> Prerequisites: Python 3.10+ with the pipeline dependencies — `pip install -r requirements.txt` (strands-agents, openai, pydantic, pytest). The script prefers a local `.venv-win` if present and falls back to your system Python otherwise.

```bash
bash verify.sh
# → deterministic test suite (84 tests, zero LLM calls)
# → dry scan of the demo repo (12 expected PITAX hits)
# → eval regression check (full expected-coverage + severity floor)
# → clean control repo currently produces zero findings on the checked control fixture (not a population-wide FP rate)
```

## 6-agent pipeline quick start (`codeark/`)

```bash
# 1. Deterministic instant scan (Agent0 rule layer only, no model calls)
python -m codeark.cli demo/vuln-demo-repo --dry

# 2. Full pipeline:
#    Agent0 (PITAX rules) → Scout (semantic-increment recon)
#    → Verify (per-hypothesis verdicts, can REFUTE)
#    → Deepen (per-item attack chains)
#    → Arbiter (heterogeneous multi-source verdict)
#    → Report (JSON / SARIF 2.1.0 / Markdown)
python test_e2e.py            # real LLMs, ~15 min with concurrency tuning, reports land in reports/

# 3. Regression-check a report against the private eval set
python eval/check_report.py --report reports/dry_eval/report.json
```

Model binding is environment-driven (`codeark/models/routing.py` + `factory.py`), no code changes needed:

- **API cloud council (default)** — four stages on four distinct provider families, each with its own endpoint / key / timeout: Scout `step-5-preview` (StepFun, with an independent fallback endpoint `gpt-5.6-luna`), Verify `Qwen3.8-Flash-Next`, Deepen `DeepSeek-V4-Flash`, Arbiter `gpt-6-sol`. Enable with the per-stage keys (`ARCA_SCOUT_PRIMARY_API_KEY`, `ARCA_VERIFY_API_KEY`, …); every field is overridable via `ARCA_<STAGE>_MODEL | BASE_URL | TIMEOUT | TOOL_FORMAT | …`.
- **MI300X local council** — `ARCA_DEPLOYMENT=local` binds all four stages to loopback llama-servers: `:8081 muse-scout` (Muse-Glimmer-30B) / `:8182 qwen-verify` (Qwen3.8-27B) / `:8083 r1-deepen` (R1-Distill-32B) / `:8084 gemma-arbiter` (Gemma4-26B-A4B). One-click provisioning below.

> Legacy single-model adapters (Step-3.7-Flash `local_step.py`, Nemotron, and the XML tool-call formats in `xml_model.py`) remain in `codeark/models/` for one-model local runs; they are not part of either current setup.

- **Loop-stage tuning** — `ARCA_VERIFY_MAX_CONCURRENCY` / `ARCA_DEEPEN_MAX_CONCURRENCY` (+ inter-call delay / invoke watchdog) cut the full e2e run from 35m42s to 15m07s.

Key engineering mechanisms:

- **Prompt quarantine layer** — every LLM prompt sees only a sanitized view: invisible/bidirectional characters stripped, injection trigger phrases neutralized into `[QUARANTINED]` markers, repository content wrapped in UNTRUSTED DATA boundaries. Raw files always reach the deterministic tools, so the evidence chain never loses bytes.
- **Heterogeneous model council** — the four stages run on four distinct model families, and the Arbiter never shares a family with the proposers: judging is decorrelated from proposing to prevent self-endorsement.
- **Severity deterministic floor** — rule-level severity is the baseline; LLMs may escalate with evidence, never downgrade.
- **Node-level degradation disclosure** — any model outage falls back to a deterministic path and is disclosed in the report (empty findings ≠ safe repository).
- **Evidence pack** — see [`evidence/`](evidence/) for real run artifacts, including model logs where agents face live injection bait and report it as data instead of obeying. Demo narrative: [`docs/DEMO-SCRIPT.md`](docs/DEMO-SCRIPT.md).

## Self-hosted local council (one-click, AMD MI300X / ROCm)

[`deploy/mi300x-oneclick.sh`](deploy/mi300x-oneclick.sh) provisions the full four-llama-server council on a fresh instance: idempotent (existing files are skipped), resumable downloads (`curl -C -`), quota-proof (writes only to `/root`, never the NFS workspace), self-healing (rebuilds llama.cpp for `gfx942` if the binary is missing), health-checks all four endpoints and reports VRAM.

```bash
curl -fsSL https://raw.githubusercontent.com/a9320/arcanum-spark/master/deploy/mi300x-oneclick.sh | bash
# → downloads 4 GGUF models (~71 GB): Muse-Glimmer-30B / Qwen3.8-27B / R1-Distill-32B / Gemma4-26B-A4B
# → builds llama.cpp (HIP, gfx942), starts scout :8081 / verify :8182 / deepen :8083 / arbiter :8084
# → run the pipeline with ARCA_DEPLOYMENT=local
```

Any CUDA/OpenAI-compatible box works the same way: start four llama-servers on those ports (or point `ARCA_<STAGE>_BASE_URL` elsewhere) and export `ARCA_DEPLOYMENT=local`.

## Detection rules (PITAX, aligned with taxonomy v1.6.1)

| Rule | Name | Severity | CWE | MITRE ATLAS | CVE |
|------|------|----------|-----|-------------|-----|
| PIT-E-23 | Invisible Text | HIGH | - | AML.T0051.001 | - |
| PIT-E-54 | Trojan Source | HIGH | - | - | CVE-2021-42574 |
| PIT-T-46 | Agent Instruction-File Injection | CRITICAL | CWE-77 | AML.T0051.001 | CVE-2025-53773 |
| PIT-T-51 | Instruction Override | HIGH | - | AML.T0051.001 | - |
| PIT-N-06 | Document / File Upload | HIGH | - | AML.T0051.001 | - |
| PIT-E-07 | Base64 Encoding | MEDIUM | - | AML.T0051.001 | - |
| PIT-E-14 | Cipher (ROT13) | MEDIUM | - | AML.T0051.001 | - |
| PIT-E-36 | Reverse | MEDIUM | - | AML.T0051.001 | - |
| PIT-E-57 | Layered Encoding | CRITICAL | - | AML.T0051.001 | - |

> CWE/ATLAS mappings are annotated only where the official taxonomy defines them; AML.T0051.001 = Indirect LLM Prompt Injection.

## Project structure

```
skills/                 # ai-repo-audit — PITAX deterministic layer packaged as an Agent Skill
deploy/                 # mi300x-oneclick.sh — one-click local-council deployment (idempotent, ROCm)
codeark/                # 6-agent pipeline (Strands Agents SDK)
├── agents/             # agent0_pitax / scout / verify / deepen / arbiter / report
├── graph/              # pipeline orchestration + prompt quarantine layer
├── models/             # per-stage endpoint routing + provider factory + local adapters + Pydantic schemas
├── pitax/              # PITAX detection engine (imported by Agent0 and the ai-repo-audit skill)
├── memory/             # pluggable memory layer (local + DynamoDB): past false-positive patterns re-injected into Scout prompts
├── tools/              # pitax_scan / static_scan / taint_flow / dep_scan (bound no-arg tools)
└── tests/              # deterministic test suite (84 tests, zero LLM calls)
app/                    # legacy platform
├── pitax/              # PITAX detection engine (rules/detectors/scanner/CLI/SARIF, pure stdlib)
├── agents/             # Agent 0: input sanitizer / PITAX pre-scan
├── tasks.py            # Celery tasks (Agent 0 → Agent 1-4 pipeline)
├── prompt_guard.py     # system-prompt vault + output guardrail
├── main.py             # FastAPI entry (analyze / webhook / zip upload / direct_upload)
engine/                 # built-in classic vulnerability engines (static / taint / deps / LLM semantics)
demo/                   # demo repo generator + vuln-demo-repo (12 PITAX hits) + clean-repo (FP control)
eval/                   # private regression set (expected.json) + deterministic checker
evidence/               # real run artifacts: reports, anti-injection log quotes, verify output
reports/                # generated audit reports & run artifacts (JSON / SARIF / Markdown)
docs/                   # architecture, demo script, sprint plan, submission checklist
tests/                  # legacy test suite (57 tests)
```

## Legacy platform pipeline (Agent 0–4)

```
Agent 0 (PITAX pre-scan) → Agent 1 (static) → Agent 2 (semantic) → Agent 3 (verify) → Agent 4 (report)
       └─ AI-era findings (prompt injection / Unicode / Trojan Source / config backdoors / docs / encoding)
          merge into the report's ai_findings section
       └─ Agent 4 output passes an OutputGuardrail sanitizer (system-prompt leak prevention)
```

Run it locally (no GPU required):

```bash
# Start Redis (task queue only)
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 1: API service
uvicorn app.main:app --port 8000

# Terminal 2: Celery worker
celery -A app.tasks worker --loglevel=info -P solo

# Terminal 3: submit a direct_upload analysis
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"source":"direct_upload","files":[{"path":"src/app.py","content":"import os\ndef run(cmd):\n    os.system(cmd)\n"}]}'

# Poll progress & fetch the report
curl -H "Authorization: Bearer dev-key-change-in-production" \
  http://localhost:8000/api/v1/tasks/<task_id>
```

**Degradation behavior** (no GPU / optional deps missing):

| Agent | Dependency | Behavior without it |
|-------|------------|---------------------|
| Agent 0 PITAX | none (pure stdlib) | fully functional ✅ |
| Agent 1 static | rich | fully functional ✅ (pure rule matching) |
| Agent 1b taint | none | fully functional ✅ |
| Agent 1c deps | none | fully functional ✅ |
| Agent 2 semantic | local LLM (llama.cpp / OpenAI-compatible) | skipped (logged) |
| Agent 3 deep verify | local LLM | keeps original findings, proceeds to report |
| Agent 4 report | Nutrient DWS (PDF only) | JSON/SARIF fully functional ✅ |

> The full Agent 0–4 pipeline is demonstrable with zero GPU (Agents 2/3 degrade gracefully). With an AMD GPU, point `CODERISK_MODEL_PATH` at a GGUF model to enable semantic analysis.

## Documentation

- [Architecture & sprint plan](docs/SPRINT-0914-PLAN.md)
- [Demo video script & pitch narrative](docs/DEMO-SCRIPT.md)
- [Hackathon submission checklist](docs/HACKATHON-SUBMISSION-CHECKLIST.md)
- [PITAX integration notes](docs/PITAX.md) · [Roadmap](docs/ROADMAP.md) · [Competition positioning](docs/COMPETITION.md)

## Acknowledgements

- **koljiu** — for uploading our demo video to YouTube on our behalf. This hackathon submission would not have been possible without your help.
- The Agents for Humans hackathon organizers — for accommodating participants from network-restricted regions.

## License & attribution

- Code: original work for this project, MIT licensed (see [LICENSE](LICENSE))
- PITAX taxonomy: Arcanum Prompt Injection Taxonomy v1.6.1, by Jason Haddix / Arcanum Information Security; this project is a derived implementation under CC BY 4.0
- References: OWASP LLM Top 10 / MITRE ATLAS / the Arcanum seven-pillar methodology

---
*Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix, Arcanum Information Security (arcanum-sec.com). CC BY 4.0.*

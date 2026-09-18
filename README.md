---
deployspec:
  entry_file: app.py
---

# CodeRisk Arcanum

**A code security platform for AI-era vulnerabilities** — built on the [Arcanum Prompt Injection Taxonomy](https://arcanum-sec.com/pitax) (Jason Haddix, Arcanum Information Security).

> 🏆 **Contest build (2026 Chuanzhibei, track 10041):** contest-period development happens in [a9320/code-risk-arcanum-contest](https://github.com/a9320/code-risk-arcanum-contest) — work title *CodeRisk·ZhiJian* (智鉴). This repository remains the MIT open-source baseline of record.

CodeRisk Arcanum is among the first tools designed to detect **AI prompt injection, invisible-character smuggling, Trojan Source, AI configuration backdoors, document poisoning, and layered-encoding payloads** — attack surfaces that traditional SAST/DAST tools (Semgrep, CodeQL, Snyk) do not parse.

It ships in two layers:

1. **`codeark/` — a 6-agent audit pipeline** (Strands Agents SDK + heterogeneous domestic-model council): a deterministic rule layer, semantic reconnaissance, per-hypothesis verification with bound tools, attack-chain derivation, multi-source arbiter, and deterministic report rendering.
2. **`app/` — the legacy deterministic platform**: the pure-stdlib PITAX engine, FastAPI service, and Celery pipeline (powers the [live demo](https://www.modelscope.cn/studios/Weike22/code-risk-arcanum)).

![6-agent pipeline architecture — rule layer, Scout, Verify, Deepen, Arbiter, Report with heterogeneous model routing](docs/architecture-6node.png)

## One-click verification (zero LLM API calls)

> Prerequisites: Python 3.10+ with the pipeline dependencies — `pip install -r requirements.txt` (strands-agents, openai, pydantic, pytest). The script prefers a local `.venv-win` if present and falls back to your system Python otherwise.

```bash
bash verify.sh
# → deterministic test suite (54 tests)
# → dry scan of the demo repo (12 expected PITAX hits)
# → eval regression check (full expected-coverage + severity floor)
# → clean control repo FP=0 check
```

## 6-agent pipeline quick start (`codeark/`)

```bash
# 1. Deterministic instant scan (Agent0 rule layer only, no model calls)
python -m codeark.cli demo/vuln-demo-repo --dry

# 2. Full pipeline:
#    Agent0 (PITAX rules) → Scout (GLM-5.3, semantic-increment recon)
#    → Verify (DeepSeek-V4-Flash, per-hypothesis verdicts, can REFUTE)
#    → Deepen (per-item attack chains)
#    → Arbiter (GLM-5.3, heterogeneous multi-source verdict)
#    → Report (JSON / SARIF 2.1.0 / Markdown)
python test_e2e.py            # real LLMs, 10-30 min, reports land in reports/

# 3. Regression-check a report against the private eval set
python eval/check_report.py --report reports/dry_eval/report.json
```

Key engineering mechanisms:

- **Prompt quarantine layer** — every LLM prompt sees only a sanitized view: invisible/bidirectional characters stripped, injection trigger phrases neutralized into `[QUARANTINED]` markers, repository content wrapped in UNTRUSTED DATA boundaries. Raw files always reach the deterministic tools, so the evidence chain never loses bytes.
- **Heterogeneous model council** — Scout/Arbiter run on GLM-5.3 while Verify/Deepen run on DeepSeek: proposing and judging are decorrelated across model families to prevent self-endorsement.
- **Severity deterministic floor** — rule-level severity is the baseline; LLMs may escalate with evidence, never downgrade.
- **Node-level degradation disclosure** — any model outage falls back to a deterministic path and is disclosed in the report (empty findings ≠ safe repository).
- **Evidence pack** — see [`evidence/`](evidence/) for real run artifacts, including model logs where agents face live injection bait and report it as data instead of obeying. Demo narrative: [`docs/DEMO-SCRIPT.md`](docs/DEMO-SCRIPT.md).

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
codeark/                # 6-agent pipeline (Strands Agents SDK)
├── agents/             # agent0_pitax / scout / verify / deepen / arbiter / report
├── graph/              # pipeline orchestration + prompt quarantine layer
├── models/             # model factory (GLM / Kimi / DeepSeek / Qwen routing) + Pydantic schemas
├── tools/              # pitax_scan / static_scan / taint_flow / dep_scan (bound no-arg tools)
└── tests/              # deterministic test suite (54 tests, zero LLM calls)
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
docs/                   # architecture, demo script, sprint plan, submission checklist
tests/                  # legacy test suite
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
- PITAX taxonomy: **CC BY 4.0** (Arcanum Information Security / Jason Haddix)
- References: OWASP LLM Top 10 / MITRE ATLAS / the Arcanum seven-pillar methodology

---
*Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix, Arcanum Information Security (arcanum-sec.com). CC BY 4.0.*

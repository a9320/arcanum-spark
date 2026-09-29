# Threat Model

Status: local engineering baseline, 2026-09-29. This document records the
security boundary that the repository currently implements. It is not a claim
that deployment, infrastructure, or residual risks are eliminated.

## Scope and Assets

In scope:

- Uploaded source code, local repository paths, and repository-derived prompts.
- API keys, webhook secrets, model endpoint credentials, and system prompts.
- Redis task metadata, task status, generated JSON/SARIF/PDF reports, and report
  signatures.
- LLM stage inputs and intermediate Scout/Verify/Deepen/Arbiter results.
- The deterministic PITAX findings and their decoded-payload evidence.

Security properties sought:

1. Untrusted repository text must not become an instruction to an audit agent.
2. One API tenant must not download another tenant's report.
3. Uploaded or local source paths must not escape their allowed workspace.
4. A report must disclose degradation and must not silently become an empty safe
   result.
5. Credentials and system prompts must not be written into reports or logs.

## Trust Boundaries

```text
Client / GitHub webhook
        |
        | authenticated API request or signed webhook
        v
FastAPI API process ---- Redis task metadata/status ---- Celery worker
        |                                          |
        | report access checks                       | source preparation
        v                                          v
Report files                         temporary or /repos read-only source
        |
        v
LLM prompts and intermediate model outputs
        |
        v
Deterministic report renderer and output guardrail
```

Repository files and model outputs are untrusted data at every boundary. The
prompt quarantine layer sanitizes content for LLM prompts, while deterministic
scanners retain raw bytes for evidence. The renderer generates files but does
not publish them to an external channel.

## Threat Surfaces and Current Controls

### API and report access

- API routes require the configured bearer key through `verify_api_key()`.
- Report metadata stores a short hash of the requesting authorization value;
  report and PDF download compare that hash before serving the file.
- The former unauthenticated `/reports` static mount is removed. Report access
  goes through authenticated API routes.
- Compose no longer publishes Redis to the host. The API and worker use the
  internal Redis service.

Residual risk: the default development key remains a deployment concern outside
Compose. Production deployments must set a strong `CODERISK_API_KEY`, use TLS,
and protect Redis and report storage at the platform layer.

### GitHub webhook

- The webhook requires `X-Hub-Signature-256`.
- It returns `503` when `GITHUB_WEBHOOK_SECRET` is not configured instead of
  accepting an unsigned event.
- A configured secret is compared with a constant-time comparison.

Residual risk: webhook replay protection and event-id deduplication are not
implemented in this repository. Deployments should place the endpoint behind
provider replay controls or add an event timestamp/id policy before exposure.

### CORS and browser clients

- Allowed origins are read from the explicit `CODERISK_CORS_ORIGINS` list.
- Credentialed cross-origin requests are disabled.

Residual risk: an operator can still configure an overly broad origin list. The
configuration is deployment policy, not an allowlist discovered automatically.

### Uploaded ZIPs and local paths

- Direct uploads enforce file-count, per-file, and total-size limits.
- ZIP extraction checks decompressed size, member count, and path traversal before
  extraction.
- Local scans require a normalized path under `/repos/` and reject `..` path
  components.
- `_prepare_code()` returns an ownership flag. Cleanup removes only temporary
  directories created by the task; a user-owned local source directory is never
  recursively deleted.
- Compose mounts `/repos` read-only.

Residual risk: archive expansion and filesystem races still depend on the host
filesystem and container privileges. Run the worker with least privilege and
keep report/upload directories outside sensitive host paths.

### Repository prompt injection and model output

- Prompt quarantine strips invisible/Bidi characters and neutralizes known
  injection trigger patterns before LLM prompt rendering.
- Raw repository content remains available only to deterministic tools, so
  evidence is not silently changed by prompt sanitization.
- Inter-agent JSON is rendered as untrusted data sections before being passed to
  another model.
- Scout, Verify, Deepen, and Arbiter failures are recorded as node errors and
  use disclosed deterministic fallbacks where implemented.
- The severity floor prevents an LLM from downgrading a deterministic rule
  severity.
- Reports pass through the output guardrail before the final SHA-256 signature
  is calculated.

Residual risk: quarantine is pattern-based and cannot prove that every future
prompt-injection form is neutralized. Model endpoints, provider logs, and token
usage are outside this repository's trust boundary; use local endpoints for
sensitive code and avoid sending secrets as source material.

### Network and CVE lookup

- CVE lookup uses a local SQLite database by default.
- The NVD API fallback is disabled unless `CODERISK_ALLOW_NVD=1` is explicitly
  set.
- The explicit switch must be treated as an outbound-data policy decision.

Residual risk: enabling the fallback sends CWE query information to NVD and
introduces availability and privacy dependencies. Keep it disabled for offline
or confidential scans.

### Credentials, memory, and reports

- Endpoint API keys are excluded from endpoint configuration `repr` output and
  error text is redacted by the routing helper.
- The memory service is opt-in through an explicit pipeline argument. When used,
  Scout receives historical constraints only as a quarantined prompt suffix;
  Verify observations are persisted under a stable type/path key rather than
  raw evidence or prompt text.
- The single-agent ablation explicitly disables the deterministic rule layer
  and records that fact in report metadata.

Residual risk: local memory JSON and model/provider logs remain sensitive state.
Use a protected path and retention policy. The memory backend does not provide
multi-tenant authorization by itself.

## Out of Scope / Deferred Controls

- Rate limiting, account lifecycle, and production TLS termination.
- Redis ACLs/encryption and platform-level volume encryption.
- Webhook replay/idempotency controls.
- Callback URL delivery: the API accepts a callback field, but delivery is not
  implemented; callers must not treat it as a completion guarantee.
- Independent external truth labels for semantic findings. The current local
  experiments distinguish deterministic rule hits from model verdicts; an
  independently labeled corpus is a separate M8 workstream.
- Runtime Laya gate activation before the hard-exam v2 DSW decision gate passes.

## Review Triggers

Revisit this document when any of the following changes:

- A new upload source, report delivery channel, or webhook event type is added.
- A model provider, prompt boundary, tool binding, or memory backend changes.
- `CODERISK_ALLOW_NVD`, CORS, API-key, or container volume policy changes.
- The DSW three-arm ablation or gate v1 is enabled in a production path.

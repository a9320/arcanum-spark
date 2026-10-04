# Third-Party Notices

## Arcanum Prompt Injection Taxonomy (PITAX) v1.6.1
- Copyright (c) Jason Haddix, Arcanum Information Security
- License: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
- Reference: https://arcanum-sec.com/pitax
- Used by: rule IDs aligned with the public taxonomy in `app/pitax/` and `codeark/`

## Bundled dependencies (pip)
- strands-agents — Apache-2.0
- openai — Apache-2.0
- pydantic — MIT
- fastapi — MIT
- celery / redis — BSD-3-Clause
- gradio — Apache-2.0

## M8 external truth datasets (consumed in place, not rehosted)
Per `docs/M8-CTF-TRUTH.md`: evaluation scripts read task data from the upstream
repositories directly; no dataset or benchmark code is copied into this project.
- NYU CTF Bench (NYU-LLM-CTF/NYU_CTF_Bench, NeurIPS 2024) — benchmark code GPL-2.0;
  this project consumes only the task data distributed with the upstream repo.
- cybench (andyzorigin/cybench, Stanford) — Apache-2.0; secondary source, same
  in-place consumption.

## Laya fine-tuned checkpoints (GitHub Release assets)
**Base model chain (verified 2026-10-03):**
- Base encoder: `answerdotai/ModernBERT-base` (HF) — Apache-2.0
- Base model: `convaiinnovations/laya` (HF), `typed-decisions` subset — Apache-2.0
- Head re-init & fine-tune: this project (`vendor/rl_agent_api.py` inference shim is
  pure stdlib + numpy)

**Training data provenance (all first-party or permissively licensed):**
1. Pipeline-produced evidence: `records_r*.train.jsonl` rows derive from this
   project's own 6-agent audit runs (CONFIRMED hypotheses + deterministic tool
   bindings) over public demo/test repositories — first-party data.
2. Synthetic contrast pairs: TWIN/BOUND/PARA/REDUN/ECHO batches
   (`eval/build_r*.py`) are fully self-constructed benign/malicious mirrors —
   first-party data, no third-party text.
3. PITAX-aligned labels: rule IDs and taxonomy mapping reference the Arcanum
   PITAX v1.6.1 taxonomy (CC BY 4.0, attribution above) — labels/metadata only,
   no taxonomy text redistributed.

**No leaked, scraped, or unlicensed third-party datasets are used in any
checkpoint's training data.** The two published checkpoints (`laya-r5`,
`laya-r6`; see GitHub Release `laya-checkpoints`) are derivatives of the
Apache-2.0 base under the project's MIT license, consistent with the upstream
license terms.

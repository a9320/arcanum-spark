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

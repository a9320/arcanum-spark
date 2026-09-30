# Ablation Summary

> REFUTED counts are model verdicts, not independently labeled false-positive rates. Missing usage or timing stays `null`.

| Arm | Agent | Baseline | Final | Confirmed | Semantic increment | Refuted | Uncertain | Seconds | Tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rules | agent0 | 14 | 0 | 0 | 0 | 0 | 0 | null | null |
| single_agent | single_agent | 0 | 8 | 0 | 8 | 0 | 0 | 200.502 | null |
| six_agent | six_agent | 14 | 13 | 6 | 6 | 0 | 0 | null | null |

# Ablation Summary

> REFUTED counts are model verdicts, not independently labeled false-positive rates. Missing usage or timing stays `null`.

| Arm | Agent | Baseline | Final | Confirmed | Semantic increment | Refuted | Uncertain | Seconds | Tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rules | agent0 | 14 | 0 | 0 | 0 | 0 | 0 | null | null |
| single_agent | single_agent | 0 | 7 | 0 | 7 | 0 | 0 | 159.887 | null |
| six_agent | six_agent | 14 | 9 | 2 | 2 | 0 | 3 | null | null |

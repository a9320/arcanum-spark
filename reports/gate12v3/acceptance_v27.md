# Gate e2e Acceptance

> baseline=`/mnt/workspace/runs/20261002-gate12v3/nogate_v27/report.json` — verdict: **ACCEPT** (P1 reorder-only / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | P4 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya_v27 | laya | ✅ | ✅ | ✅ | ✅ | 4(4) | 11(11) | 5 | 1 | 652.934 | PASS |
| det_v27 | deterministic | ✅ | ✅ | ✅ | ✅ | 4(4) | 11(11) | 5 | 1 | 676.635 | PASS |

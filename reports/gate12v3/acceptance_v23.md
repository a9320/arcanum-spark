# Gate e2e Acceptance

> baseline=`/mnt/workspace/runs/20261002-gate12v3/nogate_v23/report.json` — verdict: **ACCEPT** (P1 reorder-only / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | P4 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya_v23 | laya | ✅ | ✅ | ✅ | ✅ | 4(4) | 11(11) | 6 | 2 | 1067.504 | PASS |
| det_v23 | deterministic | ✅ | ✅ | ✅ | ✅ | 4(4) | 11(11) | 6 | 2 | 1075.84 | PASS |

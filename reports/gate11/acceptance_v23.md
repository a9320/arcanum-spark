# Gate e2e Acceptance

> baseline=`/mnt/workspace/runs/20261001-gate11/nogate_v23/report.json` — verdict: **ACCEPT** (P1 reorder-only / P2 no-fallback / P3 quality-floor; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | ---: | --- |
| laya_v23 | laya | ✅ | ✅ | ✅ | 3(3) | 10(10) | 5 | 1 | 1563.218 | PASS |
| det_v23 | deterministic | ✅ | ✅ | ✅ | 4(3) | 11(10) | 5 | 1 | 1167.364 | PASS |

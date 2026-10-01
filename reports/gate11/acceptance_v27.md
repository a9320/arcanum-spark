# Gate e2e Acceptance

> baseline=`/mnt/workspace/runs/20261001-gate11/nogate_v27/report.json` — verdict: **REJECT** (P1 reorder-only / P2 no-fallback / P3 quality-floor; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | ---: | --- |
| laya_v27 | laya | ✅ | ✅ | ❌ | 4(6) | 11(13) | 5 | 1 | 1140.283 | FAIL |
| det_v27 | deterministic | ✅ | ✅ | ✅ | 6(6) | 13(13) | 7 | 1 | 1627.487 | PASS |

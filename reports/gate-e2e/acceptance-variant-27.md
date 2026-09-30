# Gate e2e Acceptance

> baseline=`/mnt/workspace/runs/20260928-variant-27/variant-27/e2e_report.json` — verdict: **REJECT** (P1 reorder-only / P2 no-fallback / P3 quality-floor; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | ---: | --- |
| variant-27_gate_laya | laya | ✅ | ✅ | ✅ | 5(5) | 12(12) | 5 | 0 | 881.368 | PASS |
| variant-27_gate_det | deterministic | ✅ | ✅ | ❌ | 3(5) | 11(12) | 5 | 0 | 667.628 | FAIL |

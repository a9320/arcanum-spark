# Gate e2e Acceptance

> baseline=`/mnt/workspace/runs/20260928-variant-23/variant-23/e2e_report.json` — verdict: **REJECT** (P1 reorder-only / P2 no-fallback / P3 quality-floor; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | ---: | --- |
| variant-23_gate_laya | laya | ✅ | ✅ | ❌ | 3(4) | 10(11) | 6 | 1 | 1434.699 | FAIL |
| variant-23_gate_det | deterministic | ✅ | ✅ | ✅ | 4(4) | 11(11) | 6 | 2 | 2032.799 | PASS |

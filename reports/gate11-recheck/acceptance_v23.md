# Gate e2e Acceptance

> baseline=`reports\gate11\nogate_v23\report.json` — verdict: **REJECT** (P1 reorder-only / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | P4 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya_v23 | laya | ✅ | ✅ | ✅ | ❌ | 3(3) | 10(10) | 5 | 1 | 1563.218 | FAIL |
| det_v23 | deterministic | ✅ | ✅ | ✅ | ✅ | 4(3) | 11(10) | 5 | 1 | 1167.364 | PASS |
> laya_v23: 基线 CONFIRMED 未覆盖键: H3

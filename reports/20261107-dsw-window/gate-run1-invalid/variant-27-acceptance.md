# Gate e2e Acceptance

> baseline=`reports/variant-27_gate_laya/e2e_report.json` — verdict: **REJECT** (P1/P1′ reorder-or-subset-integrity / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage / P6 rule-layer preservation[structural]; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1/P1′ | P2 | P3 | P4 | P6 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| variant-27-arm0-off | laya | ✅ | ❌ | ✅ | ✅ | – | 5(5) | 12(12) | 5 | 0 | 4.194 | FAIL |
| variant-27-arm1-structural | laya | ✅ | ❌ | ✅ | ✅ | – | 5(5) | 12(12) | 5 | 0 | 4.258 | FAIL |

# Gate e2e Acceptance

> baseline=`reports/v12-fp/pandas-e2e-gate/report.json` — verdict: **REJECT** (P1/P1′ reorder-or-subset-integrity / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage / P6 rule-layer preservation[structural]; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1/P1′ | P2 | P3 | P4 | P6 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pandas-arm0-off | laya | ✅ | ❌ | ✅ | ✅ | – | 3(0) | 3(0) | 3 | 0 | 4.367 | FAIL |
| pandas-arm1-structural | laya | ✅ | ❌ | ✅ | ✅ | – | 3(0) | 3(0) | 3 | 0 | 4.462 | FAIL |

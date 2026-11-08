# Gate e2e Acceptance

> baseline=`reports/variant-27_gate_laya/e2e_report.json` — verdict: **REJECT** (P1/P1′ reorder-or-subset-integrity / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage / P6 rule-layer preservation[structural]; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1/P1′ | P2 | P3 | P4 | P6 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| variant-27-arm0-off | laya | ✅ | ✅ | ❌ | ❌ | – | 4(5) | 11(12) | 5 | 0 | 185.869 | FAIL |
| variant-27-arm1-structural | laya | ✅ | ✅ | ❌ | ❌ | ✅ | 4(5) | 11(12) | 5 | 0 | 210.447 | FAIL |
> variant-27-arm0-off: 基线 CONFIRMED 未覆盖键: H5
> variant-27-arm1-structural: 基线 CONFIRMED 未覆盖键: H5

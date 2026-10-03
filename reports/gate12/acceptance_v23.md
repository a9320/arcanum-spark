# Gate e2e Acceptance

> baseline=`reports/gate11/nogate_v23/report.json` — verdict: **REJECT** (P1 reorder-only / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | P4 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya_v23 | laya | ✅ | ✅ | ❌ | ❌ | 2(3) | 9(10) | 6 | 2 | 1374.523 | FAIL |
| det_v23 | deterministic | ✅ | ✅ | ❌ | ❌ | 2(3) | 9(10) | 6 | 2 | 1108.576 | FAIL |
> laya_v23: 基线 CONFIRMED 未覆盖键: H5
> det_v23: 基线 CONFIRMED 未覆盖键: H5

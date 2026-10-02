# Gate e2e Acceptance

> baseline=`reports\gate11\nogate_v27\report.json` — verdict: **REJECT** (P1 reorder-only / P2 no-fallback / P3 quality-floor / P4 confirmed-coverage; REFUTED is a model verdict, not an FP rate)

| Arm | Backend | P1 | P2 | P3 | P4 | Confirmed(base) | Final(base) | Verify req | Protected | Seconds | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya_v27 | laya | ✅ | ✅ | ❌ | ❌ | 4(6) | 11(13) | 5 | 1 | 1140.283 | FAIL |
| det_v27 | deterministic | ✅ | ✅ | ✅ | ❌ | 6(6) | 13(13) | 7 | 1 | 1627.487 | FAIL |
> laya_v27: 基线 CONFIRMED 未覆盖键: H2, H6
> det_v27: 基线 CONFIRMED 未覆盖键: H2

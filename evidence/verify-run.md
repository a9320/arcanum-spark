
==== 1/4 确定性测试套件（无 LLM） ====
✅ PASS: 确定性测试全绿（详见 /tmp/verify_pytest.log）

==== 2/4 漏洞仓确定性秒扫（dry-run，12 条预期命中） ====
✅ PASS: demo 扫描完成（reports/verify/report.json）

==== 3/4 eval 回归校验（预期检出全覆盖 + severity 底线） ====
agent0: 12 命中 / 定稿: 7 条
  [PASS] 预期检出全覆盖，无降级
✅ PASS: 预期检出表校验

==== 4/4 干净仓误报检查（FP=0） ====
  [PASS] 干净仓 FP=0
✅ PASS: 干净仓 FP=0

==== 结果: 4 通过 / 0 失败 ====

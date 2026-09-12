#!/usr/bin/env bash
# CodeRisk Arcanum — 评委一键验证（全确定性，零 LLM API 调用）
# 用法: bash verify.sh
set -uo pipefail
cd "$(dirname "$0")"

PY=".venv-win/Scripts/python.exe"
[ -x "$PY" ] || PY="python"

pass=0; fail=0
step() { echo; echo "==== $1 ===="; }
check() { if [ "$1" -eq 0 ]; then echo "✅ PASS: $2"; pass=$((pass+1)); else echo "❌ FAIL: $2"; fail=$((fail+1)); fi; }

step "1/4 确定性测试套件（无 LLM）"
"$PY" -m pytest codeark/tests/ -q \
  --ignore=codeark/tests/test_model_connect.py \
  --ignore=codeark/tests/test_scout_loop.py \
  --ignore=codeark/tests/test_scout_loop_v2.py >/tmp/verify_pytest.log 2>&1
check $? "确定性测试全绿（详见 /tmp/verify_pytest.log）"

step "2/4 漏洞仓确定性秒扫（dry-run，12 条预期命中）"
"$PY" -m codeark.cli demo/vuln-demo-repo --dry --formats json --out reports/verify >/tmp/verify_scan.log 2>&1
check $? "demo 扫描完成（reports/verify/report.json）"

step "3/4 eval 回归校验（预期检出全覆盖 + severity 底线）"
"$PY" eval/check_report.py --report reports/verify/report.json
check $? "预期检出表校验"

step "4/4 干净仓误报检查（FP=0）"
"$PY" -m codeark.cli demo/clean-repo --dry --formats json --out reports/verify_clean >/dev/null 2>&1
"$PY" eval/check_report.py --report reports/verify_clean/report.json --clean
check $? "干净仓 FP=0"

echo
echo "==== 结果: $pass 通过 / $fail 失败 ===="
[ "$fail" -eq 0 ]

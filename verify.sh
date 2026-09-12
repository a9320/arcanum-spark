#!/usr/bin/env bash
# CodeRisk Arcanum — 评委一键验证（全确定性，零 LLM API 调用）
# 用法: bash verify.sh
set -uo pipefail
cd "$(dirname "$0")"

PY=".venv-win/Scripts/python.exe"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"

pass=0; fail=0
step() { echo; echo "==== $1 ===="; }
check() { if [ "$1" -eq 0 ]; then echo "✅ PASS: $2"; pass=$((pass+1)); else echo "❌ FAIL: $2"; fail=$((fail+1)); fi; }

step "1/4 Deterministic test suite (no LLM)"
"$PY" -m pytest codeark/tests/ -q \
  --ignore=codeark/tests/test_model_connect.py \
  --ignore=codeark/tests/test_scout_loop.py \
  --ignore=codeark/tests/test_scout_loop_v2.py >/tmp/verify_pytest.log 2>&1
check $? "All deterministic tests green (log: /tmp/verify_pytest.log)"

step "2/4 Vulnerable-repo deterministic scan (dry-run, 12 expected hits)"
"$PY" -m codeark.cli demo/vuln-demo-repo --dry --formats json --out reports/verify >/tmp/verify_scan.log 2>&1
check $? "Demo scan done (reports/verify/report.json)"

step "3/4 Eval regression check (full expected coverage + severity floor)"
"$PY" eval/check_report.py --report reports/verify/report.json
check $? "Expected-detection table verified"

step "4/4 Clean-repo false-positive check (FP=0)"
"$PY" -m codeark.cli demo/clean-repo --dry --formats json --out reports/verify_clean >/dev/null 2>&1
"$PY" eval/check_report.py --report reports/verify_clean/report.json --clean
check $? "Clean repo FP=0"

echo
echo "==== Result: $pass passed / $fail failed ===="
[ "$fail" -eq 0 ]

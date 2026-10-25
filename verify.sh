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

step "1/5 Explicit test count"
"$PY" scripts/test_count.py >/tmp/verify_count.log 2>&1
check $? "Test count collected from codeark/tests + tests (log: /tmp/verify_count.log)"

step "2/5 Deterministic test suite (no LLM)"
# test_engine_integration.py 保持显式排除（口径稳定）：该文件 import
# app.tasks → 需要 redis+celery，engine 模块另需 rich——最小验证环境不装
# 这些重型依赖（CI 侧理由见 .github/workflows/ci.yml 头注；10-25 审计
# A-F2 校正：此前"并不需要 Redis/rich"的注释与事实不符）。
"$PY" -m pytest -c codeark/pyproject.toml codeark/tests tests -q \
  --ignore=tests/test_engine_integration.py >/tmp/verify_pytest.log 2>&1
check $? "All deterministic tests green (log: /tmp/verify_pytest.log)"

step "3/5 Vulnerable-repo deterministic scan (dry-run, 12 expected hits)"
"$PY" -m codeark.cli demo/vuln-demo-repo --dry --formats json --out reports/verify >/tmp/verify_scan.log 2>&1
check $? "Demo scan done (reports/verify/report.json)"

step "4/5 Eval regression check (full expected coverage + severity floor)"
"$PY" eval/check_report.py --report reports/verify/report.json
check $? "Expected-detection table verified"

step "5/5 Clean-repo false-positive check (FP=0)"
"$PY" -m codeark.cli demo/clean-repo --dry --formats json --out reports/verify_clean >/dev/null 2>&1
"$PY" eval/check_report.py --report reports/verify_clean/report.json --clean
check $? "Clean repo FP=0"

echo
echo "==== Result: $pass passed / $fail failed ===="
[ "$fail" -eq 0 ]

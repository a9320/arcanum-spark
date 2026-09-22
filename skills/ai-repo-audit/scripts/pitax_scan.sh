#!/usr/bin/env bash
# ai-repo-audit 确定性扫描入口（SKILL.md 路由表指向本脚本）。
# 用法: ./pitax_scan.sh <repo-path> [--format json|sarif|md] [--out 文件]
# 全离线、只读、零 LLM。底层由 skills/ai-repo-audit/scripts/pitax_scan.py 实现。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 探测真实可用的 Python（Windows 上 python3 常是 Microsoft Store 桩，静默无输出）
pick_python() {
    local candidates=()
    [ -n "${PYTHON:-}" ] && candidates+=("$PYTHON")
    candidates+=(python3 python py)
    local c
    for c in "${candidates[@]}"; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c "print(1)" 2>/dev/null | grep -q 1; then
            echo "$c"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(pick_python)" || {
    echo "错误：未找到可用的 Python（≥3.10）。请安装 Python 或设置 PYTHON 环境变量。" >&2
    exit 127
}

exec "$PYTHON_BIN" "$SCRIPT_DIR/pitax_scan.py" "$@"
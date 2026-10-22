#!/usr/bin/env python3
"""交互式生成 .env — 本地委员会 / 云端 API / 纯确定性（纯标准库）。

用法:
  python scripts/setup_config.py                     # 交互式选择模式
  python scripts/setup_config.py --mode local
  python scripts/setup_config.py --mode cloud
  python scripts/setup_config.py --mode deterministic
  python scripts/setup_config.py --mode local --out .env.local --force

规则:
  - 目标文件已存在时拒绝覆盖（除非 --force）；
  - 云端密钥用 getpass 输入：不回显、不落日志、不打印；
  - 非交互环境（无 TTY）且未给 --mode 时，默认 local。
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

LOCAL_TEMPLATE = """# Arcanum Spark — 本地委员会（MI300X/DGX，五 llama-server：四阶段 + verify 热备）
ARCA_DEPLOYMENT=local
# 阶段默认端点（factory 内置；可用 ARCA_<STAGE>_BASE_URL / _MODEL 覆盖）:
#   scout :8081 muse-scout | verify :8085 gpt-oss-verify |
#   deepen :8083 r1-deepen | arbiter :8084 gemma-arbiter | 热备 :8182 qwen-verify
# verify 并发=1（2026-10-21 拍板：~29k token 证据包需独占上下文窗口）
ARCA_VERIFY_MAX_CONCURRENCY=1
"""

CLOUD_HEADER = """# Arcanum Spark — 云端 API 委员会
# 每阶段至少填一个 key；base_url / model 缺省走 factory 内置预设，
# 可用 ARCA_<STAGE>_BASE_URL / ARCA_<STAGE>_MODEL 覆盖。
# 最小配置：四个阶段可全部指向同一个 OpenAI 兼容端点（同一 key / base_url），
# 以可用性优先；要恢复异构委员会时再逐阶段覆盖即可。
"""

STAGE_KEYS = [
    ("ARCA_SCOUT_PRIMARY_API_KEY", "Scout 主端点"),
    ("ARCA_SCOUT_FALLBACK_API_KEY", "Scout 回退端点（可留空）"),
    ("ARCA_VERIFY_API_KEY", "Verify"),
    ("ARCA_DEEPEN_API_KEY", "Deepen"),
    ("ARCA_ARBITER_API_KEY", "Arbiter"),
]


def build_cloud() -> str:
    lines = [CLOUD_HEADER]
    for env_name, label in STAGE_KEYS:
        try:
            value = getpass.getpass(f"{label} key（留空跳过）: ")
        except (EOFError, KeyboardInterrupt):
            value = ""
        lines.append(f"{env_name}={value}\n" if value else f"# {env_name}=\n")
    return "".join(lines)


def choose_mode() -> str:
    if not sys.stdin.isatty():
        return "local"
    print("选择部署模式: 1) 本地委员会 local  2) 云端 API cloud  3) 纯确定性 deterministic")
    choice = input("输入序号 [1]: ").strip() or "1"
    return {"1": "local", "2": "cloud", "3": "deterministic"}.get(choice, "local")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate .env for Arcanum Spark")
    ap.add_argument("--mode", choices=["local", "cloud", "deterministic"])
    ap.add_argument("--out", default=".env")
    ap.add_argument("--force", action="store_true", help="overwrite an existing file")
    args = ap.parse_args()

    mode = args.mode or choose_mode()

    if mode == "deterministic":
        print("纯确定性模式无需任何环境变量，直接运行：")
        print("  python -m codeark.cli <repo> --dry --formats json,sarif,markdown")
        return 0

    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"拒绝覆盖已存在的 {out}（确需覆盖请加 --force）", file=sys.stderr)
        return 2

    content = LOCAL_TEMPLATE if mode == "local" else build_cloud()
    out.write_text(content, encoding="utf-8")
    print(f"已写入 {out}（mode={mode}）")
    if mode == "local":
        print("下一步: bash deploy/mi300x-oneclick.sh 起服务；"
              "python scripts/check_endpoints.py 预检")
    else:
        print("下一步: python scripts/check_endpoints.py --deployment cloud --probe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
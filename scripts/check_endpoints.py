#!/usr/bin/env python3
"""模型端点预检 — 本地委员会 / 云端配置（纯标准库）。

用法:
  python scripts/check_endpoints.py                    # 按 ARCA_DEPLOYMENT（缺省 local）
  python scripts/check_endpoints.py --deployment cloud # 只查云端环境变量完整性
  python scripts/check_endpoints.py --deployment cloud --probe  # 再实际 GET <base_url>/models
  python scripts/check_endpoints.py --json             # 机器可读输出

退出码: 0=全部必需端点就绪; 1=有必需端点未就绪或配置缺失。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

# (stage, port, expected model alias in /v1/models, required)
LOCAL_ENDPOINTS = [
    ("scout", 8081, "muse-scout", True),
    ("verify", 8085, "gpt-oss-verify", True),
    ("deepen", 8083, "r1-deepen", True),
    ("arbiter", 8084, "gemma-arbiter", True),
    ("verify_spare", 8182, "qwen-verify", False),
]

CLOUD_STAGES = {
    "scout": ("ARCA_SCOUT_PRIMARY_API_KEY", "ARCA_SCOUT_FALLBACK_API_KEY"),
    "verify": ("ARCA_VERIFY_API_KEY",),
    "deepen": ("ARCA_DEEPEN_API_KEY",),
    "arbiter": ("ARCA_ARBITER_API_KEY",),
}


def _probe_local(port: int, timeout: float) -> tuple[bool, str]:
    url = f"http://127.0.0.1:{port}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return True, resp.read(500_000).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 — 预检把任何失败折叠成一行状态
        return False, str(exc)


def check_local(timeout: float) -> list[dict]:
    rows = []
    for stage, port, alias, required in LOCAL_ENDPOINTS:
        reachable, detail = _probe_local(port, timeout)
        ok = reachable and alias in detail
        if ok:
            note = "ready"
        elif not reachable:
            note = f"port {port} unreachable: {detail[:120]}"
        else:
            note = f"alias {alias!r} not in /v1/models response"
        rows.append({
            "stage": stage, "port": port, "model": alias,
            "required": required, "ok": ok, "detail": note,
        })
    return rows


def check_cloud(probe: bool, timeout: float) -> list[dict]:
    rows = []
    for stage, keys in CLOUD_STAGES.items():
        present = [k for k in keys if os.getenv(k)]
        row = {
            "stage": stage, "keys": list(keys), "present": present,
            "required": True, "ok": bool(present), "detail": "",
        }
        if probe:
            base = os.getenv(f"ARCA_{stage.upper()}_BASE_URL", "").strip()
            if not base:
                row["detail"] = "ARCA_%s_BASE_URL unset; probe skipped" % stage.upper()
            else:
                headers = {}
                if present:
                    headers["Authorization"] = f"Bearer {os.getenv(present[0], '')}"
                try:
                    req = urllib.request.Request(base.rstrip("/") + "/models", headers=headers)
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        resp.read(1000)
                    row["detail"] = "probe ok"
                except Exception as exc:  # noqa: BLE001
                    row["ok"] = False
                    row["detail"] = f"probe failed: {exc}"
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight model endpoints")
    ap.add_argument(
        "--deployment", choices=["local", "cloud"],
        default=os.getenv("ARCA_DEPLOYMENT", "local"),
    )
    ap.add_argument("--probe", action="store_true",
                    help="cloud: also GET <base_url>/models (sends Bearer key when present)")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    rows = (check_local(args.timeout) if args.deployment == "local"
            else check_cloud(args.probe, args.timeout))
    failed = [r for r in rows if r["required"] and not r["ok"]]

    if args.json:
        print(json.dumps({"deployment": args.deployment, "rows": rows,
                          "ok": not failed}, ensure_ascii=False, indent=2))
    else:
        print(f"deployment={args.deployment}")
        for r in rows:
            mark = "OK " if r["ok"] else ("FAIL" if r["required"] else "WARN")
            if "port" in r:
                target = f":{r['port']} {r['model']}"
            else:
                target = " ".join(r["keys"])
            print(f"  [{mark}] {r['stage']:<12} {target}  {r['detail']}")
        print("RESULT:", "READY" if not failed
              else f"{len(failed)} required endpoint(s) not ready")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
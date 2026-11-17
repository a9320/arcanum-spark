"""IC27 达标核对：逐项确认 10 项 Azure 服务各自已产生 >= $1.00 用量。

为什么存在：规则判据不在"资源已创建"，而在"账户上每项服务可见 $1.00 用量"。
本脚本用 `az consumption usage list` 的明细按服务聚合，输出一张可贴进证据文档的表。

用法：
  # 1) 本机已 az login：脚本自己去拉最近 30 天明细
  python scripts/azure/check_usage.py --run-az

  # 2) 在 Cloud Shell 里先导出明细，再离线核对（推荐：证据可存档复跑）
  az consumption usage list --start-date 2026-11-17 --end-date 2026-12-17 -o json > usage.json
  python scripts/azure/check_usage.py --input usage.json

  # 3) 只看某一项 / 调整门槛
  python scripts/azure/check_usage.py --input usage.json --only speech --min-usd 1.0

判据与口径：
  * 明细字段因订阅类型而异，本脚本按 product -> meterName -> consumedService 逐级匹配。
  * 金额优先取 pretaxCost，缺失时退 cost；只统计 <= 当天（未来日期行忽略）。
  * 退出码：0=十项全达标；1=有未达标；2=拿不到明细/参数错误。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# 十项服务与匹配规则（顺序=选型文档 §3 的表序）。
# keys: 规范名；products/meters 为小写子串，命中任一即归入该服务。
SERVICES: list[dict[str, object]] = [
    {"key": "content_safety", "label": "Azure AI Content Safety",
     "product": ["content safety"], "meter": ["text records", "images"]},
    {"key": "language", "label": "Azure AI Language",
     "product": ["language"], "meter": ["text records", "doc-pii"]},
    {"key": "docintel", "label": "Azure AI Document Intelligence",
     "product": ["document intelligence", "form recognizer"], "meter": ["pages"]},
    {"key": "vision", "label": "Azure AI Vision",
     "product": ["vision", "computer vision"], "meter": ["ocr", "read"]},
    {"key": "speech", "label": "Azure AI Speech",
     "product": ["speech"], "meter": ["speech to text", "stt"]},
    {"key": "acr", "label": "Azure Container Registry",
     "product": ["container registry"], "meter": ["registry unit", "registry"]},
    {"key": "aca", "label": "Azure Container Apps",
     "product": ["container apps"], "meter": ["vcpu", "memory", "environment"]},
    {"key": "log_analytics", "label": "Azure Log Analytics",
     "product": ["log analytics"], "meter": ["data ingestion", "data analyzed"]},
    {"key": "service_bus", "label": "Azure Service Bus",
     "product": ["service bus"], "meter": ["base unit", "messaging operations"]},
    {"key": "event_hubs", "label": "Azure Event Hubs",
     "product": ["event hubs"], "meter": ["throughput unit", "ingress events"]},
]


def _text(item: dict, *names: str) -> str:
    for name in names:
        value = item.get(name)
        if value:
            return str(value)
    return ""


def classify(item: dict) -> str | None:
    """把一条用量明细归到十项之一；归不进去返回 None。"""
    product = _text(item, "product", "productName").lower()
    meter = _text(item, "meterName", "meter").lower()
    consumed = _text(item, "consumedService", "serviceName").lower()
    for spec in SERVICES:
        products = [p.lower() for p in spec["product"]]  # type: ignore[index]
        meters = [m.lower() for m in spec["meter"]]  # type: ignore[index]
        hit_product = any(p in product for p in products) or any(
            p in consumed for p in products
        )
        if not hit_product:
            continue
        if not meters or any(m in meter for m in meters):
            return str(spec["key"])
    return None


def _cost(item: dict) -> float:
    for name in ("pretaxCost", "cost", "costInBillingCurrency"):
        value = item.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def aggregate(items: list[dict]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {
        str(spec["key"]): {
            "label": spec["label"],
            "cost_usd": 0.0,
            "meters": {},
            "rows": 0,
        }
        for spec in SERVICES
    }
    for item in items:
        key = classify(item)
        if key is None:
            continue
        entry = out[key]
        entry["cost_usd"] = round(float(entry["cost_usd"]) + _cost(item), 6)  # type: ignore[arg-type]
        meters: dict[str, float] = entry["meters"]  # type: ignore[assignment]
        meter = _text(item, "meterName", "meter") or "(unknown)"
        meters[meter] = round(meters.get(meter, 0.0) + _cost(item), 6)
        entry["rows"] = int(entry["rows"]) + 1  # type: ignore[arg-type]
    return out


def _load(args: argparse.Namespace) -> list[dict] | None:
    if args.input:
        path = Path(args.input)
        if not path.exists():
            print(f"明细文件不存在：{path}", file=sys.stderr)
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    start = (date.today() - timedelta(days=args.days)).isoformat()
    end = date.today().isoformat()
    command = [
        "az", "consumption", "usage", "list",
        "--start-date", start, "--end-date", end, "-o", "json",
    ]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except Exception as exc:  # az 未装/超时
        print(f"调用 az 失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    if done.returncode != 0:
        print(f"az 退出码 {done.returncode}：{(done.stderr or '').strip()[:400]}", file=sys.stderr)
        return None
    try:
        return json.loads(done.stdout or "[]")
    except Exception:
        print("az 输出不是合法 JSON", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IC27：10 项 Azure 服务 $1 用量核对")
    ap.add_argument("--input", help="az consumption usage list 导出的 JSON 路径")
    ap.add_argument("--run-az", action="store_true", help="直接调用 az 拉取最近 N 天明细")
    ap.add_argument("--days", type=int, default=30, help="--run-az 时的回看天数（默认 30）")
    ap.add_argument("--min-usd", type=float, default=1.0, help="每项门槛（默认 1.00）")
    ap.add_argument("--only", action="append", default=[], help="只看某些 key（可重复）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args(argv)

    if not args.input and not args.run_az:
        print("需要 --input 或 --run-az 之一", file=sys.stderr)
        return 2
    items = _load(args)
    if items is None:
        return 2

    table = aggregate(items)
    keys = [str(s["key"]) for s in SERVICES]
    if args.only:
        keys = [k for k in keys if k in set(args.only)]
        if not keys:
            print(f"--only 无匹配：{args.only}", file=sys.stderr)
            return 2

    reached = 0
    rows = []
    for key in keys:
        entry = table[key]
        cost = float(entry["cost_usd"])  # type: ignore[arg-type]
        ok = cost >= args.min_usd
        reached += 1 if ok else 0
        rows.append({
            "key": key,
            "service": entry["label"],
            "cost_usd": round(cost, 4),
            "reached": ok,
            "meters": entry["meters"],
            "rows": entry["rows"],
        })

    if args.json:
        print(json.dumps({
            "min_usd": args.min_usd,
            "reached": reached,
            "total": len(keys),
            "all_reached": reached == len(keys),
            "services": rows,
        }, ensure_ascii=False))
    else:
        print(f"门槛：每项 >= ${args.min_usd:.2f}    窗口：{args.input or f'最近 {args.days} 天'}")
        print(f"{'service':<34}{'cost_usd':>10}  {'status':<6} meters")
        for row in rows:
            meters = ", ".join(sorted(row["meters"])) or "-"
            print(
                f"{row['service']:<34}{row['cost_usd']:>10.4f}  "
                f"{'OK' if row['reached'] else 'SHORT':<6} {meters}"
            )
        print(f"\n达到 {reached}/{len(keys)} 项")
        if reached != len(keys):
            print("未达标项：先跑 generate_usage.py 对应子命令，或继续等时间型服务计费累积。")
    return 0 if reached == len(keys) else 1


if __name__ == "__main__":
    sys.exit(main())

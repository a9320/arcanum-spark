"""IC27 达标核对：逐项确认 10 项 Azure 服务各自已产生 >= $1.00 用量。

为什么不用 `az consumption usage list`：学生订阅（Azure for Students）上它只返回
一行占位记录（pretaxCost/usageQuantity/meterDetails 全是 None），拿不到可用明细。

改用 **Cost Management 查询 API，按 ResourceId 分组**：
  * 账单的 ServiceName 维度把 5 项 AI 服务合并成一项 "Foundry Tools"，无法区分；
    ResourceId 粒度能保留"一项服务一个资源"的事实。
  * 学生订阅按 CNY 记账，所以用 --cny-per-usd（默认 7.2）换算成美元再对 $1 门槛判定。

用法：
  python scripts/azure/check_usage.py                 # 本月至今（MonthToDate）
  python scripts/azure/check_usage.py --days 3        # 最近 3 天（Custom 窗口）
  python scripts/azure/check_usage.py --json          # 只输出 JSON（存档用）
  python scripts/azure/check_usage.py --input out.json  # 离线核对已保存的查询结果

判据与口径：
  * 明细有 4–24 小时延迟：当天跑量当天查大概率还是 0，属正常。
  * 金额取 Cost Management 的 Cost 列；币种取 Currency 列。
  * 退出码：0=十项全达标；1=有未达标；2=拿不到数据/参数错误。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

# 资源名前缀 -> (规范 key, 展示名)。顺序=选型文档 §3 的表序。
RESOURCE_MAP: list[tuple[tuple[str, ...], str, str]] = [
    (("arca-cs-",), "content_safety", "Azure AI Content Safety"),
    (("arca-ai-",), "language", "Azure AI Language"),
    (("arca-di-",), "docintel", "Azure AI Document Intelligence"),
    (("arca-cv-",), "vision", "Azure AI Vision"),
    (("arca-sp-",), "speech", "Azure AI Speech"),
    (("arcaacr",), "acr", "Azure Container Registry"),
    (("arca-aca-",), "aca", "Azure Container Apps"),
    (("arca-law-",), "log_analytics", "Azure Log Analytics"),
    (("arca-sb-",), "service_bus", "Azure Service Bus"),
    (("arca-eh-",), "event_hubs", "Azure Event Hubs"),
]

DEFAULT_CNY_PER_USD = 7.2


def service_for_resource(resource_id: str) -> tuple[str, str] | None:
    """把 ResourceId 归到十项之一（按资源名匹配前缀）。"""
    name = resource_id.rstrip("/").rsplit("/", 1)[-1].lower()
    if not name:
        return None
    for prefixes, key, label in RESOURCE_MAP:
        if any(name.startswith(p) for p in prefixes):
            return key, label
    return None


def az_command(override: str | None = None) -> list[str]:
    """解析 az；Windows 的 az.cmd 必须经 cmd /c 启动（否则 WinError 2）。"""
    exe = override or shutil.which("az") or shutil.which("az.cmd") or shutil.which("az.bat")
    if not exe:
        return []
    if exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe]
    return [exe]


def build_query(days: int | None) -> dict:
    dataset = {
        "granularity": "None",
        "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
        "grouping": [
            {"type": "Dimension", "name": "ResourceId"},
            {"type": "Dimension", "name": "Meter"},
        ],
    }
    if days is None:
        return {"type": "ActualCost", "timeframe": "MonthToDate", "dataset": dataset}
    end = date.today()
    start = end - timedelta(days=max(1, days))
    return {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T23:59:59Z"},
        "dataset": dataset,
    }


def _curl_query(az: list[str], subscription: str, body: dict) -> dict | None:
    """az rest 失败时的兜底：curl + bearer token（本机到 management.azure.com 会间歇性重置）。

    安全：token **不进 argv**（同机进程可读命令行）。认证头经 `curl -K -` 从 stdin 读入，
    既不落 argv 也不落磁盘。
    """
    curl = shutil.which("curl")
    if not curl:
        return None
    token = subprocess.run(
        az + ["account", "get-access-token", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    token_text = (token.stdout or "").strip()
    if token.returncode != 0 or not token_text:
        return None
    url = (
        f"https://management.azure.com/subscriptions/{subscription}"
        f"/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    )
    # curl 配置走 stdin：header 只在内存里，进程列表看不到。
    config = (
        f'header = "Authorization: Bearer {token_text}"\n'
        'header = "Content-Type: application/json"\n'
    )
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(body, handle)
        handle.close()
        for attempt in range(3):
            done = subprocess.run(
                # --http1.1：本机到 management.azure.com 的 HTTP/2 会被重置（10-28 已实证）
                [curl, "-sk", "--http1.1", "--max-time", "180", "-K", "-", "-X", "POST", url,
                 "--data", f"@{handle.name}"],
                input=config,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            )
            text = (done.stdout or "").strip()
            if done.returncode == 0 and text.startswith("{"):
                data = json.loads(text)
                if "properties" in data:
                    return data
                code = str((data.get("error") or {}).get("code") or "")
                if code == "429" or "Too many requests" in text:
                    wait = 45 * (attempt + 1)
                    print(f"  curl 被限流，{wait}s 后重试（{attempt + 1}/3）", file=sys.stderr)
                    time.sleep(wait)
                    continue
                print(f"  curl 返回异常：{text[:200]}", file=sys.stderr)
                return None
            detail = (done.stderr or done.stdout or "").strip()[:160]
            print(f"  curl 失败 rc={done.returncode}：{detail}"
                  + ("，15s 后重试" if attempt < 2 else ""), file=sys.stderr)
            if attempt < 2:
                time.sleep(15)
        return None
    except Exception as exc:
        # 只报类型与消息，并把可能的 token 回显擦掉（异常文本可能带命令行）。
        detail = f"{type(exc).__name__}: {exc}".replace(token_text, "***") if token_text else f"{type(exc).__name__}"
        print(f"  curl 兜底异常：{detail[:200]}", file=sys.stderr)
        return None
    finally:
        Path(handle.name).unlink(missing_ok=True)


def run_query(az: list[str], subscription: str, body: dict, retries: int = 3) -> dict | None:
    url = (
        f"https://management.azure.com/subscriptions/{subscription}"
        f"/providers/Microsoft.CostManagement/query?api-version=2023-11-01"
    )
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(body, handle)
        handle.close()
        for attempt in range(retries):
            done = subprocess.run(
                az + ["rest", "--method", "post", "--url", url, "--body", f"@{handle.name}", "-o", "json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            )
            if done.returncode == 0:
                try:
                    return json.loads(done.stdout or "{}")
                except json.JSONDecodeError:
                    print("az rest 输出不是合法 JSON", file=sys.stderr)
                    return None
            stderr = (done.stderr or "").strip()
            throttled = "429" in stderr or "Too many requests" in stderr
            wait = 30 * (attempt + 1) if throttled else 10 * (attempt + 1)
            print(f"  查询失败（{'限流' if throttled else '连接'}），{wait}s 后重试（{attempt + 1}/{retries}）",
                  file=sys.stderr)
            time.sleep(wait)
        print("  az rest 连续失败，改用 curl 兜底", file=sys.stderr)
        return _curl_query(az, subscription, body)
    finally:
        Path(handle.name).unlink(missing_ok=True)


def aggregate(payload: dict, cny_per_usd: float) -> dict[str, dict[str, object]]:
    """把 Cost Management 的 rows 按服务汇总；同时返回币种与美元估算。"""
    table: dict[str, dict[str, object]] = {
        key: {"label": label, "cost": 0.0, "currency": "", "cost_usd": 0.0,
              "resources": {}, "meters": {}}
        for _, key, label in RESOURCE_MAP
    }
    props = payload.get("properties") or {}
    columns = [str(col.get("name", "")) for col in props.get("columns", [])]
    if "Cost" not in columns or "ResourceId" not in columns:
        return table
    i_cost, i_res = columns.index("Cost"), columns.index("ResourceId")
    i_cur = columns.index("Currency") if "Currency" in columns else None
    i_meter = columns.index("Meter") if "Meter" in columns else None
    for row in props.get("rows", []):
        try:
            cost = float(row[i_cost] or 0)
            resource = str(row[i_res] or "")
            currency = str(row[i_cur] or "") if i_cur is not None else ""
        except (TypeError, ValueError, IndexError):
            continue
        mapped = service_for_resource(resource)
        if mapped is None:
            continue
        key, _label = mapped
        entry = table[key]
        entry["cost"] = round(float(entry["cost"]) + cost, 6)  # type: ignore[arg-type]
        entry["currency"] = currency or entry["currency"]
        resources: dict[str, float] = entry["resources"]  # type: ignore[assignment]
        name = resource.rstrip("/").rsplit("/", 1)[-1]
        resources[name] = round(resources.get(name, 0.0) + cost, 6)
        if i_meter is not None:
            meter = str(row[i_meter] or "(unknown)")
            meters: dict[str, float] = entry["meters"]  # type: ignore[assignment]
            meters[meter] = round(meters.get(meter, 0.0) + cost, 6)
    for entry in table.values():
        currency = str(entry["currency"] or "USD").upper()
        cost = float(entry["cost"])  # type: ignore[arg-type]
        entry["cost_usd"] = round(cost / cny_per_usd, 4) if currency == "CNY" else round(cost, 4)
    return table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IC27：10 项 Azure 服务 $1 用量核对（Cost Management/ResourceId）")
    ap.add_argument("--input", help="已保存的 Cost Management 查询结果 JSON（离线核对）")
    ap.add_argument("--days", type=int, help="自定义窗口天数（默认 MonthToDate）")
    ap.add_argument("--min-usd", type=float, default=1.0, help="每项门槛（默认 1.00）")
    ap.add_argument("--cny-per-usd", type=float, default=DEFAULT_CNY_PER_USD,
                    help=f"CNY→USD 换算（默认 {DEFAULT_CNY_PER_USD}；学生订阅按 CNY 记账）")
    ap.add_argument("--az", help="az 可执行文件路径（默认自动解析）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args(argv)

    if args.input:
        path = Path(args.input)
        if not path.exists():
            print(f"结果文件不存在：{path}", file=sys.stderr)
            return 2
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        az = az_command(args.az)
        if not az:
            print("未找到 az：请安装 azure-cli，或用 --input 传已保存的查询结果", file=sys.stderr)
            return 2
        sub = subprocess.run(
            az + ["account", "show", "--query", "id", "-o", "tsv"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        subscription = (sub.stdout or "").strip()
        if sub.returncode != 0 or not subscription:
            print(f"拿不到订阅 ID（az 未登录？）：{(sub.stderr or '').strip()[:200]}", file=sys.stderr)
            return 2
        payload = run_query(az, subscription, build_query(args.days)) or {}
        if not payload:
            return 2

    table = aggregate(payload, args.cny_per_usd)
    rows = []
    reached = 0
    for _prefixes, key, label in RESOURCE_MAP:
        entry = table[key]
        usd = float(entry["cost_usd"])  # type: ignore[arg-type]
        ok = usd >= args.min_usd
        reached += 1 if ok else 0
        rows.append({
            "key": key,
            "service": label,
            "cost": float(entry["cost"]),  # type: ignore[arg-type]
            "currency": entry["currency"] or "-",
            "cost_usd": round(usd, 4),
            "reached": ok,
            "resources": entry["resources"],
            "meters": entry["meters"],
        })

    if args.json:
        print(json.dumps({
            "min_usd": args.min_usd,
            "cny_per_usd": args.cny_per_usd,
            "window": args.input or (f"最近 {args.days} 天" if args.days else "MonthToDate"),
            "reached": reached,
            "total": len(rows),
            "all_reached": reached == len(rows),
            "services": rows,
        }, ensure_ascii=False))
    else:
        window = args.input or (f"最近 {args.days} 天" if args.days else "MonthToDate")
        print(f"门槛：每项 >= ${args.min_usd:.2f}（CNY 按 {args.cny_per_usd} 折算）  窗口：{window}")
        print(f"{'service':<34}{'cost':>10} {'cur':<5}{'usd':>9}  status")
        for row in rows:
            print(f"{row['service']:<34}{row['cost']:>10.4f} {row['currency']:<5}"
                  f"{row['cost_usd']:>9.3f}  {'OK' if row['reached'] else 'SHORT'}")
        print(f"\n达到 {reached}/{len(rows)} 项")
        if reached != len(rows):
            print("未达标：AI 项跑 generate_usage.py 对应子命令；时间型四项等计费累积。")
            print("注意账单延迟 4–24 小时，当天跑量当天查仍为 0 属正常。")
    return 0 if reached == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())

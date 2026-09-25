"""端点并发容忍度探测 — 为 verify/deepen 的 max_concurrency 调优提供实测依据。

对单个端点按递增并发档位发小请求，统计成功/429/503/其他错误与时延。
密钥只从环境变量读取，输出永不打印凭据。

用法：
  python eval/probe_concurrency.py --stage verify --levels 1 2 4 8 [--rounds 2]
  python eval/probe_concurrency.py --stage deepen --levels 1 2 4

端点/模型取自 codeark.models.factory._REMOTE_ROUTE_DEFAULTS（与线上路由同源），
key 取对应 ARCA_*_API_KEY。退出码：档位全绿=0，任一档位出现限流/拒绝=1。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from openai import AsyncOpenAI  # noqa: E402

from codeark.models.factory import _REMOTE_ROUTE_DEFAULTS  # noqa: E402

_PROBE_PROMPT = "只回复两个字母：pong"
_PROBE_MAX_TOKENS = 200  # 部分模型带推理输出，给足余量避免截断错误干扰判断


def _classify(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "429"
    if status == 503:
        return "503"
    text = str(exc)
    if "429" in text and ("rate" in text.lower() or "limit" in text.lower()):
        return "429"
    if "503" in text:
        return "503"
    return "other"


async def _fire(client: AsyncOpenAI, model: str) -> tuple[bool, float, str]:
    start = time.perf_counter()
    try:
        await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _PROBE_PROMPT}],
            max_tokens=_PROBE_MAX_TOKENS,
        )
        return True, time.perf_counter() - start, ""
    except Exception as exc:
        return False, time.perf_counter() - start, _classify(exc)


async def _probe_level(client: AsyncOpenAI, model: str, level: int, rounds: int) -> dict:
    ok = fails = 0
    buckets: dict[str, int] = {"429": 0, "503": 0, "other": 0}
    latencies: list[float] = []
    for _ in range(rounds):
        results = await asyncio.gather(*[_fire(client, model) for _ in range(level)])
        for success, seconds, kind in results:
            latencies.append(seconds)
            if success:
                ok += 1
            else:
                fails += 1
                buckets[kind] += 1
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    return {
        "level": level, "ok": ok, "fail": fails,
        "429": buckets["429"], "503": buckets["503"], "other": buckets["other"],
        "p50": p50, "max": latencies[-1] if latencies else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=sorted(_REMOTE_ROUTE_DEFAULTS))
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()

    spec = _REMOTE_ROUTE_DEFAULTS[args.stage]
    api_key = os.environ.get(str(spec["key_env"]), "").strip()
    if not api_key:
        print(f"[probe] missing env {spec['key_env']}", file=sys.stderr)
        return 2
    base_url = str(spec["base_url"])
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    model = str(spec["model_id"])

    print(f"[probe] stage={args.stage} model={model} gateway={base_url} "
          f"levels={args.levels} rounds={args.rounds}")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=90.0)

    blocked = False
    print(f"{'level':>5} {'ok':>4} {'429':>4} {'503':>4} {'other':>6} {'p50_s':>7} {'max_s':>7}")
    rows = asyncio.run(_run_levels(client, model, args.levels, args.rounds))
    for row in rows:
        print(f"{row['level']:>5} {row['ok']:>4} {row['429']:>4} {row['503']:>4} "
              f"{row['other']:>6} {row['p50']:>7.2f} {row['max']:>7.2f}")
        if row["429"] or row["503"]:
            blocked = True
    if blocked:
        print("[probe] verdict: 该端点出现限流/拒绝，max_concurrency 保持在触发档位以下")
        return 1
    print("[probe] verdict: 全部档位无 429/503，可取最高实测档位为该端点 max_concurrency")
    return 0


async def _run_levels(client: AsyncOpenAI, model: str, levels: list[int], rounds: int) -> list[dict]:
    return [await _probe_level(client, model, max(1, level), max(1, rounds)) for level in levels]


if __name__ == "__main__":
    raise SystemExit(main())

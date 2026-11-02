#!/usr/bin/env python3
"""并发/热服务串话回归 — 审计判决正确性闸（纯标准库，2026-11-02 落地）。

背景（AMD 社区问答 §13 P0-1，ID 27148/22629/29092/909/984/478）：
llama.cpp 存在跨请求污染 bug 族 —— HIP GatedDeltaNet 递归状态跨请求泄漏
（温度 0 确定性复现、单 slot 顺序请求也中招）、RAM prompt cache 把无关会话
恢复进新 slot、多序列 seq_cp 同后缀 logits 不一致。这类缺陷**逐点重启式测法
永远暴露不了**，必须在热服务器上做"不相关请求 diff"。

本脚本两个模式：
  warm        顺序：发请求 A（长上下文+唯一标记）→ 再发请求 B（无关任务+唯一
              标记）→ 检查 B 的回答是否泄漏 A 的任何标记。
  concurrent  并发：K 路请求同时打同一服务，每路带唯一标记并要求原样回显 →
              检查任一响应是否混入其他路的标记（slot 错配/串状态）。

判定：出现任一跨请求标记 = FAIL（exit 1）。服务不可达 = exit 2（环境问题，
不算 FAIL）。全部干净 = PASS（exit 0）。

用法（DSW 五服务各跑一遍；建议每次升级 llama.cpp 构建后、以及每批实验前）:
  python scripts/regression_concurrency.py --port 8081 --model muse-scout
  python scripts/regression_concurrency.py --port 8083 --model r1-deepen --rounds 6
  python scripts/regression_concurrency.py --port 8085 --model gpt-oss-verify --concurrency 4
  python scripts/regression_concurrency.py --all-local      # 一次跑五服务
  python -m pytest 无关：本脚本是运维闸，不收集进 pytest（文件名非 test_ 前缀）。

注意：标记用 8 位十六进制随机串，prompt 要求"只原样输出标记"；模型多吐内容是
正常的（宽容判定），只把"出现他人标记"当串话证据。
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LOCAL_PORTS = [
    (8081, "muse-scout"),
    (8182, "qwen-verify"),
    (8083, "r1-deepen"),
    (8084, "gemma-arbiter"),
    (8085, "gpt-oss-verify"),
]


def _chat(base_url: str, model: str, user: str, system: str, max_tokens: int,
          timeout: float) -> str:
    payload = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else [])
        + [{"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        # 思考型模型（muse/r1/gpt-oss）在短 max_tokens 下会把预算全烧进 reasoning，
        # content 返回空 → 串话判定退化成"全部未回显"假绿（2026-11-02 DSW smoke
        # 实测：muse max_tokens=64 → content='' reasoning_len=197）。模板支持的模型
        # 关思考直出；不支持的模型忽略该字段（无害），靠 max_tokens 余量兜住。
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    return (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""


def _mark() -> str:
    return "M" + secrets.token_hex(4).upper()


def run_warm(base_url: str, model: str, rounds: int, timeout: float,
             system: str, max_tokens: int = 192) -> dict:
    """顺序 A→B：B 的响应不得含 A 的标记（同一 slot 复用下的状态残留）。"""
    leaks = []
    for i in range(rounds):
        ma, mb = _mark(), _mark()
        # A：要求复述一段长上下文 + 标记（占满 slot，留下可识别的状态）
        a_user = (
            "请阅读并记住下面这段记录，然后只输出其中出现的代号：\n"
            + "\n".join(f"行{j}: 记录编号 {ma}-{j}，内容为常规审计日志。" for j in range(1, 25))
            + f"\n\n只输出代号 {ma}，不要输出其他任何内容。"
        )
        a_out = _chat(base_url, model, a_user, system, max_tokens, timeout)
        # B：完全无关的短任务 + 自己的标记
        b_user = f"忽略此前所有内容。这是新任务：请只原样输出代号 {mb}。"
        b_out = _chat(base_url, model, b_user, system, max_tokens, timeout)
        if ma in b_out:
            leaks.append({"round": i + 1, "mode": "warm", "leaked": ma,
                          "a_out": a_out[:120], "b_out": b_out[:200]})
        if mb not in b_out:
            # 未回显自己的标记：模型不遵循指令，不构成串话证据，单列观察
            leaks.append({"round": i + 1, "mode": "warm", "note": "B 未回显自身标记",
                          "b_out": b_out[:200]})
    return {"mode": "warm", "rounds": rounds, "leaks": leaks}


def run_concurrent(base_url: str, model: str, concurrency: int, timeout: float,
                   system: str, max_tokens: int = 192) -> dict:
    """K 路并发：每路唯一标记，任一响应含他人标记 = slot 错配/串状态。"""
    marks = [_mark() for _ in range(concurrency)]

    def one(idx: int) -> dict:
        m = marks[idx]
        user = (
            f"请只原样输出代号 {m}。" + "（上下文填充：" + "x" * (120 * idx) + "）"
        )
        out = _chat(base_url, model, user, system, max_tokens, timeout)
        return {"idx": idx, "mark": m, "out": out}

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, range(concurrency)))

    leaks = []
    for r in results:
        foreign = [m for m in marks if m != r["mark"] and m in r["out"]]
        if foreign:
            leaks.append({"mode": "concurrent", "idx": r["idx"],
                          "own": r["mark"], "foreign": foreign,
                          "out": r["out"][:200]})
        elif r["mark"] not in r["out"]:
            leaks.append({"mode": "concurrent", "idx": r["idx"],
                          "note": "未回显自身标记", "out": r["out"][:200]})
    return {"mode": "concurrent", "concurrency": concurrency, "leaks": leaks}


def probe(base_url: str, model: str, timeout: float) -> str | None:
    """返回 None=可达且 alias 在位；否则返回失败原因（串话判定一律 build 在可达之上）。"""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=timeout) as r:
            body = r.read(500_000).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return f"不可达: {exc}"
    return None if model in body else f"/v1/models 无别名 {model!r}"


def main() -> int:
    ap = argparse.ArgumentParser(description="跨请求串话回归（审计判决正确性闸）")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--model", default="muse-scout")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--base-url", default=None,
                    help="覆盖 --host/--port（如 http://127.0.0.1:8085/v1）")
    ap.add_argument("--rounds", type=int, default=4, help="warm 模式往返次数")
    ap.add_argument("--concurrency", type=int, default=3, help="concurrent 模式并发数")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-tokens", type=int, default=192,
                    help="生成预算；思考型模型 32 会全烧 reasoning 致 content 空（假绿）")
    ap.add_argument("--system", default="你是代码安全审计助手。",
                    help="共享 system prompt（模拟我们五服务的固定模板）")
    ap.add_argument("--mode", choices=["warm", "concurrent", "both"], default="both")
    ap.add_argument("--all-local", action="store_true",
                    help="依次跑五服务（每服务 both 模式）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets = (LOCAL_PORTS if args.all_local
               else [(args.port, args.model)])
    report = {"targets": [], "verdict": "PASS"}

    for port, model in targets:
        base = args.base_url or f"http://{args.host}:{port}/v1"
        row: dict = {"port": port, "model": model, "base_url": base}
        reason = probe(base, model, min(args.timeout, 10))
        if reason:
            row.update({"status": "UNREACHABLE", "detail": reason})
            report["targets"].append(row)
            continue
        results = []
        if args.mode in ("warm", "both"):
            results.append(run_warm(base, model, args.rounds, args.timeout, args.system,
                                    args.max_tokens))
        if args.mode in ("concurrent", "both"):
            results.append(run_concurrent(base, model, args.concurrency,
                                          args.timeout, args.system, args.max_tokens))
        leaks = [lk for r in results for lk in r["leaks"]]
        hard = [lk for lk in leaks if "leaked" in lk or "foreign" in lk]
        row.update({
            "status": "FAIL" if hard else "PASS",
            "findings": leaks,
            "hard_leaks": len(hard),
        })
        if hard:
            report["verdict"] = "FAIL"
        report["targets"].append(row)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"串话回归 | verdict={report['verdict']}")
        for row in report["targets"]:
            print(f"\n[{row['status']}] :{row['port']} {row['model']}")
            if row.get("detail"):
                print(f"  {row['detail']}")
                continue
            for f in row["findings"]:
                kind = "LEAK" if ("leaked" in f or "foreign" in f) else "观察"
                print(f"  {kind}: {json.dumps(f, ensure_ascii=False)[:240]}")
            if not row["findings"]:
                print("  干净：无跨请求标记、无标记缺失")

    if report["verdict"] == "FAIL":
        return 1
    if all(t["status"] == "UNREACHABLE" for t in report["targets"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
#!/usr/bin/env python3
"""ai-repo-audit 解码复核工具（decode-verify）。

对疑似被编码隐藏的提示注入载荷做逐层剥离（base64 → ROT13 → 反转，至多 5 层），
输出每层解码结果，供审计 Agent 在报告前人工复核"解码后确实命中注入关键词"。

复用 codeark/pitax/detectors 的同一套剥离逻辑（单源、零漂移）。

用法:
    decode.py "<被编码字符串>"      # 直接传参
    echo "<字符串>" | decode.py     # 或读 stdin

退出码：解码后命中注入关键词 → 0（并打印剥离链与最终明文）；
        无编码/未命中关键词 → 1（无确认价值，提示人工判断）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from codeark.pitax.detectors import _contains_injection, _peel_layers  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="decode.py", description="解码复核疑似编码注入载荷")
    ap.add_argument("payload", nargs="?", help="被编码的字符串；省略则读 stdin")
    args = ap.parse_args(argv)

    payload = args.payload
    if payload is None:
        payload = sys.stdin.read().strip()
    if not payload:
        print("错误：未提供载荷。用法：decode.py \"<字符串>\" 或管道输入。", file=sys.stderr)
        return 2

    final, layers = _peel_layers(payload)
    hit = _contains_injection(final)

    print(f"输入（前 120 字符）：{payload[:120]}{'...' if len(payload) > 120 else ''}")
    if not layers:
        print("未剥离出编码层：该字符串本身不是 base64/ROT13/反转 可解码的注入载荷。")
        print("注意：无编码层不代表安全——请结合上下文判断是否为明文注入。")
        return 1

    print(f"剥离链：{' → '.join(layers)}（共 {len(layers)} 层）")
    print(f"最终明文：{final[:200]}{'...' if len(final) > 200 else ''}")
    if hit:
        if len(layers) >= 2:
            code = "PIT-E-57 多层"
        else:
            code = {"base64": "PIT-E-07", "rot13": "PIT-E-14", "reverse": "PIT-E-36"}.get(
                layers[0], "PIT-E-57")
        print(f"判定：解码后命中提示注入关键词 → 属于 PITAX 编码类规则（{code}）。")
        return 0
    print("判定：解码结果未命中注入关键词 → 不构成 PITAX 编码类命中（可能是正常数据）。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
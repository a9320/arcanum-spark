#!/usr/bin/env python
"""按 K1 manifest 从 GitHub 历史提交抓取 20 题快照（零模型、可复现）。

背景（2026-11-08/09）：上游 HEAD 已删 19/20 题，GitHub 历史提交仍可取；
DSW 旧克隆不再是唯一实物。本脚本以 `data/m8_k1_manifest.json` 的
`upstream_path` 自动派生目录前缀，取指定提交的 blob，逐文件按 tree 声明的
size 校验后落盘。

用法：
    python scripts/fetch_nyu_k1_snapshot.py --out D:/nyu-backup/nyu-bench-4c5744f
    # GitHub 直连不通时走镜像（gh-proxy 可透传 api.github.com 与 Authorization）
    python scripts/fetch_nyu_k1_snapshot.py --out <dir> \
        --api-base https://gh-proxy.com/https://api.github.com
    # 下载后立即校验（推荐）
    python scripts/k1_data_check.py --corpus <dir> --sha-list data/nyu_k1_20tasks.sha256

纪律：
- token 只从环境变量读（默认 GITHUB_TOKEN），绝不打印、不写入任何文件；
- 文件大小以 tree 声明为准逐个校验，半截件写 .part 再原子替换；
- 任一题前缀零命中 → exit 2（manifest 与提交不匹配，不做静默降级）。
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_SHA = "4c5744f55a31a58e03d6118c9dbb1c18e5bbdfa9"  # 2025-09-22，仍含全部 20 题
DEFAULT_REPO = "NYU-LLM-CTF/NYU_CTF_Bench"
DEFAULT_API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "data" / "m8_k1_manifest.json"

_lock = threading.Lock()
_state = {"done": 0, "ok": 0, "fail": 0, "fails": []}


def prefixes_from_manifest(path: Path) -> list[str]:
    """从 manifest 取 upstream_path 去尾斜杠，保持声明顺序去重。"""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    seen: list[str] = []
    for row in rows:
        value = str(row.get("upstream_path") or "").strip().rstrip("/")
        if value and value not in seen:
            seen.append(value)
    if not seen:
        raise ValueError(f"manifest 无 upstream_path: {path}")
    return seen


def _request(url: str, token: str, timeout: float):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "arcanum-k1-snapshot",
        "Accept-Encoding": "gzip",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_json(url: str, token: str, tries: int = 4, timeout: float = 180.0) -> dict:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            with _request(url, token, timeout) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 网络抖动逐次重试，最后汇总
            last = exc
            time.sleep(1.5 * (attempt + 1))
    assert last is not None
    raise last


def select_blobs(tree: dict, prefixes: list[str]) -> list[dict]:
    """只保前缀目录下的 blob，并断言每个前缀至少命中一次。"""
    blobs = [
        entry
        for entry in tree.get("tree", [])
        if entry.get("type") == "blob"
        and any(entry["path"].startswith(prefix + "/") for prefix in prefixes)
    ]
    empty = [p for p in prefixes if not any(b["path"].startswith(p + "/") for b in blobs)]
    if empty:
        raise ValueError(f"{len(empty)} 个前缀零命中（manifest 与提交不匹配）: {empty[:3]}")
    return blobs


def _download_one(base: str, token: str, out: Path, entry: dict) -> None:
    dest = out / entry["path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not (dest.exists() and dest.stat().st_size == entry["size"]):
            blob = fetch_json(f"{base}/git/blobs/{entry['sha']}", token)
            data = base64.b64decode(blob["content"])
            if len(data) != entry["size"]:
                raise ValueError(f"size {len(data)} != {entry['size']}")
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            if entry.get("mode") == "100755":
                os.chmod(dest, 0o755)
        with _lock:
            _state["ok"] += 1
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _state["fail"] += 1
            _state["fails"].append((entry["path"], str(exc)))
    with _lock:
        _state["done"] += 1
        if _state["done"] % 25 == 0:
            print(
                f"progress {_state['done']} ok={_state['ok']} fail={_state['fail']}",
                flush=True,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="抓取 NYU_CTF_Bench K1 20 题快照")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--sha", default=DEFAULT_SHA, help="提交 SHA（默认 4c5744f…）")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--api-base", default=DEFAULT_API, help="API 根（可换 gh-proxy 镜像）")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--tree-cache", default="", help="树清单缓存 JSON（存在则复用）")
    args = parser.parse_args(argv)

    token = os.environ.get(args.token_env, "").strip()
    prefixes = prefixes_from_manifest(Path(args.manifest))
    base = f"{args.api_base.rstrip('/')}/repos/{args.repo}"
    out = Path(args.out)

    if args.tree_cache and Path(args.tree_cache).exists():
        tree = json.loads(Path(args.tree_cache).read_text(encoding="utf-8"))
    else:
        tree = fetch_json(f"{base}/git/trees/{args.sha}?recursive=1", token)
        if args.tree_cache:
            Path(args.tree_cache).write_text(
                json.dumps(tree, ensure_ascii=False), encoding="utf-8"
            )
    if tree.get("truncated"):
        print("tree 响应被截断（recursive 超限），放弃", file=sys.stderr)
        return 2

    blobs = select_blobs(tree, prefixes)
    total_bytes = sum(b["size"] for b in blobs)
    print(
        f"prefixes={len(prefixes)} files={len(blobs)} bytes={total_bytes} "
        f"jobs={args.jobs} token={'set' if token else 'unset'}",
        flush=True,
    )

    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        list(pool.map(lambda e: _download_one(base, token, out, e), blobs))

    print(
        f"DONE ok={_state['ok']} fail={_state['fail']} elapsed={time.time() - started:.1f}s"
    )
    for path, message in _state["fails"][:10]:
        print("FAIL", path, message)
    return 0 if _state["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

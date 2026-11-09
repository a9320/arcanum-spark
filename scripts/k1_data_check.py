#!/usr/bin/env python
"""K1 题库数据前置闸（零模型、零网络）——跑批前 30 秒验题库完整。

校验三件：
1. manifest 自身 sha256 与 `scripts/k1_rescore.sh` 钉的值一致（防误用旧 manifest）；
2. `data/m8_k1_manifest.json` 里 20 个 upstream_path 全部在题库目录、且非空；
3. 给定 `--sha-list` 时逐文件比对 sha256（半截件/串版必现形）。

用法：
    python scripts/k1_data_check.py --corpus D:/nyu-backup/nyu-bench-4c5744f
    python scripts/k1_data_check.py --corpus <dir> --sha-list data/nyu_k1_20tasks.sha256
    # DSW：python scripts/k1_data_check.py --corpus /mnt/workspace/NYU_CTF_Bench

退出码：0 全绿；1 有失败项；2 用法/manifest 缺失。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "data" / "m8_k1_manifest.json"
# 与 scripts/k1_rescore.sh 的 EXPECTED_SHA 同源（改 manifest 必须同步改两处）
EXPECTED_MANIFEST_SHA = "6501ba7c8e76464a23748e9fb7ead89050d6dbb47e0c8d5dfd64d5b21c971ec4"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sha_list(path: Path) -> dict[str, str]:
    """解析 sha256sum 清单（兼容 `  ` 与 ` *` 两种分隔；路径按 posix 归一）。"""
    rows: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"清单行格式非法: {line[:80]}")
        rel = parts[1].strip().lstrip("*").lstrip("./")
        rows[rel.replace("\\", "/")] = parts[0].lower()
    return rows


def check_manifest(manifest: Path) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。"""
    errors: list[str] = []
    warnings: list[str] = []
    if not manifest.exists():
        return [f"manifest 不存在: {manifest}"], warnings
    if sha256_file(manifest) != EXPECTED_MANIFEST_SHA:
        errors.append("manifest sha256 与钉定值不一致（疑似旧版/被改动）")
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    if len(rows) != 20:
        errors.append(f"manifest 题数 {len(rows)} != 20")
    if len({str(r.get("upstream_path", "")).rstrip("/") for r in rows}) != len(rows):
        warnings.append("manifest 存在重复 upstream_path")
    return errors, warnings


def check_corpus(
    corpus: Path, manifest: Path, sha_list: Path | None
) -> tuple[list[str], list[str], list[tuple[str, int]]]:
    errors: list[str] = []
    warnings: list[str] = []
    per_task: list[tuple[str, int]] = []

    rows = json.loads(manifest.read_text(encoding="utf-8"))
    for row in rows:
        prefix = str(row.get("upstream_path") or "").rstrip("/")
        task_dir = corpus / prefix
        if not task_dir.is_dir():
            errors.append(f"缺题目录: {prefix}")
            per_task.append((prefix, 0))
            continue
        count = sum(1 for p in task_dir.rglob("*") if p.is_file())
        per_task.append((prefix, count))
        if count == 0:
            errors.append(f"题目录为空: {prefix}")

    if sha_list is not None:
        if not sha_list.exists():
            errors.append(f"sha 清单不存在: {sha_list}")
            return errors, warnings, per_task
        expected = load_sha_list(sha_list)
        missing, mismatch, seen = 0, 0, set()
        for rel, want in expected.items():
            path = corpus / rel
            if not path.is_file():
                missing += 1
                if missing <= 5:
                    errors.append(f"清单内文件缺失: {rel}")
                continue
            seen.add(rel)
            if sha256_file(path) != want:
                mismatch += 1
                if mismatch <= 5:
                    errors.append(f"内容不符: {rel}")
        if missing:
            errors.append(f"清单内文件缺失合计 {missing}")
        if mismatch:
            errors.append(f"内容不符合计 {mismatch}")
        extras = [
            str(p.relative_to(corpus)).replace("\\", "/")
            for p in corpus.rglob("*")
            if p.is_file() and str(p.relative_to(corpus)).replace("\\", "/") not in seen
        ]
        if extras:
            warnings.append(f"清单外文件 {len(extras)}（不判失败）: {sorted(extras)[:3]}")
    return errors, warnings, per_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K1 题库数据前置闸")
    parser.add_argument("--corpus", required=True, help="题库根目录（含 development/removed/test）")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--sha-list", default="", help="可选：逐文件 sha256 清单")
    parser.add_argument("--quiet", action="store_true", help="只打汇总")
    args = parser.parse_args(argv)

    corpus = Path(args.corpus)
    manifest = Path(args.manifest)
    if not corpus.is_dir():
        print(f"FAIL: 题库目录不存在: {corpus}", file=sys.stderr)
        return 2

    errors, warnings = check_manifest(manifest)
    sha_list = Path(args.sha_list) if args.sha_list else None
    corpus_errors, corpus_warnings, per_task = check_corpus(corpus, manifest, sha_list)
    errors += corpus_errors
    warnings += corpus_warnings

    if not args.quiet:
        for prefix, count in per_task:
            print(f"  {count:>5}  {prefix}")
    print(f"tasks={len(per_task)} files={sum(c for _, c in per_task)}")
    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"FAIL: {error}")
    if errors:
        return 1
    print("PASS: K1 题库数据完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

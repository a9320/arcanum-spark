#!/usr/bin/env python3
"""quickscan：批量 agent0 快扫（L1 数据扩容，零 LLM/零 GPU）。

对一批仓库目录跑 PITAX 确定性规则引擎（run_agent0），每仓产出一个
**伪 report**：{"meta": {"agent0_findings": [...]}}——与 e2e_report 的
meta.agent0_findings 同构，因此可**直接喂 `eval/replay.py synth`** 生成
回显负样本（cmd_synth 只读这一个键），零新概念接入既有链路：

    python demo/generate_demo_repo.py /mnt/workspace/repos/v1 --variant 1
    python eval/quickscan.py --repo /mnt/workspace/repos/v1 ... --out-dir /mnt/workspace/quickscan
    python eval/replay.py synth --report /mnt/workspace/quickscan/v1/pseudo_report.json \
        --out /mnt/workspace/quickscan/v1/gate_dataset_echo_neg.json
    python eval/finetune_export.py --dataset ... --out records_r1.jsonl   # 与 R0 数据合并

标签纪律：产物只含 agent0 确定性基线（铁律"结论有工具背书"），不造假假设、
不造假 KEEP——正样本（深挖/语义增量）必须来自真实 e2e 证据链（L2）。
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codeark.agents.agent0_pitax import run_agent0  # noqa: E402

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".gz", ".tar", ".whl",
                 ".pyc", ".pdf", ".woff", ".woff2", ".ttf", ".safetensors", ".bin", ".onnx"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
MAX_FILE_BYTES = 200_000


def collect_files(repo: Path, max_files: int = 300) -> dict[str, str]:
    """仓库 → {相对路径: 文本}（跳 VCS/构建/二进制/超大文件，超限截断并计数）。"""
    files: dict[str, str] = {}
    skipped = 0
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        if SKIP_DIRS & set(p.parts) or p.suffix.lower() in SKIP_SUFFIXES:
            continue
        if len(files) >= max_files:
            skipped += 1
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                skipped += 1
                continue
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped += 1
            continue
        files[p.relative_to(repo).as_posix()] = text
    if skipped:
        print(f"  [quickscan] {repo.name}: 跳过 {skipped} 个非文本/超大/超限文件")
    return files


def scan_one(repo: Path, out_dir: Path) -> dict:
    """单仓快扫 → 伪 report 落盘 → 返回摘要。"""
    files = collect_files(repo)
    findings = run_agent0(files)
    pseudo = {"meta": {"agent0_findings": findings},
              "source": str(repo), "n_files_scanned": len(files)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pseudo_report.json").write_text(
        json.dumps(pseudo, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    rules = Counter(str(f.get("rule") or f.get("type") or "?") for f in findings)
    return {"repo": repo.name, "n_files": len(files), "n_findings": len(findings),
            "rules": dict(rules), "out": str(out_dir / "pseudo_report.json")}


def main() -> int:
    ap = argparse.ArgumentParser(description="批量 agent0 快扫 → 伪 report（喂 replay synth 造回显负样本）")
    ap.add_argument("--repo", action="append", required=True, help="仓库目录，可重复（clean-repo 用于 FP=0 对照）")
    ap.add_argument("--out-dir", default="./quickscan", help="输出根目录（每仓一个子目录）")
    args = ap.parse_args()

    print(f"[quickscan] {len(args.repo)} 仓 → {args.out_dir}")
    total = 0
    for rp in args.repo:
        repo = Path(rp)
        if not repo.is_dir():
            print(f"  ⚠ 跳过不存在的仓: {repo}")
            continue
        s = scan_one(repo, Path(args.out_dir) / repo.name)
        total += s["n_findings"]
        print(f"  {s['repo']}: 文件 {s['n_files']} → 命中 {s['n_findings']}  {s['rules']}")
        print(f"    → {s['out']}")
    print(f"[quickscan] 合计命中 {total}；下一步: 对每个 pseudo_report.json 跑 "
          "`eval/replay.py synth --report <...> --out <dir>/gate_dataset_echo_neg.json`")
    return 0


if __name__ == "__main__":
    sys.exit(main())

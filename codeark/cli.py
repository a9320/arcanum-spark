"""CodeRisk Arcanum — 命令行入口。

用法：
    python -m codeark.cli <repo_dir> [--dry] [--out OUT] [--formats json,sarif,markdown]

- <repo_dir>：待扫描的仓库目录（本地路径）
- --dry：离线 dry-run（不调用 LLM，用 agent0 PITAX 基线跑通全链路；默认不启用）
- --out：报告输出目录（默认 ./reports）
- --formats：逗号分隔的格式（默认 json,sarif,markdown）

流程：读取仓库代码文件 → 6 节点 Graph → 落盘报告 + 打印风险分/命中摘要。
报告只生成到本地，不发送任何外部渠道（生成≠发布）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 让 codeark 可被直接运行（python codeark/cli.py）
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 兼容：stdout/stderr 重定向到文件或经 WSL→Windows interop 启动时，编码会退回
# 系统 ANSI 码页（GBK 等），emoji print 直接 UnicodeEncodeError → 退出码 1。
# 入口统一钉死 UTF-8；个别历史无法编码字符降级 replace，保证验证链路跨 shell 行为一致。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from graph.pipeline import run_pipeline

# 要读的代码文件扩展名
_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".rb", ".php", ".sh", ".bash", ".sql",
    ".html", ".htm", ".vue", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".txt", ".md",
}
# 跳过的目录
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}


def _read_repo(repo_dir: Path, limit_kb: int = 512) -> dict[str, str]:
    """递归读取仓库代码文件到 {相对路径: 内容}。跳过大文件与二进制。"""
    files: dict[str, str] = {}
    for p in sorted(repo_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(repo_dir)).replace("\\", "/")
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        # 无扩展名文件（如 .cursor/rules）是 AI 助手加载的高危注入面，必须纳入扫描；
        # 二进制基本都有扩展名，且下方 utf-8+strip 兜底可再滤一层
        if p.suffix and p.suffix.lower() not in _SOURCE_EXTS:
            continue
        try:
            if p.stat().st_size > limit_kb * 1024:
                continue  # 跳过超大文件
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if content.strip():
            files[rel] = content
    return files


async def _main(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        print(f"❌ Repo directory not found: {repo_dir}")
        return 1

    print(f"📂 Reading repo: {repo_dir}")
    files = _read_repo(repo_dir)
    print(f"   Read {len(files)} code files")
    if not files:
        print("   No code files read, exiting.")
        return 1

    print(f"{'🧪' if args.dry else '🤖'} Running the 6-node pipeline ({'dry-run' if args.dry else 'real LLMs'})...")
    result = await run_pipeline(files, dry=args.dry)

    # 打印摘要
    print(f"\n⚖️  Risk score: {result.risk_score}/100")
    print(f"   Agent0 PITAX hits: {len(result.agent0_findings)}")
    hyps = getattr(result.hypothesis_set, "hypotheses", [])
    print(f"   Scout hypotheses: {len(hyps)}")
    print(f"   Verify verdicts: {len(result.verifications)} (CONFIRMED={sum(1 for v in result.verifications if getattr(v,'verdict','')=='CONFIRMED')})")
    print(f"   Attack chains: {len(result.attack_chains)}")
    qs = getattr(result, "quarantine_stats", {}) or {}
    if qs:
        print(
            f"   🛡️ Prompt quarantine: {qs.get('files_changed', 0)}/{qs.get('files_total', 0)} files sanitized, "
            f"{qs.get('patterns_neutralized', 0)} injection trigger phrases neutralized, "
            f"{qs.get('chars_removed', 0)} invisible characters stripped"
        )
    if getattr(result, "deepen_failures", 0):
        print(f"   ⚠️ Deepen degradation: {result.deepen_failures} chains failed auto-derivation (disclosed as placeholders; manual review required)")
    for node, err in (getattr(result, "node_errors", {}) or {}).items():
        print(f"   ⚠️ Node degradation [{node}]: {err}")

    # 落盘报告
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    formats = [f.strip() for f in args.formats.split(",")]
    written: list[Path] = []
    for name in formats:
        if name not in result.reports:
            print(f"   ⚠️ Format not produced: {name}")
            continue
        data = result.reports[name]
        if name == "json":
            fp = out_dir / "report.json"
            fp.write_text(data, encoding="utf-8")
        elif name == "sarif":
            fp = out_dir / "report.sarif"
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        elif name == "markdown":
            fp = out_dir / "report.md"
            fp.write_text(data, encoding="utf-8")
        else:
            continue
        written.append(fp)

    print(f"\n📄 Reports written (generation ≠ publication; nothing sent externally):")
    for fp in written:
        print(f"   - {fp} ({fp.stat().st_size} B)")

    # 风险分与命中数落盘为 summary.json
    (out_dir / "summary.json").write_text(
        json.dumps({
            "risk_score": result.risk_score,
            "agent0_findings": len(result.agent0_findings),
            "hypotheses": len(hyps),
            "verifications": len(result.verifications),
            "confirmed": sum(1 for v in result.verifications if getattr(v, "verdict", "") == "CONFIRMED"),
            "attack_chains": len(result.attack_chains),
            "deepen_failures": getattr(result, "deepen_failures", 0),
            "quarantine_stats": getattr(result, "quarantine_stats", {}),
            "node_errors": getattr(result, "node_errors", {}),
            "dry_run": args.dry,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CodeRisk Arcanum — 6-agent AI vulnerability scan pipeline")
    parser.add_argument("repo", help="repository directory to scan")
    parser.add_argument("--dry", action="store_true", help="offline dry-run (no LLM calls)")
    parser.add_argument("--out", default="./reports", help="report output directory (default ./reports)")
    parser.add_argument("--formats", default="json,sarif,markdown", help="output formats, comma-separated")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    sys.exit(main())
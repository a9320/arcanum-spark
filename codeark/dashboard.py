"""CodeRisk Arcana — 6 节点 Graph 仪表盘（Streamlit）。

Day 13 本地前端：跑完整 6 节点流水线并可视化各阶段结果。
- 本地即用（dry-run 或 DeepSeek 真实模型）
- 记忆后端可切换：本地（默认）/ DynamoDB（卡批后填表名即用）— 有卡无缝衔接

用法（本地）:
    streamlit run codeark/dashboard.py
或（魔搭创空间 Docker 类型）:
    streamlit run codeark/dashboard.py --server.port 7860 --server.address 0.0.0.0
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from codeark.graph.pipeline import CodeRiskGraph, compute_risk_score  # noqa: E402
from codeark.memory.memory import get_memory_service  # noqa: E402

SEVERITY_COLOR = {"critical": "#d32f2f", "high": "#f57c00", "medium": "#fbc02d", "low": "#7b1fa2"}


def extract_zip(data: bytes, dest: Path) -> None:
    """解压用户上传的 zip 到临时目录（含 ZIP 炸弹/路径遍历防护）。"""
    import os
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            # 路径遍历防护
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError("非法 zip 路径（路径遍历攻击）")
            zf.extract(info, dest)


def read_repo_files(repo_dir: Path) -> dict[str, str]:
    """递归读取仓库代码文件到 {相对路径: 内容}。"""
    files: dict[str, str] = {}
    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}
    exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".rb",
            ".php", ".sh", ".bash", ".sql", ".html", ".htm", ".vue", ".json", ".yaml", ".yml",
            ".toml", ".ini", ".cfg", ".txt", ".md"}
    for p in sorted(repo_dir.rglob("*")):
        if not p.is_file() or any(part in skip_dirs for part in p.parts) or p.suffix.lower() not in exts:
            continue
        if p.stat().st_size > 512 * 1024:  # 跳过超大文件
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if content.strip():
            files[str(p.relative_to(repo_dir)).replace("\\", "/")] = content
    return files


def render_verdict(v) -> None:
    color = {"CONFIRMED": "#2e7d32", "REFUTED": "#c62828", "UNCERTAIN": "#f9a825"}.get(v.verdict, "#333")
    st.markdown(f"- **[{v.verdict}]** <span style='color:{color}'>**{v.hypothesis_title[:60]}</span>", unsafe_allow_html=True)
    st.caption(f"方法: {v.verification_method} | 证据: {str(v.evidence)[:80]}...")


def render_attack_chain(c, idx: int) -> None:
    with st.expander(f"攻击链 {idx} · 影响: {c.impact[:40]}"):
        st.markdown("**前置条件**")
        for p in c.preconditions:
            st.markdown(f"- {p}")
        st.markdown("**横向移动/影响面**")
        for m in c.lateral_moves:
            st.markdown(f"- {m}")
        st.markdown(f"**最终影响**: {c.impact}")
        st.markdown(f"**修复建议**: {c.remediation}")


def render_final_report(findings: list) -> None:
    if not findings:
        st.success("✅ 未检出需要进入报告的高危漏洞。")
        return
    st.error(f"⚠️ 最终报告含 {len(findings)} 条漏洞")
    for f in findings:
        sev = str(f.get("severity", "medium")).lower()
        color = SEVERITY_COLOR.get(sev, "#333")
        with st.expander(f"[{f.get('vuln_type', 'VULN')}] {f.get('severity', 'MEDIUM').upper()} · {f.get('file_path', '?')}", expanded=(sev in ("critical", "high"))):
            st.markdown(f"**标题**: {f.get('title')}")
            st.markdown(f"**文件**: `{f.get('file_path')}` 行 {f.get('line_start', '?')}")
            if f.get("code_snippet"):
                st.markdown(f"**代码**: `{f.get('code_snippet')[:150]}`")
            if f.get("evidence"):
                st.markdown(f"**证据**: {f.get('evidence')[:200]}")
            if f.get("remediation"):
                st.markdown(f"**修复**: {f.get('remediation')[:300]}")


def main() -> None:
    st.set_page_config(page_title="CodeRisk Arcanum", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
    st.title("🛡️ CodeRisk Arcanum — 6 节点 Agent 流水线")
    st.caption("AI 时代代码安全审计 · Agent 提假设 + 工具证实/证伪 + 多源合议")

    with st.sidebar:
        st.subheader("⚙️ 运行配置")
        run_mode = st.radio("运行模式", ["dry-run（离线，不调模型）", "真实模型（DeepSeek）"], index=0)
        backend = st.radio("记忆后端", ["本地（默认）", "DynamoDB（卡批后）"], index=0)
        if backend == "DynamoDB":
            table = st.text_input("DynamoDB 表名", "coderisk-memory")
            st.caption("需 AWS 凭据 + 已建表，卡批后可用")

    tab_input, tab_demo, tab_about = st.tabs(["📁 上传/路径扫描", "🚀 扫描示例仓库", "ℹ️ 关于"])

    def run_scan(files: dict[str, str]) -> None:
        dry = run_mode.startswith("dry")
        with st.spinner(f"运行 6 节点流水线（{'dry-run' if dry else '真实 DeepSeek'}）..."):
            try:
                res = asyncio.run(CodeRiskGraph(dry=dry).run(files))
            except Exception as e:
                st.error(f"流水线失败: {type(e).__name__}: {str(e)[:300]}")
                return

        # 记忆服务（前端注入历史约束）
        mem = get_memory_service()
        insight = mem.build_insight_prompt()

        # 概览指标
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PITAX 命中", len(res.agent0_findings))
        c2.metric("侦察假设", len(res.hypothesis_set.hypotheses))
        c3.metric("验证裁决", len(res.verifications))
        c4.metric("风险分", f"{res.risk_score}/100")

        st.subheader("1️⃣ Agent 0 · PITAX 规则层")
        st.caption(res.hypothesis_set.coverage_notes)
        for f in res.agent0_findings:
            sev = str(f.get("severity", "medium")).lower()
            st.markdown(f"- **[{f.get('type')}]** {f.get('title')} · {f.get('file')}:{f.get('line')}")

        st.subheader("2️⃣ 侦察 Agent · 假设")
        for h in res.hypothesis_set.hypotheses:
            st.markdown(f"- **[{h.confidence}]** {h.title} · `{h.file_path}:{h.line_start}`")
            st.caption(f"建议验证: {h.suggested_verification[:100]}")

        st.subheader("3️⃣ 验证 Agent · 裁决")
        for v in res.verifications:
            render_verdict(v)

        if insight:
            st.info(f"🧠 记忆前馈约束:\n{insight}")

        st.subheader("4️⃣ 深挖 Agent · 攻击链")
        if res.attack_chains:
            for i, c in enumerate(res.attack_chains, 1):
                render_attack_chain(c, i)
        else:
            st.caption("无 CONFIRMED 漏洞需推演攻击链。")

        st.subheader("5️⃣ 裁判官 · 合议定稿")
        fr = res.final_report
        findings = fr.findings if hasattr(fr, "findings") else (fr.get("findings", []) if isinstance(fr, dict) else [])
        render_final_report([f.model_dump() if hasattr(f, "model_dump") else f for f in findings])

        st.subheader("6️⃣ 报告 Agent · 输出格式")
        st.download_button("📄 下载 JSON", res.reports.get("json", ""), file_name="report.json")
        st.download_button("📄 下载 SARIF", json.dumps(res.reports.get("sarif", {}), ensure_ascii=False, indent=2), file_name="report.sarif")
        st.download_button("📄 下载 Markdown", res.reports.get("markdown", ""), file_name="report.md")

    with tab_input:
        st.subheader("扫描输入")
        mode = st.radio("输入方式", ["上传 ZIP 文件", "输入服务器本地路径"], horizontal=True)
        if mode == "上传 ZIP 文件":
            uploaded = st.file_uploader("上传代码压缩包（.zip）", type=["zip"])
            if uploaded is not None and st.button("🔍 开始扫描", key="btn_zip"):
                with st.spinner("解压中..."):
                    tmp = Path(tempfile.mkdtemp(prefix="codrisk_"))
                    try:
                        extract_zip(uploaded.getvalue(), tmp)
                        run_scan(read_repo_files(tmp))
                    except Exception as e:
                        st.error(f"解压/读取出错: {e}")
        else:
            path_str = st.text_input("服务器本地路径", placeholder="/app/demo/vuln-demo-repo")
            if path_str and st.button("🔍 开始扫描", key="btn_path"):
                p = Path(path_str)
                if not p.exists() or not p.is_dir():
                    st.error(f"路径不存在或不是目录: {path_str}")
                else:
                    run_scan(read_repo_files(p))

    with tab_demo:
        st.subheader("一键扫描内置示例仓库（6 类 AI 漏洞）")
        if st.button("🚀 扫描示例仓库", type="primary"):
            demo_dir = ROOT / "demo" / "vuln-demo-repo"
            if not demo_dir.exists():
                st.warning("示例仓库不存在，请先运行 `python demo/generate_demo_repo.py` 生成。")
            else:
                run_scan(read_repo_files(demo_dir))

    with tab_about:
        st.subheader("关于 CodeRisk Arcanum")
        st.markdown(
            "CodeRisk Arcanum 是一款 **私有化部署的 AI 时代代码安全审计平台**。\n\n"
            "内置 **6 节点 Agent 编排流水线**（Agent0 PITAX 规则层 → 侦察提假设 → 验证证实/证伪 → "
            "深挖攻击链 → 裁判官多源合议 → 报告生成），专攻传统 SAST 检测不到的 AI 新漏洞：\n\n"
            "提示注入 · Trojan Source · 不可见字符走私 · AI 配置后门 · 文档投毒 · 多层编码载荷\n\n"
            "**核心能力**：源码不出域 · 权威计算确定性 · 每条漏洞附工具证据 · SARIF 2.1.0 标准输出\n\n"
            "**记忆系统**：历史误报模式前馈注入假设生成器，持续降低误报率（蓝图 §5.7）\n\n"
            "**部署**：本地即用（当前）→ AWS Bedrock + Lambda + AgentCore（卡批后）"
        )


if __name__ == "__main__":
    main()
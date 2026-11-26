"""CodeRisk Arcanum — 6 节点 Graph 仪表盘（Streamlit）。

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

from codeark.graph.gate_factory import build_gate_from_env  # noqa: E402
from codeark.graph.pipeline import CodeRiskGraph, compute_risk_score  # noqa: E402
from codeark.memory.memory import get_memory_service  # noqa: E402
from codeark.models.factory import make_stage_models_from_env  # noqa: E402
from codeark.report_lang import is_en  # noqa: E402

SEVERITY_COLOR = {"critical": "#d32f2f", "high": "#f57c00", "medium": "#fbc02d", "low": "#7b1fa2"}


def extract_zip(data: bytes, dest: Path) -> None:
    """解压用户上传的 zip 到临时目录（含 ZIP 炸弹/路径遍历防护）。

    10-24 审查修复：此前 docstring 声称有炸弹防护但实现只有路径遍历检查——
    公开 demo（魔搭创空间）上传高压缩比 zip 可撑爆磁盘。补声明解压总尺寸
    与条目数上限（先验后解，超限在写盘前拒绝）。
    """
    import os
    max_total = 200 * 1024 * 1024  # 解压后合计 ≤200MB
    max_entries = 5000
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > max_entries:
            raise ValueError(f"zip entry count exceeded ({len(infos)} > {max_entries})" if is_en() else f"zip 条目数超限（{len(infos)} > {max_entries}）")
        total = sum(i.file_size for i in infos)
        if total > max_total:
            raise ValueError(f"zip total extracted size exceeded ({total} > {max_total} bytes)" if is_en() else f"zip 解压后总尺寸超限（{total} > {max_total} 字节）")
        for info in infos:
            # 路径遍历防护
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError("Illegal zip path (path traversal attack)" if is_en() else "非法 zip 路径（路径遍历攻击）")
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
    st.markdown(f"- **[{v.verdict}]** <span style='color:{color}'>**{v.hypothesis_title[:60]}**</span>", unsafe_allow_html=True)
    st.caption(f"Method: {v.verification_method} | Evidence: {str(v.evidence)[:80]}..." if is_en() else f"方法: {v.verification_method} | 证据: {str(v.evidence)[:80]}...")


def render_attack_chain(c, idx: int) -> None:
    with st.expander(f"Attack chain {idx} · Impact: {c.impact[:40]}" if is_en() else f"攻击链 {idx} · 影响: {c.impact[:40]}"):
        st.markdown("**Preconditions**" if is_en() else "**前置条件**")
        for p in c.preconditions:
            st.markdown(f"- {p}")
        st.markdown("**Lateral moves / blast radius**" if is_en() else "**横向移动/影响面**")
        for m in c.lateral_moves:
            st.markdown(f"- {m}")
        st.markdown(f"**Final impact**: {c.impact}" if is_en() else f"**最终影响**: {c.impact}")
        st.markdown(f"**Remediation**: {c.remediation}" if is_en() else f"**修复建议**: {c.remediation}")


def render_final_report(findings: list) -> None:
    if not findings:
        st.success("✅ No high-severity vulnerabilities to report." if is_en() else "✅ 未检出需要进入报告的高危漏洞。")
        return
    st.error(f"⚠️ Final report contains {len(findings)} finding(s)" if is_en() else f"⚠️ 最终报告含 {len(findings)} 条漏洞")
    for f in findings:
        sev = str(f.get("severity", "medium")).lower()
        color = SEVERITY_COLOR.get(sev, "#333")
        with st.expander(f"[{f.get('vuln_type', 'VULN')}] {f.get('severity', 'MEDIUM').upper()} · {f.get('file_path', '?')}", expanded=(sev in ("critical", "high"))):
            st.markdown(f"**Title**: {f.get('title')}" if is_en() else f"**标题**: {f.get('title')}")
            st.markdown(f"**File**: `{f.get('file_path')}` line {f.get('line_start', '?')}" if is_en() else f"**文件**: `{f.get('file_path')}` 行 {f.get('line_start', '?')}")
            if f.get("code_snippet"):
                st.markdown(f"**Code**: `{f.get('code_snippet')[:150]}`" if is_en() else f"**代码**: `{f.get('code_snippet')[:150]}`")
            if f.get("evidence"):
                st.markdown(f"**Evidence**: {f.get('evidence')[:200]}" if is_en() else f"**证据**: {f.get('evidence')[:200]}")
            if f.get("remediation"):
                st.markdown(f"**Remediation**: {f.get('remediation')[:300]}" if is_en() else f"**修复**: {f.get('remediation')[:300]}")


def main() -> None:
    st.set_page_config(page_title="CodeRisk Arcanum", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
    st.title("🛡️ CodeRisk Arcanum — 6-node Agent pipeline" if is_en() else "🛡️ CodeRisk Arcanum — 6 节点 Agent 流水线")
    st.caption("Code security audit for the AI era · Agents hypothesize + tools verify/refute + multi-source deliberation" if is_en() else "AI 时代代码安全审计 · Agent 提假设 + 工具证实/证伪 + 多源合议")

    with st.sidebar:
        st.subheader("⚙️ Run configuration" if is_en() else "⚙️ 运行配置")
        run_mode = st.radio("Run mode" if is_en() else "运行模式",
                            ["dry-run (offline, no model calls)" if is_en() else "dry-run（离线，不调模型）",
                             "Real models (per environment config)" if is_en() else "真实模型（按环境配置）"], index=0)
        backend = st.radio("Memory backend" if is_en() else "记忆后端",
                           ["Local (default)" if is_en() else "本地（默认）",
                            "DynamoDB (after card approval)" if is_en() else "DynamoDB（卡批后）"], index=0)
        if backend.startswith("DynamoDB"):  # 选项文案双语化后按前缀判（原 == 永假，table 输入框从不显示）
            table = st.text_input("DynamoDB table name" if is_en() else "DynamoDB 表名", "coderisk-memory")
            st.caption("Requires AWS credentials + an existing table; available after card approval" if is_en()
                       else "需 AWS 凭据 + 已建表，卡批后可用")

    tab_input, tab_demo, tab_about = st.tabs(["📁 Upload / path scan" if is_en() else "📁 上传/路径扫描", "🚀 Scan demo repo" if is_en() else "🚀 扫描示例仓库", "ℹ️ About" if is_en() else "ℹ️ 关于"])

    def run_scan(files: dict[str, str]) -> None:
        dry = run_mode.startswith("dry")
        with st.spinner(f"Running 6-node pipeline ({'dry-run' if dry else 'real models per environment config'})..." if is_en()
                        else f"运行 6 节点流水线（{'dry-run' if dry else '按环境配置的真实模型'}）..."):
            try:
                stage_models = None if dry else make_stage_models_from_env()
                gate, gate_meta = (None, "") if dry else build_gate_from_env()
                if not dry and gate is None:
                    st.warning(f"Hypothesis gate not mounted; continuing without gate: {gate_meta}" if is_en() else f"假设 gate 未挂载，无 gate 继续扫描: {gate_meta}")
                res = asyncio.run(
                    CodeRiskGraph(dry=dry, stage_models=stage_models, hypothesis_gate=gate).run(files)
                )
            except Exception as e:
                st.error(f"Pipeline failed: {type(e).__name__}: {str(e)[:300]}" if is_en() else f"流水线失败: {type(e).__name__}: {str(e)[:300]}")
                return

        # 记忆服务（前端注入历史约束）
        mem = get_memory_service()
        insight = mem.build_insight_prompt()

        # 概览指标
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PITAX hits" if is_en() else "PITAX 命中", len(res.agent0_findings))
        c2.metric("Scout hypotheses" if is_en() else "侦察假设", len(res.hypothesis_set.hypotheses))
        c3.metric("Verify verdicts" if is_en() else "验证裁决", len(res.verifications))
        c4.metric("Risk score" if is_en() else "风险分", f"{res.risk_score}/100")

        st.subheader("1️⃣ Agent 0 · PITAX rule layer" if is_en() else "1️⃣ Agent 0 · PITAX 规则层")
        st.caption(res.hypothesis_set.coverage_notes)
        for f in res.agent0_findings:
            sev = str(f.get("severity", "medium")).lower()
            st.markdown(f"- **[{f.get('type')}]** {f.get('title')} · {f.get('file')}:{f.get('line')}")

        st.subheader("2️⃣ Scout Agent · hypotheses" if is_en() else "2️⃣ 侦察 Agent · 假设")
        for h in res.hypothesis_set.hypotheses:
            st.markdown(f"- **[{h.confidence}]** {h.title} · `{h.file_path}:{h.line_start}`")
            st.caption(f"Suggested verification: {h.suggested_verification[:100]}" if is_en() else f"建议验证: {h.suggested_verification[:100]}")

        st.subheader("3️⃣ Verify Agent · verdicts" if is_en() else "3️⃣ 验证 Agent · 裁决")
        for v in res.verifications:
            render_verdict(v)

        if insight:
            st.info(f"🧠 Memory feed-forward constraints:\n{insight}" if is_en() else f"🧠 记忆前馈约束:\n{insight}")

        st.subheader("4️⃣ Deepen Agent · attack chains" if is_en() else "4️⃣ 深挖 Agent · 攻击链")
        if res.attack_chains:
            for i, c in enumerate(res.attack_chains, 1):
                render_attack_chain(c, i)
        else:
            st.caption("No CONFIRMED vulnerabilities require attack-chain derivation." if is_en() else "无 CONFIRMED 漏洞需推演攻击链。")

        st.subheader("5️⃣ Arbiter · final deliberation" if is_en() else "5️⃣ 裁判官 · 合议定稿")
        fr = res.final_report
        findings = fr.findings if hasattr(fr, "findings") else (fr.get("findings", []) if isinstance(fr, dict) else [])
        render_final_report([f.model_dump() if hasattr(f, "model_dump") else f for f in findings])

        st.subheader("6️⃣ Report Agent · output formats" if is_en() else "6️⃣ 报告 Agent · 输出格式")
        st.download_button("📄 Download JSON" if is_en() else "📄 下载 JSON", res.reports.get("json", ""), file_name="report.json")
        st.download_button("📄 下载 SARIF", json.dumps(res.reports.get("sarif", {}), ensure_ascii=False, indent=2), file_name="report.sarif")
        st.download_button("📄 Download Markdown" if is_en() else "📄 下载 Markdown", res.reports.get("markdown", ""), file_name="report.md")

    with tab_input:
        st.subheader("Scan input" if is_en() else "扫描输入")
        mode = st.radio("Input method" if is_en() else "输入方式",
                        ["Upload ZIP file" if is_en() else "上传 ZIP 文件",
                         "Enter server-local path" if is_en() else "输入服务器本地路径"], horizontal=True)
        if mode == ("Upload ZIP file" if is_en() else "上传 ZIP 文件"):
            uploaded = st.file_uploader("Upload code archive (.zip)" if is_en() else "上传代码压缩包（.zip）", type=["zip"])
            if uploaded is not None and st.button("🔍 Start scan" if is_en() else "🔍 开始扫描", key="btn_zip"):
                with st.spinner("Extracting..." if is_en() else "解压中..."):
                    tmp = Path(tempfile.mkdtemp(prefix="codrisk_"))
                    try:
                        extract_zip(uploaded.getvalue(), tmp)
                        run_scan(read_repo_files(tmp))
                    except Exception as e:
                        st.error(f"Extract/read error: {e}" if is_en() else f"解压/读取出错: {e}")
        else:
            path_str = st.text_input("Server-local path" if is_en() else "服务器本地路径", placeholder="/app/demo/vuln-demo-repo")
            if path_str and st.button("🔍 Start scan" if is_en() else "🔍 开始扫描", key="btn_path"):
                p = Path(path_str)
                if not p.exists() or not p.is_dir():
                    st.error(f"Path does not exist or is not a directory: {path_str}" if is_en() else f"路径不存在或不是目录: {path_str}")
                else:
                    run_scan(read_repo_files(p))

    with tab_demo:
        st.subheader("One-click scan of the bundled demo repo (6 AI vulnerability classes)" if is_en() else "一键扫描内置示例仓库（6 类 AI 漏洞）")
        if st.button("🚀 Scan demo repo" if is_en() else "🚀 扫描示例仓库", type="primary"):
            demo_dir = ROOT / "demo" / "vuln-demo-repo"
            if not demo_dir.exists():
                st.warning("Demo repo missing; run `python demo/generate_demo_repo.py` first." if is_en() else "示例仓库不存在，请先运行 `python demo/generate_demo_repo.py` 生成。")
            else:
                run_scan(read_repo_files(demo_dir))

    with tab_about:
        st.subheader("About CodeRisk Arcanum" if is_en() else "关于 CodeRisk Arcanum")
        st.markdown(
            ("CodeRisk Arcanum is a **privately deployed code-security audit platform for the AI era**.\n\n"
             "It bundles a **6-node Agent orchestration pipeline** (Agent0 PITAX rule layer → Scout hypotheses → Verify confirm/refute → "
             "Deepen attack chains → Arbiter multi-source deliberation → report generation), targeting new AI-era vulnerabilities that traditional SAST misses:\n\n"
             "prompt injection · Trojan Source · invisible-character smuggling · AI config backdoors · document poisoning · layered-encoding payloads\n\n"
             "**Core capabilities**: source code never leaves your domain · deterministic authoritative computation · tool evidence per finding · SARIF 2.1.0 output\n\n"
             "**Memory system**: historical false-positive patterns feed forward into hypothesis generation, continuously reducing false positives (blueprint §5.7)\n\n"
             "**Deployment**: local out of the box (current) → AWS Bedrock + Lambda + AgentCore (after card approval)")
            if is_en() else
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
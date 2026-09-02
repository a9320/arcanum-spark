"""
CodeRisk Arcanum — 魔搭创空间独立 Streamlit 入口
方案1 轻量版：不依赖 FastAPI/Redis/Celery/LLM，纯本地跑 PITAX 扫描。

用法（魔搭创空间 Docker 类型）:
    streamlit run streamlit_app.py --server.port 7860 --server.address 0.0.0.0
"""
import os
import sys
import tempfile
import zipfile
import shutil
import io
from pathlib import Path

import streamlit as st

# 确保项目根目录在 sys.path（app.pitax 可导入）
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pitax.sanitizer import scan_directory  # noqa: E402
from app.pitax.rules import PITAX_VERSION  # noqa: E402
from app.pitax.sarif import build_sarif  # noqa: E402

SEVERITY_COLOR = {
    "critical": "#d32f2f",
    "high": "#f57c00",
    "medium": "#fbc02d",
    "low": "#7b1fa2",
}


def scan_path(path: Path) -> tuple[list, dict]:
    """对目录跑 PITAX 扫描，返回 (findings, stats)。"""
    return scan_directory(str(path))


def extract_zip(data: bytes, dest: Path) -> None:
    """解压用户上传的 zip 到临时目录。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)


def render_findings(findings: list) -> None:
    if not findings:
        st.success("✅ 未检出 AI 提示注入类漏洞（好样的，这个仓库很干净）。")
        return
    st.error(f"⚠️ 检出 {len(findings)} 条 AI 时代漏洞")
    for f in findings:
        sev = f["severity"].lower()
        color = SEVERITY_COLOR.get(sev, "#333")
        with st.expander(
            f"[{f['type']}] {f['severity'].upper()} · {Path(f['file']).name}:{f['line']}",
            expanded=(sev in ("critical", "high")),
        ):
            st.markdown(f"**描述**: {f['description']}")
            st.markdown(f"**文件**: `{f['file']}` 行 {f['line']}")
            st.markdown(f"**证据**: `{f['pitax']['evidence']}`")
            if f["pitax"].get("decoded_payload"):
                st.markdown(f"**解码载荷**: `{f['pitax']['decoded_payload'][:200]}`")
            meta = []
            if f.get("cwe"):
                meta.append(f"CWE {f['cwe']}")
            if f.get("mitre_atlas"):
                meta.append(f"ATLAS {f['mitre_atlas']}")
            if f["pitax"].get("cve"):
                meta.append(f"CVE {f['pitax']['cve']}")
            if meta:
                st.markdown(f"**映射**: {', '.join(meta)}")
            refs = f["pitax"].get("references") or []
            if refs:
                st.markdown(f"**参考**: [{refs[0]}]({refs[0]})")
            # 展示对应源码行
            src_path = Path(f["file"])
            if src_path.exists():
                try:
                    lines = src_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    start = max(0, f["line"] - 2)
                    end = min(len(lines), f["line"] + 1)
                    st.code("\n".join(f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start=start)), language="python")
                except Exception:
                    pass


def main() -> None:
    st.set_page_config(
        page_title="CodeRisk Arcanum",
        page_icon="🛡️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("🛡️ CodeRisk Arcanum")
    st.caption("AI 时代代码安全审计 · 基于 Arcanum Prompt Injection Taxonomy (PITAX)")
    st.markdown(
        "检测 **AI 提示注入 · Trojan Source 隐藏代码 · 不可见字符走私 · 配置文件后门 · 文档投毒 · 多层编码载荷**"
    )

    tab_input, tab_demo, tab_about = st.tabs(["📁 上传代码扫描", "🚀 扫描示例仓库", "ℹ️ 关于"])

    with tab_input:
        st.subheader("上传代码仓库（zip 或直接填路径）")
        mode = st.radio("输入方式", ["上传 ZIP 文件", "输入服务器本地路径"], horizontal=True)

        if mode == "上传 ZIP 文件":
            uploaded = st.file_uploader("上传代码压缩包（.zip）", type=["zip"])
            if uploaded is not None and st.button("🔍 开始扫描", key="btn_zip"):
                with st.spinner("解压并扫描中..."):
                    tmp = Path(tempfile.mkdtemp(prefix="codrisk_"))
                    try:
                        extract_zip(uploaded.getvalue(), tmp)
                        findings, stats = scan_path(tmp)
                        st.markdown(f"*扫描 {stats['files_scanned']} 个文件，规则集 v{stats['pitax_version']}*")
                        render_findings(findings)
                    except Exception as e:
                        st.error(f"扫描出错: {e}")
        else:
            path_str = st.text_input("服务器本地路径", placeholder="/app/demo/vuln-demo-repo")
            if path_str and st.button("🔍 开始扫描", key="btn_path"):
                p = Path(path_str)
                if not p.exists() or not p.is_dir():
                    st.error(f"路径不存在或不是目录: {path_str}")
                else:
                    with st.spinner("扫描中..."):
                        findings, stats = scan_path(p)
                        st.markdown(f"*扫描 {stats['files_scanned']} 个文件，规则集 v{stats['pitax_version']}*")
                        render_findings(findings)

    with tab_demo:
        st.subheader("一键扫描内置示例仓库")
        st.markdown("内置一个**故意植入 6 类 AI 漏洞**的示例仓库，直接体验检测能力。")
        if st.button("🚀 扫描示例仓库", type="primary"):
            demo_dir = ROOT / "demo" / "vuln-demo-repo"
            if not demo_dir.exists():
                st.warning("示例仓库不存在，请先运行 `python demo/generate_demo_repo.py` 生成。")
            else:
                with st.spinner("扫描中..."):
                    findings, stats = scan_path(demo_dir)
                    st.markdown(f"*扫描 {stats['files_scanned']} 个文件，规则集 v{stats['pitax_version']}，检出 {len(findings)} 条漏洞*")
                    render_findings(findings)

    with tab_about:
        st.subheader("关于 CodeRisk Arcanum")
        st.markdown(
            "CodeRisk Arcanum 是一款 **100% 私有化部署的企业代码安全审计数字员工**。\n\n"
            "它内置四层智能体流水线（静态分析 → AI 语义理解 → 深度验证 → 报告交付），"
            "专攻 **AI 时代的新漏洞**：传统 SAST（Semgrep/CodeQL/Snyk）检测不到 "
            "AI 提示注入、Trojan Source、不可见字符、AI 配置文件后门、文档投毒、多层编码载荷。\n\n"
            "**核心能力**：源码不出域 · 本地推理 · SARIF 2.1.0 标准输出 · 每条漏洞附完整证据链\n\n"
            f"**检测规则**：Arcanum PITAX Taxonomy v{PITAX_VERSION}（9 条规则）\n\n"
            "**团队**：AI溢出安全实验室（Overflow Security Lab）"
        )


if __name__ == "__main__":
    main()
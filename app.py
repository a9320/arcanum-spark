"""
CodeRisk Arcanum — 魔搭创空间 Gradio 入口 (app.py)
当前创空间为 gradio 类型，默认入口是 app.py。
本文件调用 PITAX 引擎做 AI 代码安全审计（纯本地零依赖，不需要 LLM API / Redis / Docker）。

用法: python app.py  (魔搭 gradio 类型自动以 app.py 为入口启动)
"""
import os
import sys
import tempfile
import zipfile
import shutil
import io
from pathlib import Path

import gradio as gr

# 确保项目根目录在 sys.path（app.pitax 可导入）
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pitax.sanitizer import scan_directory  # noqa: E402
from app.pitax.rules import PITAX_VERSION  # noqa: E402

SEVERITY_LABEL = {
    "critical": "严重(Critical)",
    "high": "高危(High)",
    "medium": "中危(Medium)",
    "low": "低危(Low)",
}


def scan_path(path: Path) -> tuple[list, dict]:
    """对目录跑 PITAX 扫描，返回 (findings, stats)。"""
    return scan_directory(str(path))


def extract_zip(data: bytes, dest: Path) -> None:
    """解压用户上传的 zip 到临时目录。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)


def run_scan(zip_file):
    """Gradio 回调：接收 zip 文件，解压后扫描，返回结果文本。"""
    if zip_file is None:
        return "请先上传一个包含代码的 zip 压缩包（或点击'扫描内置示例仓库'）。"
    try:
        # 解压到临时目录
        tmp = Path(tempfile.mkdtemp(prefix="coderisk_"))
        extract_zip(zip_file, tmp)
        findings, stats = scan_path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        return f"⚠️ 扫描出错：{e}"

    if not findings:
        return "✅ 未检出 AI 提示注入类漏洞（这个仓库很干净）。"

    # 组织结果文本
    lines = [f"⚠️ 检出 {len(findings)} 条 AI 时代漏洞", "", f"扫描耗时：{stats.get('elapsed_ms', '?')}ms，扫描文件：{stats.get('files_scanned', '?')} 个", ""]
    for i, f in enumerate(findings, 1):
        sev = SEVERITY_LABEL.get(str(f.get("severity", "")).lower(), str(f.get("severity", "")))
        lines.append(f"### [{i}] {f.get('rule_id', '?')} — {f.get('title', '?')} ({sev})")
        loc = f.get("location") or {}
        path = loc.get("path", "?") if isinstance(loc, dict) else "?"
        lines.append(f"  文件: {path}  行: {loc.get('line', '?') if isinstance(loc, dict) else '?'}")
        desc = f.get("description", "")
        if desc:
            lines.append(f"  说明: {desc}")
        lines.append("")
    return "\n".join(lines)


def scan_demo():
    """扫描内置示例仓库 demo/vuln-demo-repo。"""
    demo_dir = ROOT / "demo" / "vuln-demo-repo"
    if not demo_dir.exists():
        # 尝试生成
        try:
            import subprocess
            subprocess.run([sys.executable, str(ROOT / "demo" / "generate_demo_repo.py")], check=True, cwd=str(ROOT))
        except Exception as e:
            return f"⚠️ 内置示例仓库不存在且生成失败：{e}"
        if not demo_dir.exists():
            return "⚠️ 内置示例仓库生成失败。"
    try:
        findings, stats = scan_path(demo_dir)
    except Exception as e:
        return f"⚠️ 扫描出错：{e}"
    if not findings:
        return "✅ 内置示例仓库未检出漏洞（不应出现，请检查）。"
    lines = [f"⚠️ 内置示例仓库检出 {len(findings)} 条 AI 时代漏洞", ""]
    for i, f in enumerate(findings, 1):
        sev = SEVERITY_LABEL.get(str(f.get("severity", "")).lower(), str(f.get("severity", "")))
        loc = f.get("location") or {}
        path = loc.get("path", "?") if isinstance(loc, dict) else "?"
        lines.append(f"[{i}] {f.get('rule_id', '?')} — {f.get('title', '?')} ({sev}) @ {path}:{loc.get('line', '?') if isinstance(loc, dict) else '?'}")
    return "\n".join(lines)


def build_app():
    """构建 Gradio 界面。"""
    with gr.Blocks(title="CodeRisk Arcanum", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            f"# CodeRisk Arcanum — AI 代码安全审计数字员工\n\n"
            f"专攻 AI 时代新型漏洞（提示注入、Trojan Source、不可见字符、文档投毒、多层编码载荷）。\n"
            f"检测规则：Arcanum PITAX Taxonomy v{PITAX_VERSION}（9 条规则），纯本地运行，源码不出域。"
        )
        with gr.Tab("上传代码扫描"):
            file_input = gr.File(label="上传代码压缩包 (zip)")
            scan_btn = gr.Button("开始扫描", variant="primary")
            out = gr.Markdown()
            scan_btn.click(run_scan, inputs=file_input, outputs=out)
        with gr.Tab("扫描内置示例"):
            demo_btn = gr.Button("扫描内置示例仓库（含 6 类 AI 漏洞）")
            demo_out = gr.Markdown()
            demo_btn.click(scan_demo, outputs=demo_out)
        with gr.Tab("关于"):
            gr.Markdown(
                "**CodeRisk Arcanum** 基于 [Arcanum Prompt Injection Taxonomy](https://arcanum-sec.com/pitax)（Jason Haddix）。\n\n"
                "- 静态规则 + AI 语义三重交叉验证\n"
                "- 每条漏洞附完整证据链\n"
                "- 输出 SARIF 2.1 标准报告\n"
                "- 本地 GPU/CPU 离线推理，源码不出域\n\n"
                "作品仓库：https://github.com/a9320/code-risk-arcanum"
            )
    return demo


# 魔搭 gradio 类型会执行 app.py 并期望启动一个 Gradio 应用
demo = build_app()

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
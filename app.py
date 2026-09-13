"""
CodeRisk Arcanum — ModelScope Space Gradio entry (app.py)
Gradio-type Space; app.py is the default entry file.
Runs the PITAX engine for AI-era code security auditing (fully local, zero
external dependencies — no LLM API / Redis / Docker required).

Usage: python app.py  (ModelScope gradio Spaces launch app.py automatically)
"""
import os
import sys
import tempfile
import zipfile
import shutil
import io
from pathlib import Path

import gradio as gr

# Make sure the project root is on sys.path (so app.pitax is importable)
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pitax.sanitizer import scan_directory  # noqa: E402
from app.pitax.rules import PITAX_VERSION  # noqa: E402

SEVERITY_LABEL = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}


def scan_path(path: Path) -> tuple[list, dict]:
    """Scan a directory with the PITAX engine. Returns (findings, stats)."""
    return scan_directory(str(path))


def extract_zip(data: bytes, dest: Path) -> None:
    """Extract an uploaded zip into a temp directory."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)


def _finding_fields(f: dict) -> tuple[str, str, str, str, str]:
    """Pull (rule_code, title, severity_label, file, line) from a finding dict."""
    sev = SEVERITY_LABEL.get(str(f.get("severity", "")).lower(), str(f.get("severity", "")).upper())
    code = f.get("type") or f.get("rule_id") or "?"
    title = f.get("title", "?")
    loc = f.get("location") if isinstance(f.get("location"), dict) else {}
    path = f.get("file") or loc.get("path", "?")
    line = f.get("line", loc.get("line", "?"))
    return str(code), str(title), sev, str(path), str(line)


def run_scan(zip_file):
    """Gradio callback: receive a zip, extract it, scan, return report text."""
    if zip_file is None:
        return "Please upload a code archive (.zip) first — or click 'Scan the built-in vulnerable demo'."
    try:
        tmp = Path(tempfile.mkdtemp(prefix="coderisk_"))
        extract_zip(zip_file, tmp)
        findings, stats = scan_path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:
        return f"⚠️ Scan error: {e}"

    if not findings:
        return "✅ No AI-era vulnerabilities detected — this repository looks clean."

    lines = [
        f"⚠️ Detected {len(findings)} AI-era vulnerabilities",
        "",
        f"Scanned {stats.get('files_scanned', '?')} files in {stats.get('elapsed_ms', '?')} ms",
        "",
    ]
    for i, f in enumerate(findings, 1):
        code, title, sev, path, line = _finding_fields(f)
        lines.append(f"### [{i}] {title} ({sev})")
        lines.append(f"  File: `{path}`  Line: {line}")
        desc = f.get("description", "")
        if desc:
            lines.append(f"  Details: {desc}")
        lines.append("")
    return "\n".join(lines)


def scan_demo():
    """Scan the built-in vulnerable demo repository."""
    demo_dir = ROOT / "demo" / "vuln-demo-repo"
    if not demo_dir.exists():
        try:
            import subprocess
            subprocess.run([sys.executable, str(ROOT / "demo" / "generate_demo_repo.py")], check=True, cwd=str(ROOT))
        except Exception as e:
            return f"⚠️ Built-in demo repo missing and generation failed: {e}"
        if not demo_dir.exists():
            return "⚠️ Built-in demo repo generation failed."
    try:
        findings, stats = scan_path(demo_dir)
    except Exception as e:
        return f"⚠️ Scan error: {e}"
    if not findings:
        return "✅ Built-in demo repo came back clean (unexpected — please check)."
    lines = [f"⚠️ Detected {len(findings)} AI-era vulnerabilities in the built-in demo repo", ""]
    for i, f in enumerate(findings, 1):
        code, title, sev, path, line = _finding_fields(f)
        lines.append(f"[{i}] **{title}** ({sev}) @ `{path}:{line}`")
    lines += ["", "_Deterministic PITAX rule layer — zero LLM calls, fully reproducible._"]
    return "\n".join(lines)


def build_app():
    """Build the Gradio UI."""
    with gr.Blocks(title="CodeRisk Arcanum", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            f"# CodeRisk Arcanum — AI-era code security auditor\n\n"
            f"Specialized in AI-era vulnerabilities: prompt injection, Trojan Source, "
            f"invisible-character smuggling, document poisoning, layered-encoding payloads.\n\n"
            f"Detection rules: Arcanum PITAX Taxonomy v{PITAX_VERSION} (9 rules). "
            f"Runs fully locally — your source code never leaves this Space."
        )
        with gr.Tab("Scan your code (zip)"):
            file_input = gr.File(label="Upload a code archive (.zip)")
            scan_btn = gr.Button("Start scan", variant="primary")
            out = gr.Markdown()
            scan_btn.click(run_scan, inputs=file_input, outputs=out)
        with gr.Tab("Scan the built-in demo"):
            demo_btn = gr.Button("Scan the built-in vulnerable demo repo", variant="primary")
            demo_out = gr.Markdown()
            demo_btn.click(scan_demo, outputs=demo_out)
        with gr.Tab("About"):
            gr.Markdown(
                "**CodeRisk Arcanum** is built on the [Arcanum Prompt Injection Taxonomy]"
                "(https://arcanum-sec.com/pitax) (Jason Haddix, Arcanum Information Security).\n\n"
                "- Deterministic rules + multi-source AI cross-verification\n"
                "- Every finding carries its full evidence chain\n"
                "- SARIF 2.1 standard reports\n"
                "- Runs fully locally — source code never leaves this Space\n\n"
                "Repository: https://github.com/a9320/code-risk-arcanum"
            )
    return demo


# ModelScope gradio-type Spaces execute app.py and expect a running Gradio app
demo = build_app()

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)

"""CodeRisk Cloud — Streamlit Dashboard with Local Scan support.

PATCH (DevNetwork Day 8):
- File 列改为只显示文件名（Path.name），Detail View 保留完整路径
"""
import streamlit as st
import requests
import json
import os
import time
from datetime import datetime
from pathlib import Path  # ← 新增

# ── Configuration ──
# 魔搭创空间单容器模式：localhost；docker-compose 多容器模式：api 服务名
API_BASE = os.environ.get("API_URL", "http://api:8000")
DEMO_API = f"{API_BASE}/demo"
HEALTH_API = f"{API_BASE}/health"
SCAN_LOCAL_API = f"{API_BASE}/api/v1/scan-local"
TASKS_API = f"{API_BASE}/api/v1/tasks"
REPORTS_API = f"{API_BASE}/api/v1/reports"

# ── Page Config ──
st.set_page_config(
    page_title="CodeRisk Cloud",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom Dark Theme CSS ──
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    .metric-card { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .severity-critical { color: #ef4444; font-weight: bold; }
    .severity-high { color: #f97316; font-weight: bold; }
    .severity-medium { color: #eab308; font-weight: bold; }
    .severity-low { color: #22c55e; font-weight: bold; }
    .severity-info { color: #6b7280; font-weight: bold; }
    .code-block { background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; font-family: 'SF Mono', monospace; font-size: 13px; color: #e6edf3; overflow-x: auto; }
    .task-card { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 14px; margin-bottom: 10px; }
    .task-card:hover { border-color: #58a6ff; }
    .status-completed { color: #3fb950; font-weight: 600; }
    .status-pending { color: #f0883e; }
    .status-failed { color: #ef4444; }
    .progress-bar { background-color: #21262d; border-radius: 4px; height: 6px; overflow: hidden; }
    .progress-fill { background-color: #3fb950; height: 100%; border-radius: 4px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-right: 6px; }
    .badge-critical { background: #3b1f1f; color: #ef4444; }
    .badge-high { background: #3a2d1a; color: #f97316; }
    .badge-medium { background: #3a3a1a; color: #eab308; }
    .badge-low { background: #1f3a2f; color: #22c55e; }
    .badge-info { background: #1f1f2d; color: #6b7280; }
    .section-title { color: #58a6ff; font-size: 18px; font-weight: 600; margin-bottom: 12px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
    .sidebar-brand { font-size: 22px; font-weight: 700; color: #58a6ff; margin-bottom: 4px; }
    .sidebar-sub { font-size: 12px; color: #8b949e; margin-bottom: 20px; }
    .api-status-online { color: #3fb950; font-weight: 600; }
    .api-status-offline { color: #ef4444; }
    .stButton>button { background-color: #238636; color: white; border: none; border-radius: 6px; padding: 8px 20px; font-weight: 600; }
    .stButton>button:hover { background-color: #2ea043; }
    .stTextInput>div>div>input, .stSelectbox>div>div { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

# ── Session State ──
if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "selected_task" not in st.session_state:
    st.session_state.selected_task = None
if "demo_loaded" not in st.session_state:
    st.session_state.demo_loaded = False
if "polling_since" not in st.session_state:
    st.session_state.polling_since = {}

# ── API Helpers ──
def api_get(url, timeout=10):
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code, r.json() if r.status_code == 200 else None
    except Exception as e:
        return None, str(e)

def api_post(url, payload, headers=None, timeout=10):
    try:
        h = headers or {}
        h.setdefault("Content-Type", "application/json")
        r = requests.post(url, json=payload, headers=h, timeout=timeout)
        return r.status_code, r.json() if r.status_code in (200, 201, 202) else None
    except Exception as e:
        return None, str(e)


# ── Polling Logic ──
POLL_INTERVAL = 2
POLL_TIMEOUT = 60

def poll_pending_tasks():
    """轮询所有 pending 任务的状态，返回是否更新了任何任务"""
    updated = False
    now = time.time()

    for task in st.session_state.tasks:
        if task.get("status") != "pending":
            continue

        task_id = task["task_id"]
        started = st.session_state.polling_since.get(task_id)
        if started is None:
            st.session_state.polling_since[task_id] = now
            started = now

        # 超时检查
        if now - started > POLL_TIMEOUT:
            task["status"] = "failed"
            task["error"] = "扫描超时（超过60秒）"
            updated = True
            continue

        # 获取任务状态
        api_key = st.session_state.get("api_key", "dev-key-change-in-production")
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            r = requests.get(f"{TASKS_API}/{task_id}", headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                new_status = data.get("status", "pending")
                new_progress = data.get("progress", 0)
                task["progress"] = new_progress

                if new_status == "completed":
                    task["status"] = "completed"
                    task["progress"] = 100

                    # 获取报告数据
                    try:
                        report_r = requests.get(f"{REPORTS_API}/{task_id}", headers=headers, timeout=10)
                        if report_r.status_code == 200:
                            report = report_r.json()
                            task["findings"] = report.get("findings", [])
                            task["summary"] = report.get("summary", {})
                            task["analysis"] = report.get("analysis", {})
                            task["report_urls"] = report.get("report_urls", {})
                    except Exception:
                        pass

                    # 自动选中该任务
                    st.session_state.selected_task = task_id
                    updated = True

                elif new_status == "failed":
                    task["status"] = "failed"
                    task["error"] = data.get("error", "扫描失败")
                    updated = True

                elif new_progress != task.get("progress"):
                    updated = True
        except Exception:
            pass

    return updated

# ── Load Demo Data on Startup ──
def load_demo_data():
    code, data = api_get(DEMO_API, timeout=5)
    if code == 200 and data and "findings" in data:
        task = {
            "task_id": data.get("task_id", "cr-demo-20260820-001"),
            "status": "completed",
            "progress": 100,
            "source": data.get("source", "demo"),
            "repo_url": data.get("repo_url", "https://github.com/example/flask-vulnerable-app"),
            "branch": "main",
            "summary": data.get("summary", {}),
            "findings": data.get("findings", []),
            "analysis": data.get("analysis", {}),
            "report_urls": data.get("report_urls", {}),
            "completed_at": data.get("completed_at", datetime.utcnow().isoformat() + "Z"),
            "is_demo": True,
        }
        existing_ids = {t["task_id"] for t in st.session_state.tasks}
        if task["task_id"] not in existing_ids:
            st.session_state.tasks.insert(0, task)
        st.session_state.demo_loaded = True
        return True
    return False

if not st.session_state.demo_loaded:
    load_demo_data()

# ── Detect Local Repos ──
def get_local_repos():
    """Scan /repos/ for available directories."""
    repos = []
    repos_base = "/repos"
    if os.path.isdir(repos_base):
        for d in os.listdir(repos_base):
            full = os.path.join(repos_base, d)
            if os.path.isdir(full):
                repos.append(full)
    return repos

# ── Sidebar ──
with st.sidebar:
    st.markdown('<div class="sidebar-brand">🛡️ CodeRisk Cloud</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">AI-Powered Code Security</div>', unsafe_allow_html=True)

    status_code, _ = api_get(HEALTH_API, timeout=3)
    if status_code == 200:
        st.markdown('<div class="api-status-online">● API Online</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="api-status-offline">● API Offline</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Quick Links**")
    st.link_button("📘 API Docs", f"{API_BASE}/docs", use_container_width=True)
    st.link_button("💻 GitHub Repo", "https://github.com/a9320/coderisk-cloud", use_container_width=True)
    st.link_button("📑 Nutrient DWS", "https://www.nutrient.io/", use_container_width=True)
    st.markdown("---")
    st.caption("DevNetwork 2026 · AI溢出安全实验室")

# ── Main: Submit Form ──
st.markdown('<div class="section-title">Submit New Analysis</div>', unsafe_allow_html=True)

# Scan Mode selector
scan_mode = st.radio("Scan Mode", ["GitHub", "Local"], horizontal=True)

api_key = st.text_input("API Key", value="dev-key-change-in-production", type="password")
st.session_state["api_key"] = api_key

if scan_mode == "GitHub":
    col_form1, col_form2, col_form3 = st.columns([3, 1, 1])
    with col_form1:
        repo_url = st.text_input("Repository URL", placeholder="https://github.com/user/repo", label_visibility="collapsed")
    with col_form2:
        branch = st.text_input("Branch", value="main", label_visibility="collapsed")
    with col_form3:
        output_fmt = st.selectbox("Output", ["json", "sarif", "pdf"], label_visibility="collapsed")

    if st.button("🚀 Start Analysis", use_container_width=False):
        if not repo_url:
            st.error("Please enter a repository URL")
        else:
            payload = {
                "source": "github",
                "repo_url": repo_url,
                "branch": branch,
                "output_formats": [output_fmt] if output_fmt != "pdf" else ["json", "sarif", "pdf"],
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            code, resp = api_post(f"{API_BASE}/api/v1/analyze", payload, headers)
            if code == 200 and resp:
                st.success(f"Analysis queued! Task ID: `{resp.get('task_id')}`")
                task_id = resp.get('task_id')
                st.session_state.tasks.insert(0, {
                    "task_id": task_id,
                    "status": resp.get("status", "pending"),
                    "progress": 0,
                    "source": "github",
                    "repo_url": repo_url,
                    "branch": branch,
                    "summary": {},
                    "findings": [],
                    "analysis": {},
                    "report_urls": {},
                    "is_demo": False,
                })
                st.session_state.polling_since[task_id] = time.time()
            else:
                st.error(f"Failed: {resp or 'Unknown error'}")

else:  # Local scan mode
    local_repos = get_local_repos()

    if not local_repos:
        st.warning("No local repositories found in /repos/. Please mount a directory.")
        local_path = st.text_input("Local Path (manual)", value="/repos/Damn-Vulnerable-Flask-Application")
    else:
        local_path = st.selectbox("Select Local Repository", local_repos)

    output_fmt_local = st.selectbox("Output Format", ["json", "sarif", "pdf"], key="local_output")

    if st.button("🚀 Start Local Scan", use_container_width=False):
        if not local_path:
            st.error("Please select or enter a local path")
        else:
            payload = {
                "local_path": local_path,
                "output_formats": [output_fmt_local] if output_fmt_local != "pdf" else ["json", "sarif", "pdf"],
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            code, resp = api_post(SCAN_LOCAL_API, payload, headers)
            if code == 200 and resp:
                st.success(f"Local scan queued! Task ID: `{resp.get('task_id')}`")
                task_id = resp.get('task_id')
                st.session_state.tasks.insert(0, {
                    "task_id": task_id,
                    "status": resp.get("status", "pending"),
                    "progress": 0,
                    "source": "local",
                    "repo_url": local_path,
                    "branch": "N/A",
                    "summary": {},
                    "findings": [],
                    "analysis": {},
                    "report_urls": {},
                    "is_demo": False,
                })
                st.session_state.polling_since[task_id] = time.time()
            else:
                st.error(f"Failed: {resp or 'Unknown error'}")

st.markdown("---")

# ── Two-Column Layout: Tasks | Report ──
col_tasks, col_report = st.columns([2, 3])

# ── Left: Analysis Tasks ──
with col_tasks:
    st.markdown('<div class="section-title">Analysis Tasks</div>', unsafe_allow_html=True)

    if not st.session_state.tasks:
        st.info("No tasks yet. Submit an analysis above or wait for demo data to load.")
    else:
        for task in st.session_state.tasks:
            tid = task["task_id"]
            status = task.get("status", "pending")
            progress = task.get("progress", 0)
            summary = task.get("summary", {})
            is_selected = st.session_state.selected_task == tid

            status_class = "status-completed" if status == "completed" else ("status-failed" if status == "failed" else "status-pending")
            status_icon = "✅" if status == "completed" else ("❌" if status == "failed" else "⏳")

            badges = ""
            if summary:
                for sev, color_class in [("critical", "badge-critical"), ("high", "badge-high"),
                                          ("medium", "badge-medium"), ("low", "badge-low"), ("info", "badge-info")]:
                    count = summary.get(sev, 0)
                    if count > 0:
                        badges += f'<span class="badge {color_class}">{sev.upper()} {count}</span>'

            demo_badge = '<span class="badge" style="background:#1a3a5c;color:#58a6ff;">DEMO</span>' if task.get("is_demo") else ""
            source_badge = f'<span class="badge" style="background:#1f2d1a;color:#3fb950;">{task.get("source","").upper()}</span>'

            if st.button(f"View {tid[:16]}...", key=f"btn_{tid}", use_container_width=True):
                st.session_state.selected_task = tid
                st.rerun()

            st.markdown(f"""
            <div class="task-card">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div style="font-weight:600;font-size:14px;color:#e6edf3;">{tid[:20]}...</div>
                    <div>{demo_badge} {source_badge}</div>
                </div>
                <div style="font-size:12px;color:#8b949e;margin-bottom:6px;">{task.get('repo_url','')[:40]}</div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <div class="{status_class}">{status_icon} {status.upper()}</div>
                    <div style="font-size:12px;color:#8b949e;">{task.get('branch','main')}</div>
                </div>
                <div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>
                <div style="margin-top:8px;">{badges}</div>
            </div>
            """, unsafe_allow_html=True)

# ── Right: Report Preview ──
with col_report:
    st.markdown('<div class="section-title">Report Preview</div>', unsafe_allow_html=True)

    selected = None
    if st.session_state.selected_task:
        selected = next((t for t in st.session_state.tasks if t["task_id"] == st.session_state.selected_task), None)

    if not selected:
        st.info("Select a task from the left to view the report.")
    else:
        task = selected
        summary = task.get("summary", {})
        findings = task.get("findings", [])
        analysis = task.get("analysis", {})

        # Summary Cards
        st.markdown("**Vulnerability Summary**")
        c1, c2, c3, c4, c5 = st.columns(5)
        sev_data = [
            ("🔴 Critical", summary.get("critical", 0), "#ef4444"),
            ("🟠 High", summary.get("high", 0), "#f97316"),
            ("🟡 Medium", summary.get("medium", 0), "#eab308"),
            ("🟢 Low", summary.get("low", 0), "#22c55e"),
            ("⚪ Info", summary.get("info", 0), "#6b7280"),
        ]
        for col, (label, count, color) in zip([c1, c2, c3, c4, c5], sev_data):
            with col:
                st.markdown(f"""
                <div style="text-align:center;padding:10px;background:#161b22;border:1px solid #30363d;border-radius:8px;">
                    <div style="font-size:24px;font-weight:700;color:{color};">{count}</div>
                    <div style="font-size:11px;color:#8b949e;">{label}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

        # Findings Table
        st.markdown("**Findings**")
        if findings:
            import pandas as pd
            table_data = []
            for f in findings:
                sev = f.get("severity", "info").lower()
                sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "⚪"}.get(sev, "⚪")
                # PATCH: File 列只显示文件名，避免长路径截断
                file_path = f.get("file", "")
                file_name = Path(file_path).name if file_path else ""
                table_data.append({
                    "ID": f.get("id", ""),
                    "Severity": f"{sev_emoji} {sev.upper()}",
                    "Category": f.get("category", f.get("type", "")),
                    "File": file_name,  # ← 只显示文件名
                    "Line": f.get("line", ""),
                    "Confidence": f"{f.get('confidence', 0)*100:.0f}%",
                    "Agent": f.get("agent", ""),
                })
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Detail Expansion
            st.markdown("**Detail View**")
            finding_ids = [f"{f.get('id','')} — {f.get('category','')}" for f in findings]
            selected_finding = st.selectbox("Select a finding", finding_ids)
            if selected_finding:
                idx = finding_ids.index(selected_finding)
                f = findings[idx]

                col_d1, col_d2 = st.columns([1, 1])
                with col_d1:
                    st.markdown(f"**ID:** `{f.get('id')}`")
                    st.markdown(f"**Severity:** <span class='severity-{f.get('severity','info').lower()}'>{f.get('severity','').upper()}</span>", unsafe_allow_html=True)
                    st.markdown(f"**Category:** {f.get('category', f.get('type', ''))}")
                    st.markdown(f"**CWE:** {f.get('cwe', 'N/A')}")
                    st.markdown(f"**Confidence:** {f.get('confidence', 0)*100:.0f}%")
                    st.markdown(f"**Agent:** `{f.get('agent', '')}`")
                with col_d2:
                    st.markdown(f"**File:** `{f.get('file')}`:{f.get('line')}")  # ← Detail View 保留完整路径
                    st.markdown("**Code Snippet:**")
                    snippet = f.get("code_snippet", "N/A")
                    st.markdown(f'<div class="code-block">{snippet}</div>', unsafe_allow_html=True)

                st.markdown("**Description:**")
                st.markdown(f.get("description", "N/A"))
                st.markdown("**Recommendation:**")
                st.info(f.get("recommendation", "N/A"))
        else:
            st.info("No findings available for this task.")

        # Analysis Stats
        if analysis:
            st.markdown("---")
            st.markdown("**Analysis Metadata**")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                st.metric("Duration", f"{analysis.get('duration_seconds', 0)}s")
            with s2:
                st.metric("Agents Used", analysis.get("agents_used", 0))
            with s3:
                st.metric("Files Scanned", analysis.get("files_scanned", 0))
            with s4:
                st.metric("Lines of Code", f"{analysis.get('lines_of_code', 0):,}")

        # Report Downloads
        report_urls = task.get("report_urls", {})
        if report_urls:
            st.markdown("---")
            st.markdown("**Downloads**")
            dl_cols = st.columns(3)
            with dl_cols[0]:
                if report_urls.get("json"):
                    st.link_button("📄 JSON", f"{API_BASE}{report_urls['json']}", use_container_width=True)
            with dl_cols[1]:
                if report_urls.get("sarif"):
                    st.link_button("📊 SARIF", f"{API_BASE}{report_urls['sarif']}", use_container_width=True)
            with dl_cols[2]:
                if report_urls.get("pdf"):
                    st.link_button("📑 PDF", f"{API_BASE}{report_urls['pdf']}", use_container_width=True)
                else:
                    st.button("📑 PDF", disabled=True, use_container_width=True)

# ── Footer ──

# ── Auto-polling: 有 pending 任务时自动刷新 ──
has_pending = any(t.get("status") == "pending" for t in st.session_state.tasks)
if has_pending:
    updated = poll_pending_tasks()
    if updated:
        st.rerun()
    else:
        time.sleep(POLL_INTERVAL)
        st.rerun()

st.markdown("---")
st.caption("CodeRisk Cloud v1.0.0 · DevNetwork 2026 · AI溢出安全实验室")

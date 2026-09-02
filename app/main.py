"""CodeRisk Cloud — FastAPI 主应用"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import redis
from fastapi import FastAPI, Header, HTTPException, Request, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Annotated, Optional

from app.config import settings
from app.models import (
    AnalyzeRequest, AnalyzeResponse, ErrorResponse,
    ReportResponse, TaskResponse, TaskStatus,
)
from app.tasks import analyze_codebase_task, celery_app

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("coderisk.cloud.api")

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="AI-powered code security API with local GPU inference",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

r = redis.from_url(settings.REDIS_URL, decode_responses=True)


def verify_api_key(authorization: str | None = Header(None)):
    """验证 API Key（防时序攻击）"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "").strip()
    if not hmac.compare_digest(token, settings.API_KEY):
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return token


@app.post(f"{settings.API_PREFIX}/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest, authorization: str | None = Header(None)):
    verify_api_key(authorization)
    if request.source == "github" and not request.repo_url:
        raise HTTPException(status_code=400, detail="repo_url required when source=github")
    if request.source == "direct_upload" and not request.files:
        raise HTTPException(status_code=400, detail="files required when source=direct_upload")

    task_id = f"cr-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    meta = {
        "task_id": task_id,
        "source": request.source,
        "repo_url": request.repo_url,
        "branch": request.branch,
        "files": request.files,
        "output_formats": request.output_formats,
        "callback_url": request.callback_url,
        "created_at": datetime.now().isoformat(),
        "api_key_hash": hashlib.sha256(authorization.encode()).hexdigest()[:16],
    }
    r.set(f"task:{task_id}:meta", json.dumps(meta), ex=86400)
    r.set(f"task:{task_id}:status", json.dumps({
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "agent_status": {},
        "updated_at": datetime.now().isoformat(),
    }), ex=86400)

    analyze_codebase_task.delay(task_id, meta)
    logger.info(f"[{task_id}] Analysis task created, source={request.source}")
    return AnalyzeResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message=f"Analysis task created. Use GET {settings.API_PREFIX}/tasks/{task_id} to check progress."
    )


@app.get(f"{settings.API_PREFIX}/tasks/{{task_id}}", response_model=TaskResponse)
async def get_task_status(task_id: str, authorization: str | None = Header(None)):
    verify_api_key(authorization)
    status_data = r.get(f"task:{task_id}:status")
    if not status_data:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    data = json.loads(status_data)
    return TaskResponse(
        task_id=data["task_id"],
        status=TaskStatus(data["status"]),
        progress=data.get("progress", 0),
        agent_status=data.get("agent_status", {}),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        error=data.get("error"),
    )


@app.get(f"{settings.API_PREFIX}/reports/{{task_id}}", response_model=ReportResponse)
async def get_report(task_id: str, authorization: str | None = Header(None)):
    verify_api_key(authorization)

    # 报告隔离校验
    meta_raw = r.get(f"task:{task_id}:meta")
    if not meta_raw:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    meta = json.loads(meta_raw)
    current_key_hash = hashlib.sha256(authorization.encode()).hexdigest()[:16]
    if meta.get("api_key_hash") != current_key_hash:
        raise HTTPException(status_code=403, detail="Access denied for this report")

    status_data = r.get(f"task:{task_id}:status")
    if not status_data:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    data = json.loads(status_data)
    if data["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Task not completed. Current status: {data['status']}")

    report_path = settings.REPORTS_DIR / f"{task_id}.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    report = json.loads(report_path.read_text(encoding="utf-8"))

    return ReportResponse(
        task_id=task_id,
        summary=report.get("summary", {}),
        findings=report.get("findings", []),
        report_urls={
            "json": f"/reports/{task_id}/report.json",
            "sarif": f"/reports/{task_id}/report.sarif" if "sarif_path" in report else None,
            "pdf": f"/reports/{task_id}/report.pdf" if "pdf_path" in report else None,
        },
        digital_signature=report.get("digital_signature"),
        completed_at=report.get("generated_at"),
    )


@app.post(f"{settings.API_PREFIX}/webhooks/github")
async def github_webhook(request: Request, x_hub_signature: str | None = Header(None)):
    """接收 GitHub Push Webhook，自动触发分析"""
    payload = await request.body()

    # 验证 Webhook 签名
    if not x_hub_signature:
        raise HTTPException(status_code=401, detail="Webhook signature required (X-Hub-Signature-256 header missing)")
    if settings.GITHUB_WEBHOOK_SECRET:
        expected = "sha256=" + hmac.new(
            settings.GITHUB_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        logger.warning("GitHub Webhook received without signature verification (GITHUB_WEBHOOK_SECRET not set)")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    repo_url = data.get("repository", {}).get("clone_url")
    ref = data.get("ref", "refs/heads/main")
    branch = ref.replace("refs/heads/", "")

    if not repo_url:
        raise HTTPException(status_code=400, detail="Missing repository URL")

    # 复用 analyze 逻辑
    task_id = f"cr-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    meta = {
        "task_id": task_id,
        "source": "github",
        "repo_url": repo_url,
        "branch": branch,
        "output_formats": ["json", "sarif"],
        "callback_url": None,
        "created_at": datetime.now().isoformat(),
        "api_key_hash": "webhook",
    }
    r.set(f"task:{task_id}:meta", json.dumps(meta), ex=86400)
    r.set(f"task:{task_id}:status", json.dumps({
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "agent_status": {},
        "updated_at": datetime.now().isoformat(),
    }), ex=86400)

    analyze_codebase_task.delay(task_id, meta)
    logger.info(f"[{task_id}] GitHub webhook triggered analysis for {repo_url}")
    return {"task_id": task_id, "status": "pending", "message": "Webhook analysis started"}


@app.get("/health")
async def health():
    """健康检查：Redis + Celery Worker + GPU"""
    checks = {"redis": False, "celery_worker": False, "gpu": False}

    # Redis
    try:
        r.ping()
        checks["redis"] = True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")

    # Celery Worker
    try:
        inspector = celery_app.control.inspect()
        active = inspector.active()
        checks["celery_worker"] = bool(active)
    except Exception as e:
        logger.warning(f"Celery health check failed: {e}")

    # GPU（ROCm）
    try:
        import subprocess
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "VRAM"],
            capture_output=True,
            timeout=5,
        )
        checks["gpu"] = result.returncode == 0
    except Exception:
        pass

    # GPU 是可选项，不影响整体健康状态
    core_ok = checks["redis"] and checks["celery_worker"]
    status_code = 200 if core_ok else 503

    return JSONResponse(
        {
            "status": "ok" if core_ok else "degraded",
            "checks": checks,
            "version": settings.API_VERSION,
        },
        status_code=status_code,
    )


@app.get(f"{settings.API_PREFIX}/reports/{{task_id}}/pdf")
async def download_report_pdf(task_id: str, authorization: str | None = Header(None)):
    """下载 PDF 报告文件"""
    verify_api_key(authorization)

    # 报告隔离校验
    meta_raw = r.get(f"task:{task_id}:meta")
    if not meta_raw:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    meta = json.loads(meta_raw)
    current_key_hash = hashlib.sha256(authorization.encode()).hexdigest()[:16]
    if meta.get("api_key_hash") != current_key_hash:
        raise HTTPException(status_code=403, detail="Access denied for this report")

    pdf_path = settings.REPORTS_DIR / f"{task_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF report not found. Ensure output_formats includes 'pdf'.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"coderisk-report-{task_id}.pdf",
    )


# ── 静态文件挂载：/reports 目录直接可访问 ──
app.mount("/reports", StaticFiles(directory=str(settings.REPORTS_DIR)), name="reports")


@app.post(f"{settings.API_PREFIX}/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(
    file: UploadFile = File(..., description="ZIP archive containing source code to analyze"),
    output_formats: str = Form("json,sarif,pdf", description="Comma-separated output formats"),
    callback_url: Optional[str] = Form(None, description="Optional callback URL when analysis completes"),
    authorization: Optional[str] = Header(None),
):
    """
    上传 ZIP 文件进行代码安全分析。

    文件要求：
    - 格式：.zip
    - 大小：≤ 100 MB
    - 内容：解压后 ≤ 100 MB，文件数 ≤ 10,000
    """
    verify_api_key(authorization)

    # 验证文件名
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only ZIP files are supported (.zip)")

    # 读取并限制大小（100MB）
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {e}")

    MAX_ZIP_SIZE = 100 * 1024 * 1024  # 100 MB
    if len(content) > MAX_ZIP_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size {len(content)} bytes exceeds limit of {MAX_ZIP_SIZE} bytes (100MB)",
        )

    # 生成 task_id
    task_id = f"cr-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"

    # 保存 ZIP 到 uploads 目录
    upload_dir = settings.REPORTS_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    zip_path = upload_dir / f"{task_id}.zip"
    try:
        zip_path.write_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # 解析输出格式
    formats = [f.strip().lower() for f in output_formats.split(",") if f.strip()]
    valid_formats = {"json", "sarif", "pdf"}
    invalid = set(formats) - valid_formats
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid output formats: {invalid}. Valid: {valid_formats}")

    # 构建 meta
    meta = {
        "task_id": task_id,
        "source": "zip",
        "zip_path": str(zip_path),
        "original_filename": file.filename,
        "output_formats": formats,
        "callback_url": callback_url,
        "created_at": datetime.now().isoformat(),
        "api_key_hash": hashlib.sha256(authorization.encode()).hexdigest()[:16],
    }

    # 写入 Redis
    r.set(f"task:{task_id}:meta", json.dumps(meta), ex=86400)
    r.set(f"task:{task_id}:status", json.dumps({
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "agent_status": {},
        "updated_at": datetime.now().isoformat(),
    }), ex=86400)

    # 触发 Celery
    analyze_codebase_task.delay(task_id, meta)
    logger.info(f"[{task_id}] ZIP upload analysis started, file={file.filename}, size={len(content)} bytes")

    return AnalyzeResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message=f"ZIP upload accepted. Analysis task created. Use GET {settings.API_PREFIX}/tasks/{task_id} to check progress.",
    )


@app.get("/")
async def root():
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "docs": "/docs",
        "health": "/health",
        "demo": "/demo",
    }


@app.get("/demo")
async def demo():
    """Demo endpoint — 返回一份预置的示例扫描结果，无需 API Key"""
    from app.demo_fixture import DEMO_REPORT
    return DEMO_REPORT


# ── LOCAL SCAN ENDPOINT (DevNetwork Day 5) ──
@app.post("/api/v1/scan-local")
async def scan_local(request: Request, authorization: str | None = Header(None)):
    """扫描本地目录（Docker 环境无法访问 GitHub 时使用）

    Body: {"local_path": "/repos/Damn-Vulnerable-Flask-Application"}
    """
    import os
    verify_api_key(authorization)

    body = await request.json()
    local_path = body.get("local_path", "").strip()

    if not local_path:
        raise HTTPException(status_code=400, detail="local_path is required")

    # 安全校验：三层防护
    normalized = os.path.normpath(local_path)
    if ".." in normalized.split(os.sep):
        raise HTTPException(status_code=400, detail="Path traversal detected")
    if not normalized.startswith("/repos/"):
        raise HTTPException(status_code=400, detail="Path must be under /repos/")
    if not os.path.isdir(normalized):
        raise HTTPException(status_code=400, detail=f"Directory does not exist: {normalized}")

    task_id = f"cr-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    formats = body.get("output_formats", ["json"])

    meta = {
        "task_id": task_id,
        "source": "local",
        "local_path": normalized,
        "output_formats": formats,
        "callback_url": None,
        "created_at": datetime.now().isoformat(),
        "api_key_hash": hashlib.sha256(authorization.encode()).hexdigest()[:16],
    }
    r.set(f"task:{task_id}:meta", json.dumps(meta), ex=86400)
    r.set(f"task:{task_id}:status", json.dumps({
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "agent_status": {},
        "updated_at": datetime.now().isoformat(),
    }), ex=86400)

    analyze_codebase_task.delay(task_id, meta)
    logger.info(f"[{task_id}] Local scan started, path={normalized}")

    return AnalyzeResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message=f"Local scan queued. Use GET /api/v1/tasks/{task_id} to check progress.",
    )

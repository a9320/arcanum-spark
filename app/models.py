"""CodeRisk Cloud — Pydantic 数据模型"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# 请求模型
# ──────────────────────────────────────────────────────────────

class CodeSource(str, Enum):
    """代码来源类型"""
    GITHUB = "github"
    ZIP = "zip"
    DIRECT_UPLOAD = "direct_upload"


class AnalyzeRequest(BaseModel):
    """分析请求"""
    source: CodeSource = Field(
        default=CodeSource.DIRECT_UPLOAD,
        description="代码来源: github / zip / direct_upload",
    )
    repo_url: Optional[str] = Field(
        default=None,
        description="GitHub 仓库 URL（source=github 时必填）",
    )
    branch: str = Field(
        default="main",
        description="Git 分支",
    )
    callback_url: Optional[str] = Field(
        default=None,
        description="分析完成后的回调 URL",
    )
    files: Optional[list[dict[str, str]]] = Field(
        default=None,
        description=(
            "source=direct_upload 时必填："
            '[{"path": "src/main.py", "content": "..."}]，'
            "≤200 个文件，单文件 ≤1MB，总量 ≤10MB"
        ),
    )
    output_formats: list[str] = Field(
        default=["json", "sarif"],
        description="输出格式: json / sarif / pdf",
    )


class QuickscanRequest(BaseModel):
    """同步快扫请求（确定性 PITAX，秒级，无队列/Redis 依赖）"""
    text: str = Field(description="待扫描文本内容（≤200k 字符）")
    filename: str = Field(
        default="pasted_input.md",
        description=(
            "文件名提示，决定规则路由：AGENTS.md/CLAUDE.md/.cursor/rules → T-46（AI 配置后门）；"
            "*.md → N-06（文档投毒）；源码扩展名 → T-51（注释指令覆盖）"
        ),
    )


# ──────────────────────────────────────────────────────────────
# 响应模型
# ──────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    ANALYZING = "analyzing"
    VERIFYING = "verifying"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(BaseModel):
    """各 Agent 的执行状态"""
    agent_0_sanitizer: str = "pending"
    agent_1_static: str = "pending"
    agent_2_semantic: str = "pending"
    agent_3_verifier: str = "pending"
    agent_4_report: str = "pending"


class TaskResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: TaskStatus
    progress: int = Field(ge=0, le=100, description="进度百分比")
    agent_status: AgentStatus = Field(default_factory=AgentStatus)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    error: Optional[str] = None


class FindingSummary(BaseModel):
    """漏洞摘要"""
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class ReportURLs(BaseModel):
    """报告下载链接"""
    json_url: Optional[str] = Field(default=None, alias="json")
    sarif_url: Optional[str] = Field(default=None, alias="sarif")
    pdf_url: Optional[str] = Field(default=None, alias="pdf")

    model_config = {"populate_by_name": True}


class ReportResponse(BaseModel):
    """报告响应"""
    task_id: str
    summary: FindingSummary = Field(default_factory=FindingSummary)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    ai_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="PITAX AI 漏洞（Agent 0 检出，带 PITAX 编号/映射/参考链接）",
    )
    ai_findings_count: int = 0
    output_guardrail: Optional[dict[str, Any]] = None
    report_urls: ReportURLs = Field(default_factory=ReportURLs)
    digital_signature: Optional[str] = None
    completed_at: Optional[str] = None


class QuickscanResponse(BaseModel):
    """同步快扫响应（findings 与 Agent 0 报告字段同构，可直接复用渲染）"""
    findings_count: int = 0
    scan_ms: int = 0
    pitax_version: str = ""
    filename: str = ""
    severity_summary: dict[str, int] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """分析请求响应"""
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    message: str = "Analysis task created successfully"


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None

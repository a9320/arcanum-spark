"""CodeRisk Cloud — Celery 任务定义"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import shutil
import sys
import tempfile
import zipfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import redis
from celery import Celery

from app.config import settings
from app.nutrient_client import NutrientDWSClient
from app.agents.sanitizer_agent import run_agent0  # Agent 0: PITAX 预扫描 (Arcanum)
from app.prompt_guard import guard_report          # 主线 A: 输出护栏
from app.pitax.sarif import build_sarif            # SARIF 2.1.0 + PITAX 元数据

# ── 日志 ──
logger = logging.getLogger("coderisk.cloud.tasks")

# ── 模块级 Redis 连接池 ──
_redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, max_connections=20)


def _get_redis():
    return redis.Redis(connection_pool=_redis_pool)


# ── Celery 应用 ──
celery_app = Celery(
    "coderisk",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=settings.WORKER_CONCURRENCY,
    task_time_limit=1800,      # 硬限制 30 分钟
    task_soft_time_limit=1500,   # 软限制 25 分钟，优雅收尾
)

# ── CodeRisk 引擎（内置 engine/，路径注入在 app.config 模块级完成）──

_static_analyzer = None
_semantic_analyzer = None
_deep_verifier = None
_llm_client = None


def _get_llm_client():
    """Lazy-init LLM client (may be None if not configured)."""
    global _llm_client
    if _llm_client is None:
        try:
            from core.llm_client import LLMClient
            _llm_client = LLMClient()
        except Exception:
            _llm_client = None
    return _llm_client


def _get_static_analyzer():
    global _static_analyzer
    if _static_analyzer is None:
        from agents.static_analyzer import StaticAnalyzer
        _static_analyzer = StaticAnalyzer()
    return _static_analyzer


def _get_semantic_analyzer():
    global _semantic_analyzer
    if _semantic_analyzer is None:
        from agents.semantic_analyzer import SemanticAnalyzer
        llm = _get_llm_client()
        if llm is None:
            return None
        _semantic_analyzer = SemanticAnalyzer(llm)
    return _semantic_analyzer


def _get_deep_verifier():
    global _deep_verifier
    if _deep_verifier is None:
        from agents.deep_verifier import DeepVerifier
        from core.memory import MemoryLayer
        from core.cve_client import CVEClient
        llm = _get_llm_client()
        _deep_verifier = DeepVerifier(
            llm_client=llm,
            memory=MemoryLayer(),
            cve_client=CVEClient(),
        )
    return _deep_verifier


# ═══════════════════════════════════════════════════════════════
# Cloud 层 ↔ 引擎层 数据模型转换（Kimi v33 集成）
# ═══════════════════════════════════════════════════════════════

def _scan_code_files(work_dir: str) -> list:
    """扫描工作目录，收集所有支持的代码文件为 CodeFile 对象"""
    try:
        from core.models import CodeFile
    except ImportError as e:
        logger.error(f"Cannot import CodeFile from engine: {e}")
        return []

    code_files = []
    work_path = Path(work_dir)
    extensions = (".c", ".h", ".py")

    for ext in extensions:
        for file_path in work_path.rglob(f"*{ext}"):
            if not file_path.is_file():
                continue
            try:
                code_file = CodeFile.from_path(file_path)
                code_files.append(code_file)
            except Exception as e:
                logger.debug(f"Skipping file {file_path}: {e}")
                continue

    logger.info(f"Scanned {len(code_files)} code files from {work_dir}")
    return code_files


def _dict_to_risk(finding: dict):
    """将 API 层的 dict finding 转换为引擎层的 Risk 对象"""
    from core.models import Risk, Severity, Confidence, Language, Evidence

    severity_str = str(finding.get("severity", "info")).lower()
    try:
        severity = Severity(severity_str)
    except ValueError:
        severity = Severity.INFO

    conf_raw = finding.get("confidence", 50)
    if isinstance(conf_raw, (int, float)):
        if conf_raw <= 1.0:
            conf_raw = conf_raw * 100
        if conf_raw >= 70:
            confidence = Confidence.HIGH
        elif conf_raw >= 40:
            confidence = Confidence.MEDIUM
        else:
            confidence = Confidence.LOW
    else:
        conf_str = str(conf_raw).lower()
        try:
            confidence = Confidence(conf_str)
        except ValueError:
            confidence = Confidence.LOW

    lang_str = str(finding.get("language", "unknown")).lower()
    try:
        language = Language(lang_str)
    except ValueError:
        language = Language.UNKNOWN

    file_path = Path(finding.get("file", ".")) if finding.get("file") else Path(".")

    # evidence 映射（v34 改进）
    evidence = []
    snippet = finding.get("code_snippet", "")
    if snippet:
        evidence.append(Evidence(
            source=finding.get("agent", "unknown"),
            rule_id=finding.get("type"),
            snippet=snippet,
            line_start=finding.get("line", 0),
            line_end=finding.get("line", 0),
            reasoning=finding.get("description", ""),
        ))

    return Risk(
        id=finding.get("id") or f"RISK-{uuid.uuid4().hex[:8].upper()}",
        title=finding.get("title") or finding.get("category", "Unknown Risk"),
        description=finding.get("description", ""),
        severity=severity,
        confidence=confidence,
        cwe_id=finding.get("cwe") or finding.get("type"),
        language=language,
        file_path=file_path,
        line_start=finding.get("line", 0),
        line_end=finding.get("line", 0),
        evidence=evidence,
        suggestion=finding.get("recommendation") or finding.get("suggestion", "Review this code section."),
    )


def _risk_to_dict(risk) -> dict:
    """将引擎层的 Risk 对象转换为 API 层的 dict（v34 改进）"""
    conf_map = {"high": 80, "medium": 50, "low": 30}
    confidence_val = conf_map.get(risk.confidence.value, 30)

    snippet = ""
    agent = "unknown"
    if risk.evidence:
        snippet = risk.evidence[0].snippet
        agent = risk.evidence[0].source

    return {
        "id": risk.id,
        "type": risk.cwe_id or "CWE-1395",
        "title": risk.title,
        "category": risk.title,
        "severity": risk.severity.value,
        "confidence": confidence_val,
        "cwe": risk.cwe_id,
        "description": risk.description,
        "file": str(risk.file_path),
        "line": risk.line_start,
        "language": risk.language.value,
        "code_snippet": snippet,
        "agent": agent,
        "suggestion": risk.suggestion,
    }


# ── 进度更新 ──

def _update_progress(task_id: str, status: str, progress: int, agent_status: dict | None = None):
    """更新任务进度到 Redis（连接池复用）"""
    r = _get_redis()
    data = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "agent_status": agent_status or {},
        "updated_at": datetime.now().isoformat(),
    }
    r.set(f"task:{task_id}:status", json.dumps(data), ex=86400)


# ── 核心分析任务 ──

@celery_app.task(bind=True, name="analyze_codebase")
def analyze_codebase_task(self, task_id: str, source_config: dict[str, Any]) -> dict:
    """
    执行代码安全分析。

    流程：
      1. 获取代码（Git clone / 解压 ZIP / 读取上传文件）
      2. Agent 1 + Agent 2: 静态分析与语义分析（并行）
      3. Agent 3: 深度验证（交叉验证）
      4. Agent 4: 报告生成（JSON/SARIF/PDF）
    """
    logger.info(f"[{task_id}] Starting analysis, source={source_config.get('source')}")
    work_dir = None
    nutrient = NutrientDWSClient()

    try:
        # 阶段 1: 准备代码
        _update_progress(task_id, "analyzing", 5, {
            "agent_1_static": "preparing",
            "agent_2_semantic": "pending",
            "agent_3_verifier": "pending",
            "agent_4_report": "pending",
        })
        work_dir = _prepare_code(task_id, source_config)
        if not work_dir:
            raise ValueError("Failed to prepare source code")
        logger.info(f"[{task_id}] Code prepared at {work_dir}")

        # 阶段 1.5: Agent 0 — Input Sanitizer / PITAX 预扫描（AI 新漏洞检测）
        _update_progress(task_id, "analyzing", 10, {
            "agent_0_sanitizer": "running",
            "agent_1_static": "pending",
            "agent_2_semantic": "pending",
            "agent_3_verifier": "pending",
            "agent_4_report": "pending",
        })
        pitax_findings, pitax_stats = run_agent0(work_dir)
        _update_progress(task_id, "analyzing", 13, {
            "agent_0_sanitizer": f"done:{len(pitax_findings)}",
            "agent_1_static": "pending",
            "agent_2_semantic": "pending",
            "agent_3_verifier": "pending",
            "agent_4_report": "pending",
        })
        logger.info(f"[{task_id}] Agent 0 (PITAX): {len(pitax_findings)} AI findings")

        # 阶段 2: Agent 1 静态分析（串行，结果传给 Agent 2）
        _update_progress(task_id, "analyzing", 15, {
            "agent_1_static": "running",
            "agent_2_semantic": "pending",
            "agent_3_verifier": "pending",
            "agent_4_report": "pending",
        })

        static_findings = _run_static_analysis(task_id, work_dir)

        # 阶段 2b: 污点分析（source→sink 数据流追踪）
        taint_findings = _run_taint_analysis(task_id, work_dir)
        static_findings.extend(taint_findings)

        # 阶段 2c: 依赖扫描（requirements.txt 已知漏洞）
        dep_findings = _run_dependency_scan(task_id, work_dir)
        static_findings.extend(dep_findings)

        # 阶段 2d: Agent 2 语义分析（接收 Agent 1 结果，过滤误报）
        _update_progress(task_id, "analyzing", 40, {
            "agent_1_static": "completed",
            "agent_1b_taint": "completed",
            "agent_1c_dependency": "completed",
            "agent_2_semantic": "running",
            "agent_3_verifier": "pending",
            "agent_4_report": "pending",
        })
        semantic_findings = _run_semantic_analysis(task_id, work_dir, static_findings)

        _update_progress(task_id, "analyzing", 55, {
            "agent_1_static": "completed",
            "agent_1b_taint": "completed",
            "agent_1c_dependency": "completed",
            "agent_2_semantic": "completed",
            "agent_3_verifier": "pending",
            "agent_4_report": "pending",
        })
        logger.info(f"[{task_id}] Static: {len(static_findings)} findings, Semantic: {len(semantic_findings)} findings, Taint: {len(taint_findings)} findings, Dep: {len(dep_findings)} findings")

        # 合并去重
        merged_findings = _merge_findings(static_findings, semantic_findings)

        # 阶段 3: Agent 3 — 深度验证
        _update_progress(task_id, "verifying", 75, {
            "agent_1_static": "completed",
            "agent_2_semantic": "completed",
            "agent_3_verifier": "running",
            "agent_4_report": "pending",
        })
        verified_findings = _run_verification(task_id, work_dir, merged_findings)
        _update_progress(task_id, "verifying", 90, {
            "agent_1_static": "completed",
            "agent_2_semantic": "completed",
            "agent_3_verifier": "completed",
            "agent_4_report": "pending",
        })
        logger.info(f"[{task_id}] Verified: {len(verified_findings)} findings")

        # 阶段 4: Agent 4 — 报告生成
        _update_progress(task_id, "generating_report", 95, {
            "agent_1_static": "completed",
            "agent_2_semantic": "completed",
            "agent_3_verifier": "completed",
            "agent_4_report": "running",
        })
        report = _generate_report(task_id, verified_findings, source_config.get("output_formats", ["json"]), nutrient, pitax_findings=pitax_findings)
        _update_progress(task_id, "completed", 100, {
            "agent_1_static": "completed",
            "agent_2_semantic": "completed",
            "agent_3_verifier": "completed",
            "agent_4_report": "completed",
        })
        logger.info(f"[{task_id}] Report generated: {report.get('total_findings', 0)} findings")

        # 保存结果
        result_path = settings.REPORTS_DIR / f"{task_id}.json"
        result_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        return {"task_id": task_id, "status": "completed", "report": report}

    except Exception as e:
        logger.exception(f"[{task_id}] Analysis failed: {e}")
        _update_progress(task_id, "failed", 0, {
            "agent_0_sanitizer": "error",
            "agent_1_static": "error",
            "agent_2_semantic": "error",
            "agent_3_verifier": "error",
            "agent_4_report": "error",
        })
        return {"task_id": task_id, "status": "failed", "error": str(e)}

    finally:
        # 清理临时文件
        if work_dir and Path(work_dir).exists():
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info(f"[{task_id}] Cleaned up work dir: {work_dir}")

        # 清理上传的 ZIP 文件（如果存在）
        zip_path_str = source_config.get("zip_path")
        if zip_path_str:
            zip_path = Path(zip_path_str)
            if zip_path.exists():
                try:
                    zip_path.unlink(missing_ok=True)
                    logger.info(f"[{task_id}] Cleaned up ZIP file: {zip_path}")
                except Exception as e:
                    logger.warning(f"[{task_id}] Failed to clean up ZIP file: {e}")


# ── 内部实现 ──

def _prepare_code(task_id: str, config: dict) -> str | None:
    """准备代码：clone / 解压 / 读取"""
    work_dir = Path(tempfile.mkdtemp(prefix=f"cr-{task_id}-"))
    source = config.get("source", "direct_upload")

    if source == "github":
        repo_url = config.get("repo_url", "").strip()
        branch = config.get("branch", "main")

        if not repo_url:
            return None

        # 白名单校验 + 防注入
        allowed_hosts = ("https://github.com/", "https://gitlab.com/", "https://gitee.com/")
        if not any(repo_url.startswith(h) for h in allowed_hosts):
            raise ValueError(f"Unsupported repo URL: {repo_url}")

        import subprocess
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "-b", branch, repo_url, str(work_dir)],
                capture_output=True,
                timeout=120,
                check=True,
            )
            return str(work_dir)
        except subprocess.CalledProcessError as e:
            logger.error(f"Git clone failed: {e.stderr.decode()[:200]}")
            return None

    elif source == "local":
        local_path = config.get("local_path", "").strip()
        if not local_path:
            logger.error(f"[{task_id}] Local source but local_path is empty")
            return None

        import os
        normalized = os.path.normpath(local_path)
        if ".." in normalized.split(os.sep):
            logger.error(f"[{task_id}] Path traversal detected: {local_path}")
            return None
        if not normalized.startswith("/repos/"):
            logger.error(f"[{task_id}] Local path must be under /repos/: {local_path}")
            return None
        if not os.path.isdir(normalized):
            logger.error(f"[{task_id}] Directory does not exist: {normalized}")
            return None

        logger.info(f"[{task_id}] Using local directory: {normalized}")
        return normalized

    elif source == "zip":
        zip_path_str = config.get("zip_path")
        if not zip_path_str:
            logger.error(f"[{task_id}] ZIP source but zip_path is empty")
            return None

        zip_path = Path(zip_path_str)
        if not zip_path.exists():
            logger.error(f"[{task_id}] ZIP file not found: {zip_path}")
            return None

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                infolist = zf.infolist()

                # ZIP 炸弹防护 1：解压后总大小
                total_size = sum(f.file_size for f in infolist)
                MAX_DECOMPRESSED = 100 * 1024 * 1024  # 100 MB
                if total_size > MAX_DECOMPRESSED:
                    raise ValueError(
                        f"ZIP decompressed size {total_size} bytes exceeds "
                        f"limit of {MAX_DECOMPRESSED} bytes (100MB)"
                    )

                # ZIP 炸弹防护 2：文件数量
                MAX_FILES = 10000
                if len(infolist) > MAX_FILES:
                    raise ValueError(
                        f"ZIP contains {len(infolist)} files, exceeds limit of {MAX_FILES}"
                    )

                # 路径遍历防护
                for member in infolist:
                    if member.is_dir():
                        continue
                    target = work_dir / member.filename
                    try:
                        target.resolve().relative_to(work_dir.resolve())
                    except ValueError:
                        raise ValueError(
                            f"ZIP path traversal detected: {member.filename}"
                        )

                # 解压
                zf.extractall(work_dir)

            logger.info(f"[{task_id}] ZIP extracted: {len(infolist)} files to {work_dir}")
            return str(work_dir)

        except zipfile.BadZipFile:
            logger.error(f"[{task_id}] Invalid ZIP file: {zip_path}")
            return None
        except ValueError as e:
            logger.error(f"[{task_id}] ZIP validation failed: {e}")
            return None
        except Exception as e:
            logger.exception(f"[{task_id}] ZIP extraction failed: {e}")
            return None

    elif source == "direct_upload":
        # 直接上传代码片段/文件：config["files"] = [{"path": "src/a.py", "content": "..."}]
        files = config.get("files") or []
        if not files:
            logger.error(f"[{task_id}] direct_upload but files is empty")
            return None

        MAX_FILES = 200
        MAX_FILE_BYTES = 1024 * 1024   # 单文件 1MB
        MAX_TOTAL_BYTES = 10 * 1024 * 1024  # 总量 10MB
        total = 0
        if len(files) > MAX_FILES:
            logger.error(f"[{task_id}] direct_upload files={len(files)} exceeds limit {MAX_FILES}")
            return None
        try:
            for item in files:
                rel = str(item.get("path", "")).strip()
                content = item.get("content", "")
                if not rel:
                    raise ValueError("file path is empty")
                # 路径遍历防护：拒绝绝对路径（含 Windows 下 /x、\x 形式）与 .. 片段
                p = Path(rel)
                if p.is_absolute() or rel.startswith(("/", "\\")) or ".." in p.parts:
                    raise ValueError(f"unsafe file path: {rel}")
                data = content.encode("utf-8", errors="replace")
                total += len(data)
                if len(data) > MAX_FILE_BYTES:
                    raise ValueError(f"file {rel} exceeds {MAX_FILE_BYTES} bytes")
                if total > MAX_TOTAL_BYTES:
                    raise ValueError(f"total upload size exceeds {MAX_TOTAL_BYTES} bytes")
                target = work_dir / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        except (ValueError, OSError) as e:
            logger.error(f"[{task_id}] direct_upload rejected: {e}")
            return None
        logger.info(f"[{task_id}] direct_upload wrote {len(files)} file(s) to {work_dir}")
        return str(work_dir)

    return None


def _run_static_analysis(task_id: str, code_path: str) -> list[dict]:
    """Agent 1: 静态分析（Tree-sitter 模式匹配）"""
    try:
        analyzer = _get_static_analyzer()
        code_files = _scan_code_files(code_path)
        if not code_files:
            logger.warning(f"[{task_id}] No analyzable files found in {code_path}")
            return []
        risks = analyzer.analyze_batch(code_files)
        return [_risk_to_dict(r) for r in risks]
    except Exception as e:
        logger.error(f"[{task_id}] Static analysis failed: {e}")
        return []


def _run_semantic_analysis(task_id: str, code_path: str, static_findings: list[dict]) -> list[dict]:
    """Agent 2: 语义分析（LLM）"""
    try:
        analyzer = _get_semantic_analyzer()
        if analyzer is None:
            logger.info(f"[{task_id}] No LLM client, skipping semantic analysis")
            return []
        code_files = _scan_code_files(code_path)
        existing_risks = []
        all_risks = []
        for cf in code_files:
            risks = analyzer.analyze(cf, existing_risks)
            all_risks.extend(risks)
        return [_risk_to_dict(r) for r in all_risks]
    except Exception as e:
        logger.error(f"[{task_id}] Semantic analysis failed: {e}")
        return []


def _run_verification(task_id: str, code_path: str, findings: list[dict]) -> list[dict]:
    """Agent 3: 深度验证（交叉验证）"""
    try:
        verifier = _get_deep_verifier()
        code_files = _scan_code_files(code_path)
        if not findings:
            return findings
        risks = [_dict_to_risk(f) for f in findings]
        verified_risks = verifier.verify_batch(code_files, risks)
        findings = [_risk_to_dict(r) for r in verified_risks]
        logger.info(f"[{task_id}] Deep verification: {len(findings)} findings after verification")
        return findings
    except Exception as e:
        logger.error(f"[{task_id}] Verification failed: {e}")
        return findings


def _run_taint_analysis(task_id: str, code_path: str) -> list[dict]:
    """Agent 1b: 污点分析（source→sink 数据流追踪）"""
    try:
        from core.taint_analyzer import TaintAnalyzer
        from core.models import Language
        taint = TaintAnalyzer()
        code_files = _scan_code_files(code_path)
        if not code_files:
            return []
        all_flows = []
        for cf in code_files:
            content = cf.content
            file_path = str(cf.path)
            if cf.language == Language.C:
                flows = taint.analyze_c(content, file_path)
            elif cf.language == Language.PYTHON:
                flows = taint.analyze_python(content, file_path)
            else:
                continue
            for flow in flows:
                all_flows.append({
                    "id": f"TAINT-{hash(str(flow)) & 0xFFFF:04x}",
                    "type": flow.cwe_id,
                    "title": f"Taint: {flow.source} -> {flow.sink}",
                    "severity": flow.severity,
                    "description": flow.description,
                    "file": file_path,
                    "line": flow.sink_line,
                    "confidence": 60 if flow.confidence == "medium" else 80,
                })
        logger.info(f"[{task_id}] Taint analysis: {len(all_flows)} flows found")
        return all_flows
    except Exception as e:
        logger.error(f"[{task_id}] Taint analysis failed: {e}")
        return []


def _run_dependency_scan(task_id: str, code_path: str) -> list[dict]:
    """Agent 1c: 依赖扫描（requirements.txt / package.json 已知漏洞）"""
    try:
        from core.dependency_scanner import scan_project_dependencies
        risks = scan_project_dependencies(Path(code_path))
        result = []
        for r in risks:
            pkg = r.get("package", "unknown")
            result.append({
                "id": f"DEP-{pkg.upper()}",
                "type": r.get("cwe", "CWE-1395"),
                "title": f"Vulnerable dependency: {pkg} {r.get('version', '')}".strip(),
                "severity": "high",
                "description": r.get("description", ""),
                "file": r.get("file", "requirements.txt"),
                "line": 0,
                "confidence": 50,
            })
        logger.info(f"[{task_id}] Dependency scan: {len(result)} findings")
        return result
    except Exception as e:
        logger.error(f"[{task_id}] Dependency scan failed: {e}")
        return []


def _merge_findings(static: list[dict], semantic: list[dict]) -> list[dict]:
    """合并静态分析和语义分析结果，去重"""
    merged = {f.get("id", f.get("title", str(hash(str(f))))): f for f in static}
    for f in semantic:
        key = f.get("id", f.get("title", str(hash(str(f)))))
        if key in merged:
            # 合并：取更高 severity
            existing = merged[key]
            sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
            if sev_order.get(f.get("severity", "info"), 0) > sev_order.get(existing.get("severity", "info"), 0):
                merged[key] = f
        else:
            merged[key] = f
    return list(merged.values())


def _generate_report(task_id: str, findings: list[dict], formats: list[str], nutrient: NutrientDWSClient, pitax_findings: list[dict] | None = None) -> dict:
    """Agent 4: 报告生成（合并传统漏洞 + PITAX AI 漏洞）"""
    pitax_findings = pitax_findings or []
    # 合并 AI 漏洞到总列表（确定性结果，不重复验证）
    all_findings = findings + pitax_findings
    summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in all_findings:
        sev = f.get("severity", "info").lower()
        if sev in summary:
            summary[sev] += 1

    report = {
        "task_id": task_id,
        "generated_at": datetime.now().isoformat(),
        "summary": summary,
        "findings": all_findings,
        "total_findings": len(all_findings),
        "ai_findings": pitax_findings,
        "ai_findings_count": len(pitax_findings),
    }

    # SARIF
    if "sarif" in formats:
        sarif_path = settings.REPORTS_DIR / f"{task_id}.sarif"
        sarif = _to_sarif(all_findings)
        sarif_path.write_text(json.dumps(sarif, indent=2), encoding="utf-8")
        report["sarif_path"] = str(sarif_path)

    # PDF via Nutrient DWS
    if "pdf" in formats:
        pdf_path = settings.REPORTS_DIR / f"{task_id}.pdf"
        import asyncio
        try:
            pdf_bytes = asyncio.run(nutrient.generate_pdf(report))
            if pdf_bytes:
                signed_bytes = asyncio.run(nutrient.sign_pdf(pdf_bytes))
                final_bytes = signed_bytes or pdf_bytes
                pdf_path.write_bytes(final_bytes)
                report["pdf_path"] = str(pdf_path)
                report["pdf_size"] = len(final_bytes)
                logger.info(f"[{task_id}] PDF saved: {pdf_path} ({len(final_bytes)} bytes)")
            else:
                report["pdf_path"] = None
                report["pdf_error"] = "Nutrient API unavailable or key not configured"
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                logger.warning(f"[{task_id}] PDF generation skipped: event loop conflict in Celery worker")
                report["pdf_path"] = None
                report["pdf_error"] = "PDF generation not supported in async worker context"
            else:
                raise
        report["digital_signature"] = "sha256:" + hashlib.sha256(json.dumps(report).encode()).hexdigest()[:32]

    # 主线 A: 输出护栏 — 报告输出前脱敏系统提示内容，防止 Agent 泄露
    report = guard_report(report)
    return report


def _to_sarif(findings: list[dict]) -> dict:
    """转换为 SARIF 2.1.0（PITAX findings 附带 rules[] + properties.pitax 元数据）"""
    return build_sarif(findings)


def _severity_to_sarif_level(severity: str) -> str:
    mapping = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "none"}
    return mapping.get(severity, "none")

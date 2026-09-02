"""Agent 0: Input Sanitizer / PITAX 预扫描。
主线 A（自我加固）：在 4-Agent 流水线前消毒输入；
主线 B（能力升级）：产出带 PITAX 编号的 AI 漏洞 findings，并入最终报告。
"""
from __future__ import annotations

import logging

logger = logging.getLogger("coderisk.cloud.agent0")

AGENT_NAME = "agent_0_sanitizer"


def run_agent0(work_dir: str) -> tuple[list[dict], dict]:
    """扫描 work_dir，返回 (findings, stats)。永不抛异常（失败不影响主流程）。"""
    try:
        from app.pitax.sanitizer import scan_directory
        findings, stats = scan_directory(work_dir)
        logger.info(f"[agent_0] PITAX pre-scan done: {len(findings)} AI findings")
        return findings, stats
    except Exception as e:  # 防御性：Agent 0 故障不阻断分析
        logger.error(f"[agent_0] PITAX pre-scan failed: {e}")
        return [], {"error": str(e)}

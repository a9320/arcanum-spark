"""System Prompt Vault + Output Guardrail（七支柱 P4 加固的参赛最小实现）。
主线 A（自我加固）：
- 金库：系统提示只从环境变量/外部文件加载，绝不明文出现在代码库；
- 护栏：报告输出前扫描并脱敏系统提示内容，防止 Agent 在报告中泄露。
基于智谱方案 app/prompt_guard.py。
"""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger("coderisk.guardrail")

_GENERIC_LEAK_PATTERNS = [
    re.compile(r"<\|im_start\|>\s*system", re.I),
    re.compile(r"<\|system\|>", re.I),
    re.compile(r"(?i)\byou\s+are\s+(now\s+)?(the\s+)?coderisk\s+(cloud\s+)?(agent|system)"),
    re.compile(r"(?i)SYSTEM\s+PROMPT\s*[:=]"),
]


class SystemPromptVault:
    """从环境加载系统提示（JSON 数组 / 单条 / 外部文件）。"""

    def __init__(self) -> None:
        self._secrets: list[str] = []
        raw = os.getenv("CODERISK_SYSTEM_PROMPTS", "")
        if raw:
            try:
                self._secrets = [s for s in json.loads(raw) if isinstance(s, str) and len(s) >= 20]
            except json.JSONDecodeError:
                logger.warning("CODERISK_SYSTEM_PROMPTS is not valid JSON; ignored")
        single = os.getenv("CODERISK_SYSTEM_PROMPT", "")
        if len(single) >= 20:
            self._secrets.append(single)
        path = os.getenv("CODERISK_SYSTEM_PROMPT_FILE", "")
        if path and os.path.isfile(path):
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
                if len(text) >= 20:
                    self._secrets.append(text)
            except Exception as e:
                logger.warning(f"Could not read prompt file {path}: {e}")
        logger.info(f"Prompt vault loaded: {len(self._secrets)} secret(s)")

    @property
    def secrets(self) -> list[str]:
        return list(self._secrets)


class OutputGuardrail:
    def __init__(self, vault: SystemPromptVault | None = None) -> None:
        self.vault = vault or SystemPromptVault()

    def _redact(self, text: str) -> tuple[str, bool]:
        out, hit = text, False
        for s in self.vault.secrets:
            if s in out:
                out, hit = out.replace(s, "[REDACTED: system prompt content]"), True
        for rx in _GENERIC_LEAK_PATTERNS:
            if rx.search(out):
                out = rx.sub("[REDACTED: potential system prompt leakage]", out)
                hit = True
        return out, hit

    def guard_report(self, report: dict) -> dict:
        """递归脱敏报告中的字符串字段。"""
        redactions = 0

        def walk(node):
            nonlocal redactions
            if isinstance(node, str):
                new, hit = self._redact(node)
                redactions += int(hit)
                return new
            if isinstance(node, list):
                return [walk(x) for x in node]
            if isinstance(node, dict):
                return {k: walk(v) for k, v in node.items()}
            return node

        guarded = walk(report)
        guarded["output_guardrail"] = {
            "enabled": True,
            "redactions": redactions,
            "status": "leak_blocked" if redactions else "clean",
        }
        if redactions:
            logger.warning(f"Output guardrail redacted {redactions} potential leak(s)")
        return guarded


_default_guardrail: OutputGuardrail | None = None


def guard_report(report: dict) -> dict:
    global _default_guardrail
    if _default_guardrail is None:
        _default_guardrail = OutputGuardrail()
    try:
        return _default_guardrail.guard_report(report)
    except Exception as e:
        logger.error(f"Output guardrail failed: {e}")
        report.setdefault("output_guardrail", {"enabled": False, "error": str(e)})
        return report

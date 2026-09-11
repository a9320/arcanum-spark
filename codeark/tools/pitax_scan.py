"""PITAX 确定性扫描 — 封装为 Strands @tool。

设计原则（整合版蓝图铁律）：
- 这是"侦察/验证"阶段的确定性工具：由规则代码产出结构化证据，LLM 只引用、不编造；
- 按文件路径分流：AI 配置 → PIT-T-46，文档 → PIT-N-06，其余代码 → 6 个检测器；
- 输出是 report_dict 列表（含 pitax_code / severity / confidence / evidence），
  与 Finding.to_report_dict() 完全一致，可直接进最终报告 ai_findings 区块；
- 纯确定性、无 LLM、永不抛异常——失败返回空列表 + 日志，不中断流水线。
"""
from __future__ import annotations

from typing import Any

# Strands @tool 装饰器。若环境不可用则退化为普通函数（保可导入、可单测）。
try:  # pragma: no cover - 导入降级分支
    from strands.tools import tool as _strands_tool
    _HAS_STRANDS = True
except Exception:  # pragma: no cover
    _strands_tool = lambda f: f
    _HAS_STRANDS = False

from ..pitax.detectors import (
    Finding,
    detect_ai_config_injection,
    detect_comment_injection,
    detect_doc_injection,
    detect_encoded_payloads,
    detect_invisible_text,
    detect_trojan_source,
    is_ai_config_path,
    is_doc_path,
)

__all__ = ["pitax_scan", "scan_file", "scan_repo"]


# ── 单文件扫描：按路径分流，返回该文件命中的 report_dict 列表 ──
def scan_file(path: str, content: str, _n: int = 0) -> list[dict]:
    """对单个文件跑匹配的 PITAX 检测器。

    分流规则：
      - is_ai_config_path(path)  → 只跑 PIT-T-46（AI 指令文件后门）
      - is_doc_path(path)        → 只跑 PIT-N-06（文档投毒）
      - 否则                     → 跑其余 6 个检测器
    """
    findings: list[Finding] = []
    try:
        if is_ai_config_path(path):
            findings = detect_ai_config_injection(content, path)
        elif is_doc_path(path):
            findings = detect_doc_injection(content, path)
        else:
            # 代码/文本：跑 6 个检测器（PIT-E-23/54/T-51 + 编码 PIT-E-07/14/36/57）
            findings = [
                *detect_invisible_text(content, path),
                *detect_trojan_source(content, path),
                *detect_comment_injection(content, path),
                *detect_encoded_payloads(content, path),
            ]
    except Exception as exc:  # pragma: no cover - 防御：单文件失败不拖垮整次扫描
        print(f"[pitax_scan] 扫描 {path} 失败: {exc}")
        return []

    # 统一转为带 id 的 report_dict（同文件内递增）
    return [
        f.to_report_dict(f"pitax-{_n}-{i}")
        for i, f in enumerate(findings, start=1)
    ]


# ── 多文件扫描：输入 {路径: 内容} 字典，返回全部命中 ──
def scan_repo(files: dict[str, str]) -> list[dict]:
    """对仓库全部文件跑 PITAX 检测。

    Args:
        files: {"相对路径": "文件内容字符串"}。key 用于路径分流与报告定位。

    Returns:
        report_dict 列表（空列表 = 无命中或全部失败）。
    """
    all_findings: list[dict] = []
    for _n, (path, content) in enumerate(files.items(), start=1):
        all_findings.extend(scan_file(path, content, _n=_n))
    return all_findings


# ── Strands @tool 封装：模型可调用入口 ──
# 手动传 inputSchema（JSON Schema dict）明确 files 参数结构，
# 绕开 dict[str,str] 注解自动生成的 bug（否则报 unrecognized tool specification）。
_PITAX_SCAN_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "文件路径到文件内容的映射字典，key 为仓库相对路径（AI配置→T-46 / 文档→N-06 / 代码→其余）",
        }
    },
    "required": ["files"],
}


if _HAS_STRANDS:
    @_strands_tool(inputSchema=_PITAX_SCAN_SCHEMA)
    def pitax_scan(files: dict[str, str]) -> list[dict]:
        """对仓库文件跑 PITAX 确定性检测（9 条 AI 提示注入/欺骗规则）。

        Args:
            files: 文件路径到文件内容的映射字典，key 为仓库相对路径。

        Returns:
            report_dict 列表；每条含
            type(pitax_code)/severity/confidence/evidence/file/line/code_snippet/pitax。
            这是确定性工具，结果可直接作为漏洞证据引用。
        """
        return scan_repo(files)
else:  # pragma: no cover - 无 Strands 时退化为普通函数，保证可单测
    def pitax_scan(files: dict[str, str]) -> list[dict]:
        """PITAX 确定性扫描（无 Strands 环境时退化实现）。"""
        return scan_repo(files)
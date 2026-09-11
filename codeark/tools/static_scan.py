"""@tool 封装静态规则扫描（启发式）— 找常见漏洞模式。

侦察 Agent 的静态扫描工具（暂用 Python 正则/启发式，后续可换 Tree-sitter 精化）。
- 输入：files: dict[str, str]（文件路径 → 文件内容）
- 输出：findings 列表，每条含 type/severity/evidence/file/line/code_snippet
- 确定性工具，结果可直接作为漏洞证据引用（与 pitax_scan 一致）
"""
from __future__ import annotations

import re
from typing import Any

# ── 启发式规则：模式名 → (正则, 严重级别, 描述) ──
# 按文件路径分流：代码文件跑这些规则；配置文件/文档跳过（交给 pitax_scan 处理）
_RULES: list[tuple[str, str, str, re.Pattern]] = [
    (
        "COMMAND_INJECTION",
        "high",
        "命令注入：拼接字符串执行系统命令",
        re.compile(r"(os\.system|subprocess\.(run|Popen|call)|eval|exec)\s*\([^)]*[+f]", re.I),
    ),
    (
        "SQL_INJECTION",
        "high",
        "SQL 注入：字符串拼接 SQL 查询（含 f-string 插值/格式化）",
        re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WHERE)\b[^;]{0,160}\{", re.I),
    ),
    (
        "PATH_TRAVERSAL",
        "medium",
        "路径穿越：拼接用户输入构造文件路径",
        re.compile(r"(open|Path|join)\s*\([^)]*(request|input|argv|query|params)", re.I),
    ),
    (
        "HARDCODED_SECRET",
        "high",
        "硬编码密钥：疑似明文密码/密钥/令牌",
        re.compile(r"(password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.I),
    ),
    (
        "INSECURE_HASH",
        "medium",
        "不安全的哈希：使用 md5/sha1 处理敏感数据",
        re.compile(r"(hashlib\.(md5|sha1)|\.md5\(|\.sha1\()", re.I),
    ),
    (
        "HARDPARSED_B64",  # 简单解码检测（非 PITAX 那套）
        "low",
        "可疑 Base64：字符串中有大段 base64 编码",
        re.compile(r"['\"][A-Za-z0-9+/]{40,}={0,2}['\"]", re.I),
    ),
]

# 需跳过的扩展名（非代码文件，不跑静态规则）
_SKIP_SUFFIXES = (
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".lock", ".svg", ".png", ".jpg", ".gif", ".ico", ".lockb",
)


def scan_file(path: str, content: str, *, _n: int = 0) -> list[dict[str, Any]]:
    """对单文件跑全部静态规则，返回命中列表。"""
    findings: list[dict[str, Any]] = []
    lower_path = path.lower()
    if lower_path.endswith(_SKIP_SUFFIXES):
        return findings  # 非代码文件跳过

    lines = content.splitlines()
    for rule_name, severity, desc, pattern in _RULES:
        for m in pattern.finditer(content):
            line_no = content.count("\n", 0, m.start()) + 1
            line_text = lines[line_no - 1].strip() if line_no <= len(lines) else ""
            findings.append(
                {
                    "type": rule_name,
                    "severity": severity,
                    "confidence": 90,  # 规则命中=确定性高（同 pitax_scan 约定）
                    "evidence": desc,
                    "file": path,
                    "line": line_no,
                    "code_snippet": line_text[:200],
                    "rule": f"STATIC-{rule_name}",
                }
            )
    return findings


def scan_repo(files: dict[str, str]) -> list[dict[str, Any]]:
    """对多文件跑静态规则，聚合全部命中。"""
    all_findings: list[dict[str, Any]] = []
    for path, content in files.items():
        all_findings.extend(scan_file(path, content, _n=0))
    return all_findings


# ── Strands @tool 封装：模型可调用入口 ──
try:  # pragma: no cover - 导入降级分支
    from strands.tools import tool as _strands_tool
    _HAS_STRANDS = True
except Exception:  # pragma: no cover
    _strands_tool = lambda f: f
    _HAS_STRANDS = False

_STATIC_SCAN_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "文件路径到文件内容的映射字典（代码文件跑静态规则，非代码自动跳过）",
        }
    },
    "required": ["files"],
}


if _HAS_STRANDS:
    @_strands_tool(inputSchema=_STATIC_SCAN_SCHEMA)
    def static_scan(files: dict[str, str]) -> list[dict]:
        """对仓库代码文件做启发式静态扫描，找常见漏洞模式。

        Args:
            files: 文件路径到文件内容的映射字典，key 为仓库相对路径。

        Returns:
            findings 列表；每条含 type/severity/confidence/evidence/file/line/code_snippet/rule。
            这是确定性工具，结果可直接作为漏洞证据引用。
        """
        return scan_repo(files)
else:  # pragma: no cover - 无 Strands 时退化为普通函数
    def static_scan(files: dict[str, str]) -> list[dict]:
        """静态启发式扫描（无 Strands 环境时退化实现）。"""
        return scan_repo(files)


__all__ = ["scan_file", "scan_repo", "static_scan", "_RULES", "_SKIP_SUFFIXES"]
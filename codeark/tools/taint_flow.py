"""@tool 封装污点追踪（source→sink）— 启发式。

侦察 Agent 的污点追踪工具（暂用启发式：匹配污点源变量流向不安全 sink）。
- 输入：files: dict[str, str]（文件路径 → 文件内容）
- 输出：flows 列表，每条含 source/sink/intermediate/file/line/severity/confidence
- 确定性工具，结果可直接作为漏洞证据引用
"""
from __future__ import annotations

import re
from typing import Any

# 污点源：用户/外部可控的输入
_SOURCES = [
    ("user_input", r"\b(user_input|request\.args|request\.form|request\.json|argv\[|sys\.argv|os\.environ|getenv|query_params|input\()", "用户输入"),
    ("file_content", r"\b(read\(\)|open\([^)]*\)\.read|request\.files|uploaded)", "文件内容"),
    ("network", r"\b(request\.get|requests\.(get|post|put)|urllib|httpx|fetch\(|socket)", "网络数据"),
]

# 不安全 sink：执行/查询/路径等
_SINKS = [
    ("system", r"\b(os\.system|subprocess\.(run|Popen|call|check_output)|eval|exec)\s*\(", "系统命令执行"),
    ("sql", r"\b(execute|cursor\.execute|query)\s*\(|SELECT\s", "SQL 查询"),
    ("path", r"\b(open|Path|join|mkdir|remove|unlink)\s*\(", "文件系统操作"),
]

# 赋值传播：简单追踪 var = source，然后 var 流入 sink
_ASSIGN_RE = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)")


def _find_taint_flows(content: str, path: str) -> list[dict[str, Any]]:
    """在单文件内容中找 source→sink 的污点流（启发式）。"""
    flows: list[dict[str, Any]] = []
    lines = content.splitlines()

    # 1. 收集所有潜在污点变量（被 source 赋值）
    tainted_vars: set[str] = set()
    source_locations: dict[str, dict] = {}  # var -> 来源信息
    for lineno, line in enumerate(lines, start=1):
        am = _ASSIGN_RE.match(line.strip())
        if not am:
            continue
        var, rhs = am.group(1), am.group(2)
        for src_name, pattern, desc in _SOURCES:
            if re.search(pattern, rhs, re.I):
                tainted_vars.add(var)
                source_locations[var] = {
                    "name": src_name,
                    "desc": desc,
                    "file": path,
                    "line": lineno,
                    "code": line.strip()[:200],
                }
                break

    if not tainted_vars:
        return flows

    # 2. 找这些污点变量流向 sink（sink 调用在前，污点变量作参数在后）
    var_alt = "|".join(re.escape(v) for v in tainted_vars)
    if not var_alt:
        return flows
    sink_search = re.compile(rf"\b(os\.system|subprocess|eval|exec|execute|open|Path|join|SELECT)\b[^\n]{{0,200}}\b({var_alt})\b", re.I)
    for lineno, line in enumerate(lines, start=1):
        sm = sink_search.search(line)
        if not sm:
            continue
        sink_kw = sm.group(1).lower()
        used_var = sm.group(2)
        if used_var not in tainted_vars:
            continue
        src = source_locations[used_var]
        # 判断 sink 类型
        if re.search(r"os\.system|subprocess|eval|exec", sink_kw):
            sink_type = "system"
        elif re.search(r"execute|SELECT", sink_kw):
            sink_type = "sql"
        else:
            sink_type = "path"
        flows.append(
            {
                "type": f"TAINT_{sink_type.upper()}",
                "severity": "high" if sink_type == "system" else "medium",
                "confidence": 80,  # 启发式关联，略低于规则命中
                "source": src,
                "sink": {
                    "kind": sink_type,
                    "file": path,
                    "line": lineno,
                    "code": line.strip()[:200],
                },
                "evidence": f"污点源「{src['desc']}」经变量 {used_var} 流入{sink_type} sink",
                "file": path,
                "line": lineno,
                "code_snippet": line.strip()[:200],
                "rule": f"STATIC-TAINT-{sink_type.upper()}",
            }
        )
    return flows


def scan_repo(files: dict[str, str]) -> list[dict[str, Any]]:
    """对多文件跑污点追踪，聚合全部流。"""
    all_flows: list[dict[str, Any]] = []
    for path, content in files.items():
        if path.lower().endswith((".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".lock")):
            continue  # 非代码文件跳过
        all_flows.extend(_find_taint_flows(content, path))
    return all_flows


# ── Strands @tool 封装 ──
try:  # pragma: no cover
    from strands.tools import tool as _strands_tool
    _HAS_STRANDS = True
except Exception:  # pragma: no cover
    _strands_tool = lambda f: f
    _HAS_STRANDS = False

_TAINT_FLOW_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "文件路径到文件内容的映射字典（代码文件跑污点追踪，非代码自动跳过）",
        }
    },
    "required": ["files"],
}


if _HAS_STRANDS:
    @_strands_tool(inputSchema=_TAINT_FLOW_SCHEMA)
    def taint_flow(files: dict[str, str]) -> list[dict]:
        """对仓库代码文件做污点追踪（source→sink），找输入流向危险操作的链路。

        Args:
            files: 文件路径到文件内容的映射字典，key 为仓库相对路径。

        Returns:
            flows 列表；每条含 type/severity/confidence/source/sink/evidence/file/line。
            这是确定性工具，结果可直接作为漏洞证据引用。
        """
        return scan_repo(files)
else:  # pragma: no cover
    def taint_flow(files: dict[str, str]) -> list[dict]:
        """污点追踪（无 Strands 环境时退化实现）。"""
        return scan_repo(files)


__all__ = ["scan_repo", "taint_flow"]
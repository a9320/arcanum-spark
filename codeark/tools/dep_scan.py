"""@tool 封装依赖扫描（OSV 已知漏洞比对）— 本地确定性。

侦察/验证 Agent 的依赖漏洞工具。
- 输入：files: dict[str, str]（文件路径 → 文件内容），只解析依赖清单
  （requirements.txt / pyproject.toml / package.json / composer.json /
  composer.lock；Pipfile / environment.yml 暂不解析，静默跳过），
  另对 Dockerfile/composer.json 做 PHP 运行时钉检查（PHP2Shell 动机样本）
- 输出：findings 列表，每条含 package/version/cwe/description/fix/source/ecosystem/file
- 确定性工具：依赖与本地 OSV 数据/内置已知漏洞库比对，结果可直接作为漏洞证据引用
- 零网络调用：OSV 数据预置（本地 index.json 若存在则用，否则回落内置库）
"""
from __future__ import annotations

import json
import re
from typing import Any

# 内置已知漏洞库（OSV 本地数据缺失时回落）
_LOCAL_VULN_DB: dict[str, dict] = {
    "django":   {"vulnerable_below": "4.2.0", "cwe": "CWE-89",  "desc": "旧版 Django 存在 SQL 注入漏洞"},
    "flask":    {"vulnerable_below": "2.3.0", "cwe": "CWE-79",  "desc": "旧版 Flask 存在 XSS 漏洞"},
    "requests": {"vulnerable_below": "2.31.0", "cwe": "CWE-295", "desc": "旧版 requests 证书校验缺陷"},
    "pyyaml":   {"vulnerable_below": "6.0",   "cwe": "CWE-502", "desc": "旧版 PyYAML yaml.load() 可致任意代码执行"},
    "pillow":   {"vulnerable_below": "10.0.0", "cwe": "CWE-120", "desc": "旧版 Pillow 存在缓冲区溢出"},
    "cryptography": {"vulnerable_below": "41.0.0", "cwe": "CWE-327", "desc": "旧版 cryptography 弱算法支持"},
    "lodash":   {"vulnerable_below": "4.17.21", "cwe": "CWE-1321", "desc": "旧版 lodash 原型污染"},
    "express":  {"vulnerable_below": "4.18.0", "cwe": "CWE-1321", "desc": "旧版 Express 开放重定向"},
    "axios":    {"vulnerable_below": "1.6.0",  "cwe": "CWE-918",  "desc": "旧版 Axios SSRF 漏洞"},
    # PHP/Packagist 条目（2026-10-25 R-PHP：经 OSV API 逐条实证，键=完整 composer
    # 包名，desc 内 GHSA id 可溯源；动机样本=PHP2Shell 解释器层 RCE 需依赖层承接）
    "phpmailer/phpmailer": {"vulnerable_below": "5.2.20",  "cwe": "CWE-74",  "desc": "旧版 PHPMailer 发件人字段注入可致远程代码执行（OSV GHSA-4pc3-96mx-wwc8 / CVE-2016-10045）"},
    "smarty/smarty":       {"vulnerable_below": "3.1.21",  "cwe": "CWE-94",  "desc": "旧版 Smarty 任意 PHP 代码执行（OSV GHSA-2pmx-6mm6-6v72 / CVE-2014-8350）"},
    "guzzlehttp/psr7":     {"vulnerable_below": "2.10.2",  "cwe": "CWE-113", "desc": "旧版 guzzlehttp/psr7 URI Host 组件 CRLF 注入（OSV GHSA-hq7v-mx3g-29hw / CVE-2026-49214）"},
}


def _parse_version(version_str: str) -> tuple[int, ...]:
    """解析版本字符串为可比较元组（去掉比较前缀）。"""
    cleaned = re.sub(r"^[><=!~^]+", "", version_str.strip())
    parts = []
    for p in cleaned.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


def _version_below(current: str, threshold: str) -> bool:
    """判断当前版本是否低于阈值版本。"""
    return _parse_version(current) < _parse_version(threshold)


def _query_osv(pkg_name: str, version: str) -> list[dict]:
    """查本地 OSV index.json（若存在），否则查内置库。"""
    try:
        idx = json.loads(_OSV_INDEX_JSON)
        for key in (f"PyPI:{pkg_name.lower()}", f"npm:{pkg_name.lower()}", f"Packagist:{pkg_name.lower()}"):
            for vuln in idx.get(key, []):
                if version in vuln.get("versions", []):
                    return [{
                        "cwe": vuln.get("cwe", "CWE-000"),
                        "summary": vuln.get("summary", "通过 OSV 发现的漏洞"),
                        "id": vuln.get("id", "OSV"),
                    }]
                for rng in vuln.get("ranges", []):
                    introduced = rng.get("introduced")
                    fixed = rng.get("fixed")
                    cur = _parse_version(version)
                    intro = _parse_version(introduced) if introduced else None
                    fix = _parse_version(fixed) if fixed else None
                    if intro and cur < intro:
                        continue
                    if fix and cur >= fix:
                        continue
                    return [{
                        "cwe": vuln.get("cwe", "CWE-000"),
                        "summary": vuln.get("summary", "通过 OSV 发现的漏洞"),
                        "id": vuln.get("id", "OSV"),
                    }]
    except Exception:
        pass
    return []


# 可选：若部署时有 OSV index.json 内容，注入此处；否则空则只用内置库
_OSV_INDEX_JSON = "{}"


def _parse_requirements(content: str) -> list[tuple[str, str]]:
    """解析 requirements.txt，返回 [(包名小写, 版本), ...]。"""
    out = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", "--")):
            continue
        m = re.match(r"^([a-zA-Z0-9_.-]+)\s*[<>=!~]+\s*([0-9][0-9.]*)", line)
        if m:
            out.append((m.group(1).lower(), m.group(2)))
    return out


def _parse_pyproject(content: str) -> list[tuple[str, str]]:
    """解析 pyproject.toml 的 [project].dependencies 列表。"""
    out = []
    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if not m:
        return out
    for line in m.group(1).splitlines():
        mm = re.match(r'^\s*["\']([a-zA-Z0-9_.-]+)[><=!~]*([0-9][0-9.]*)', line)
        if mm:
            out.append((mm.group(1).lower(), mm.group(2)))
    return out


def _parse_package_json(content: str) -> list[tuple[str, str]]:
    """解析 package.json 的 dependencies + devDependencies。"""
    out = []
    try:
        data = json.loads(content)
    except Exception:
        return out
    for section in ("dependencies", "devDependencies"):
        for name, ver in (data.get(section) or {}).items():
            clean = re.sub(r"^[><=!~^]+", "", str(ver).strip())
            if clean:
                out.append((name.lower(), clean))
    return out


def _parse_composer_json(content: str) -> list[tuple[str, str]]:
    """解析 composer.json 的 require + require-dev（PHP 伪包除外）。

    仅「纯数字点分版本」参与包级漏洞比对——带 */||/比较符的区间约束不做
    版本可判定（FP 最小化：约束允许的多个版本有干净有受累，误报风险大于
    漏报代价；精确锁定版交给 composer.lock）。php/ext-*/lib-* 伪包跳过
    （php 约束另走 _check_php_runtime 的下限检查）。
    """
    out = []
    try:
        data = json.loads(content)
    except Exception:
        return out
    for section in ("require", "require-dev"):
        for name, ver in (data.get(section) or {}).items():
            if name in ("php", "php-64bit", "hhvm") or name.startswith(("ext-", "lib-")):
                continue
            clean = str(ver).strip()
            if re.fullmatch(r"v?\d+(?:\.\d+)*", clean):
                out.append((name.lower(), clean.lstrip("v")))
    return out


def _parse_composer_lock(content: str) -> list[tuple[str, str]]:
    """解析 composer.lock 的 packages + packages-dev（精确锁定版）。"""
    out = []
    try:
        data = json.loads(content)
    except Exception:
        return out
    for section in ("packages", "packages-dev"):
        for item in data.get(section) or []:
            name = str(item.get("name") or "").strip()
            ver = str(item.get("version") or "").strip()
            if name and re.fullmatch(r"v?\d+(?:\.\d+)*(?:-[0-9A-Za-z.]+)?", ver):
                out.append((name.lower(), ver.lstrip("v")))
    return out


# PHP2Shell（CVE-2026-109618/109619，PHP 解释器层 RCE）各分支官方修复版
# （PHP 组 2026-10-21 例外公告，CrowdStrike/Unit42 双源引述；8.1 及更早分支
# 无修复版）。动机：解释器层 RCE 是源码级 SAST 的天然盲区，只有运行时/
# 依赖货币度层接得住。
_PHP2SHELL_FIXED = {"8.2": "8.2.35", "8.3": "8.3.36", "8.4": "8.4.27", "8.5": "8.5.12"}


def _check_php_runtime(path: str, base: str, content: str) -> list[dict]:
    """PHP 运行时钉检查（PHP2Shell 动机样本）。

    - Dockerfile `FROM php:X.Y.Z...`：精确 patch 钉低于所在分支修复版 → 命中；
      可修复分支的浮动 tag（无 patch 位）→ 跳过（FP 最小化：实际运行版本由
      运维决定，钉住才可判定）；
    - Dockerfile `FROM php:X.Y` 浮动 tag：仅当分支无官方修复版（<8.2）→ 命中
      （浮动解析到分支最新=永久无修复，判定无歧义）；
    - composer.json `require.php`：约束下限允许 <8.2 → 命中。
    """

    def _hit(version_label: str, desc: str, fix: str) -> dict:
        return {
            "package": "php",
            "version": version_label,
            "ecosystem": "php-runtime",
            "cwe": "CWE-1104",
            "description": desc,
            "fix": fix,
            "source": "local_fallback",
            "file": path,
            "severity": "high",
            "confidence": 90,
            "rule": "DEP-PHP2SHELL",
        }

    findings: list[dict] = []
    if base == "dockerfile" or base.startswith("dockerfile."):
        for m in re.finditer(r"(?im)^\s*FROM\s+php:(\d+)\.(\d+)(?:\.(\d+))?(?:[-\s].*)?$", content):
            major, minor = int(m.group(1)), int(m.group(2))
            patch = m.group(3)
            branch = f"{major}.{minor}"
            label = f"php:{branch}.{patch}" if patch else f"php:{branch}"
            if (major, minor) >= (8, 2):
                if branch in _PHP2SHELL_FIXED and patch and _version_below(
                        f"{branch}.{patch}", _PHP2SHELL_FIXED[branch]):
                    findings.append(_hit(
                        label,
                        f"Dockerfile 钉定 PHP {branch}.{patch} 低于 PHP2Shell（CVE-2026-109618/109619）"
                        f"修复版 {_PHP2SHELL_FIXED[branch]}（解释器层 RCE，无需认证）",
                        f"升级 PHP 至 >= {_PHP2SHELL_FIXED[branch]}（{branch} 分支）"))
                # 可修复分支浮动 tag：跳过（文档化决策，见 docstring）
            elif (major, minor) < (8, 2):
                findings.append(_hit(
                    label,
                    f"Dockerfile 使用 PHP {branch} 分支——无 PHP2Shell（CVE-2026-109618/109619）官方"
                    f"修复版（2026-10-21 例外公告仅覆盖 8.2.35/8.3.36/8.4.27/8.5.12），该分支必须整体升级",
                    "升级至受支持分支（8.2/8.3/8.4/8.5）并 >= 对应分支修复版"))
            # 未知的更高主分支（如 9.x）：无公告依据，跳过
    elif base == "composer.json":
        try:
            data = json.loads(content)
        except Exception:
            return findings
        constraint = str(((data.get("require") or {}).get("php") or "")).strip()
        if constraint and constraint != "*":
            pairs = re.findall(r"(\d+)\.(\d+)", constraint)
            if pairs:
                lo = min((int(a), int(b)) for a, b in pairs)
                if lo < (8, 2):
                    findings.append(_hit(
                        f"php constraint '{constraint}'",
                        f"composer require.php 约束 '{constraint}' 允许安装 <8.2 的 PHP——这些分支无 "
                        f"PHP2Shell（CVE-2026-109618/109619）官方修复版",
                        "收紧 php 约束至 >=8.2，部署环境升级到分支修复版"
                        "（8.2.35/8.3.36/8.4.27/8.5.12）"))
    return findings


def _check_deps(deps: list[tuple[str, str]], ecosystem: str, file: str) -> list[dict]:
    """对依赖列表比对已知漏洞，返回 findings。"""
    findings = []
    for pkg, version in deps:
        # 1) 本地 OSV index（若有）
        osv_hits = _query_osv(pkg, version)
        if osv_hits:
            for v in osv_hits:
                findings.append({
                    "package": pkg,
                    "version": version,
                    "ecosystem": ecosystem,
                    "cwe": v["cwe"],
                    "description": v["summary"],
                    "fix": f"升级 {pkg} — 详见 {v['id']}",
                    "source": "osv_local",
                    "file": file,
                    "severity": "high",
                    "confidence": 90,
                    "rule": f"DEP-{v['cwe'].replace('-', '')}",
                })
            continue
        # 2) 内置已知漏洞库
        if pkg in _LOCAL_VULN_DB:
            vuln = _LOCAL_VULN_DB[pkg]
            if _version_below(version, vuln["vulnerable_below"]):
                findings.append({
                    "package": pkg,
                    "version": version,
                    "ecosystem": ecosystem,
                    "cwe": vuln["cwe"],
                    "description": vuln["desc"],
                    "fix": f"升级 {pkg} 至 >= {vuln['vulnerable_below']}",
                    "source": "local_fallback",
                    "file": file,
                    "severity": "high",
                    "confidence": 90,
                    "rule": f"DEP-{vuln['cwe'].replace('-', '')}",
                })
    return findings


def scan_deps(files: dict[str, str]) -> list[dict[str, Any]]:
    """对依赖清单文件跑已知漏洞比对，聚合全部 findings。

    Args:
        files: 文件路径 → 文件内容映射（仅处理依赖清单文件名）。

    Returns:
        findings 列表，每条含 package/version/ecosystem/cwe/description/fix/
        source/file/severity/confidence/rule。
    """
    all_findings: list[dict[str, Any]] = []
    for path, content in files.items():
        base = path.rsplit("/", 1)[-1].lower()
        if base == "requirements.txt":
            all_findings += _check_deps(_parse_requirements(content), "PyPI", path)
        elif base == "pyproject.toml":
            all_findings += _check_deps(_parse_pyproject(content), "PyPI", path)
        elif base == "package.json":
            all_findings += _check_deps(_parse_package_json(content), "npm", path)
        elif base == "composer.json":
            all_findings += _check_deps(_parse_composer_json(content), "Packagist", path)
            all_findings += _check_php_runtime(path, base, content)
        elif base == "composer.lock":
            all_findings += _check_deps(_parse_composer_lock(content), "Packagist", path)
        elif base == "dockerfile" or base.startswith("dockerfile."):
            all_findings += _check_php_runtime(path, base, content)
        # Pipfile / environment.yml 暂不解析，静默跳过
    return all_findings


# ── Strands @tool 封装 ──
try:  # pragma: no cover
    from strands.tools import tool as _strands_tool
    _HAS_STRANDS = True
except Exception:  # pragma: no cover
    _strands_tool = lambda f: f
    _HAS_STRANDS = False

_DEP_SCAN_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": "文件路径到文件内容的映射字典（只解析 requirements.txt/pyproject.toml/package.json/composer.json/composer.lock，Dockerfile/composer.json 另做 PHP 运行时钉检查，其余自动跳过）",
        }
    },
    "required": ["files"],
}


if _HAS_STRANDS:
    @_strands_tool(inputSchema=_DEP_SCAN_SCHEMA)
    def dep_scan(files: dict[str, str]) -> list[dict]:
        """对依赖清单做已知漏洞（OSV/内置库）比对。

        Args:
            files: 文件路径到文件内容的映射字典，key 为仓库相对路径。
                仅处理 requirements.txt / pyproject.toml / package.json /
                composer.json / composer.lock；Dockerfile 与 composer.json
                另做 PHP 运行时钉检查（PHP2Shell）。

        Returns:
            findings 列表；每条含 package/version/ecosystem/cwe/description/fix/
            source/file/severity/confidence/rule。
            确定性工具，结果可直接作为漏洞证据引用。
        """
        return scan_deps(files)
else:  # pragma: no cover
    def dep_scan(files: dict[str, str]) -> list[dict]:
        return scan_deps(files)


# ── 闭包绑定工具工厂（无参数，文件集内置；理由同 pitax_scan.make_bound_tool）──
_BOUND_EMPTY_SCHEMA = {"type": "object", "properties": {}, "required": []}


def make_bound_tool(files: dict[str, str]):
    """构造绑定 files 快照的**无参数** dep_scan 工具（供 Agent 注册）。"""
    if _HAS_STRANDS:
        @_strands_tool(inputSchema=_BOUND_EMPTY_SCHEMA)
        def dep_scan() -> list[dict]:  # noqa: F811 - 对模型保持同名，仅去掉参数
            """对当前审计任务已绑定的依赖清单做已知漏洞（OSV/内置库）比对。

            无需任何参数——文件集已内置于本工具。

            Returns:
                findings 列表；每条含 package/version/ecosystem/cwe/description/fix/
                source/file/severity/confidence/rule。
                确定性工具，结果可直接作为漏洞证据引用。
            """
            return scan_deps(files)
        return dep_scan

    def dep_scan() -> list[dict]:  # pragma: no cover - 无 Strands 退化路径
        return scan_deps(files)
    return dep_scan
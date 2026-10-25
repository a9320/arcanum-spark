"""dep_scan 工具逻辑测试（确定性，无需模型调用）。

验证 scan_deps 对依赖清单的已知漏洞比对：
  1. requirements.txt 命中内置库（如旧版 requests/django）
  2. 干净 requirements.txt 不误报
  3. package.json 命中内置库（如旧版 lodash）
  4. pyproject.toml 解析
  5. 非依赖清单文件静默跳过
  6. @tool 封装在 Strands 环境可用
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # 跨环境便携路径(原 WSL 硬编码)

from codeark.tools.dep_scan import (
    scan_deps,
    _parse_requirements,
    _parse_pyproject,
    _parse_package_json,
    _parse_composer_json,
    _parse_composer_lock,
)


def test_requirements_hit() -> None:
    files = {
        "requirements.txt": (
            "flask==1.1.2\n"
            "django==3.2.0\n"
            "requests==2.25.0\n"
            "fastapi==0.115.0\n"
        ),
    }
    findings = scan_deps(files)
    pkgs = {f["package"] for f in findings}
    assert "flask" in pkgs, f"flask 应命中，实际 {pkgs}"
    assert "django" in pkgs, f"django 应命中，实际 {pkgs}"
    assert "requests" in pkgs, f"requests 应命中，实际 {pkgs}"
    assert "fastapi" not in pkgs, f"fastapi 0.115.0 不应命中，实际 {pkgs}"
    assert all(f["source"] == "local_fallback" for f in findings)
    assert all(f["confidence"] == 90 for f in findings)
    print(f"  ✅ requirements 命中: {sorted(pkgs)}")


def test_requirements_clean() -> None:
    files = {"requirements.txt": "fastapi==0.115.0\nuvicorn==0.32.0\n# 注释\npytest==9.1.1\n"}
    findings = scan_deps(files)
    assert findings == [], f"干净 requirements 不应命中，实际 {findings}"
    print("  ✅ 干净 requirements 无误报")


def test_package_json_hit() -> None:
    files = {
        "package.json": (
            '{\n'
            '  "dependencies": {\n'
            '    "lodash": "4.17.20",\n'
            '    "express": "4.17.1",\n'
            '    "axios": "1.8.0"\n'
            '  }\n'
            '}'
        ),
    }
    findings = scan_deps(files)
    pkgs = {f["package"] for f in findings}
    assert "lodash" in pkgs, f"lodash 应命中，实际 {pkgs}"
    assert "express" in pkgs, f"express 应命中，实际 {pkgs}"
    assert "axios" not in pkgs, f"axios 1.8.0 不应命中，实际 {pkgs}"
    print(f"  ✅ package.json 命中: {sorted(pkgs)}")


def test_pyproject() -> None:
    files = {
        "pyproject.toml": (
            '[project]\n'
            'name = "demo"\n'
            'dependencies = [\n'
            '  "django>=4.1.0",\n'
            '  "flask==1.0",\n'
            '  "pydantic==2.9.0",\n'
            ']\n'
        ),
    }
    findings = scan_deps(files)
    pkgs = {f["package"] for f in findings}
    assert "django" in pkgs, f"django 4.1.0 < 4.2.0 应命中，实际 {pkgs}"
    assert "flask" in pkgs, f"flask 1.0 应命中，实际 {pkgs}"
    assert "pydantic" not in pkgs, f"pydantic 不应命中，实际 {pkgs}"
    print(f"  ✅ pyproject.toml 命中: {sorted(pkgs)}")


def test_skip_non_dep_files() -> None:
    files = {
        "src/app.py": "import os\nos.system(x)\n",
        "README.md": "# readme\n",
        "config.yaml": "key: value\n",
    }
    findings = scan_deps(files)
    assert findings == [], f"非依赖清单文件不应命中，实际 {findings}"
    print("  ✅ 非依赖清单文件静默跳过")


def test_parser_helpers() -> None:
    assert _parse_requirements("flask==1.1.2\n# c\n-django\n") == [("flask", "1.1.2")]
    assert ("django", "4.1.0") in _parse_pyproject('dependencies = [\n  "django>=4.1.0",\n]')
    assert ("lodash", "4.17.20") in _parse_package_json('{"dependencies": {"lodash": "4.17.20"}}')
    print("  ✅ 解析辅助函数")


# ── PHP 生态扩展（2026-10-25 R-PHP：PHP2Shell 动机样本，composer+运行时钉）──

def test_composer_json_hit() -> None:
    files = {
        "composer.json": json.dumps({
            "require": {
                "php": "^8.2",
                "phpmailer/phpmailer": "5.2.19",
                "monolog/monolog": "^3.0",
                "ext-json": "*",
            },
        })
    }
    findings = scan_deps(files)
    pkgs = {f["package"] for f in findings}
    assert "phpmailer/phpmailer" in pkgs, f"phpmailer 5.2.19 应命中，实际 {pkgs}"
    assert "monolog/monolog" not in pkgs, "区间约束不做版本可判定（FP 最小化）"
    assert "php" not in pkgs and "ext-json" not in pkgs, "PHP 伪包不进包级比对"
    print(f"  ✅ composer.json 命中: {sorted(pkgs)}")


def test_composer_lock_hit() -> None:
    files = {
        "composer.lock": json.dumps({
            "packages": [
                {"name": "smarty/smarty", "version": "v3.1.20"},
                {"name": "guzzlehttp/psr7", "version": "2.9.0"},
            ],
            "packages-dev": [{"name": "phpmailer/phpmailer", "version": "v5.2.19"}],
        })
    }
    findings = scan_deps(files)
    pkgs = {f["package"] for f in findings}
    assert {"smarty/smarty", "guzzlehttp/psr7", "phpmailer/phpmailer"} <= pkgs, f"lock 精确版应命中，实际 {pkgs}"
    assert all(f["ecosystem"] == "Packagist" for f in findings)
    print(f"  ✅ composer.lock 命中: {sorted(pkgs)}")


def test_dockerfile_php_runtime_pins() -> None:
    files = {
        "deploy/Dockerfile": (
            "FROM php:8.2.30-apache\n"        # 精确钉 <8.2.35 → 命中
            "FROM php:8.4.27-cli AS build\n"  # 恰为修复版 → 不命中
            "FROM php:8.2-apache\n"           # 可修复分支浮动 tag → 不命中
            "FROM php:8.1.31-fpm\n"           # 无修复版分支精确钉 → 命中
            "FROM php:8.1-fpm\n"              # 无修复版分支浮动 → 命中
            "FROM node:20-alpine\n"           # 非 php 基础镜像 → 不命中
        )
    }
    findings = [f for f in scan_deps(files) if f["rule"] == "DEP-PHP2SHELL"]
    vers = [f["version"] for f in findings]
    assert "php:8.2.30" in vers, f"8.2.30 < 8.2.35 应命中，实际 {vers}"
    assert "php:8.1.31" in vers and "php:8.1" in vers, f"无修复版分支应命中，实际 {vers}"
    assert "php:8.4.27" not in vers, "恰为修复版不应命中"
    assert "php:8.2" not in vers, "可修复分支浮动 tag 不应命中（FP 最小化）"
    assert all(f["cwe"] == "CWE-1104" and f["ecosystem"] == "php-runtime" for f in findings)
    print(f"  ✅ Dockerfile PHP 运行时钉: {vers}")


def test_composer_php_constraint_floor() -> None:
    low = scan_deps({"composer.json": json.dumps({"require": {"php": "^8.1.0 || 7.4"}})})
    low_runtime = [f for f in low if f["rule"] == "DEP-PHP2SHELL"]
    assert len(low_runtime) == 1, f"约束下限 8.1 <8.2 应恰命中一条，实际 {low_runtime}"
    assert "无" in low_runtime[0]["description"] and "修复版" in low_runtime[0]["description"]
    assert scan_deps({"composer.json": json.dumps({"require": {"php": "^8.2"}})}) == [], "^8.2 不应命中"
    assert scan_deps({"composer.json": json.dumps({"require": {"php": "*"}})}) == [], "* 无信息不应命中"
    print("  ✅ composer require.php 下限检查")


def test_php_multistage_and_noise() -> None:
    files = {
        "Dockerfile.modelscope": "FROM php:7.4.33-zts\nRUN echo hi\n",  # 前缀变体名也要覆盖
        "README.md": "FROM php:8.0.1 不在代码块里也无妨——仅 Dockerfile 文件名参与",
    }
    findings = [f for f in scan_deps(files) if f["rule"] == "DEP-PHP2SHELL"]
    assert len(findings) == 1 and findings[0]["version"] == "php:7.4.33", f"变体文件名应覆盖，实际 {findings}"
    print("  ✅ Dockerfile 变体文件名覆盖 + 噪音不误报")


def test_composer_parse_helpers() -> None:
    assert _parse_composer_json('{"require": {"php": "^8.2", "ext-json": "*", "phpmailer/phpmailer": "5.2.19", "smarty/smarty": "^4.0"}}') == [
        ("phpmailer/phpmailer", "5.2.19"),
    ]
    assert ("phpmailer/phpmailer", "5.2.19") in _parse_composer_lock(
        '{"packages": [{"name": "phpmailer/phpmailer", "version": "v5.2.19"}]}')
    print("  ✅ composer 解析辅助函数")


if __name__ == "__main__":
    print("=== dep_scan 逻辑测试 ===")
    test_requirements_hit()
    test_requirements_clean()
    test_package_json_hit()
    test_pyproject()
    test_skip_non_dep_files()
    test_parser_helpers()
    test_composer_json_hit()
    test_composer_lock_hit()
    test_dockerfile_php_runtime_pins()
    test_composer_php_constraint_floor()
    test_php_multistage_and_noise()
    test_composer_parse_helpers()
    print("\n全部通过 ✅")
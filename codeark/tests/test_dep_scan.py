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

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # 跨环境便携路径(原 WSL 硬编码)

from tools.dep_scan import scan_deps, _parse_requirements, _parse_pyproject, _parse_package_json


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


if __name__ == "__main__":
    print("=== dep_scan 逻辑测试 ===")
    test_requirements_hit()
    test_requirements_clean()
    test_package_json_hit()
    test_pyproject()
    test_skip_non_dep_files()
    test_parser_helpers()
    print("\n全部通过 ✅")
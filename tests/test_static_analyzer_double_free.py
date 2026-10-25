"""R13 审计修复：9a796dd double-free 变量级去重回归锚（10-25 全仓审计 A-F6）。

10-24 修复（9a796dd）当时零新增测试。本文件钉死契约：
- 同一变量 ≥2 行 free → 恰好一条 double-free Risk（变量名与计数入 description）；
- 不同变量各自一条；
- 单次 free → 不报 double-free。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# rich 是 requirements 硬依赖但本地最小 venv 未装（与 test_engine_integration
# 被 verify.sh 排除同因）——CI 装 requirements 必有，本地缺失时按仓内
# importorskip 惯例跳过，不红本地验证。
pytest.importorskip("rich", reason="engine 控制台输出依赖 rich")

# 引擎约定：app.config 导入时把 CODERISK_PATH（engine 根）挂进 sys.path，
# 模块内为扁平导入（agents.* / core.*），与 test_engine_integration 同款。
from app.config import settings  # noqa: E402,F401

assert settings.CODERISK_PATH in sys.path  # 与 test_engine_integration 同判据

from agents.static_analyzer import StaticAnalyzer  # noqa: E402
from core.models import CodeFile, Language  # noqa: E402


def _analyze_c(content: str) -> list:
    f = CodeFile(path=Path("a.c"), content=content, language=Language.C)
    return StaticAnalyzer().analyze(f)


def _double_free_risks(risks: list) -> list:
    return [r for r in risks if "Double Free" in (r.title or "")]


def test_same_var_freed_twice_reports_exactly_once():
    # 两次 free 必须分行：计数按"含 free(p) 的行数"统计
    code = "int main(){\nchar*p=malloc(1);\nfree(p);\nfree(p);\nreturn 0;}\n"
    df = _double_free_risks(_analyze_c(code))
    assert len(df) == 1
    assert "'p' freed 2 times" in df[0].description


def test_distinct_vars_each_report_once():
    code = "void f(){\nfree(a);\nfree(a);\nfree(b);\nfree(b);\n}\n"
    df = _double_free_risks(_analyze_c(code))
    assert len(df) == 2
    descs = " | ".join(r.description for r in df)
    assert "'a' freed 2 times" in descs and "'b' freed 2 times" in descs


def test_single_free_not_flagged_as_double_free():
    code = "void g(){\nchar*q=malloc(1);\nfree(q);\n}\n"
    assert _double_free_risks(_analyze_c(code)) == []

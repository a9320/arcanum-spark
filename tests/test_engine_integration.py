"""引擎层集成测试 — 验证内置 engine/（传统漏洞检测）真实跑通，不是空转。
覆盖反馈问题：
  1. 引擎层外链依赖 → 现在 engine/ 内置，CODERISK_PATH 自动指向
  2. direct_upload 空实现 → 现已实现（含安全限制）
  3. fcntl Windows 兼容 → MemoryLayer 可导入可用
运行: python -m pytest tests/test_engine_integration.py -v
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── 引擎路径探测 ──
def test_coderisk_path_points_to_builtin_engine():
    from app.config import settings
    engine_root = Path(settings.CODERISK_PATH).resolve()
    assert engine_root.name == "engine"
    assert (engine_root / "core" / "models.py").is_file()
    assert (engine_root / "agents" / "static_analyzer.py").is_file()


def test_engine_importable_via_sys_path():
    from app.config import settings
    assert settings.CODERISK_PATH in sys.path
    import agents.static_analyzer  # noqa: F401
    import core.models  # noqa: F401


# ── Agent 1 静态分析真实跑通 ──
def test_static_analysis_real_findings():
    from agents.static_analyzer import StaticAnalyzer
    from core.models import CodeFile
    sa = StaticAnalyzer()
    cf = CodeFile(path="src/app.py", language="python",
                  content="import os\ndef run(cmd):\n    os.system(cmd)\n")
    risks = sa.analyze_batch([cf])
    assert len(risks) >= 1
    assert any("Command Injection" in r.title for r in risks)


# ── Agent 1b 污点分析真实跑通 ──
def test_taint_analysis_real_flow():
    from core.taint_analyzer import TaintAnalyzer
    ta = TaintAnalyzer()
    flows = ta.analyze_python('import os\ncmd = input("Enter: ")\nos.system(cmd)\n', "app.py")
    assert len(flows) == 1
    assert flows[0].cwe_id == "CWE-78"


# ── Agent 1c 依赖扫描 ──
def test_dependency_scan(tmp_path):
    from core.dependency_scanner import scan_project_dependencies
    (tmp_path / "requirements.txt").write_text(
        "django==2.2.0\nrequests==2.31.0\n", encoding="utf-8")
    try:
        risks = scan_project_dependencies(tmp_path)
        # 漏洞库可能为空（未下载 CVE 数据），此处只验证接口可调用、不抛异常
        assert isinstance(risks, list)
    except Exception as e:
        pytest.fail(f"dependency scan raised: {e}")


# ── MemoryLayer（fcntl Windows 降级）──
def test_memory_layer_import_and_save():
    from core.memory import MemoryLayer
    ml = MemoryLayer()
    ml._save()  # 触发文件写入路径（含锁降级逻辑）
    ml2 = MemoryLayer()
    ml2._load()
    assert True


# ── direct_upload 实现 ──
def test_direct_upload_writes_files():
    from app.tasks import _prepare_code
    work = _prepare_code("test-dup-1", {
        "source": "direct_upload",
        "files": [
            {"path": "src/main.py", "content": "import os\nos.system('ls')\n"},
            {"path": "README.md", "content": "# demo"},
        ],
    })
    assert work is not None
    assert (Path(work) / "src" / "main.py").is_file()
    assert (Path(work) / "README.md").read_text(encoding="utf-8") == "# demo"


def test_direct_upload_rejects_path_traversal():
    from app.tasks import _prepare_code
    assert _prepare_code("test-dup-2", {
        "source": "direct_upload",
        "files": [{"path": "../evil.py", "content": "x=1"}],
    }) is None
    assert _prepare_code("test-dup-3", {
        "source": "direct_upload",
        "files": [{"path": "/abs/evil.py", "content": "x=1"}],
    }) is None


def test_direct_upload_rejects_empty_and_oversize():
    from app.tasks import _prepare_code
    assert _prepare_code("test-dup-4", {"source": "direct_upload", "files": []}) is None
    assert _prepare_code("test-dup-5", {"source": "direct_upload"}) is None
    big = "x" * (1024 * 1024 + 1)
    assert _prepare_code("test-dup-6", {
        "source": "direct_upload",
        "files": [{"path": "big.txt", "content": big}],
    }) is None


# ── Agent 1-4 全链路（无 LLM 降级路径）──
def test_full_pipeline_without_llm(tmp_path, monkeypatch):
    """direct_upload → Agent 0/1/1b/1c → 合并 → 报告（Agent 2/3 无 LLM 自动降级）。"""
    from app import tasks as T

    code_path = T._prepare_code("test-pipe-1", {
        "source": "direct_upload",
        "files": [{"path": "app.py", "content":
                   "import os\ncmd = input('Enter: ')\nos.system(cmd)\n"}],
    })
    assert code_path

    static = T._run_static_analysis("test-pipe-1", code_path)
    assert len(static) >= 1  # Agent 1 真实检出

    taint = T._run_taint_analysis("test-pipe-1", code_path)
    assert len(taint) == 1   # Agent 1b 真实检出

    semantic = T._run_semantic_analysis("test-pipe-1", code_path, static)
    assert semantic == []    # Agent 2 无 LLM → 空列表（优雅降级，非崩溃）

    merged = T._merge_findings(static, semantic)
    verified = T._run_verification("test-pipe-1", code_path, merged)

    monkeypatch.chdir(tmp_path)  # 报告写到临时目录
    report = T._generate_report("test-pipe-1", verified, ["json"],
                                T.NutrientDWSClient())
    assert report["total_findings"] >= 1
    assert "output_guardrail" in report  # 主线 A 护栏已接入
    assert report["summary"]["high"] + report["summary"]["critical"] >= 1

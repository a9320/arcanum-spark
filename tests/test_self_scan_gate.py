"""自扫描闸门策略函数单测（2026-10-25 PHP2Shell 自扫窗立项）。

只测策略判定与豁免清单本身；全仓产品级扫描（CLI --dry）由 ci.yml 的
"Self-scan gate" 步骤执行——pytest 不重复跑产品级扫描（口径稳定 + 秒级闸门）。
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SPEC = importlib.util.spec_from_file_location(
    "self_scan_gate", Path(__file__).resolve().parents[1] / "scripts" / "self_scan_gate.py")
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def test_allowlist_dir_bound() -> None:
    # 豁免区：demo 阳性对照 + 三处测试/冒烟目录（含深层嵌套）
    for p in ("demo/vuln-demo-repo/src/config.py",
              "demo/CLAUDE.md",
              "tests/test_x.py",
              "codeark/tests/test_q.py",
              "codeark/tests/sub/deep.py",
              "scripts/smoke/scout_loop_smoke.py"):
        assert gate.findings_allowed(p), f"{p} 应在豁免区"
    # 白名单外：生产代码与"形似豁免名"的目录（前缀必须目录绑定）
    for p in ("codeark/agents/verify_agent.py",
              "app.py",
              "scripts/test_count.py",
              "scripts/self_scan_gate.py",
              "eval/check_report.py",
              "testsuite/x.py",
              "codeark/tests_extra/x.py",
              "demos/x.py"):
        assert not gate.findings_allowed(p), f"{p} 不应在豁免区"


def test_policy_covers_known_selfscan_hits() -> None:
    # 10-25 首跑实拍：13 条命中必须全部落在豁免区（防清单漂移）
    known_hits = [
        "demo/vuln-demo-repo/.github/copilot-instructions.md",
        "demo/vuln-demo-repo/src/config.py",
        "scripts/smoke/scout_loop_v2_smoke.py",
        "codeark/tests/test_quarantine.py",
        "codeark/tests/test_pitax_scan.py",
        "tests/test_quickscan_api.py",
        "codeark/tests/test_scout_prompt_hygiene.py",
    ]
    assert all(gate.findings_allowed(p) for p in known_hits)

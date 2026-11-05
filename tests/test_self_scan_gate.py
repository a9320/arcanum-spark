"""自扫描闸门策略函数单测（2026-10-25 立项；2026-11-05 改为逐条豁免台账语义）。

只测台账判定本身；全仓产品级扫描（CLI --dry）由 ci.yml 的
"Self-scan gate" 步骤执行——pytest 不重复跑产品级扫描（口径稳定 + 秒级闸门）。
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_SPEC = importlib.util.spec_from_file_location(
    "self_scan_gate", Path(__file__).resolve().parents[1] / "scripts" / "self_scan_gate.py")
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)

TODAY = date.today().isoformat()
LEDGER = gate.load_ledger(gate.LEDGER_PATH)


def _allowed(path: str, rule: str = "PIT-T-51") -> bool:
    entry, _ = gate.match_exemption(path, rule, LEDGER, TODAY)
    return entry is not None


def test_ledger_dir_binding() -> None:
    # 豁免区（台账条目）：demo 阳性对照 + 引擎单测 + 冒烟脚本（含深层嵌套）
    for p in ("demo/vuln-demo-repo/src/config.py",
              "demo/CLAUDE.md",
              "codeark/tests/test_q.py",
              "codeark/tests/sub/deep.py",
              "scripts/smoke/scout_loop_smoke.py"):
        assert _allowed(p), f"{p} 应被台账覆盖"
    # 白名单外：生产代码与"形似豁免名"的目录（前缀必须目录绑定）
    for p in ("codeark/agents/verify_agent.py",
              "app.py",
              "scripts/test_count.py",
              "scripts/self_scan_gate.py",
              "eval/check_report.py",
              "tests/test_x.py",
              "testsuite/x.py",
              "codeark/tests_extra/x.py",
              "demos/x.py"):
        assert not _allowed(p), f"{p} 不应被台账覆盖"


def test_ledger_rule_scoping() -> None:
    # 台账条目 rule="*" 对任意规则生效；新增单规则条目时这里补锚
    assert _allowed("demo/a.md", "PIT-N-06")
    assert _allowed("scripts/smoke/x.py", "PIT-E-57")


def test_policy_covers_current_selfscan_hits() -> None:
    # 2026-11-05 实拍：当前 11 条命中路径必须全部被台账覆盖（防台账漂移）。
    # （旧版含 tests/test_quickscan_api.py 与 codeark/tests/test_scout_prompt_hygiene.py，
    #  已随测试文件演进自然消失——这正是台账 stale 检测存在的意义。）
    current_hits = [
        "codeark/tests/test_azure_preflight_wiring.py",
        "codeark/tests/test_pitax_scan.py",
        "codeark/tests/test_quarantine.py",
        "demo/vuln-demo-repo/.cursor/rules",
        "demo/vuln-demo-repo/.github/copilot-instructions.md",
        "demo/vuln-demo-repo/docs/AGENT_GUIDE.md",
        "demo/vuln-demo-repo/src/admin_panel.py",
        "demo/vuln-demo-repo/src/config.py",
        "demo/vuln-demo-repo/src/rewards.py",
        "scripts/smoke/scout_loop_smoke.py",
        "scripts/smoke/scout_loop_v2_smoke.py",
    ]
    for p in current_hits:
        assert _allowed(p, "PIT-N-06") or _allowed(p, "PIT-T-51") or _allowed(p, "PIT-E-57"), \
            f"{p} 不被任何台账条目覆盖——台账与实际命中漂移"


def test_ledger_entries_have_required_fields() -> None:
    for e in LEDGER:
        for k in ("id", "path_prefix", "rule", "reason", "owner", "added", "expires"):
            assert str(e.get(k) or "").strip(), f"台账 {e.get('id', '?')} 缺 {k}"

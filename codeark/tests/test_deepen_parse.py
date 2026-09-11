"""deepen 攻击链解析测试（确定性，无需模型调用）。

验证 _parse_attack_chains / _parse_markdown_chains 对模型文本输出的解析：
  1. 标准 JSON 数组格式 → 解析出 N 条 AttackChain
  2. 单 JSON 对象格式 → 解析出 1 条
  3. Markdown 章节格式（模型真实输出）→ 解析出 N 条
  4. 空文本 / 无攻击链内容 → 返回空列表
"""
from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # 跨环境便携路径(原 WSL 硬编码)

from agents.deepen_agent import _parse_attack_chains, _parse_markdown_chains


def test_parse_json_array() -> None:
    raw = (
        '[{"preconditions": ["攻击者可接触代码"], "lateral_moves": ["横向移动"], '
        '"impact": "任意代码执行", "remediation": "改用 subprocess.run"},\n'
        ' {"preconditions": ["文档可被 LLM 读取"], "lateral_moves": [], '
        '"impact": "提示词泄露", "remediation": "移除注入文本"}]'
    )
    chains = _parse_attack_chains(raw)
    assert len(chains) == 2, f"JSON 数组应解析出 2 条，实际 {len(chains)}"
    assert chains[0].impact == "任意代码执行"
    assert chains[1].remediation == "移除注入文本"
    print(f"  ✅ JSON 数组解析: {len(chains)} 条")


def test_parse_single_object() -> None:
    raw = '{"preconditions": ["a"], "lateral_moves": [], "impact": "imp", "remediation": "rem"}'
    chains = _parse_attack_chains(raw)
    assert len(chains) == 1, f"单对象应解析出 1 条，实际 {len(chains)}"
    assert chains[0].impact == "imp"
    print(f"  ✅ 单 JSON 对象解析: {len(chains)} 条")


def test_parse_markdown_chapters() -> None:
    # 模拟模型真实输出的 Markdown 章节格式（含中文标签 + 编号/列表）
    raw = (
        "作为深挖官，以下是对各 CONFIRMED 漏洞的攻击链推演。\n\n"
        "### AttackChain 1: app.py 中的零宽空格注入\n\n"
        "**CONFIRMED 依据**：\n- 工具：PITAX pitax-1-1\n- 证据：U+200B\n\n"
        "**preconditions（前置条件）**：\n"
        "1. 攻击者能向仓库写入内容。\n"
        "2. 应用执行该文件。\n\n"
        "**lateral_moves（横向移动/影响面）**：\n"
        "1. 代码混淆绕过审计。\n"
        "2. 直接命令执行。\n\n"
        "**impact（最终影响）**：\n远程代码执行（RCE），系统被接管。\n\n"
        "**remediation（修复）**：\n将 os.system 改为 subprocess.run，禁用不可见字符。\n\n"
        "### AttackChain 2: README 文档投毒（Developer mode）\n\n"
        "**CONFIRMED 依据**：\n- 工具：PITAX pitax-2-1\n\n"
        "**preconditions（前置条件）**：\n"
        "1. 攻击者能写入 README.md。\n"
        "2. LLM 自动读取文档。\n\n"
        "**lateral_moves（横向移动/影响面）**：\n"
        "1. 安全机制绕过。\n\n"
        "**impact（最终影响）**：\n模型被诱导执行未授权操作。\n\n"
        "**remediation（修复）**：\n移除注入文本，加文档白名单。\n\n"
        "综合防护建议：\n1. CI/CD 加 PITAX 扫描。\n"
    )
    chains = _parse_markdown_chains(raw)
    assert len(chains) == 2, f"Markdown 章节应解析出 2 条，实际 {len(chains)}"
    c1 = chains[0]
    assert len(c1.preconditions) == 2, f"链1 前置条件应 2 条，实际 {c1.preconditions}"
    assert len(c1.lateral_moves) == 2, f"链1 横向移动应 2 条，实际 {c1.lateral_moves}"
    assert "RCE" in c1.impact, f"链1 impact 应含 RCE，实际 {c1.impact}"
    assert "subprocess.run" in c1.remediation, f"链1 修复应含 subprocess.run，实际 {c1.remediation}"
    assert len(chains[1].preconditions) == 2
    print(f"  ✅ Markdown 章节解析: {len(chains)} 条（含字段完整性校验）")


def test_parse_empty() -> None:
    assert _parse_attack_chains("") == []
    assert _parse_attack_chains("没有任何攻击链内容") == []
    assert _parse_markdown_chains("") == []
    print("  ✅ 空/无内容返回空列表")


if __name__ == "__main__":
    print("=== deepen 攻击链解析测试 ===")
    test_parse_json_array()
    test_parse_single_object()
    test_parse_markdown_chapters()
    test_parse_empty()
    print("\n全部通过 ✅")
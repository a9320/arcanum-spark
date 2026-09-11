"""深挖 Agent（Agent D）— 对 CONFIRMED 漏洞推演完整攻击链。

6 节点架构第 5 节点（Agent C 验证之后，裁判官之前）。
- 输入：Agent C 的 VerificationResult（仅处理 CONFIRMED 条目）
- 输出：AttackChain 列表（preconditions / lateral_moves / impact / remediation）
- 模型：Kimi-K3（主力）；GLM-5.2（备选）；DeepSeek-V4-Pro（fallback）
"""
from __future__ import annotations

import json
import re

from strands import Agent
from strands.models import OpenAIModel

from codeark.models.factory import make_model, ModelProvider, ModelTier
from codeark.models.schemas import AttackChain, VerificationResult

__all__ = ["DEEPEN_SYSTEM_PROMPT", "build_deepen_agent", "run_deepen"]


# ── 文本兜底：从模型原始文本解析 AttackChain 列表 ──

# 字段别名（小写子串匹配；覆盖模型各种中英文写法）
_FIELD_ALIASES = {
    "preconditions": ("precondition", "前置条件", "前提条件", "前置", "条件"),
    "lateral_moves": ("lateral", "横向移动", "横向", "攻击路径", "影响面", "移动"),
    "impact": ("impact", "最终影响", "影响"),
    "remediation": ("remediation", "修复", "缓解", "建议", "处置"),
}

# 章节标题：兼容 `## Chain-1` / `## AC-1｜...` / `## 链 1｜...` /
# `## AttackChain 1` / `## 攻击链 1` / `### AC-2：...` 等
_CHAIN_TITLE_RE = (
    r"#{2,4}\s*"
    r"(?:(?:Attack\s*)?Chain|攻击链|链|AC)"
    r"\s*[-–—:：|｜]?\s*\d+"
    r"\s*[:：|｜]?\s*(.*)"
)


def _clean_lines(text: str) -> list[str]:
    """把字段内容切成干净的要点列表（去掉序号/项目符号前缀）。"""
    if not text:
        return []
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[\-*•]\s*", "", line)                # 项目符号
        line = re.sub(r"^\d+[.、)）]\s*", "", line)          # 数字序号
        line = line.strip()
        if line:
            out.append(line)
    return out


def _parse_chain_body(body: str) -> dict[str, str]:
    """从一条攻击链正文里提取各字段内容（容错多种写法）。

    兼容：
      `**Preconditions（前置条件）**` / `**Preconditions**` /
      `- **preconditions**：内容` / `**攻击路径 / Lateral Moves**` 等
    """
    fields: dict[str, str] = {}
    if not body:
        return fields
    # 定位所有 **...** 粗体标记（可能是字段标题）
    matches = list(re.finditer(r"\*\*([^*\n]+)\*\*", body))
    for idx, m in enumerate(matches):
        label = m.group(1).strip().lower()
        core = None
        for c, aliases in _FIELD_ALIASES.items():
            if any(a in label for a in aliases):
                core = c
                break
        if core is None:
            continue
        content_start = m.end()
        # 内容到下一个粗体标题（或到文末）
        content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        content = body[content_start:content_end]
        content = re.sub(r"^\s*[:：]?\s*", "", content).strip()
        if core not in fields or len(content) > len(fields[core]):
            fields[core] = content
    return fields


def _parse_markdown_chains(raw_text: str) -> list[AttackChain]:
    """从模型 Markdown 文本解析 AttackChain（JSON 解析失败时的回退）。

    容错多种章节标题与字段写法（模型输出格式不稳定）。
    """
    if not raw_text:
        return []
    sections = re.split(_CHAIN_TITLE_RE, raw_text)
    if len(sections) < 3:
        return []
    chains = []
    for i in range(1, len(sections) - 1, 2):
        body = sections[i + 1]
        fields = _parse_chain_body(body)
        pre = fields.get("preconditions", "")
        lat = fields.get("lateral_moves", "")
        imp = fields.get("impact", "")
        rem = fields.get("remediation", "")
        # 至少要有影响/修复/前置之一，才视为有效链
        if not (imp or rem or pre):
            continue
        chains.append(AttackChain(
            preconditions=_clean_lines(pre),
            lateral_moves=_clean_lines(lat),
            impact=imp[:1000],
            remediation=rem[:1500],
        ))
    return chains


def _parse_attack_chains(raw_text: str) -> list[AttackChain]:
    """从模型文本里提取 AttackChain 列表（优先 JSON，回退 Markdown）。"""
    if not raw_text:
        return []
    m = re.search(r"\[[\s\S]*\]", raw_text, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, list):
                chains = []
                for item in parsed:
                    if isinstance(item, AttackChain):
                        chains.append(item)
                    elif isinstance(item, dict):
                        try:
                            chains.append(AttackChain.model_validate(item))
                        except Exception:
                            continue
                if chains:
                    return chains
        except Exception:
            pass
    m = re.search(r"\{[\s\S]*\}", raw_text, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                return [AttackChain.model_validate(parsed)]
        except Exception:
            pass
    return _parse_markdown_chains(raw_text)


# ── 系统提示词（深挖官）──
DEEPEN_SYSTEM_PROMPT = """\
你是漏洞深挖官。任务：对已验证 CONFIRMED 的漏洞，推演从攻击者视角出发的完整攻击链。

只处理 CONFIRMED 条目：
- REFUTED（已证伪）与 UNCERTAIN（不确定）一律跳过，不浪费时间；
- 对每条 CONFIRMED：从工具证据（实际 findings/flows）出发，推演
  preconditions（前置条件）→ lateral_moves（横向移动/影响面）→ impact（最终影响）→ remediation（修复）。

铁律：
- 所有推演必须锚定工具证据，不得编造不存在的攻击路径；
- 修复建议要具体（文件:行号、换成什么），不写空泛套话；
- 一条 CONFIRMED 对应一条 AttackChain。
"""


# ── Agent 构造 ──
def build_deepen_agent(model: OpenAIModel | None = None) -> Agent:
    """构造深挖 Agent：无独立工具（依赖传入的证据，推理为主）。
    
    默认模型：Kimi-K3（强推理）。GLM-5.2 可作为备选。
    """
    return Agent(
        name="deepen_agent",
        system_prompt=DEEPEN_SYSTEM_PROMPT,
        tools=[],
        model=model or _make_model_fallback(),
    )


def _make_model_fallback() -> OpenAIModel:
    """按优先级尝试构造模型。"""
    attempts = [
        ("Kimi-K3", lambda: make_model(ModelProvider.KIMI, ModelTier.PRO)),
        ("GLM-5.2", lambda: make_model(ModelProvider.GLM, ModelTier.PRO)),
        ("DeepSeek-V4-Pro", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.PRO)),
        ("DeepSeek-V4-Flash", lambda: make_model(ModelProvider.DEEPSEEK, ModelTier.FLASH)),
    ]
    for name, fn in attempts:
        try:
            return fn()
        except Exception as e:
            print(f"[Deepen] {name} 初始化失败: {e}")
    raise RuntimeError("所有 Deepen 模型初始化均失败")


# ── 运行入口（供 Graph 编排调用）──
async def run_deepen(
    confirmed: list[VerificationResult],
    files: dict[str, str],
    model: OpenAIModel | None = None,
) -> list[AttackChain]:
    """对 CONFIRMED 验证结果推演攻击链，返回 AttackChain 列表。"""
    if not confirmed:
        return []
    agent = build_deepen_agent(model)
    prompt = (
        "请对以下 CONFIRMED 漏洞逐条推演攻击链，输出 AttackChain 列表。\n"
        "仓库文件内容：\n" + json.dumps(files, ensure_ascii=False) + "\n"
        "已验证漏洞（CONFIRMED）：\n" + json.dumps(
            [v.model_dump() for v in confirmed], ensure_ascii=False, indent=2
        )
    )
    result = await agent.invoke_async(prompt)
    if hasattr(result, "structured_output") and result.structured_output is not None:
        out = result.structured_output
        if isinstance(out, AttackChain):
            return [out]
        if isinstance(out, list):
            return [
                c if isinstance(c, AttackChain) else AttackChain.model_validate(c)
                for c in out if c is not None
            ]
        return out
    return _parse_attack_chains(str(result))

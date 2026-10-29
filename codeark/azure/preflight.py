"""Azure 基线 gate v1（IC27 P0：把两个 Microsoft AI 服务接进主链路，**默认关**）。

定位：`codeark/graph/pipeline.py` 隔离层（quarantine）之前的云服务前哨。两件承重件：

1. **Content Safety（Prompt Shields）**——原始文件是不可信输入（被审计仓由攻击者
   控制）。在确定性 quarantine 之外再加一层语义基线：逐批（≤5 文档 / ≤9,000 字符，
   与服务的硬限对齐）扫描，命中可**扣留**该文件不进模型面（默认只记账，不改变行为）。
2. **Azure AI Language（PII）**——模型面文件在送 LLM 之前脱敏（客户代码/报告摘录
   可能含 PII）。脱敏失败的文件默认**扣留**（fail-closed：未知 ≠ 已脱敏）。

开关（全部默认关；全关时零网络、零行为变化，与 v0 前完全一致）：
  ARCA_AZURE_CONTENT_SAFETY_ENABLED=1      启用 shield 基线
  ARCA_AZURE_CONTENT_SAFETY_BLOCK=1        命中即扣留该文件（默认 0=只记账）
  ARCA_AZURE_LANGUAGE_ENABLED=1            启用 PII 脱敏
  ARCA_AZURE_GATE_WITHHOLD_ON_DEGRADED=0   脱敏降级仍放行原文（默认 1=扣留）
  ARCA_AZURE_GATE_MAX_LANGUAGE_DOCS=20     单次 PII 脱敏文档数帽（F0 月配额 5,000 条）

成本帽：CS 最多 3 批；Language 最多 N 篇且每篇 ≤5,000 字符。覆盖率（total/sampled/
scanned/withheld）全部写进 `meta.azure`，不写"扫了全仓"的假话。
"""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .content_safety import ContentSafetyClient
from .content_safety import status_from_env as content_safety_status_from_env
from .language import LanguageClient, MAX_DOC_CHARS as LANGUAGE_MAX_DOC_CHARS
from .language import status_from_env as language_status_from_env

CS_ENABLED_ENV = "ARCA_AZURE_CONTENT_SAFETY_ENABLED"
CS_BLOCK_ENV = "ARCA_AZURE_CONTENT_SAFETY_BLOCK"
LANGUAGE_ENABLED_ENV = "ARCA_AZURE_LANGUAGE_ENABLED"
WITHHOLD_ON_DEGRADED_ENV = "ARCA_AZURE_GATE_WITHHOLD_ON_DEGRADED"
MAX_LANGUAGE_DOCS_ENV = "ARCA_AZURE_GATE_MAX_LANGUAGE_DOCS"

CS_MAX_DOCS_PER_BATCH = 5
CS_MAX_CHARS_PER_BATCH = 9000  # Prompt Shields 单请求合计 ≤10K，留余量
CS_MAX_BATCHES = 3
DEFAULT_MAX_LANGUAGE_DOCS = 20

# 审计指令是我们自己的可信 prompt；被审仓库内容只作为 documents 送入，
# 映射关系与 Prompt Shields 的「用户提示 / 检索文档」语义一致。
AUDIT_PROMPT = "Audit the supplied repository files for security vulnerabilities."


@dataclass(frozen=True)
class GateOutcome:
    """files=模型面文件（可能已脱敏/扣留）；meta=入报告的显式记账。"""

    files: dict[str, str]
    meta: dict[str, Any]


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _enabled(env: Mapping[str, str], name: str) -> bool:
    return _truthy(env.get(name))


def _cs_defaults() -> dict[str, Any]:
    """异常路径也用同一 schema，报告消费方不必处理两套形状。"""
    return {
        "enabled": True,
        "configured": None,
        "endpoint_host": "",
        "api_version": "",
        "documents_total": 0,
        "documents_sampled": 0,
        "documents_scanned": 0,
        "truncated_documents": 0,
        "batches": 0,
        "attack_detected": None,
        "degraded": True,
        "reason": "",
        "blocked_documents": 0,
    }


def _language_defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "configured": None,
        "endpoint_host": "",
        "api_version": "",
        "documents_total": 0,
        "documents_sampled": 0,
        "documents_redacted": 0,
        "documents_withheld": 0,
        "skipped_too_long": 0,
        "entities_by_category": {},
        "degraded": True,
        "reason": "",
    }


def _tri(values: Sequence[bool | None]) -> bool | None:
    """三态聚合：任一 True→True；存在未知→None；否则 False。"""
    if any(v is True for v in values):
        return True
    if any(v is None for v in values):
        return None
    return False


def _cs_batches(files: Mapping[str, str]) -> tuple[list[tuple[list[str], list[str]]], int]:
    """确定性地把文件切成 (names, texts) 批；单文件超帽截断并计数。"""
    batches: list[tuple[list[str], list[str]]] = []
    names: list[str] = []
    texts: list[str] = []
    chars = 0
    truncated = 0
    for name in sorted(files):
        text = files[name]
        if len(text) > CS_MAX_CHARS_PER_BATCH:
            text = text[:CS_MAX_CHARS_PER_BATCH]
            truncated += 1
        if names and (
            len(names) >= CS_MAX_DOCS_PER_BATCH or chars + len(text) > CS_MAX_CHARS_PER_BATCH
        ):
            batches.append((names, texts))
            if len(batches) >= CS_MAX_BATCHES:
                return batches, truncated
            names, texts, chars = [], [], 0
        names.append(name)
        texts.append(text)
        chars += len(text)
    if names and len(batches) < CS_MAX_BATCHES:
        batches.append((names, texts))
    return batches, truncated


def _content_safety_block(
    files: Mapping[str, str],
    env: Mapping[str, str],
    client: ContentSafetyClient | None,
) -> tuple[dict[str, Any], set[str]]:
    status = content_safety_status_from_env(env)
    block: dict[str, Any] = {
        "enabled": True,
        "configured": status.configured,
        "endpoint_host": status.endpoint_host,
        "api_version": status.api_version,
        "documents_total": len(files),
        "documents_sampled": 0,
        "documents_scanned": 0,
        "truncated_documents": 0,
        "batches": 0,
        "attack_detected": None,
        "degraded": False,
        "reason": "",
        "blocked_documents": 0,
    }
    owned = client is None
    client = client or ContentSafetyClient.from_env(env)
    if client is None:
        block["degraded"] = True
        block["reason"] = "已启用但未配置（缺 ENDPOINT/KEY）"
        return block, set()

    batches, truncated = _cs_batches(files)
    block["truncated_documents"] = truncated
    flags: list[bool | None] = []
    flagged: set[str] = set()
    scanned = 0
    try:
        for names, texts in batches:
            result = client.shield_prompt(AUDIT_PROMPT, texts)
            block["batches"] += 1
            block["documents_sampled"] += len(names)
            flags.append(result.user_prompt_attack)
            flags.extend(result.documents_attack)
            if result.user_prompt_attack is True:
                flagged.update(names)
            for name, flag in zip(names, result.documents_attack):
                if flag is True:
                    flagged.add(name)
                if flag is not None:
                    scanned += 1
            if result.degraded:
                block["degraded"] = True
                block["reason"] = result.reason or block["reason"]
    finally:
        if owned:
            client.close()
    block["documents_scanned"] = scanned
    block["attack_detected"] = _tri(flags)
    return block, flagged


def _max_language_docs(env: Mapping[str, str]) -> int:
    try:
        value = int(env.get(MAX_LANGUAGE_DOCS_ENV) or DEFAULT_MAX_LANGUAGE_DOCS)
    except (TypeError, ValueError):
        return DEFAULT_MAX_LANGUAGE_DOCS
    return value if value > 0 else DEFAULT_MAX_LANGUAGE_DOCS


def _language_block(
    files: Mapping[str, str],
    env: Mapping[str, str],
    client: LanguageClient | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    status = language_status_from_env(env)
    block: dict[str, Any] = {
        "enabled": True,
        "configured": status.configured,
        "endpoint_host": status.endpoint_host,
        "api_version": status.api_version,
        "documents_total": len(files),
        "documents_sampled": 0,
        "documents_redacted": 0,
        "documents_withheld": 0,
        "skipped_too_long": 0,
        "entities_by_category": {},
        "degraded": False,
        "reason": "",
    }
    # 默认可扣留：脱敏没完成就不能把原文送去模型（fail-closed）
    withhold = _truthy(env.get(WITHHOLD_ON_DEGRADED_ENV, "1"))
    owned = client is None
    client = client or LanguageClient.from_env(env)
    if client is None:
        block["degraded"] = True
        block["reason"] = "已启用但未配置（缺 ENDPOINT/KEY）"
        block["documents_sampled"] = len(files)
        block["documents_withheld"] = len(files)
        return block, {}

    sampled = sorted(files)[: _max_language_docs(env)]
    block["documents_sampled"] = len(sampled)
    too_long = {name for name in sampled if len(files[name]) > LANGUAGE_MAX_DOC_CHARS}
    block["skipped_too_long"] = len(too_long)
    redactable = [name for name in sampled if name not in too_long]
    out = dict(files)
    try:
        result = client.redact_texts({name: files[name] for name in redactable})
    finally:
        if owned:
            client.close()
    redacted = result.redacted_map()
    withheld = 0
    for name in sampled:
        if name in redacted:
            out[name] = redacted[name]
            block["documents_redacted"] += 1
        elif withhold:
            out.pop(name, None)
            withheld += 1
    block["documents_withheld"] = withheld
    block["entities_by_category"] = result.entity_counts
    if result.degraded:
        block["degraded"] = True
        block["reason"] = result.reason or block["reason"]
    return block, out


def run_azure_gate(
    files: Mapping[str, str],
    *,
    env: Mapping[str, str] | None = None,
    cs_client: ContentSafetyClient | None = None,
    lang_client: LanguageClient | None = None,
) -> GateOutcome:
    """跑启用的服务；全关时返回原文件与 `enabled=false` 的显式记账（零网络）。"""
    e = os.environ if env is None else env
    cs_on = _enabled(e, CS_ENABLED_ENV)
    lang_on = _enabled(e, LANGUAGE_ENABLED_ENV)
    meta: dict[str, Any] = {
        "enabled": cs_on or lang_on,
        "content_safety": {"enabled": False, "reason": "disabled"},
        "language": {"enabled": False, "reason": "disabled"},
    }
    if not (cs_on or lang_on):
        return GateOutcome(dict(files), meta)

    work = dict(files)
    if cs_on:
        try:
            block, flagged = _content_safety_block(work, e, cs_client)
        except Exception as exc:  # 意外故障只记账，不中断；异常文本可能含 URL/密钥，不落原文
            block, flagged = _cs_defaults(), set()
            block["documents_total"] = len(work)
            block["reason"] = f"{type(exc).__name__}"
        if _enabled(e, CS_BLOCK_ENV):
            for name in sorted(flagged):
                work.pop(name, None)
            block["blocked_documents"] = len(flagged)
        meta["content_safety"] = block
    if lang_on:
        try:
            block, work = _language_block(work, e, lang_client)
        except Exception as exc:
            # 脱敏无法证明完成 → fail-closed 扣留全部模型面文件
            block = _language_defaults()
            block["reason"] = f"{type(exc).__name__}"
            block["documents_total"] = len(work)
            block["documents_sampled"] = len(work)
            block["documents_withheld"] = len(work)
            work = {}
        meta["language"] = block
    return GateOutcome(work, meta)
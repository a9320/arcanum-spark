"""Azure 基线 gate（preflight）契约锚：开关、覆盖率记账、fail-closed 扣留。

客户端用桩（零联网）；真实 HTTP 契约由 test_azure_content_safety / test_azure_language 覆盖。
"""
from __future__ import annotations

import json

from codeark.azure.content_safety import (
    ENDPOINT_ENV as CS_ENDPOINT_ENV,
    KEY_ENV as CS_KEY_ENV,
    ShieldPromptResult,
)
from codeark.azure.language import (
    ENDPOINT_ENV as LANG_ENDPOINT_ENV,
    KEY_ENV as LANG_KEY_ENV,
    PiiEntity,
    RedactedDocument,
    RedactionResult,
)
from codeark.azure.preflight import (
    CS_BLOCK_ENV,
    CS_ENABLED_ENV,
    CS_MAX_BATCHES,
    LANGUAGE_ENABLED_ENV,
    MAX_LANGUAGE_DOCS_ENV,
    WITHHOLD_ON_DEGRADED_ENV,
    run_azure_gate,
)

CS_ENV = {CS_ENDPOINT_ENV: "https://cs.example", CS_KEY_ENV: "k-cs"}
LANG_ENV = {LANG_ENDPOINT_ENV: "https://lang.example", LANG_KEY_ENV: "k-lang"}


class _StubCS:
    def __init__(self, *, user=False, docs=None, degraded=False, reason="", boom=False):
        self.user = user
        self.docs = docs
        self.degraded = degraded
        self.reason = reason
        self.boom = boom
        self.calls = 0

    def shield_prompt(self, user_prompt, documents=()):
        if self.boom:
            raise RuntimeError("boom")
        self.calls += 1
        flags = tuple(self.docs) if self.docs is not None else (False,) * len(documents)
        return ShieldPromptResult(self.user, flags, self.degraded, self.reason)

    def close(self):
        pass


class _StubLang:
    def __init__(self, *, redacted=None, degraded_ids=(), boom=False):
        self.redacted = dict(redacted or {})
        self.degraded_ids = set(degraded_ids)
        self.boom = boom

    def redact_texts(self, texts, language="en"):
        if self.boom:
            raise RuntimeError("boom")
        docs = []
        for name, text in texts.items():
            if name in self.degraded_ids:
                docs.append(RedactedDocument(doc_id=name, degraded=True, reason="stub"))
                continue
            entities = (PiiEntity("Email", "", 0, 3, 0.9),) if name in self.redacted else ()
            docs.append(RedactedDocument(
                doc_id=name,
                redacted_text=self.redacted.get(name, text),
                entities=entities,
            ))
        return RedactionResult(
            documents=tuple(docs),
            degraded=bool(self.degraded_ids),
            reason="stub-degraded" if self.degraded_ids else "",
            batches=1,
        )

    def close(self):
        pass


# ── 默认关 ──

def test_disabled_by_default_returns_files_and_explicit_meta():
    out = run_azure_gate({"a.py": "x"}, env={})
    assert out.files == {"a.py": "x"}
    assert out.meta == {
        "enabled": False,
        "content_safety": {"enabled": False, "reason": "disabled"},
        "language": {"enabled": False, "reason": "disabled"},
    }


# ── Content Safety ──

def test_cs_reports_attack_without_blocking_by_default():
    out = run_azure_gate(
        {"a.py": "evil", "b.py": "clean"},
        env={CS_ENABLED_ENV: "1", **CS_ENV},
        cs_client=_StubCS(docs=(True, False)),
    )
    cs = out.meta["content_safety"]
    assert cs["attack_detected"] is True
    assert cs["documents_sampled"] == 2
    assert cs["documents_scanned"] == 2
    assert cs["blocked_documents"] == 0
    assert set(out.files) == {"a.py", "b.py"}
    json.dumps(out.meta, ensure_ascii=False)  # 必须可入报告 JSON


def test_cs_block_removes_flagged_document():
    out = run_azure_gate(
        {"a.py": "evil", "b.py": "clean"},
        env={CS_ENABLED_ENV: "1", CS_BLOCK_ENV: "1", **CS_ENV},
        cs_client=_StubCS(docs=(True, False)),
    )
    assert set(out.files) == {"b.py"}
    assert out.meta["content_safety"]["blocked_documents"] == 1


def test_cs_enabled_without_credentials_degrades_but_keeps_files():
    out = run_azure_gate({"a.py": "x"}, env={CS_ENABLED_ENV: "1"})
    cs = out.meta["content_safety"]
    assert cs["configured"] is False
    assert cs["degraded"] is True
    assert out.files == {"a.py": "x"}


def test_cs_unknown_is_not_clean():
    out = run_azure_gate(
        {"a.py": "x"},
        env={CS_ENABLED_ENV: "1", **CS_ENV},
        cs_client=_StubCS(docs=(None,), degraded=True, reason="HTTP 500"),
    )
    cs = out.meta["content_safety"]
    assert cs["attack_detected"] is None
    assert cs["degraded"] is True
    assert cs["reason"] == "HTTP 500"


def test_cs_batches_capped():
    files = {f"f{i}.py": "x" for i in range(20)}
    out = run_azure_gate(
        files, env={CS_ENABLED_ENV: "1", **CS_ENV}, cs_client=_StubCS()
    )
    cs = out.meta["content_safety"]
    assert cs["batches"] == CS_MAX_BATCHES
    assert cs["documents_sampled"] == 15
    assert cs["documents_total"] == 20
    assert cs["attack_detected"] is False


def test_cs_client_exception_is_recorded_not_raised():
    out = run_azure_gate(
        {"a.py": "x"},
        env={CS_ENABLED_ENV: "1", **CS_ENV},
        cs_client=_StubCS(boom=True),
    )
    assert out.meta["content_safety"]["degraded"] is True
    assert out.files == {"a.py": "x"}


# ── Azure AI Language（PII）──

def test_language_redacts_model_facing_files():
    out = run_azure_gate(
        {"a.py": "mail jane@example.com", "b.py": "clean"},
        env={LANGUAGE_ENABLED_ENV: "1", **LANG_ENV},
        lang_client=_StubLang(redacted={"a.py": "mail [REDACTED:Email]"}),
    )
    lang = out.meta["language"]
    assert out.files["a.py"] == "mail [REDACTED:Email]"
    assert out.files["b.py"] == "clean"
    assert lang["documents_redacted"] == 2
    assert lang["entities_by_category"] == {"Email": 1}
    assert lang["degraded"] is False


def test_language_degraded_withholds_by_default():
    out = run_azure_gate(
        {"a.py": "x", "b.py": "y"},
        env={LANGUAGE_ENABLED_ENV: "1", **LANG_ENV},
        lang_client=_StubLang(degraded_ids={"a.py"}),
    )
    lang = out.meta["language"]
    assert "a.py" not in out.files
    assert out.files == {"b.py": "y"}
    assert lang["documents_withheld"] == 1
    assert lang["degraded"] is True


def test_language_degraded_can_pass_through_only_when_explicitly_disabled():
    out = run_azure_gate(
        {"a.py": "x"},
        env={LANGUAGE_ENABLED_ENV: "1", WITHHOLD_ON_DEGRADED_ENV: "0", **LANG_ENV},
        lang_client=_StubLang(degraded_ids={"a.py"}),
    )
    assert out.files == {"a.py": "x"}
    assert out.meta["language"]["documents_withheld"] == 0


def test_language_enabled_without_credentials_withholds_everything():
    out = run_azure_gate(
        {"a.py": "x", "b.py": "y"}, env={LANGUAGE_ENABLED_ENV: "1"}
    )
    lang = out.meta["language"]
    assert out.files == {}
    assert lang["configured"] is False
    assert lang["documents_withheld"] == 2
    assert lang["degraded"] is True


def test_language_too_long_document_is_not_sent_and_withheld():
    out = run_azure_gate(
        {"big.py": "a" * 5001, "ok.py": "x"},
        env={LANGUAGE_ENABLED_ENV: "1", **LANG_ENV},
        lang_client=_StubLang(),
    )
    lang = out.meta["language"]
    assert lang["skipped_too_long"] == 1
    assert "big.py" not in out.files
    assert out.files == {"ok.py": "x"}


def test_language_max_docs_cap_leaves_rest_untouched():
    out = run_azure_gate(
        {"a.py": "x", "b.py": "y"},
        env={LANGUAGE_ENABLED_ENV: "1", MAX_LANGUAGE_DOCS_ENV: "1", **LANG_ENV},
        lang_client=_StubLang(),
    )
    lang = out.meta["language"]
    assert lang["documents_sampled"] == 1
    assert out.files == {"a.py": "x", "b.py": "y"}


def test_language_client_exception_withholds_all():
    out = run_azure_gate(
        {"a.py": "x"},
        env={LANGUAGE_ENABLED_ENV: "1", **LANG_ENV},
        lang_client=_StubLang(boom=True),
    )
    assert out.files == {}
    assert out.meta["language"]["degraded"] is True
    assert out.meta["language"]["documents_withheld"] == 1
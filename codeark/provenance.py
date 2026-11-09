"""报告 provenance：每次跑批自带的最小可复现指纹（观测用，不参与判分）。

设计见 `docs/REPORT-PROVENANCE-DESIGN.md`。三条硬约束：

1. **白名单**：只读 `ARCA_<STAGE>_{MODEL,BASE_URL}` 与少量 tuning 变量，
   绝不读取任何 `*_API_KEY`、`.env` 或凭据文件；
2. **不推断**：未设的环境变量记 `null`，不填代码内置默认值（防与默认漂移）；
3. **失败不影响主流程**：git 探测带 2s 超时，任何异常降级为 `"unknown"`。
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_SCHEMA = 1
_ROOT = Path(__file__).resolve().parents[1]

_STAGES = ("scout", "verify", "deepen", "arbiter")

# tuning 白名单：字段名 → (环境变量, 解析器)
_TUNING: dict[str, tuple[str, type]] = {
    "verify_temperature": ("ARCA_VERIFY_TEMPERATURE", float),
    "verify_evidence_max_tokens": ("ARCA_VERIFY_EVIDENCE_MAX_TOKENS", int),
    "verify_max_concurrency": ("ARCA_VERIFY_MAX_CONCURRENCY", int),
    "scout_max_tokens": ("ARCA_SCOUT_MAX_TOKENS", int),
}


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


@lru_cache(maxsize=1)
def _commit() -> str:
    """当前代码版本：`ARCA_BUILD_COMMIT` 优先（slim/无 .git 场景），否则 git。"""
    override = _env("ARCA_BUILD_COMMIT")
    if override:
        return override[:40]
    try:
        out = subprocess.run(
            ["git", "-C", str(_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        revision = (out.stdout or "").strip()
        if out.returncode == 0 and revision:
            return revision[:40]
    except Exception:  # git 缺失/超时/权限问题一律降级，不影响报告生成
        pass
    return "unknown"


def _sanitize_url(raw: str | None) -> str | None:
    """只留 scheme://host:port：去掉 userinfo（可能含 token）、path 与 query。"""
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.hostname:
            return "redacted"
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "redacted"
    return f"{parts.scheme}://{parts.hostname}{port}"


def _tuning_value(name: str) -> tuple[Any, bool]:
    """返回 (值, 是否非法)。非法值不抛错、不回显原始字符串。"""
    env_name, caster = _TUNING[name]
    raw = _env(env_name)
    if raw is None:
        return None, False
    try:
        return caster(raw), False
    except (TypeError, ValueError):
        return None, True


def _iso(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    return (
        moment.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def collect_provenance(
    started_at: datetime | None = None, finished_at: datetime | None = None
) -> dict[str, Any]:
    """采集当前跑批的 provenance（纯读环境变量与 git，零网络、零模型调用）。"""
    notes: list[str] = []

    models: dict[str, str | None] = {}
    endpoints: dict[str, str | None] = {}
    for stage in _STAGES:
        models[stage] = _env(f"ARCA_{stage.upper()}_MODEL")
        endpoints[stage] = _sanitize_url(_env(f"ARCA_{stage.upper()}_BASE_URL"))

    tuning: dict[str, Any] = {}
    for name in _TUNING:
        value, invalid = _tuning_value(name)
        tuning[name] = value
        if invalid:
            notes.append(f"{name} invalid → ignored (null)")
    if tuning["verify_temperature"] is None and not any(
        "verify_temperature" in note for note in notes
    ):
        notes.append("verify_temperature unset → server default")

    return {
        "schema": _SCHEMA,
        "codeark_commit": _commit(),
        "deployment": _env("ARCA_DEPLOYMENT") or "unset",
        "started_at": _iso(started_at),
        "finished_at": _iso(finished_at or datetime.now(timezone.utc)),
        "models": models,
        "endpoints": endpoints,
        "tuning": tuning,
        "notes": notes,
    }

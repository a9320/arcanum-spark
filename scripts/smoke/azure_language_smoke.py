"""Azure AI Language live 冒烟（第二件承重服务：证据 PII 脱敏门的验收入口）。

用途：凭据到位后先证明四件事，再谈主链路——
1) 资源密钥/端点/API 版本可用（真联网一次）；
2) PII 实体的解析契约与 codeark.azure.language 一致（否则 v1 才爆）；
3) 返回的脱敏文本确实不含原始 PII；
4) 覆盖率语义（请求 1 篇、成功 1 篇、零降级）。

用法：
  python scripts/smoke/azure_language_smoke.py            # 只读 env 状态，零联网
  python scripts/smoke/azure_language_smoke.py --live     # 真调用（消耗 1 条记录配额）

env：ARCA_AZURE_LANGUAGE_{ENDPOINT,KEY,API_VERSION,TIMEOUT}
退出码：0=全绿；1=有降级或脱敏未生效；2=未配置/参数错误。

纪律：样本是合成的 PII，不是真实用户数据；不打印密钥；不写文件。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from codeark.azure.language import LanguageClient, status_from_env  # noqa: E402

SAMPLE_PII = "jane.doe@example.com"
SAMPLE_TEXT = (
    "Customer contact: Jane Doe, email jane.doe@example.com, phone +1 415 555 0132. "
    "Ticket notes mention an internal host 10.1.2.3."
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Azure AI Language PII live 冒烟")
    ap.add_argument("--live", action="store_true", help="真调用（不加则只打印配置状态）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args(argv)

    status = status_from_env()
    if not args.json:
        print(f"endpoint_host={status.endpoint_host or '(unset)'}")
        print(f"api_version={status.api_version}")
        print(f"configured={status.configured} missing={list(status.missing)}")
    if not args.live:
        print(json.dumps({"mode": "status", "status": status.__dict__}, ensure_ascii=False))
        return 0 if status.configured else 2
    if not status.configured:
        print(json.dumps({"mode": "live", "error": "language env 未配置",
                          "missing": list(status.missing)}, ensure_ascii=False))
        return 2

    client = LanguageClient.from_env()
    if client is None:  # status 已判 configured，理论不可达；防御式兜底
        print(json.dumps({"mode": "live", "error": "client 构造失败"}, ensure_ascii=False))
        return 2

    t0 = time.perf_counter()
    try:
        result = client.redact_texts({"smoke.txt": SAMPLE_TEXT})
    finally:
        client.close()
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    redacted = result.redacted_map().get("smoke.txt")
    sections = [
        {
            "section": "pii_detected",
            "ok": bool(result.entity_counts) and not result.degraded,
            "entities_by_category": result.entity_counts,
            "degraded": result.degraded,
            "reason": result.reason,
        },
        {
            "section": "pii_removed_from_output",
            "ok": redacted is not None and SAMPLE_PII not in redacted,
            "redacted_excerpt": (redacted or "")[:200],
        },
    ]
    ok = all(s["ok"] for s in sections)
    print(json.dumps({
        "mode": "live",
        "endpoint_host": status.endpoint_host,
        "api_version": status.api_version,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "sections": sections,
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
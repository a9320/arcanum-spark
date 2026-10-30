"""Azure AI Foundry 模型（非 OpenAI）live 冒烟。

用法：
  python scripts/smoke/azure_foundry_smoke.py            # 只读 env 状态，零联网
  python scripts/smoke/azure_foundry_smoke.py --live     # 真调一次 chat/completions

env：ARCA_FOUNDRY_{ENDPOINT,KEY,DEPLOYMENT,API_VERSION,TIMEOUT}
退出码：0=通；1=全形状失败；2=未配置。

三种形状依次试（models+api-key → models+Bearer → openai/v1+Bearer），200 即停，
输出 `path`/`auth` 供写进 env 契约。纪律：不打印密钥，不写文件。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from codeark.azure.foundry_probe import FoundryClient, status_from_env  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Azure AI Foundry 模型冒烟")
    ap.add_argument("--live", action="store_true", help="真调用（不加则只打印配置状态）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args(argv)

    status = status_from_env()
    if not args.json:
        print(f"endpoint_host={status.endpoint_host or '(unset)'}")
        print(f"deployment={status.deployment or '(unset)'}")
        print(f"api_version={status.api_version}")
        print(f"configured={status.configured} missing={list(status.missing)}")
    if not args.live:
        print(json.dumps({"mode": "status", "status": status.__dict__}, ensure_ascii=False))
        return 0 if status.configured else 2
    if not status.configured:
        print(json.dumps({"mode": "live", "error": "foundry env 未配置",
                          "missing": list(status.missing)}, ensure_ascii=False))
        return 2

    client = FoundryClient.from_env()
    if client is None:
        print(json.dumps({"mode": "live", "error": "client 构造失败"}, ensure_ascii=False))
        return 2
    try:
        result = client.probe()
    finally:
        client.close()

    print(json.dumps({
        "mode": "live",
        "ok": result.ok,
        "path": result.path,
        "auth": result.auth,
        "reply": result.reply,
        "reason": result.reason,
        "attempts": [a.__dict__ for a in result.attempts],
    }, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
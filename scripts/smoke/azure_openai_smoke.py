"""Azure OpenAI live 冒烟（IC27 v1 鉴权待验点）。

用途：资源/部署建好后，一条命令确定：
1) 端点是 v1 还是 classic 形态可用；
2) 鉴权是 `Authorization: Bearer <key>` 还是 `api-key: <key>`；
3) 部署名是否正确（400/404 与鉴权失败能区分开）。

用法：
  python scripts/smoke/azure_openai_smoke.py            # 只读 env 状态，零联网
  python scripts/smoke/azure_openai_smoke.py --live      # 真调用（最小 chat 请求）

env：
  ARCA_AZURE_OPENAI_ENDPOINT   必需  例 https://arca-openai-ic27.openai.azure.com
  ARCA_AZURE_OPENAI_KEY        必需  资源密钥；不打印、不落盘
  ARCA_AZURE_OPENAI_DEPLOYMENT 必需  部署名（不是模型名）
  ARCA_AZURE_OPENAI_API_VERSION 可选  classic 回退用，默认 2024-10-21
  ARCA_AZURE_OPENAI_TIMEOUT    可选  秒，默认 30

退出码：0=成功；1=全部尝试失败；2=未配置。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codeark.azure.openai_probe import (  # noqa: E402
    DEFAULT_API_VERSION,
    DEFAULT_TIMEOUT,
    probe_chat_completion,
)

ENDPOINT_ENV = "ARCA_AZURE_OPENAI_ENDPOINT"
KEY_ENV = "ARCA_AZURE_OPENAI_KEY"
DEPLOYMENT_ENV = "ARCA_AZURE_OPENAI_DEPLOYMENT"
API_VERSION_ENV = "ARCA_AZURE_OPENAI_API_VERSION"
TIMEOUT_ENV = "ARCA_AZURE_OPENAI_TIMEOUT"


def _env_status() -> dict:
    missing = [name for name in (ENDPOINT_ENV, KEY_ENV, DEPLOYMENT_ENV)
               if not (os.environ.get(name) or "").strip()]
    endpoint = (os.environ.get(ENDPOINT_ENV) or "").strip()
    host = ""
    if endpoint:
        try:
            host = urlsplit(endpoint).netloc
        except ValueError:
            host = ""
    return {
        "configured": not missing,
        "missing": missing,
        "endpoint_host": host,
        "deployment": (os.environ.get(DEPLOYMENT_ENV) or "").strip(),
        "api_version": (os.environ.get(API_VERSION_ENV) or "").strip() or DEFAULT_API_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Azure OpenAI live 冒烟")
    ap.add_argument("--live", action="store_true", help="真调用（不加则只打印配置状态）")
    args = ap.parse_args(argv)

    status = _env_status()
    if not args.live:
        print(json.dumps({"mode": "status", **status}, ensure_ascii=False))
        return 0 if status["configured"] else 2
    if not status["configured"]:
        print(json.dumps({"mode": "live", "error": "Azure OpenAI env 未配置",
                          "missing": status["missing"]}, ensure_ascii=False))
        return 2

    try:
        timeout = float(os.environ.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT
    result = probe_chat_completion(
        endpoint=os.environ[ENDPOINT_ENV],
        key=os.environ[KEY_ENV],
        deployment=os.environ[DEPLOYMENT_ENV],
        api_version=status["api_version"],
        timeout=timeout,
    )
    payload = {
        "mode": "live",
        "endpoint_host": status["endpoint_host"],
        "deployment": status["deployment"],
        "ok": result.ok,
        "auth_mode": result.auth_mode,
        "path": result.path,
        "elapsed_ms": result.elapsed_ms,
        "content": result.content,
        "usage": result.usage,
        "attempts": [
            {"path": a.path, "auth": a.auth, "status": a.status,
             "ok": a.ok, "detail": a.detail}
            for a in result.attempts
        ],
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
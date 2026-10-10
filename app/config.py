# -*- coding: utf-8 -*-
"""CodeRisk Cloud — 配置管理"""

import os
import sys
from pathlib import Path


class Settings:
    # API
    API_TITLE = "CodeRisk Cloud"
    API_VERSION = "1.0.0"
    API_PREFIX = "/api/v1"

    # Redis (Celery Broker + Backend)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # CodeRisk 引擎层 — 内置 engine/ 优先，环境变量 CODERISK_PATH 可覆盖
    # （引擎为传统漏洞检测：静态分析/污点/依赖/LLM 语义，纯 Python，无 tree-sitter 硬依赖）
    _default_paths = [
        os.getenv("CODERISK_PATH"),
        str(Path(__file__).parent.parent / "engine"),   # 内置引擎（交付仓自带）
        "/app/code-risk-agent",
        str(Path.home() / "code-risk-agent"),
    ]
    CODERISK_PATH = next(
        (p for p in _default_paths if p and (Path(p) / "core").is_dir()),
        None
    )
    if not CODERISK_PATH:
        # 开发环境降级：允许不存在，但运行时检查（Agent 1-3 优雅降级为空结果）
        CODERISK_PATH = os.getenv("CODERISK_PATH", str(Path(__file__).parent.parent / "engine"))

    # 引擎路径注入 sys.path：使 core.* / agents.*（engine 内）可直接 import。
    # 放在 config 模块级，保证任何先 import app.config 的代码都能用引擎。
    if CODERISK_PATH and CODERISK_PATH not in sys.path:
        sys.path.insert(0, CODERISK_PATH)

    # Nutrient DWS
    NUTRIENT_API_KEY = os.getenv("NUTRIENT_DWS_API_KEY", "")
    NUTRIENT_API_URL = os.getenv("NUTRIENT_DWS_API_URL", "https://api.nutrient.io/build")

    # Worker
    WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "2"))

    # Auth
    API_KEY = os.getenv("CODERISK_API_KEY", "dev-key-change-in-production")
    if API_KEY == "dev-key-change-in-production":
        if os.getenv("ARCA_ENV", "dev") == "production":
            # 生产姿态（ARCA_ENV=production）禁止弱默认 key：docker-compose 已有
            # ${CODERISK_API_KEY:?} 硬闸，此处封住"裸 python/uvicorn 直接起服务"旁路
            # （2026-10-10 外审 P0/P1-2 收口）。
            raise RuntimeError(
                "CODERISK_API_KEY not set with ARCA_ENV=production — "
                "refusing to start with the built-in development default key; "
                "set CODERISK_API_KEY explicitly"
            )
        print(
            "WARNING [app.config]: CODERISK_API_KEY not set — using the built-in development default key, "
            "authentication is effectively useless; production deployments must explicitly set this environment variable",
            file=sys.stderr,
        )

    # Storage
    REPORTS_DIR = Path(os.getenv("REPORTS_DIR", str(Path(__file__).parent.parent / "reports")))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Security
    GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


settings = Settings()

"""API key 默认值治理回归锚（2026-10-10 外审 P0/P1-2 收口）。

dev 姿态：默认 key 放行但 stderr 显著 WARNING；production 姿态
（ARCA_ENV=production）：import 期 RuntimeError 拒绝用内置默认 key 启动。
docker-compose 路径本就有 ${CODERISK_API_KEY:?} 硬闸，本锚封"裸 python/uvicorn
起服务"旁路。import 期副作用无法在进程内干净断言 → 子进程实测。
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _import_config(env_extra: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CODERISK_API_KEY"}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=str(REPO), env=env, capture_output=True, text=True,
    )


def test_dev_default_key_allowed_with_warning():
    r = _import_config({"ARCA_ENV": "dev"})
    assert r.returncode == 0, r.stderr
    assert "WARNING [app.config]" in r.stderr


def test_production_refuses_default_key():
    r = _import_config({"ARCA_ENV": "production"})
    assert r.returncode != 0, r.stdout
    assert "CODERISK_API_KEY" in r.stderr

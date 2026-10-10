"""克隆失败分支返回契约回归锚（2026-10-10 外审 P1-1）。

_prepare_into 签名承诺 tuple[str | None, bool]；历史实现在 CalledProcessError
分支裸 `return None`，_prepare_code 的 `result[1]` 下标访问先抛 TypeError，
"可记录的失败"变成崩溃且失败语义被掩盖。本文件锁定两分支契约。

app.tasks 模块级依赖 redis/celery：缺包环境整模块 importorskip 干净跳过
（与 tests/test_quickscan_api.py 同模式）；CI（requirements 全装）真跑。
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

pytest.importorskip("celery", reason="app.tasks needs celery/redis (CI/requirements env)")
pytest.importorskip("redis", reason="app.tasks needs redis")

import app.tasks as tasks  # noqa: E402

_REPO = {"source": "github", "repo_url": "https://github.com/a9320/arcanum-spark"}


def test_prepare_into_clone_failure_returns_tuple(monkeypatch, tmp_path):
    """克隆失败必须返回 (None, False)，裸 None 即契约违反。"""

    def _boom(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128, cmd="git clone", stderr=b"fatal: repository not found"
        )

    monkeypatch.setattr(subprocess, "run", _boom)
    assert tasks._prepare_into("t-clone-fail", dict(_REPO), tmp_path) == (None, False)


def test_prepare_into_clone_timeout_returns_tuple(monkeypatch, tmp_path):
    """克隆超时同属可记录失败：返回 (None, False)，不向调用方抛异常。"""

    def _slow(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git clone", timeout=120)

    monkeypatch.setattr(subprocess, "run", _slow)
    assert tasks._prepare_into("t-clone-timeout", dict(_REPO), tmp_path) == (None, False)

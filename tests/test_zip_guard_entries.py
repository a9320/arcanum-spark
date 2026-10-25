"""R9 审计修复回归：用户上传 zip 防护（app/zipguard.py 单一数据源）。

2026-10-25 全仓审计 A-F1：app.py / streamlit_app.py 两个公开上传入口此前
裸 extractall（61496e8 只修了 codeark/dashboard.py）。R9 抽公共模块
app/zipguard.py，本文件钉死契约：
- 正常 zip 解出全部文件；
- 声明解压总尺寸超 200MB / 条目数超 5000 → 写盘前 ValueError；
- member 路径逃逸 dest（".."）→ ValueError；
- 两个部署入口源码必须从 zipguard 导入（防退回裸 extractall）。
"""
import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.zipguard import extract_zip  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_normal_zip_extracts(tmp_path):
    data = _zip_bytes({"a.txt": b"hello", "sub/b.txt": b"world"})
    extract_zip(data, tmp_path)
    assert (tmp_path / "a.txt").read_bytes() == b"hello"
    assert (tmp_path / "sub" / "b.txt").read_bytes() == b"world"


def test_declared_total_size_over_limit_rejected(tmp_path):
    # 200MB+1 的零字节串压缩后很小——先验用 zip 头声明值，写盘前拒绝
    data = _zip_bytes({"big.bin": b"\0" * (200 * 1024 * 1024 + 1)})
    with pytest.raises(ValueError, match="尺寸|size"):
        extract_zip(data, tmp_path)
    assert not list(tmp_path.rglob("big.bin"))


def test_member_count_over_limit_rejected(tmp_path):
    data = _zip_bytes({f"f{i}.txt": b"x" for i in range(5001)})
    with pytest.raises(ValueError, match="条目|member"):
        extract_zip(data, tmp_path)


def test_path_traversal_rejected(tmp_path):
    data = _zip_bytes({"../evil.txt": b"x"})
    with pytest.raises(ValueError, match="遍历|traversal"):
        extract_zip(data, tmp_path)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_both_entrypoints_import_guarded_extract_zip():
    # 源码级接线断言：入口不许自带解压实现（防退回裸 extractall）
    for name in ("app.py", "streamlit_app.py"):
        src = (ROOT / name).read_text(encoding="utf-8")
        assert "from app.zipguard import extract_zip" in src, name
        assert "extractall" not in src, f"{name} 不得直接调用 extractall"

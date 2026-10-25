"""用户上传 zip 的统一解压入口（ZIP 炸弹/路径遍历防护，单一数据源）。

2026-10-25 全仓审计 R9（A-F1）：app.py / streamlit_app.py 两个公开上传入口
此前各自裸 extractall（61496e8 只修了 codeark/dashboard.py）。抽公共模块
对齐 dashboard 同款防护，三处防护逻辑不再分叉：
- 条目数 ≤5000、声明解压总尺寸 ≤200MB（先验后解，超限写盘前拒绝）；
- 逐 member 路径遍历检查（解析后目标必须仍在 dest 内）。

已知边界（10-25 审计 A-F10，明写不掩盖）：先验取 zip 头声明值，蓄意谎报
header 的恶意包在写盘阶段无二次计量——生产部署入口建议叠加容器磁盘配额。
"""
import io
import zipfile
from pathlib import Path

MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 解压后合计 ≤200MB
MAX_ENTRIES = 5000


def extract_zip(data: bytes, dest: Path) -> None:
    """解压用户上传的 zip 到 dest（含 ZIP 炸弹/路径遍历防护）。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError(f"zip 条目数超限（{len(infos)} > {MAX_ENTRIES}）")
        total = sum(i.file_size for i in infos)
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"zip 解压后总尺寸超限（{total} > {MAX_TOTAL_BYTES} 字节）")
        for info in infos:
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError("非法 zip 路径（路径遍历攻击）")
            zf.extract(info, dest)

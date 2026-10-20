#!/bin/bash
# DSW Python 依赖自举（source 使用）：/root 不持久，strands 钉版放 /mnt/workspace/pylibs。
# 用法：在跑批脚本 cd 到仓根后 `source scripts/dsw-env.sh`。
# 行为：①把持久库加入 PYTHONPATH；②import 失败时自动执行 dsw-bootstrap.sh（幂等）。

LIB=${ARCA_PYLIBS:-/mnt/workspace/pylibs}

case ":${PYTHONPATH:-}:" in
  *":$LIB:"*) ;;
  *) [ -d "$LIB" ] && export PYTHONPATH="$LIB${PYTHONPATH:+:$PYTHONPATH}" ;;
esac

if python -c "import strands" >/dev/null 2>&1; then
  return 0 2>/dev/null || exit 0
fi

if [ ! -d /mnt/workspace ]; then
  echo "!! strands 缺失且非 DSW 环境：请 pip install strands-agents==1.56.0" >&2
  return 1 2>/dev/null || exit 3
fi

echo "== strands 缺失，安装到 $LIB（持久区，一次性）==" >&2
bash "$(dirname "${BASH_SOURCE[0]}")/dsw-bootstrap.sh" >&2 || {
  echo "!! strands 安装失败（检查网络/pip 源）" >&2
  return 1 2>/dev/null || exit 3
}
echo "== strands 就绪: $LIB ==" >&2
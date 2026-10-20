#!/bin/bash
# 把 strands-agents 钉版安装到持久区，供 pod 重建后复用（/root 与系统 site-packages 不持久）。
# 幂等：已装且版本正确则跳过。用法：bash scripts/dsw-bootstrap.sh
set -u

LIB=${ARCA_PYLIBS:-/mnt/workspace/pylibs}
PIN=${ARCA_STRANDS_PIN:-strands-agents==1.56.0}

mkdir -p "$LIB" || exit 1

if PYTHONPATH="$LIB" python -c \
  "import importlib.metadata as m,sys; sys.exit(0 if m.version('strands-agents')=='1.56.0' else 1)" \
  2>/dev/null; then
  echo "strands 已就绪: $LIB"
else
  echo "== 安装 $PIN -> $LIB =="
  pip install -q --upgrade --target "$LIB" "$PIN" \
    || { echo "!! pip 安装失败（检查网络/pip 源）"; exit 1; }
fi

PYTHONPATH="$LIB" python -c "import strands; print('strands OK:', strands.__file__)" || exit 1
# CodeRisk Cloud × Arcanum — 本地开发 Dockerfile
# 默认 API 模式；Worker/Dashboard 通过 docker-compose command 覆盖

FROM python:3.12-slim

LABEL maintainer="CodeRisk Cloud contributors"
LABEL description="CodeRisk Cloud × Arcanum — AI-era code security platform"

WORKDIR /app

# 系统依赖：git (clone repos)、gcc (构建 Python 包)、ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（构建时一次安装）
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 应用代码（含内置引擎层 engine/）
COPY app/ ./app/
COPY engine/ ./engine/
COPY demo/ ./demo/
COPY tests/ ./tests/
COPY docs/ ./docs/
COPY README.md LICENSE .env.example ./

# 运行目录
RUN mkdir -p /app/reports /app/reports/uploads

# 环境变量默认值（本地开发模式）
ENV PYTHONPATH=/app:/app/engine
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV REDIS_URL=redis://redis:6379/0
ENV REPORTS_DIR=/app/reports
ENV CODERISK_PATH=/app/engine
ENV WORKER_CONCURRENCY=2

# 暴露端口（API）
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 默认运行 API（docker-compose command 可覆盖）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
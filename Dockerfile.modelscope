# CodeRisk Arcanum — 魔搭创空间 Docker 类型部署
# 方案1 轻量版：Streamlit 独立入口，本地跑 PITAX，不依赖 Redis/Celery/LLM
# 保留完整项目结构（app/ 包 + engine/ 引擎），streamlit_app.py 为独立入口避免命名冲突

FROM python:3.12-slim

LABEL maintainer="AI溢出安全实验室"
LABEL description="CodeRisk Arcanum — AI-era code security scanner (PITAX)"

WORKDIR /app

# 系统依赖：git (clone repos), gcc (构建), ca-certificates, curl (健康检查)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    build-essential \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir streamlit

# 应用代码（含内置引擎层 engine/ + PITAX app/pitax）
COPY app/ ./app/
COPY engine/ ./engine/
COPY demo/ ./demo/
COPY docs/ ./docs/
COPY README.md LICENSE .env.example ./
COPY streamlit_app.py ./streamlit_app.py

# 运行目录
RUN mkdir -p /app/reports

# 环境变量
ENV PYTHONPATH=/app:/app/engine
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_PORT=7860
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true

# 魔搭创空间要求的端口
EXPOSE 7860

# 健康检查：检查 Streamlit 是否在 7860 响应
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:7860/_stcore/health || exit 1

# 启动 Streamlit 独立入口
CMD ["streamlit", "run", "streamlit_app.py", "--server.port", "7860", "--server.address", "0.0.0.0"]
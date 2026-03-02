# BBooster Server Dockerfile
# Week 19: Docker化 + 배포 준비
# Base: Python 3.11-slim

FROM python:3.11-slim

# 빌드 시 버전 전달용 ARG
ARG APP_VERSION=1.0.0
ARG BUILD_DATE
ARG GIT_COMMIT

# 이미지 메타데이터 (OCI 표준)
LABEL org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.title="BBooster" \
      org.opencontainers.image.description="BBooster Trading Automation Server"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_VERSION=${APP_VERSION}

# Set working directory
WORKDIR /app

# Install system dependencies (for psycopg2, matplotlib Korean fonts)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    fontconfig \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -fv

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy data files (policies, etc.)
COPY data/ ./data/

# Copy static files (demo data, brand assets)
COPY static/ ./static/

# Create static directory for chart images
RUN mkdir -p /app/static/charts

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Run the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

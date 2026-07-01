# ─── Stage 1: dependency builder ──────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /build

# System deps for native packages (motor, cryptography, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: runtime ──────────────────────────────────────────
FROM python:3.13-slim AS runtime

WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create directories for local LLM data and reports
RUN mkdir -p omni_data/adapter omni_data static/reports logs uploads

# Create non-root user for security
RUN groupadd -r omni && useradd -r -g omni omni \
    && chown -R omni:omni /app

USER omni

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

EXPOSE 5000

CMD ["uvicorn", "app:socket_app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]

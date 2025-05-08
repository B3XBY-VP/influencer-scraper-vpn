# backend/Dockerfile (Fly.io public API)

# ---------- Build stage ----------
FROM python:3.11-slim AS builder
WORKDIR /build
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates \
      ffmpeg libnss3 libatk-bridge2.0-0 libgtk-3-0 \
      libdrm2 libgbm1 libasound2 libxdamage1 libxrandr2 fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt . 
RUN python3 -m pip install --upgrade pip \
 && python3 -m pip install --no-cache-dir -r requirements.txt \
 && python3 -m playwright install --with-deps

# ───────────────────────────────────────────────────────────────
# Runtime image
# ───────────────────────────────────────────────────────────────
FROM python:3.11-slim
LABEL org.opencontainers.image.source="https://github.com/<your-org>/influencer-tracking"

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONPATH=/app

# 1) Copy in all Python + Playwright bits
COPY --from=builder /usr/local /usr/local
COPY --from=builder /ms-playwright /ms-playwright

# 2) Install runtime deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      dumb-init ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# 3) Copy your code & entrypoint
WORKDIR /app
COPY . .

# 4) Create unprivileged user & fix perms
RUN chmod +x docker-entrypoint.sh \
 && useradd -m appuser \
 && chown -R appuser:appuser /app

USER appuser
EXPOSE 8000

# 5) Launch
ENTRYPOINT ["/usr/bin/dumb-init", "--", "/app/docker-entrypoint.sh"]







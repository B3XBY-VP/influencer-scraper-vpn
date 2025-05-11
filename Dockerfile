# ──────────────────────────────────────────────────────────────────────────────
# influencer-scraper-vpn · Dockerfile
# Produces a container that runs  ➜ Playwright + Python 3.11  ➜ Surfshark OpenVPN
# ──────────────────────────────────────────────────────────────────────────────

##############################
# 1. BUILD STAGE  (Playwright)
##############################
FROM python:3.11-slim AS builder
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /build

# ▸ Install all libraries Playwright/Chromium needs _once_ in the build stage
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gnupg ca-certificates \
      ffmpeg libnss3 libatk-bridge2.0-0 libgtk-3-0 \
      libdrm2 libgbm1 libasound2 libxdamage1 libxrandr2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps        # installs browsers into /ms-playwright


##############################
# 2. RUNTIME STAGE
##############################
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ── Runtime deps: OpenVPN + Playwright browser libs + dumb-init ───────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
      openvpn iproute2 procps libcap2-bin dumb-init bash ca-certificates \
      # Playwright / Chromium shared libs (mirror the list from builder)
      ffmpeg libnss3 libatk-bridge2.0-0 libgtk-3-0 \
      libdrm2 libgbm1 libasound2 libxdamage1 libxrandr2 libglib2.0-0 \
      fonts-liberation \
    && setcap cap_net_admin,cap_net_raw+ep "$(which openvpn)" \
    && mkdir -p /dev/net && mknod /dev/net/tun c 10 200 && chmod 600 /dev/net/tun \
    && rm -rf /var/lib/apt/lists/*

# ── Copy Python site-packages + Playwright browsers from builder ──────────────
COPY --from=builder /usr/local /usr/local
COPY --from=builder /ms-playwright /ms-playwright

# ── Copy application code ─────────────────────────────────────────────────────
WORKDIR /app
COPY . .

# ── Entrypoint permissions & unprivileged user ────────────────────────────────
RUN chmod +x docker-entrypoint.sh && \
    useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
ENTRYPOINT ["/usr/bin/dumb-init", "--", "/app/docker-entrypoint.sh"]







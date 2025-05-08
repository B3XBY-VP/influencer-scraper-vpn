# backend/docker-entrypoint.sh

#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────────────────────
# Write out GOOGLE creds so Firestore SDK can find them
# ────────────────────────────────────────────────────────────────────────────
if [[ -n "${GOOGLE_SERVICE_ACCOUNT_JSON:-}" ]]; then
  mkdir -p /app/credentials
  printf '%s' "$GOOGLE_SERVICE_ACCOUNT_JSON" \
    > /app/credentials/service-account.json
  chmod 600 /app/credentials/service-account.json
  export GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
fi

# ────────────────────────────────────────────────────────────────────────────
# Start Uvicorn
# ────────────────────────────────────────────────────────────────────────────
PORT="${PORT:-8000}"
echo "🚀 Starting Uvicorn on 0.0.0.0:${PORT}"
exec uvicorn main:app \
     --host 0.0.0.0 \
     --port "${PORT}" \
     --proxy-headers





#!/usr/bin/env bash
set -euo pipefail

# 1) Persist Surfshark creds
if [[ -n "${SURFSHARK_USER:-}" && -n "${SURFSHARK_PASS:-}" ]]; then
  mkdir -p /app/vpn
  printf '%s\n%s\n' "$SURFSHARK_USER" "$SURFSHARK_PASS" > /app/vpn/surfshark_creds.txt
  chmod 600 /app/vpn/surfshark_creds.txt
fi

# 2) Rotate VPN
if [[ -d "/app/vpn/configs/uk" && -n "${SURFSHARK_USER:-}" ]]; then
  echo "🔄 Rotating VPN…"
  for cfg in /app/vpn/configs/uk/uk-*.ovpn; do
    grep -q '^redirect-gateway' "$cfg" || echo -e '\nredirect-gateway def1 bypass-dhcp' >> "$cfg"
  done
  OVPN=$(find /app/vpn/configs/uk -name 'uk-*.ovpn' | shuf -n1)
  echo "   using: ${OVPN##*/}"
  openvpn --config "$OVPN" --auth-user-pass /app/vpn/surfshark_creds.txt --daemon
  echo "⏱  Waiting 15 s for VPN…"
  sleep 15
  echo "✅ VPN should be up"
fi

# 3) Launch Uvicorn
PORT="${PORT:-8000}"
echo "🚀 Starting Uvicorn on 0.0.0.0:${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"




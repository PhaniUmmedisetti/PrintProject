#!/usr/bin/env bash
set -euo pipefail

KIOSK_URL="${1:-http://localhost:4173}"

if command -v chromium >/dev/null 2>&1; then
  BROWSER="chromium"
elif command -v chromium-browser >/dev/null 2>&1; then
  BROWSER="chromium-browser"
else
  echo "Chromium not found. Install with: sudo apt install -y chromium" >&2
  exit 1
fi

exec "${BROWSER}" \
  --kiosk \
  --start-fullscreen \
  --window-size=800,480 \
  --window-position=0,0 \
  --force-device-scale-factor=1 \
  --touch-events=enabled \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  --disable-infobars \
  --noerrdialogs \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble \
  --disable-features=Translate,PasswordManagerEnabled,AutofillServerCommunication,MediaRouter \
  --password-store=basic \
  --use-mock-keychain \
  --disk-cache-size=1 \
  --media-cache-size=1 \
  "${KIOSK_URL}"

#!/usr/bin/env bash
set -euo pipefail

kiosk_url="${NEXTCARE_KIOSK_URL:-}"
if [[ -z "$kiosk_url" ]]; then
  echo "Set NEXTCARE_KIOSK_URL to the deployed HTTPS NextCare URL." >&2
  exit 1
fi

case "$kiosk_url" in
  https://*) ;;
  *)
    echo "NEXTCARE_KIOSK_URL must use HTTPS." >&2
    exit 1
    ;;
esac

for browser in google-chrome-stable google-chrome chromium chromium-browser; do
  if command -v "$browser" >/dev/null 2>&1; then
    exec "$browser" \
      --kiosk \
      --no-first-run \
      --disable-session-crashed-bubble \
      "$kiosk_url"
  fi
done

echo "Install Google Chrome or Chromium before launching the kiosk." >&2
exit 1

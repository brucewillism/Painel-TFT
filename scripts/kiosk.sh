#!/usr/bin/env bash
# Abre o Chromium em tela cheia apontando para o painel local.
set -euo pipefail
URL="${LANCER_URL:-http://127.0.0.1:8080/}"
# Espera o backend subir (até ~30 s).
for _ in $(seq 1 30); do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Desativa descanso de tela e cursor (ambiente X11 / Xwayland).
if command -v xset >/dev/null 2>&1; then
  xset s off -dpms || true
  xset s noblank || true
fi
if command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 0.5 -root &
fi

CHROME=""
for c in chromium-browser chromium google-chrome; do
  if command -v "$c" >/dev/null 2>&1; then
    CHROME="$c"
    break
  fi
done
if [[ -z "$CHROME" ]]; then
  echo "Chromium não encontrado." >&2
  exit 1
fi

exec "$CHROME" \
  --kiosk \
  --app="$URL" \
  --incognito \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-translate \
  --check-for-update-interval=31536000 \
  --overscroll-history-navigation=0 \
  --autoplay-policy=no-user-gesture-required \
  --window-size=800,480 \
  --window-position=0,0

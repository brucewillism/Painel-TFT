#!/usr/bin/env bash
# Abre o visualizador CarPlay/Android Auto em tela cheia (DISPLAY=:0).
# Se o driver não estiver instalado ou o dongle não estiver presente,
# sai com código 2 — o painel mostra o mock e as instruções.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DISPLAY="${DISPLAY:-:0}"

# react-carplay (Electron) é o caminho mais “central multimídia”.
if [[ -d "$ROOT/vendor/react-carplay" ]]; then
  cd "$ROOT/vendor/react-carplay"
  if command -v npx >/dev/null 2>&1; then
    exec npx electron . --kiosk || exec npm start
  fi
fi

if [[ -d "$ROOT/vendor/node-carplay" ]]; then
  cd "$ROOT/vendor/node-carplay"
  exec npm start
fi

echo "Driver node-CarPlay não instalado. Rode scripts/install-carplay.sh" >&2
exit 2

#!/usr/bin/env bash
# Instala o driver open-source node-CarPlay para dongles Carlinkit
# (CPC200-CCPA / 4.0 / 5.0, cabo ou wireless).
# Requer Node.js 18+ e o dongle encaixado em uma USB do Pi (de preferência
# numa porta USB 2.0 alimentada / hub com fonte).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/vendor"
mkdir -p "$VENDOR"
cd "$VENDOR"

if ! command -v node >/dev/null 2>&1; then
  echo "Instale o Node.js 18+ primeiro (ex.: https://nodejs.org ou apt install nodejs npm)." >&2
  exit 1
fi

if [[ ! -d node-carplay ]]; then
  echo "==> Clonando node-CarPlay (https://github.com/rhysmorgan134/node-CarPlay)"
  git clone --depth 1 https://github.com/rhysmorgan134/node-CarPlay.git node-carplay
fi
cd node-carplay
npm install

# react-carplay é um visualizador Electron/React em cima do mesmo protocolo.
cd "$VENDOR"
if [[ ! -d react-carplay ]]; then
  echo "==> Clonando react-carplay (https://github.com/rhysmorgan134/react-carplay)"
  git clone --depth 1 https://github.com/rhysmorgan134/react-carplay.git react-carplay || true
fi
if [[ -d react-carplay ]]; then
  cd react-carplay
  npm install || true
fi

echo
echo "Pronto. Conecte o dongle, desbloqueie o iPhone/Android e rode:"
echo "  $ROOT/scripts/carplay-launch.sh"
echo "Ou toque no tile CarPlay do painel."
echo
echo "Áudio: o dongle costuma aparecer como um dispositivo USB. No PipeWire:"
echo "  wpctl status          # identifique o sink do dongle e o DAC/HDMI do carro"
echo "  wpctl set-default N   # saia o som no stereo do Lancer"
echo "Microfone (Siri / Google): escolha a fonte do dongle ou um mic USB:"
echo "  wpctl set-default-source N"

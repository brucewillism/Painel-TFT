#!/usr/bin/env bash
# Instalação no Raspberry Pi OS (Lite ou Desktop). Execute com o usuário do Pi.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Pacotes do sistema"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip python3-yaml bluetooth bluez rfkill
sudo apt-get install -y python3-gps gpsd gpsd-clients can-utils || true
# rfcomm às vezes vem no pacote bluez; Chromium tem nomes diferentes no Pi OS.
sudo apt-get install -y chromium-browser || sudo apt-get install -y chromium || true

# python3-can / can-utils: instalados acima quando disponíveis (fase 2, HAT MCP2515).

echo "==> Ambiente virtual"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Pastas de dados"
mkdir -p data app/static/tiles

echo "==> Serviço systemd (backend)"
sed "s|__ROOT__|$ROOT|g; s|__USER__|$USER|g" "$ROOT/systemd/lancer-painel.service" \
  | sudo tee /etc/systemd/system/lancer-painel.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable lancer-painel.service

# Autostart do kiosk: se houver desktop gráfico, usa .desktop; senão, serviço.
if [[ -d /etc/xdg/autostart ]] && [[ -n "${DISPLAY:-}" || -d /home/$USER/.config ]]; then
  mkdir -p "$HOME/.config/autostart"
  sed "s|__ROOT__|$ROOT|g" "$ROOT/systemd/lancer-painel-kiosk.desktop" \
    > "$HOME/.config/autostart/lancer-painel-kiosk.desktop"
  echo "Kiosk instalado em ~/.config/autostart"
fi

chmod +x "$ROOT/scripts/"*.sh

echo
echo "Pronto. Próximos passos:"
echo "  1. Pareie o ELM327:  sudo $ROOT/scripts/pair-elm327.sh"
echo "  2. Edite $ROOT/config.yaml  (source: obd  e o MAC/porta)"
echo "  3. sudo systemctl start lancer-painel"
echo "  4. Teste no simulador:  LANCER_SOURCE=simulator $ROOT/scripts/run-simulator.sh"
echo "  5. (Opcional) baixe tiles: $ROOT/scripts/download-tiles.sh -23.58 -46.67 -23.55 -46.63 12 16"

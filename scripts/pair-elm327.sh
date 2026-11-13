#!/usr/bin/env bash
# Pareia um clone ELM327 Bluetooth e cria /dev/rfcomm0.
# Uso: sudo scripts/pair-elm327.sh [MAC]
# PIN típico dos clones v1.5/v2.1: 1234 (às vezes 0000).
set -euo pipefail

PIN="${ELM_PIN:-1234}"
MAC="${1:-}"

if [[ $EUID -ne 0 ]]; then
  echo "Execute com sudo." >&2
  exit 1
fi

bluetoothctl power on
bluetoothctl agent on
bluetoothctl default-agent

if [[ -z "$MAC" ]]; then
  echo "Procurando adaptadores OBD/ELM por 12 segundos…"
  bluetoothctl --timeout 12 scan on || true
  echo
  echo "Dispositivos encontrados:"
  bluetoothctl devices
  echo
  read -r -p "Digite o MAC do ELM327 (AA:BB:CC:DD:EE:FF): " MAC
fi

if [[ ! "$MAC" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]; then
  echo "MAC inválido: $MAC" >&2
  exit 1
fi

# Alguns clones precisam do PIN no agent.
bluetoothctl <<BT
pair $MAC
$PIN
trust $MAC
connect $MAC
quit
BT

# Libera um bind antigo e recria o rfcomm 0.
rfcomm release 0 2>/dev/null || true
# Canal RFCOMM 1 é o padrão SPP do ELM327.
rfcomm bind 0 "$MAC" 1
sleep 0.5
if [[ -e /dev/rfcomm0 ]]; then
  echo "OK: /dev/rfcomm0 ligado a $MAC"
  ls -l /dev/rfcomm0
else
  echo "Falha ao criar /dev/rfcomm0. Tente: rfcomm connect 0 $MAC 1" >&2
  exit 1
fi

# Persistência no boot: /etc/bluetooth/rfcomm.conf (Debian/Raspberry Pi OS)
CONF=/etc/bluetooth/rfcomm.conf
if [[ ! -f $CONF ]] || ! grep -q "$MAC" "$CONF"; then
  cat >> "$CONF" <<CFG

# lancer-painel ELM327
rfcomm0 {
  bind yes;
  device $MAC;
  channel 1;
  comment "ELM327 Lancer";
}
CFG
  echo "Bind persistente gravado em $CONF"
fi

#!/usr/bin/env bash
# Configura um módulo u-blox NEO-6M/7M/M8 (USB ou UART) para 10 Hz.
# Use com gpsd:  sudo gpsd -n /dev/ttyACM0
# Depois:       ./scripts/ublox-10hz.sh /dev/ttyACM0
# O NEO-6M em 9600 baud às vezes não sustenta 10 Hz com NMEA completo —
# prefira 115200 e, se precisar, só GGA+RMC, ou um NEO-7M/M8.
set -euo pipefail
DEV="${1:-/dev/ttyACM0}"
BAUD="${2:-115200}"

if ! command -v python3 >/dev/null; then
  echo "python3 é necessário" >&2
  exit 1
fi

python3 - "$DEV" "$BAUD" << 'PY'
import sys, time
from pathlib import Path

dev, baud = sys.argv[1], int(sys.argv[2])

def ubx(cls, mid, payload=b""):
    body = bytes([cls, mid]) + len(payload).to_bytes(2, "little") + payload
    ck_a = ck_b = 0
    for b in body:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return b"\xb5\x62" + body + bytes([ck_a, ck_b])

try:
    import serial  # type: ignore
except ImportError:
    print("Instale pyserial:  pip install pyserial", file=sys.stderr)
    sys.exit(1)

# tenta 9600 e depois a baud desejada
ser = serial.Serial(dev, 9600, timeout=0.3)
time.sleep(0.1)
# CFG-PRT UART 115200 8N1
# payload: portID=1, reserved, txReady=0, mode=8N1, baud, in/out proto nmea+ubx
def cfg_prt(baudrate, port=1):
    import struct
    mode = 0x08D0  # 8N1
    payload = struct.pack("<BBHIIHHHH", port, 0, 0, mode, baudrate, 0x07, 0x03, 0, 0)
    # struct may be wrong length; use documented 20-byte payload
    payload = struct.pack("<BBHIIIHH", port, 0, 0, mode, baudrate, 7, 3) + b"\x00\x00"
    return ubx(0x06, 0x00, payload[:20] if len(payload) > 20 else payload)

# melhor: enviar em 9600 o pedido de 115200 e reabrir
ser.write(ubx(0x06, 0x00, __import__("struct").pack("<BBHIIHHH", 1, 0, 0, 0x08D0, baud, 0x0007, 0x0003, 0)))
ser.flush(); time.sleep(0.3); ser.close()
ser = serial.Serial(dev, baud, timeout=0.3)
# CFG-RATE: measRate=100 ms (10 Hz), navRate=1, timeRef=1 (GPS)
ser.write(ubx(0x06, 0x08, __import__("struct").pack("<HHH", 100, 1, 1)))
ser.flush()
# CFG-CFG save to BBR+flash
ser.write(ubx(0x06, 0x09, b"\x00\x00\x00\x00\xff\xff\x00\x00\x00\x00\x17"))
ser.flush()
time.sleep(0.2)
ser.close()
print(f"u-blox em {dev}: tentou {baud} baud e 10 Hz (UBX-CFG-RATE measRate=100 ms).")
print("Confira com:  cgps  ou  gpspipe -w  (o campo 'spd' deve atualizar ~10 vezes/s).")
print("Se o módulo travar, volte a 9600 e 1 Hz com a u-center ou o mesmo script em 9600/1000 ms.")
PY

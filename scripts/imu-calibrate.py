#!/usr/bin/env python3
"""Calibração da IMU (MPU-6050 / MPU-9250 / ICM-20948) com o carro parado e nivelado.

Ligação no Raspberry Pi (I2C1):
  VCC → 3V3 (pino 1)     GND → GND (pino 6)
  SDA → GPIO2 (pino 3)   SCL → GPIO3 (pino 5)
Alguns módulos 5 V precisam de divisores ou de um transmissor de nível.
Endereço padrão 0x68 (AD0 no GND); 0x69 se AD0 estiver em VCC.

Montagem sugerida: X aponta para a frente do carro, Y para a direita, Z para cima.
Este script zera os offsets de AX/AY e deixa AZ ≈ 1 g (gravidade).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "imu-calib.json"
ADDR = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x68
BUSN = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def main() -> int:
    try:
        from smbus2 import SMBus
    except ImportError:
        try:
            from smbus import SMBus  # type: ignore
        except ImportError:
            print("Instale smbus2:  pip install smbus2")
            return 1
    bus = SMBus(BUSN)
    try:
        who = bus.read_byte_data(ADDR, 0x75)
        print(f"WHO_AM_I = 0x{who:02X} (0x68/70/71/73 = MPU, 0xEA no banco 0 = ICM-20948)")
        bus.write_byte_data(ADDR, 0x6B, 0x00)  # acorda MPU
        time.sleep(0.05)
    except OSError as exc:
        print(f"Falha no I2C (bus {BUSN} addr 0x{ADDR:02X}): {exc}")
        return 1

    print("Deixe o carro parado e nivelado. Amostrando 2 s…")
    samples = []
    t0 = time.time()
    while time.time() - t0 < 2.0:
        raw = bus.read_i2c_block_data(ADDR, 0x3B, 6)

        def s16(h, l):
            v = (h << 8) | l
            return v - 65536 if v > 32767 else v

        samples.append((s16(raw[0], raw[1]) / 16384.0,
                        s16(raw[2], raw[3]) / 16384.0,
                        s16(raw[4], raw[5]) / 16384.0))
        time.sleep(0.02)
    n = len(samples)
    ax = sum(s[0] for s in samples) / n
    ay = sum(s[1] for s in samples) / n
    az = sum(s[2] for s in samples) / n
    calib = {"ax": ax, "ay": ay, "az": az - 1.0}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(calib, indent=2), encoding="utf-8")
    print(f"Média bruta: ax={ax:.3f} ay={ay:.3f} az={az:.3f} g")
    print(f"Offsets gravados em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

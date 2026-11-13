"""TPMS Bluetooth BLE: anúncios de sensores externos baratos, um por roda."""

from __future__ import annotations

import logging
import struct
import time
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

WHEELS = ("fl", "fr", "rl", "rr")
WHEEL_NAME = {"fl": "Dianteiro esquerdo", "fr": "Dianteiro direito",
              "rl": "Traseiro esquerdo", "rr": "Traseiro direito"}


def parse_advertisement(payload: bytes) -> dict | None:
    """Tenta decodificar payloads comuns de sensores TPMS externos.

    Formatos cobertos (os mais vendidos em clones de 'BLE TPMS'):
    - 19 bytes com manufacturer data começando por 00 01 / ou id 0x0100,
      pressão em kPa*10 ou PSI*10, temp signed °C, bateria %.
    - 16-byte 'BR' style: id 6 bytes + kPa uint16 BE + temp int16 + bat.
    - 8–10 bytes curtos: press uint16 LE kPa, temp int8, bat uint8.
    """
    if not payload:
        return None
    data = payload
    # tira flags AD se vier o pacote inteiro
    if len(data) >= 3 and data[0] in (0x02, 0x03) and data[1] == 0x01:
        data = _extract_mfr(data) or data
    for fn in (_parse_long19, _parse_br16, _parse_short, _parse_sysgration):
        try:
            out = fn(data)
        except Exception:
            out = None
        if out:
            return out
    return None


def _extract_mfr(pkt: bytes) -> bytes | None:
    i = 0
    while i < len(pkt):
        ln = pkt[i]
        if ln == 0 or i + 1 + ln > len(pkt):
            break
        typ = pkt[i + 1]
        if typ in (0xFF, 0x16):
            return pkt[i + 2:i + 1 + ln]
        i += 1 + ln
    return None


def _parse_long19(d: bytes) -> dict | None:
    if len(d) < 16:
        return None
    # [id 6][kPa*10 u16 BE][temp i8][bat u8] ...
    ident = d[0:6].hex()
    kpa = struct.unpack_from(">H", d, 6)[0]
    if not (80 <= kpa <= 5000):
        kpa = struct.unpack_from("<H", d, 6)[0]
    if not (80 <= kpa <= 5000):
        return None
    temp = struct.unpack_from("b", d, 8)[0]
    bat = d[9] if len(d) > 9 else 100
    if bat > 100:
        bat = 100
    if not (-40 <= temp <= 125):
        return None
    return {"id": ident, "kpa": float(kpa) if kpa > 500 else kpa * 10, "psi": None,
            "temp_c": float(temp), "battery": int(bat)}


def _parse_br16(d: bytes) -> dict | None:
    if len(d) < 14:
        return None
    # alguns usam pressão em 1/10 PSI nos bytes 8-9
    ident = d[0:6].hex()
    psi10 = struct.unpack_from(">H", d, 8)[0]
    temp = struct.unpack_from("b", d, 10)[0] if len(d) > 10 else 25
    bat = d[11] if len(d) > 11 else 100
    psi = psi10 / 10.0
    if not (10 <= psi <= 80):
        return None
    return {"id": ident, "kpa": psi * 6.89476, "psi": psi, "temp_c": float(temp), "battery": min(100, int(bat))}


def _parse_short(d: bytes) -> dict | None:
    if not (8 <= len(d) <= 12):
        return None
    kpa = struct.unpack_from("<H", d, 0)[0]
    if not (80 <= kpa <= 500):
        kpa = struct.unpack_from(">H", d, 0)[0]
    if not (80 <= kpa <= 500):
        return None
    temp = struct.unpack_from("b", d, 2)[0]
    bat = d[3] if len(d) > 3 else 100
    ident = d[4:8].hex() if len(d) >= 8 else d.hex()
    return {"id": ident, "kpa": float(kpa), "psi": kpa / 6.89476, "temp_c": float(temp), "battery": min(100, int(bat))}


def _parse_sysgration(d: bytes) -> dict | None:
    """Alguns sensores 'Sysgration/Tech400' usam 7+ bytes: press kPa*10 LE, temp, bat, flags."""
    if len(d) < 7:
        return None
    kpa10 = struct.unpack_from("<H", d, 1)[0]
    kpa = kpa10 / 10.0
    if not (80 <= kpa <= 450):
        return None
    temp = struct.unpack_from("b", d, 3)[0]
    bat = d[4]
    ident = d[0:1].hex() + d[-2:].hex()
    return {"id": ident, "kpa": kpa, "psi": kpa / 6.89476, "temp_c": float(temp), "battery": min(100, int(bat))}


class TPMS:
    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = cfg.get("tpms") or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.warn_kpa = float(self.cfg.get("warn_kpa", 190))  # ~27.5 psi; Lancer ~32 psi / 220 kPa
        self.hot_c = float(self.cfg.get("hot_c", 70))
        # binding id → wheel
        self.bind: dict[str, str] = dict(self.cfg.get("bind") or {})
        self.wheels: dict[str, dict] = {w: None for w in WHEELS}
        self._by_id: dict[str, dict] = {}
        self._scan = None
        self.simulate = bool(self.cfg.get("simulate", True))
        self._t0 = time.time()
        if self.enabled and not self.simulate:
            self._start_ble()

    def _start_ble(self) -> None:
        try:
            import asyncio
            from bleak import BleakScanner  # type: ignore

            def _cb(device, adv):
                mfr = b""
                if getattr(adv, "manufacturer_data", None):
                    for k, v in adv.manufacturer_data.items():
                        mfr = k.to_bytes(2, "little") + bytes(v)
                        break
                payload = mfr or (adv.service_data and next(iter(adv.service_data.values()), b"")) or b""
                parsed = parse_advertisement(payload)
                if parsed:
                    parsed["rssi"] = getattr(adv, "rssi", None)
                    parsed["addr"] = getattr(device, "address", None)
                    self.ingest(parsed)

            # scanner em thread, best-effort
            import threading

            def _run():
                try:
                    asyncio.run(BleakScanner.start() if False else BleakScanner.discover(timeout=0))
                except Exception:
                    pass
                # loop simples de discovery
                while self.enabled:
                    try:
                        asyncio.run(_discover_once())
                    except Exception as exc:
                        log.debug("TPMS BLE: %s", exc)
                        time.sleep(5)

            async def _discover_once():
                await BleakScanner.discover(timeout=8, detection_callback=_cb)

            threading.Thread(target=_run, daemon=True).start()
            log.info("Scanner BLE TPMS iniciado.")
        except Exception as exc:
            log.info("BLE TPMS indisponível (%s) — usando simulação se habilitada.", exc)
            self.simulate = True

    def bind_wheel(self, wheel: str, sensor_id: str) -> dict:
        if wheel not in WHEELS:
            raise ValueError("roda inválida")
        # remove bind antigo
        self.bind = {k: v for k, v in self.bind.items() if v != wheel and k != sensor_id}
        self.bind[sensor_id] = wheel
        self._refresh_wheels()
        return self.snapshot()

    def ingest(self, parsed: dict) -> None:
        sid = parsed.get("id")
        if not sid:
            return
        parsed = dict(parsed)
        if parsed.get("psi") is None and parsed.get("kpa") is not None:
            parsed["psi"] = parsed["kpa"] / 6.89476
        parsed["ts"] = time.time()
        self._by_id[sid] = parsed
        self._refresh_wheels()

    def _refresh_wheels(self) -> None:
        self.wheels = {w: None for w in WHEELS}
        for sid, rec in self._by_id.items():
            w = self.bind.get(sid)
            if w:
                self.wheels[w] = {**rec, "wheel": w, "name": WHEEL_NAME[w], "alert": self._alert(rec)}
        # se não houver bind e temos exatamente 4, atribui em ordem de aparição
        unbound = [sid for sid in self._by_id if sid not in self.bind]
        free = [w for w in WHEELS if self.wheels[w] is None]
        for sid, w in zip(unbound, free):
            rec = self._by_id[sid]
            self.wheels[w] = {**rec, "wheel": w, "name": WHEEL_NAME[w], "alert": self._alert(rec), "unbound": True}

    def _alert(self, rec: dict) -> str | None:
        if rec.get("kpa") is not None and rec["kpa"] < self.warn_kpa:
            return "pressão baixa"
        if rec.get("temp_c") is not None and rec["temp_c"] >= self.hot_c:
            return "temperatura alta"
        if rec.get("battery") is not None and rec["battery"] < 15:
            return "bateria do sensor"
        return None

    def tick(self) -> dict:
        if self.simulate:
            self._sim()
        snap = self.snapshot()
        self.store.set_meta("tpms", snap)
        return snap

    def _sim(self) -> None:
        import math
        t = time.time() - self._t0
        # pressões típicas ~ 220 kPa, um pouco abaixo no DE (desgaste/demo de alerta suave)
        base = {"fl": 218, "fr": 224, "rl": 226, "rr": 221}
        for i, w in enumerate(WHEELS):
            kpa = base[w] + 2.0 * math.sin(t / 8 + i)
            rec = {
                "id": f"sim{w}",
                "kpa": round(kpa, 1),
                "psi": round(kpa / 6.89476, 1),
                "temp_c": round(28 + 6 * math.sin(t / 20 + i), 1),
                "battery": 87 - i,
                "ts": time.time(),
            }
            self.bind.setdefault(rec["id"], w)
            self._by_id[rec["id"]] = rec
        self._refresh_wheels()

    def snapshot(self) -> dict[str, Any]:
        alerts = [self.wheels[w] for w in WHEELS if self.wheels.get(w) and self.wheels[w].get("alert")]
        return {
            "enabled": self.enabled,
            "simulate": self.simulate,
            "warn_kpa": self.warn_kpa,
            "wheels": self.wheels,
            "sensors": self._by_id,
            "bind": self.bind,
            "alerts": len(alerts),
        }

"""G-meter: IMU I2C (MPU-6050/9250, ICM-20948) ou estimativa por GPS/velocidade."""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

# Endereços I2C comuns
_ADDRS = {
    "MPU-6050": 0x68,
    "MPU-9250": 0x68,
    "ICM-20948": 0x68,
}


class GForce:
    def __init__(self, store: DataStore, cfg: dict, root: Path) -> None:
        self.store = store
        self.cfg = cfg.get("imu") or {}
        self.root = root
        self.calib_path = Path(self.cfg.get("calib_path") or (root / "data/imu-calib.json"))
        if not self.calib_path.is_absolute():
            self.calib_path = root / self.calib_path
        self.offset = {"ax": 0.0, "ay": 0.0, "az": 0.0}
        self._load_calib()
        self.bus = None
        self.chip = None
        self.source = "gps"
        self.ax = self.ay = self.az = 0.0
        self.peak_lat = self.peak_lon = 0.0
        self.trail: list[tuple[float, float]] = []
        self._last_v = None
        self._last_hdg = None
        self._last_t = time.time()
        self._detect()

    def _load_calib(self) -> None:
        if self.calib_path.is_file():
            try:
                self.offset.update(json.loads(self.calib_path.read_text()))
            except Exception:
                pass

    def save_calib(self) -> dict:
        self.calib_path.parent.mkdir(parents=True, exist_ok=True)
        self.calib_path.write_text(json.dumps(self.offset), encoding="utf-8")
        return dict(self.offset)

    def _detect(self) -> None:
        if self.cfg.get("force_gps"):
            self.source = "gps"
            return
        try:
            from smbus2 import SMBus  # type: ignore
        except Exception:
            try:
                from smbus import SMBus  # type: ignore
            except Exception:
                self.source = "gps"
                return
        addr = int(self.cfg.get("address", 0x68))
        busn = int(self.cfg.get("bus", 1))
        try:
            bus = SMBus(busn)
            who = bus.read_byte_data(addr, 0x75)  # WHO_AM_I MPU
            # ICM-20948 bank0 WHO_AM_I is 0x00 and value 0xEA — try anyway
            bus.write_byte_data(addr, 0x6B, 0x00)  # wake MPU
            self.bus = bus
            self.chip = "MPU-6050" if who in {0x68, 0x70, 0x71, 0x73} else f"IMU 0x{who:02X}"
            self.source = "imu"
            log.info("IMU detectada: %s (I2C 0x%02X)", self.chip, addr)
        except Exception as exc:
            log.info("IMU I2C indisponível (%s) — G estimado pelo GPS/OBD.", exc)
            self.source = "gps"

    def _read_imu(self) -> tuple[float, float, float] | None:
        if not self.bus:
            return None
        addr = int(self.cfg.get("address", 0x68))
        try:
            raw = self.bus.read_i2c_block_data(addr, 0x3B, 6)
            def s16(h, l):
                v = (h << 8) | l
                return v - 65536 if v > 32767 else v
            ax = s16(raw[0], raw[1]) / 16384.0 - self.offset["ax"]
            ay = s16(raw[2], raw[3]) / 16384.0 - self.offset["ay"]
            az = s16(raw[4], raw[5]) / 16384.0 - self.offset["az"]
            # convenção: X frente, Y direita, Z cima; valor em g
            return ax, ay, az
        except Exception:
            return None

    def calibrate(self, seconds: float = 2.0) -> dict:
        """Nível parado: média dos eixos vira offset (az ≈ 1 g)."""
        samples = []
        t0 = time.time()
        while time.time() - t0 < seconds:
            v = self._read_imu()
            if v:
                samples.append(v)
            time.sleep(0.02)
        if not samples:
            # calibração GPS: zera
            self.offset = {"ax": 0.0, "ay": 0.0, "az": 0.0}
            return self.save_calib()
        n = len(samples)
        self.offset = {
            "ax": sum(s[0] + self.offset["ax"] for s in samples) / n,
            "ay": sum(s[1] + self.offset["ay"] for s in samples) / n,
            "az": sum(s[2] + self.offset["az"] for s in samples) / n - 1.0,  # gravidade
        }
        return self.save_calib()

    def tick(self, speed: float, dt: float) -> None:
        now = time.time()
        imu = self._read_imu() if self.source == "imu" else None
        if imu:
            self.ax, self.ay, self.az = imu
            self.source = "imu"
        else:
            # estimativa: longitudinal = dv/dt; lateral = v * ω
            ax = ay = 0.0
            if self._last_v is not None and dt > 0.01:
                dv = (speed - self._last_v) / 3.6  # m/s
                # ignora saltos do simulador (troca de modo) e limita a ±2,5 g
                if abs(dv) < 25 and dt < 1.5:
                    ax = max(-2.5, min(2.5, dv / dt / 9.81))
            hdg = self.store.value("gps_heading")
            if hdg is not None and self._last_hdg is not None and dt > 0.01:
                dhdg = (float(hdg) - self._last_hdg + 540) % 360 - 180
                omega = math.radians(dhdg) / dt
                v = speed / 3.6
                ay = (v * omega) / 9.81
            # suaviza um pouco
            a = 0.35
            self.ax = (1 - a) * self.ax + a * ax
            self.ay = (1 - a) * self.ay + a * ay
            self.az = 1.0
            self.source = "gps"
            if hdg is not None:
                self._last_hdg = float(hdg)
        self._last_v = speed
        self.peak_lon = max(self.peak_lon, abs(self.ax), key=lambda x: x if x != self.peak_lon else abs(self.ax))
        self.peak_lon = max(abs(self.ax), self.peak_lon)
        self.peak_lat = max(abs(self.ay), self.peak_lat)
        self.trail.append((self.ay, self.ax))
        if len(self.trail) > 180:
            self.trail = self.trail[-180:]
        self.store.update("g_lon", round(self.ax, 3), "g", self.source, "G longitudinal")
        self.store.update("g_lat", round(self.ay, 3), "g", self.source, "G lateral")
        self.store.update("g_vert", round(self.az, 3), "g", self.source, "G vertical")
        self.store.set_meta("gforce", self.snapshot())

    def snapshot(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "chip": self.chip,
            "ax": round(self.ax, 3),
            "ay": round(self.ay, 3),
            "az": round(self.az, 3),
            "peak_lon": round(self.peak_lon, 3),
            "peak_lat": round(self.peak_lat, 3),
            "trail": self.trail[-80:],
        }

    def reset_peaks(self) -> None:
        self.peak_lat = self.peak_lon = 0.0
        self.trail = []

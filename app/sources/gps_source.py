"""Fonte GPS via gpsd (módulo USB u-blox NEO-6M/7M)."""

from __future__ import annotations

import logging
import threading
import time

from ..store import DataStore
from .base import GpsSource

log = logging.getLogger(__name__)


class GpsdSource(GpsSource):
    name = "gpsd"

    def __init__(self, store: DataStore, cfg: dict) -> None:
        super().__init__(store, cfg)
        self._connected = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._session = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="gpsd", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._connected = False
        self.store.set_meta("gps_connected", False)

    @property
    def connected(self) -> bool:
        return self._connected

    def _loop(self) -> None:
        gps_cfg = self.cfg.get("gps", {})
        host = gps_cfg.get("host", "127.0.0.1")
        port = str(gps_cfg.get("port", 2947))
        while not self._stop.is_set():
            try:
                self._run_session(host, port)
            except Exception as exc:
                log.warning("gpsd desconectou: %s", exc)
                self._connected = False
                self.store.set_meta("gps_connected", False)
                if self._stop.wait(2):
                    break

    def _run_session(self, host: str, port: str) -> None:
        try:
            from gps import gps, WATCH_ENABLE, WATCH_NEWSTYLE
        except ImportError:
            # fallback: gpsd-py3
            try:
                from gpsd import connect, get_current
            except ImportError as exc:
                log.error("Instale o pacote 'gps' (python3-gps) ou gpsd-py3: %s", exc)
                self._stop.wait(10)
                return
            connect(host=host, port=int(port))
            while not self._stop.is_set():
                try:
                    pkt = get_current()
                except Exception:
                    time.sleep(0.5)
                    continue
                self._publish_gpsdpy3(pkt)
                time.sleep(0.2)
            return

        session = gps(host=host, port=port)
        session.stream(WATCH_ENABLE | WATCH_NEWSTYLE)
        self._session = session
        while not self._stop.is_set():
            try:
                report = session.next()
            except StopIteration:
                break
            if report is None:
                continue
            self._publish_libgps(report)

    def _publish_libgps(self, report) -> None:
        klass = getattr(report, "class", "")
        if klass == "TPV":
            mode = getattr(report, "mode", 0) or 0
            self._connected = mode >= 2
            self.store.set_meta("gps_connected", self._connected)
            if hasattr(report, "lat"):
                self.store.update("gps_lat", float(report.lat), "°", "gpsd", "Latitude")
            if hasattr(report, "lon"):
                self.store.update("gps_lon", float(report.lon), "°", "gpsd", "Longitude")
            if hasattr(report, "alt"):
                self.store.update("gps_alt", float(report.alt), "m", "gpsd", "Altitude")
            if hasattr(report, "speed"):
                # gpsd entrega m/s
                self.store.update("gps_speed", float(report.speed) * 3.6, "km/h", "gpsd", "Velocidade GPS")
            if hasattr(report, "track"):
                self.store.update("gps_heading", float(report.track), "°", "gpsd", "Rumo")
            self.store.update("gps_fix", mode, "", "gpsd", "Fix GPS")
        elif klass == "SKY":
            sats = 0
            satellites = getattr(report, "satellites", None) or []
            for sat in satellites:
                used = getattr(sat, "used", False)
                if used:
                    sats += 1
            if not sats and hasattr(report, "uSat"):
                sats = int(report.uSat)
            self.store.update("gps_sats", sats, "", "gpsd", "Satélites")

    def _publish_gpsdpy3(self, pkt) -> None:
        try:
            lat = pkt.lat
            lon = pkt.lon
        except Exception:
            self._connected = False
            self.store.set_meta("gps_connected", False)
            return
        self._connected = True
        self.store.set_meta("gps_connected", True)
        self.store.update("gps_lat", float(lat), "°", "gpsd", "Latitude")
        self.store.update("gps_lon", float(lon), "°", "gpsd", "Longitude")
        try:
            self.store.update("gps_alt", float(pkt.alt), "m", "gpsd", "Altitude")
        except Exception:
            pass
        try:
            hs = float(pkt.hspeed) * 3.6
            self.store.update("gps_speed", hs, "km/h", "gpsd", "Velocidade GPS")
        except Exception:
            pass
        try:
            self.store.update("gps_heading", float(pkt.track), "°", "gpsd", "Rumo")
        except Exception:
            pass
        try:
            self.store.update("gps_sats", int(pkt.sats), "", "gpsd", "Satélites")
        except Exception:
            pass

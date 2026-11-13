"""Hub que dispara fusão de velocidade, desempenho, pista, G, log, câmera, saúde, LEDs, TPMS e valet."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from . import sport_db
from .config import ROOT
from .dashcam import DashCam
from .fuse import SpeedFuse
from .gforce import GForce
from .health import CarHealth
from .leds import AmbientLeds
from .perf import PerfTimer
from .shift_alerts import ShiftAlerts
from .store import DataStore
from .telemetry import Telemetry
from .tpms import TPMS
from .trackmode import TrackTimer
from .valet import Valet

log = logging.getLogger(__name__)


class SportHub:
    def __init__(self, store: DataStore, cfg: dict, root: Path | None = None) -> None:
        self.store = store
        self.cfg = cfg
        self.root = Path(root or cfg.get("_root") or ROOT)
        db_path = (cfg.get("sport") or {}).get("db_path") or str(self.root / "data" / "sport.sqlite")
        p = Path(db_path)
        if not p.is_absolute():
            p = self.root / p
        self.conn = sport_db.connect(p)
        sport_db.init(self.conn)
        self.fuse = SpeedFuse(store)
        self.perf = PerfTimer(store, self.conn, cfg)
        self.track = TrackTimer(store, self.conn, cfg)
        self.gforce = GForce(store, cfg, self.root)
        self.telem = Telemetry(store, self.conn, cfg, self.root)
        self.dash = DashCam(store, self.conn, cfg, self.root)
        self.shift = ShiftAlerts(store, cfg)
        self.health = CarHealth(store, self.conn, cfg)
        self.leds = AmbientLeds(store, cfg)
        self.tpms = TPMS(store, cfg)
        self.valet = Valet(store, self.conn, cfg)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if cfg.get("source") == "simulator" or (cfg.get("sport") or {}).get("seed_demo", True):
            self.seed_demo()

    def seed_demo(self) -> None:
        try:
            self.perf.seed_demo()
            self.track.seed_demo()
            self.telem.seed_demo()
            self.dash.seed_demo()
            self.health.seed_demo()
        except Exception as exc:
            log.warning("Seed de demonstração falhou: %s", exc)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sport-hub", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        try:
            if self.telem.session_id:
                self.telem.stop()
            if self.dash.running:
                self.dash.stop()
            self.conn.close()
        except Exception:
            pass

    def _run(self) -> None:
        last = time.time()
        while not self._stop.wait(0.05):
            now = time.time()
            dt = min(0.25, now - last)
            last = now
            try:
                self.tick(dt)
            except Exception:
                log.exception("SportHub tick")

    def tick(self, dt: float) -> None:
        speed = self.fuse.update()
        lat = self.store.value("gps_lat")
        lon = self.store.value("gps_lon")
        self.gforce.tick(speed, dt)
        self.perf.tick(speed, dt)
        self.track.tick(lat, lon, speed, dt)
        self.telem.tick(dt)
        self.dash.tick()
        self.shift.tick()
        self.health.tick(speed, dt)
        media = self.store.get_meta("media") or {}
        level = None
        if isinstance(media, dict):
            level = media.get("level") or media.get("audio_level")
        self.leds.tick(level)
        self.tpms.tick()
        self.valet.tick(
            speed, lat, lon,
            self.store.value("g_lon") or 0.0,
            self.store.value("g_lat") or 0.0,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "perf": self.perf.snapshot(),
            "track": self.track.snapshot(),
            "gforce": self.gforce.snapshot(),
            "telemetry": self.telem.snapshot(),
            "dashcam": self.dash.status(),
            "shift": self.shift.snapshot(),
            "health": self.health.snapshot(),
            "leds": self.leds.snapshot(),
            "tpms": self.tpms.snapshot(),
            "valet": self.valet.snapshot(),
            "fuse": self.fuse.snapshot(),
        }

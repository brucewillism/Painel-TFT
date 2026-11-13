"""Registro de viagens em SQLite (GPS + OBD) e exportação GPX."""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .store import DataStore

LOG_SIGNAL_KEYS = [
    "rpm", "speed", "coolant_temp", "intake_temp", "engine_load", "throttle",
    "maf", "map", "battery_voltage", "module_voltage", "fuel_level",
    "instant_consumption", "avg_consumption", "gear", "stft_b1", "ltft_b1",
]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TripLogger:
    def __init__(self, store: DataStore, db_path: str, interval_s: float = 1.0) -> None:
        self.store = store
        self.db_path = Path(db_path)
        self.interval_s = interval_s
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._current_id: int | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _init_db(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at REAL NOT NULL,
                ended_at REAL,
                distance_km REAL DEFAULT 0,
                fuel_l REAL DEFAULT 0,
                max_speed REAL DEFAULT 0,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                ts REAL NOT NULL,
                lat REAL,
                lon REAL,
                alt REAL,
                gps_speed REAL,
                heading REAL,
                sats INTEGER,
                rpm REAL,
                speed REAL,
                coolant_temp REAL,
                intake_temp REAL,
                engine_load REAL,
                throttle REAL,
                maf REAL,
                map REAL,
                voltage REAL,
                fuel_level REAL,
                consumption REAL,
                gear INTEGER,
                payload_json TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips(id)
            );
            CREATE INDEX IF NOT EXISTS idx_samples_trip ON samples(trip_id, ts);
            """
        )
        self._conn.commit()

    def start(self, auto: bool = True) -> int | None:
        if auto:
            self.start_trip()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="trip-logger", daemon=True)
        self._thread.start()
        return self._current_id

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.end_trip()
        with self._lock:
            self._conn.close()

    def start_trip(self) -> int:
        with self._lock:
            if self._current_id is not None:
                return self._current_id
            cur = self._conn.cursor()
            cur.execute("INSERT INTO trips (started_at) VALUES (?)", (time.time(),))
            self._conn.commit()
            self._current_id = int(cur.lastrowid)
            self.store.set_meta("trip_id", self._current_id)
            return self._current_id

    def end_trip(self) -> None:
        with self._lock:
            if self._current_id is None:
                return
            distance = self.store.value("trip_distance", 0) or 0
            fuel = self.store.value("trip_fuel", 0) or 0
            max_speed = self.store.value("max_speed", 0) or 0
            self._conn.execute(
                "UPDATE trips SET ended_at=?, distance_km=?, fuel_l=?, max_speed=? WHERE id=?",
                (time.time(), distance, fuel, max_speed, self._current_id),
            )
            self._conn.commit()
            self._current_id = None
            self.store.set_meta("trip_id", None)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            try:
                self._sample()
            except Exception:
                pass

    def _sample(self) -> None:
        with self._lock:
            trip_id = self._current_id
            if trip_id is None:
                return
            s = self.store
            voltage = s.value("battery_voltage")
            if voltage is None:
                voltage = s.value("module_voltage")
            self._conn.execute(
                """
                INSERT INTO samples (
                    trip_id, ts, lat, lon, alt, gps_speed, heading, sats,
                    rpm, speed, coolant_temp, intake_temp, engine_load, throttle,
                    maf, map, voltage, fuel_level, consumption, gear
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trip_id,
                    time.time(),
                    s.value("gps_lat"),
                    s.value("gps_lon"),
                    s.value("gps_alt"),
                    s.value("gps_speed"),
                    s.value("gps_heading"),
                    s.value("gps_sats"),
                    s.value("rpm"),
                    s.value("speed"),
                    s.value("coolant_temp"),
                    s.value("intake_temp"),
                    s.value("engine_load"),
                    s.value("throttle"),
                    s.value("maf"),
                    s.value("map"),
                    voltage,
                    s.value("fuel_level"),
                    s.value("instant_consumption"),
                    s.value("gear"),
                ),
            )
            self._conn.commit()

    def list_trips(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM trips ORDER BY started_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def trip_samples(self, trip_id: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM samples WHERE trip_id=? ORDER BY ts",
                (trip_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def export_gpx(self, trip_id: int) -> str | None:
        samples = self.trip_samples(trip_id)
        pts = [s for s in samples if s.get("lat") is not None and s.get("lon") is not None]
        if not pts:
            # ainda gera um GPX vazio com metadados da viagem
            pass
        with self._lock:
            trip = self._conn.execute("SELECT * FROM trips WHERE id=?", (trip_id,)).fetchone()
        if trip is None:
            return None
        name = f"Lancer viagem {trip_id}"
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gpx version="1.1" creator="lancer-painel" xmlns="http://www.topografix.com/GPX/1/1">',
            "  <trk>",
            f"    <name>{escape(name)}</name>",
            "    <trkseg>",
        ]
        for s in pts:
            ele = f"<ele>{s['alt']:.1f}</ele>" if s.get("alt") is not None else ""
            speed = ""
            if s.get("gps_speed") is not None:
                # km/h → m/s no GPX
                speed = f"<speed>{float(s['gps_speed'])/3.6:.2f}</speed>"
            lines.append(
                f'      <trkpt lat="{s["lat"]:.7f}" lon="{s["lon"]:.7f}">'
                f"<time>{_iso(s['ts'])}</time>{ele}{speed}</trkpt>"
            )
        lines += ["    </trkseg>", "  </trk>", "</gpx>", ""]
        return "\n".join(lines)

"""SQLite compartilhado: arrancadas, voltas, telemetria, dashcam, saúde, valet."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS perf_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            started_at REAL NOT NULL,
            ended_at REAL,
            time_s REAL,
            v_start REAL,
            v_end REAL,
            distance_m REAL,
            v_max REAL,
            source TEXT,
            notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_perf_kind ON perf_runs(kind, time_s);

        CREATE TABLE IF NOT EXISTS track_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            ended_at REAL,
            name TEXT,
            gate_lat REAL, gate_lon REAL, gate_hdg REAL, gate_width_m REAL,
            best_lap_s REAL,
            laps INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS track_laps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            lap INTEGER NOT NULL,
            started_at REAL,
            time_s REAL,
            sectors_json TEXT,
            valid INTEGER DEFAULT 1,
            FOREIGN KEY (session_id) REFERENCES track_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS track_points (
            session_id INTEGER,
            ts REAL,
            lat REAL, lon REAL, speed REAL
        );

        CREATE TABLE IF NOT EXISTS telem_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            ended_at REAL,
            name TEXT,
            hz REAL,
            samples INTEGER DEFAULT 0,
            path TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS dash_clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            ended_at REAL,
            path TEXT,
            camera_id TEXT,
            duration_s REAL,
            protected INTEGER DEFAULT 0,
            reason TEXT,
            size INTEGER
        );

        CREATE TABLE IF NOT EXISTS odometer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at REAL,
            manual_km REAL,
            gps_km REAL,
            obd_km REAL,
            total_km REAL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            name TEXT,
            interval_km REAL,
            interval_days REAL,
            last_km REAL,
            last_at REAL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS dtc_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            first_seen REAL,
            last_seen REAL,
            cleared_at REAL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS battery_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            kind TEXT,
            voltage REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS valet_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at REAL NOT NULL,
            ended_at REAL,
            max_speed REAL DEFAULT 0,
            distance_km REAL DEFAULT 0,
            events INTEGER DEFAULT 0,
            report_json TEXT
        );
        CREATE TABLE IF NOT EXISTS valet_events (
            session_id INTEGER,
            ts REAL,
            kind TEXT,
            value REAL,
            lat REAL, lon REAL, speed REAL
        );
        CREATE TABLE IF NOT EXISTS valet_trail (
            session_id INTEGER,
            ts REAL, lat REAL, lon REAL, speed REAL
        );
        """
    )
    conn.commit()


def rows(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    with _lock:
        cur = conn.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

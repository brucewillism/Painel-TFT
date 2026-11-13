"""Registrador de telemetria (RPM, velocidade, acelerador, temps, G, GPS) e exportação CSV."""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from pathlib import Path
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

KEYS = ("rpm", "speed", "speed_fused", "throttle", "coolant_temp", "intake_temp",
        "cvt_temp", "g_lon", "g_lat", "g_vert", "gps_lat", "gps_lon",
        "gps_heading", "engine_load", "maf", "battery_voltage", "module_voltage")


class Telemetry:
    def __init__(self, store: DataStore, conn, cfg: dict, root: Path) -> None:
        self.store = store
        self.conn = conn
        self.cfg = cfg.get("telemetry") or {}
        self.root = root
        self.export_dir = root / "data" / "telemetry"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.session_id: int | None = None
        self.hz = float(self.cfg.get("hz", 10))
        self._acc = 0.0
        self._n = 0
        self._t0 = 0.0
        self._rows: list[dict] = []

    def start(self, hz: float | None = None, name: str | None = None) -> dict:
        if self.session_id:
            self.stop()
        self.hz = float(hz or self.hz or 10)
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO telem_sessions(started_at, name, hz, samples) VALUES (?,?,?,0)",
            (now, name or "Log", self.hz),
        )
        self.conn.commit()
        self.session_id = cur.lastrowid
        self._acc = 0.0
        self._n = 0
        self._t0 = now
        self._rows = []
        self.store.set_meta("telemetry", self.snapshot())
        return self.snapshot()

    def stop(self) -> dict:
        if not self.session_id:
            return self.snapshot()
        ended = time.time()
        path = self.export_dir / f"log-{self.session_id}.csv"
        self._write_csv(path, self._rows)
        self.conn.execute(
            "UPDATE telem_sessions SET ended_at=?, samples=?, path=? WHERE id=?",
            (ended, self._n, str(path), self.session_id),
        )
        self.conn.commit()
        sid = self.session_id
        self.session_id = None
        snap = self.snapshot()
        snap["last_id"] = sid
        snap["path"] = str(path)
        self.store.set_meta("telemetry", snap)
        return snap

    def tick(self, dt: float) -> None:
        if not self.session_id:
            return
        self._acc += dt
        period = 1.0 / max(1.0, self.hz)
        if self._acc < period:
            return
        self._acc -= period
        now = time.time()
        row = {"ts": now}
        for k in KEYS:
            rec = self.store.get(k)
            row[k] = rec.value if rec else None
        self._rows.append(row)
        self._n += 1
        if self._n % 25 == 0:
            self.store.set_meta("telemetry", self.snapshot())

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = ["ts", *KEYS]
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    def export_csv(self, sid: int) -> tuple[str, bytes]:
        row = self.conn.execute("SELECT * FROM telem_sessions WHERE id=?", (sid,)).fetchone()
        if not row:
            raise FileNotFoundError("sessão não encontrada")
        p = row["path"]
        if p and Path(p).is_file():
            return (f"log-{sid}.csv", Path(p).read_bytes())
        # sessão em andamento
        if sid == self.session_id:
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=["ts", *KEYS])
            w.writeheader()
            for r in self._rows:
                w.writerow(r)
            return (f"log-{sid}.csv", buf.getvalue().encode("utf-8"))
        raise FileNotFoundError("arquivo da sessão não encontrado")

    def session_rows(self, sid: int, limit: int = 4000) -> list[dict]:
        if sid == self.session_id:
            return self._rows[-limit:]
        row = self.conn.execute("SELECT path FROM telem_sessions WHERE id=?", (sid,)).fetchone()
        if not row or not row["path"] or not Path(row["path"]).is_file():
            return []
        out = []
        with Path(row["path"]).open(encoding="utf-8") as fh:
            for i, rec in enumerate(csv.DictReader(fh)):
                out.append(rec)
        return out[-limit:]

    def sessions(self, limit: int = 30) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM telem_sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def snapshot(self) -> dict[str, Any]:
        return {
            "running": bool(self.session_id),
            "session_id": self.session_id,
            "hz": self.hz,
            "samples": self._n,
            "elapsed_s": (time.time() - self._t0) if self.session_id else 0,
        }

    def seed_demo(self) -> None:
        n = self.conn.execute("SELECT COUNT(*) c FROM telem_sessions").fetchone()["c"]
        if n:
            return
        # gera um log curto em torno de Av. Paulista
        now = time.time()
        rows = []
        lat0, lon0 = -23.5614, -46.6558
        for i in range(240):
            t = now - 240 + i
            spd = 40 + 25 * math_sin(i / 18)
            rows.append({
                "ts": t, "rpm": 1800 + spd * 18, "speed": spd, "speed_fused": spd,
                "throttle": 20 + spd * 0.4, "coolant_temp": 88, "intake_temp": 32,
                "cvt_temp": 86, "g_lon": math_sin(i / 12) * 0.18, "g_lat": math_sin(i / 9) * 0.25,
                "g_vert": 1.0, "gps_lat": lat0 + i * 0.00004, "gps_lon": lon0 + i * 0.00003,
                "gps_heading": 45, "engine_load": 30 + spd * 0.3, "maf": 8 + spd * 0.12, "battery_voltage": 13.9, "module_voltage": 13.9,
            })
        path = self.export_dir / "log-demo.csv"
        self._write_csv(path, rows)
        self.conn.execute(
            "INSERT INTO telem_sessions(started_at, ended_at, name, hz, samples, path) VALUES (?,?,?,?,?,?)",
            (now - 240, now, "Paulista (demo)", 10, len(rows), str(path)),
        )
        self.conn.commit()


def math_sin(x: float) -> float:
    import math
    return math.sin(x)

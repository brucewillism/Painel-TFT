"""Modo circuito: cronômetro de volta, setores, delta e traçado."""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)


def _gate_sides(lat: float, lon: float, gate_lat: float, gate_lon: float, hdg: float) -> float:
    """Produto cruzado 2D: sinal diz de que lado da linha o ponto está."""
    # linha perpendicular ao heading (portão de chegada)
    rad = math.radians(hdg)
    # direção da linha (perpendicular): heading + 90
    lx, ly = math.sin(rad + math.pi / 2), math.cos(rad + math.pi / 2)
    # vetor do centro do portão ao ponto, em metros approx
    dx = (lon - gate_lon) * 111320 * math.cos(math.radians(gate_lat))
    dy = (lat - gate_lat) * 110540
    return dx * ly - dy * lx  # not really cross with lx,ly...
    # cross of line dir (lx,ly) and point (dx,dy) = lx*dy - ly*dx


def side_of_gate(lat, lon, gate_lat, gate_lon, hdg) -> float:
    rad = math.radians(hdg)
    lx, ly = math.sin(rad + math.pi / 2), math.cos(rad + math.pi / 2)
    dx = (lon - gate_lon) * 111320 * math.cos(math.radians(gate_lat))
    dy = (lat - gate_lat) * 110540
    return lx * dy - ly * dx


def dist_m(lat1, lon1, lat2, lon2) -> float:
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians(lat1))
    dy = (lat2 - lat1) * 110540
    return math.hypot(dx, dy)


class TrackTimer:
    def __init__(self, store: DataStore, conn, cfg: dict) -> None:
        self.store = store
        self.conn = conn
        self.cfg = cfg.get("track") or {}
        self.session_id: int | None = None
        self.gate: dict[str, float] | None = None
        self.sectors: list[dict] = []  # extra gates
        self.lap = 0
        self.lap_t0: float | None = None
        self.best_s: float | None = None
        self.best_profile: list[tuple[float, float]] = []  # (dist, t)
        self.cur_dist = 0.0
        self.cur_profile: list[tuple[float, float]] = []
        self.last_lap: dict | None = None
        self._last_side: float | None = None
        self._last_pt: tuple[float, float, float] | None = None  # lat,lon,t
        self._trace: list[dict] = []
        self._sector_idx = 0
        self._sector_t0 = 0.0
        self._sectors_cur: list[float] = []

    def set_gate(self, lat: float, lon: float, hdg: float | None = None, width_m: float = 18.0) -> dict:
        heading = hdg if hdg is not None else float(self.store.value("gps_heading") or 0)
        self.gate = {"lat": float(lat), "lon": float(lon), "hdg": float(heading), "width_m": float(width_m)}
        return self.gate

    def set_gate_here(self) -> dict | None:
        lat, lon = self.store.value("gps_lat"), self.store.value("gps_lon")
        if lat is None or lon is None:
            return None
        return self.set_gate(float(lat), float(lon), float(self.store.value("gps_heading") or 0))

    def start_session(self, name: str | None = None) -> dict:
        if not self.gate:
            self.set_gate_here()
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO track_sessions(started_at, name, gate_lat, gate_lon, gate_hdg, gate_width_m) "
            "VALUES (?,?,?,?,?,?)",
            (now, name or "Sessão", *( [self.gate[k] for k in ("lat","lon","hdg","width_m")] if self.gate else (None,)*4 )),
        )
        self.conn.commit()
        self.session_id = cur.lastrowid
        self.lap = 0
        self.lap_t0 = None
        self.cur_dist = 0.0
        self.cur_profile = []
        self._trace = []
        self._last_side = None
        self.last_lap = None
        # carrega melhor perfil da sessão anterior no mesmo portão? simples: best da sessão
        self.best_s = None
        self.best_profile = []
        return self.snapshot()

    def stop_session(self) -> dict:
        if self.session_id:
            self.conn.execute(
                "UPDATE track_sessions SET ended_at=?, best_lap_s=?, laps=? WHERE id=?",
                (time.time(), self.best_s, self.lap, self.session_id),
            )
            self.conn.commit()
        snap = self.snapshot()
        self.session_id = None
        self.lap_t0 = None
        return snap

    def tick(self, lat, lon, speed, dt) -> None:
        if not self.session_id or not self.gate or lat is None or lon is None:
            self.store.set_meta("track", self.snapshot())
            return
        now = time.time()
        # distância ao portão para rejeitar cruzamentos longe
        dgate = dist_m(lat, lon, self.gate["lat"], self.gate["lon"])
        side = side_of_gate(lat, lon, self.gate["lat"], self.gate["lon"], self.gate["hdg"])
        crossed = (
            self._last_side is not None
            and side * self._last_side < 0
            and dgate <= self.gate["width_m"] * 1.4
        )
        if self._last_pt:
            self.cur_dist += dist_m(self._last_pt[0], self._last_pt[1], lat, lon)
        if self.lap_t0:
            self.cur_profile.append((self.cur_dist, now - self.lap_t0))
            self._trace.append({"lat": lat, "lon": lon, "speed": speed, "t": now - self.lap_t0})
            if len(self._trace) > 4000:
                self._trace = self._trace[-4000:]
            self.conn.execute(
                "INSERT INTO track_points(session_id, ts, lat, lon, speed) VALUES (?,?,?,?,?)",
                (self.session_id, now, lat, lon, speed),
            )
        if crossed:
            self._on_crossing(now)
        self._last_side = side
        self._last_pt = (lat, lon, now)
        self.store.set_meta("track", self.snapshot())

    def _on_crossing(self, now: float) -> None:
        if self.lap_t0 is None:
            # primeira passagem: começa a volta 1
            self.lap_t0 = now
            self.lap = 1
            self.cur_dist = 0.0
            self.cur_profile = [(0.0, 0.0)]
            self._sectors_cur = []
            return
        time_s = now - self.lap_t0
        if time_s < 5:  # debounce
            return
        valid = time_s > 8
        self.conn.execute(
            "INSERT INTO track_laps(session_id, lap, started_at, time_s, sectors_json, valid) VALUES (?,?,?,?,?,?)",
            (self.session_id, self.lap, self.lap_t0, time_s, json.dumps(self._sectors_cur), int(valid)),
        )
        self.conn.commit()
        self.last_lap = {"lap": self.lap, "time_s": time_s, "valid": valid}
        if valid and (self.best_s is None or time_s < self.best_s):
            self.best_s = time_s
            self.best_profile = list(self.cur_profile)
        self.lap += 1
        self.lap_t0 = now
        self.cur_dist = 0.0
        self.cur_profile = [(0.0, 0.0)]
        self._sectors_cur = []
        log.info("Volta %s: %.3f s (best=%.3f)", self.lap - 1, time_s, self.best_s or 0)

    def delta(self) -> float | None:
        """Delta vs melhor volta na mesma distância percorrida."""
        if not self.lap_t0 or not self.best_profile:
            return None
        t = time.time() - self.lap_t0
        # interpola t_best em cur_dist
        prof = self.best_profile
        d = self.cur_dist
        if d <= 0 or not prof:
            return None
        for i in range(1, len(prof)):
            if prof[i][0] >= d:
                d0, t0 = prof[i - 1]
                d1, t1 = prof[i]
                if d1 == d0:
                    tb = t1
                else:
                    tb = t0 + (t1 - t0) * (d - d0) / (d1 - d0)
                return t - tb
        return t - prof[-1][1]

    def snapshot(self) -> dict[str, Any]:
        elapsed = (time.time() - self.lap_t0) if self.lap_t0 else None
        return {
            "session_id": self.session_id,
            "gate": self.gate,
            "lap": self.lap if self.lap_t0 else 0,
            "elapsed_s": elapsed,
            "best_s": self.best_s,
            "delta_s": self.delta(),
            "distance_m": self.cur_dist,
            "last_lap": self.last_lap,
            "trace": self._trace[-400:] or self._last_session_trace(),
            "running": bool(self.session_id),
        }

    def _last_session_trace(self, limit: int = 400) -> list[dict]:
        row = self.conn.execute("SELECT id FROM track_sessions ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            return []
        cur = self.conn.execute(
            "SELECT lat, lon, speed, ts as t FROM track_points WHERE session_id=? ORDER BY ts LIMIT ?",
            (row["id"], limit),
        )
        return [dict(r) for r in cur.fetchall()]

    def sessions(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM track_sessions ORDER BY started_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def session_laps(self, sid: int) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM track_laps WHERE session_id=? ORDER BY lap", (sid,))
        return [dict(r) for r in cur.fetchall()]

    def seed_demo(self) -> None:
        n = self.conn.execute("SELECT COUNT(*) c FROM track_sessions").fetchone()["c"]
        if n:
            return
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO track_sessions(started_at, ended_at, name, gate_lat, gate_lon, gate_hdg, gate_width_m, best_lap_s, laps) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (now - 3600, now - 3000, "Interlagos (demo)", -23.701, -46.697, 90, 18, 92.41, 4),
        )
        sid = cur.lastrowid
        for i, t in enumerate((94.12, 93.05, 92.41, 92.88), 1):
            self.conn.execute(
                "INSERT INTO track_laps(session_id, lap, started_at, time_s, valid) VALUES (?,?,?,?,1)",
                (sid, i, now - 3600 + i * 100, t),
            )
        import math
        for i in range(180):
            ang = i / 180 * 2 * math.pi
            lat = -23.701 + 0.0018 * math.sin(ang)
            lon = -46.697 + 0.0024 * math.cos(ang)
            self.conn.execute(
                "INSERT INTO track_points(session_id, ts, lat, lon, speed) VALUES (?,?,?,?,?)",
                (sid, now - 3500 + i, lat, lon, 90 + 10 * math.sin(ang * 2)),
            )
        self.conn.commit()

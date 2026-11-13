"""Modo valet: PIN, restrição de telas, log de velocidade/rota/eventos e relatório."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

RESTRICTED = {"media", "phone", "carplay", "radio", "settings", "companion"}


class Valet:
    def __init__(self, store: DataStore, conn, cfg: dict) -> None:
        self.store = store
        self.conn = conn
        self.cfg = cfg.get("valet") or {}
        pin = str(self.cfg.get("pin") or "1234")
        self.pin_hash = _hash(pin)
        self.active = False
        self.session_id: int | None = None
        self.max_speed = 0.0
        self._trail: list[dict] = []
        self._last_pt_t = 0.0
        self._g_evt_at = 0.0
        self.last_report: dict | None = None
        self.harsh_g = float(self.cfg.get("harsh_g", 0.55))

    def is_locked(self) -> bool:
        return self.active

    def locked_pages(self) -> list[str]:
        return list(RESTRICTED) if self.active else []

    def lock(self, pin: str | None = None) -> dict:
        # Trava sem PIN (uso típico do valet). O PIN só é exigido para destravar.
        if pin and not _ok(pin, self.pin_hash):
            return {"ok": False, "error": "PIN inválido"}
        if self.active:
            return {"ok": True, **self.snapshot()}
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO valet_sessions(started_at, max_speed, distance_km, events) VALUES (?,?,0,0)",
            (now, 0),
        )
        self.conn.commit()
        self.session_id = cur.lastrowid
        self.active = True
        self.max_speed = 0.0
        self._trail = []
        self.last_report = None
        self.store.set_meta("valet", self.snapshot())
        return {"ok": True, **self.snapshot()}

    def unlock(self, pin: str) -> dict:
        if not _ok(pin, self.pin_hash):
            return {"ok": False, "error": "PIN inválido"}
        report = self._close()
        self.active = False
        self.last_report = report
        self.store.set_meta("valet", self.snapshot())
        return {"ok": True, "report": report, **self.snapshot()}

    def change_pin(self, old: str, new: str) -> dict:
        if not _ok(old, self.pin_hash):
            return {"ok": False, "error": "PIN atual inválido"}
        if not (new and 4 <= len(str(new)) <= 8 and str(new).isdigit()):
            return {"ok": False, "error": "novo PIN deve ter 4 a 8 dígitos"}
        self.pin_hash = _hash(str(new))
        return {"ok": True}

    def tick(self, speed: float, lat, lon, g_lon, g_lat) -> None:
        if not self.active or not self.session_id:
            self.store.set_meta("valet", self.snapshot())
            return
        now = time.time()
        if speed > self.max_speed:
            self.max_speed = speed
            self.conn.execute("UPDATE valet_sessions SET max_speed=? WHERE id=?", (self.max_speed, self.session_id))
        if lat is not None and lon is not None and now - self._last_pt_t >= 2.0:
            self._trail.append({"t": now, "lat": lat, "lon": lon, "speed": speed})
            self.conn.execute(
                "INSERT INTO valet_trail(session_id, ts, lat, lon, speed) VALUES (?,?,?,?,?)",
                (self.session_id, now, lat, lon, speed),
            )
            self._last_pt_t = now
        g = ((g_lon or 0) ** 2 + (g_lat or 0) ** 2) ** 0.5
        if g >= self.harsh_g and now - self._g_evt_at > 3:
            self._g_evt_at = now
            kind = "aceleração" if abs(g_lon or 0) >= abs(g_lat or 0) and (g_lon or 0) > 0 else (
                "frenagem" if (g_lon or 0) < 0 else "curva")
            self.conn.execute(
                "INSERT INTO valet_events(session_id, ts, kind, value, lat, lon) VALUES (?,?,?,?,?,?)",
                (self.session_id, now, kind, g, lat, lon),
            )
            self.conn.execute(
                "UPDATE valet_sessions SET events=events+1 WHERE id=?", (self.session_id,)
            )
        self.conn.commit()
        self.store.set_meta("valet", self.snapshot())

    def _close(self) -> dict:
        if not self.session_id:
            return {}
        now = time.time()
        dist = 0.0
        for a, b in zip(self._trail, self._trail[1:]):
            dist += _haversine(a["lat"], a["lon"], b["lat"], b["lon"])
        ev = [dict(r) for r in self.conn.execute(
            "SELECT * FROM valet_events WHERE session_id=? ORDER BY ts", (self.session_id,)
        ).fetchall()]
        row = self.conn.execute("SELECT started_at FROM valet_sessions WHERE id=?", (self.session_id,)).fetchone()
        started = row["started_at"] if row else now
        self.conn.execute(
            "UPDATE valet_sessions SET ended_at=?, max_speed=?, distance_km=?, events=? WHERE id=?",
            (now, self.max_speed, dist, len(ev), self.session_id),
        )
        self.conn.commit()
        report = {
            "session_id": self.session_id,
            "started_at": started,
            "ended_at": now,
            "duration_s": now - started,
            "max_speed": round(self.max_speed, 1),
            "distance_km": round(dist, 2),
            "events": ev,
            "event_count": len(ev),
            "trail": self._trail[-400:],
        }
        self.session_id = None
        self._trail = []
        return report

    def snapshot(self) -> dict[str, Any]:
        ev_n = 0
        if self.session_id:
            row = self.conn.execute("SELECT events FROM valet_sessions WHERE id=?", (self.session_id,)).fetchone()
            ev_n = (row["events"] if row else 0) or 0
        return {
            "active": self.active,
            "restricted": self.locked_pages(),
            "max_speed": round(self.max_speed, 1) if self.active else None,
            "events": ev_n if self.active else 0,
            "session_id": self.session_id,
            "last_report": self.last_report,
        }


def _hash(pin: str) -> str:
    return hashlib.sha256(("lancer-valet:" + pin).encode()).hexdigest()


def _ok(pin: str, hashed: str) -> bool:
    return _hash(str(pin or "")) == hashed


def _haversine(lat1, lon1, lat2, lon2) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))

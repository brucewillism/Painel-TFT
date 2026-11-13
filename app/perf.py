"""Cronômetro de desempenho: 0–100, 80–120, 402 m e 100–0, com auto start/stop."""

from __future__ import annotations

import logging
import time
from typing import Any

from . import sport_db
from .store import DataStore

log = logging.getLogger(__name__)

KINDS = ("0-100", "80-120", "402m", "100-0")


class PerfTimer:
    def __init__(self, store: DataStore, conn, cfg: dict) -> None:
        self.store = store
        self.conn = conn
        self.cfg = cfg.get("perf") or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.runs: dict[str, dict[str, Any]] = {k: self._idle(k) for k in KINDS}
        self._last_v = 0.0
        self._low_since: float | None = None
        self._was_over_100 = False
        self._mono: float | None = None

    def _idle(self, kind: str) -> dict[str, Any]:
        return {"kind": kind, "state": "idle", "t0": None, "time_s": None,
                "dist_m": 0.0, "v_start": None, "v_max": 0.0}

    def tick(self, speed: float, dt: float) -> None:
        if not self.enabled or dt <= 0:
            self._last_v = speed
            return
        if self._mono is None:
            self._mono = time.time()
        else:
            self._mono += dt
        now = self._mono
        # 0-100 e 402 m compartilham a largada parado.
        if speed < 2.0:
            if self._low_since is None:
                self._low_since = now
        else:
            self._low_since = None

        armed_long = self._low_since is not None and (now - self._low_since) >= 0.25

        r = self.runs["0-100"]
        if r["state"] in {"idle", "armed"} and armed_long:
            r["state"] = "armed"
        if r["state"] == "armed" and speed >= 2.5:
            self._start(r, now, speed)
        if r["state"] == "running":
            self._update(r, now, speed, dt)
            if speed >= 100.0:
                self._finish(r, now, speed)

        q = self.runs["402m"]
        if q["state"] in {"idle", "armed"} and armed_long:
            q["state"] = "armed"
        if q["state"] == "armed" and speed >= 2.5:
            self._start(q, now, speed)
        if q["state"] == "running":
            self._update(q, now, speed, dt)
            if q["dist_m"] >= 402.0:
                self._finish(q, now, speed)
            elif speed < 2.0:
                q.update(self._idle("402m"))

        s = self.runs["80-120"]
        if s["state"] in {"idle", "armed"} and 74.0 <= speed < 80.0 and speed >= self._last_v:
            s["state"] = "armed"
        if s["state"] == "armed" and speed >= 80.0:
            self._start(s, now, speed)
        if s["state"] == "running":
            self._update(s, now, speed, dt)
            if speed >= 120.0:
                self._finish(s, now, speed)
            elif speed < 70.0:
                s.update(self._idle("80-120"))

        b = self.runs["100-0"]
        if speed >= 100.0:
            self._was_over_100 = True
            if b["state"] in {"idle", "armed"}:
                b["state"] = "armed"
        if b["state"] == "armed" and self._was_over_100 and speed < 100.0 and speed < self._last_v:
            self._start(b, now, 100.0)
        if b["state"] == "running":
            self._update(b, now, speed, dt)
            if speed <= 2.0:
                self._finish(b, now, speed)
            elif speed > 105.0:
                b.update(self._idle("100-0"))
                self._was_over_100 = True
        if speed < 2.0:
            self._was_over_100 = False

        self._last_v = speed
        self.store.set_meta("perf", self.snapshot())

    def _start(self, r: dict, now: float, speed: float) -> None:
        r["state"] = "running"
        r["t0"] = now
        r["time_s"] = 0.0
        r["dist_m"] = 0.0
        r["v_start"] = speed
        r["v_max"] = speed

    def _update(self, r: dict, now: float, speed: float, dt: float) -> None:
        r["time_s"] = now - r["t0"]
        r["dist_m"] += max(0.0, speed) / 3.6 * dt
        r["v_max"] = max(r["v_max"], speed)

    def _finish(self, r: dict, now: float, speed: float) -> None:
        r["state"] = "done"
        r["time_s"] = now - r["t0"]
        self.conn.execute(
            "INSERT INTO perf_runs(kind, started_at, ended_at, time_s, v_start, v_end, distance_m, v_max, source) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (r["kind"], r["t0"], now, r["time_s"], r["v_start"], speed, r["dist_m"], r["v_max"],
             self.store.get_meta("source") or "fused"),
        )
        self.conn.commit()
        log.info("Perf %s: %.3f s (vmax=%.1f)", r["kind"], r["time_s"], r["v_max"])
        # re-arma para a próxima
        # mantém "done" visível até a próxima largada (0-100 recomeça quando parar)

    def reset(self, kind: str | None = None) -> None:
        kinds = [kind] if kind in KINDS else KINDS
        for k in kinds:
            self.runs[k] = self._idle(k)
        self.store.set_meta("perf", self.snapshot())

    def snapshot(self) -> dict[str, Any]:
        best = {}
        for k in KINDS:
            row = self.conn.execute(
                "SELECT time_s, started_at, v_max FROM perf_runs WHERE kind=? AND time_s IS NOT NULL "
                "ORDER BY time_s ASC LIMIT 1", (k,),
            ).fetchone()
            best[k] = dict(row) if row else None
        return {"enabled": self.enabled, "runs": {k: dict(v) for k, v in self.runs.items()}, "best": best}

    def clear_history(self, kind: str | None = None) -> None:
        if kind in KINDS:
            self.conn.execute("DELETE FROM perf_runs WHERE kind=?", (kind,))
        else:
            self.conn.execute("DELETE FROM perf_runs")
        self.conn.commit()
        self.store.set_meta("perf", self.snapshot())

    def history(self, kind: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if kind:
            return sport_db.rows(self.conn,
                "SELECT * FROM perf_runs WHERE kind=? ORDER BY started_at DESC LIMIT ?", (kind, limit))
        return sport_db.rows(self.conn, "SELECT * FROM perf_runs ORDER BY started_at DESC LIMIT ?", (limit,))

    def seed_demo(self) -> None:
        """Melhores de demonstração no simulador, se a tabela estiver vazia."""
        n = self.conn.execute("SELECT COUNT(*) c FROM perf_runs").fetchone()["c"]
        if n:
            return
        now = time.time()
        demo = [("0-100", 10.84, 0, 100, 165, 101),
                ("0-100", 11.21, 0, 100, 172, 103),
                ("80-120", 7.62, 80, 120, 195, 121),
                ("402m", 17.95, 0, 118, 402, 118),
                ("100-0", 3.42, 100, 0, 48, 101)]
        for i, (k, t, vs, ve, d, vm) in enumerate(demo):
            self.conn.execute(
                "INSERT INTO perf_runs(kind, started_at, ended_at, time_s, v_start, v_end, distance_m, v_max, source, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (k, now - 86400 * (i + 1), now - 86400 * (i + 1) + t, t, vs, ve, d, vm, "demo", "melhor de demo"),
            )
        self.conn.commit()

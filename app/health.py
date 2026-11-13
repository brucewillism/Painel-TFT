"""Saúde do carro: manutenção por km/tempo, hodômetro, histórico de DTC e bateria."""

from __future__ import annotations

import logging
import time
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

# Intervalos padrão Lancer 2016 (aprox. manual BR; conferir no manual)
DEFAULT_ITEMS = [
    {"id": "oil", "name": "Óleo do motor", "interval_km": 10000, "interval_days": 365},
    {"id": "cvt", "name": "Fluido do CVT", "interval_km": 40000, "interval_days": 730},
    {"id": "engine_filter", "name": "Filtro de óleo/ar", "interval_km": 10000, "interval_days": 365},
    {"id": "cabin_filter", "name": "Filtro de cabine", "interval_km": 15000, "interval_days": 365},
    {"id": "tires", "name": "Rodízio/pneus", "interval_km": 10000, "interval_days": 180},
    {"id": "brake_fluid", "name": "Fluido de freio", "interval_km": 40000, "interval_days": 730},
    {"id": "spark", "name": "Velas", "interval_km": 40000, "interval_days": 730},
]


class CarHealth:
    def __init__(self, store: DataStore, conn, cfg: dict) -> None:
        self.store = store
        self.conn = conn
        self.cfg = cfg.get("health") or {}
        self._last_v = None
        self._trip_km = 0.0
        self._crank_armed = True
        self._crank_min = None
        self._engine_was_off = True
        self._ensure_odo()
        self._ensure_items()

    def _ensure_odo(self) -> None:
        row = self.conn.execute("SELECT * FROM odometer ORDER BY id DESC LIMIT 1").fetchone()
        if row:
            return
        self.conn.execute(
            "INSERT INTO odometer(updated_at, manual_km, gps_km, obd_km, total_km, notes) VALUES (?,?,?,?,?,?)",
            (time.time(), 87540.0, 0.0, 0.0, 87540.0, "hodômetro inicial (ajuste em Saúde)"),
        )
        self.conn.commit()

    def _ensure_items(self) -> None:
        n = self.conn.execute("SELECT COUNT(*) c FROM maintenance").fetchone()["c"]
        if n:
            return
        now = time.time()
        # último serviço fictício há alguns milhares de km
        odo = self.odometer()["total_km"]
        items = (self.cfg.get("health") or {}).get("items") or (
            (self.cfg.get("_profile") or {}).get("maintenance")
        ) or DEFAULT_ITEMS
        for it in items:
            last = odo - it["interval_km"] * 0.72
            self.conn.execute(
                "INSERT INTO maintenance(item_id, name, interval_km, interval_days, last_km, last_at, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (it["id"], it["name"], it["interval_km"], it["interval_days"], last, now - it["interval_days"] * 86400 * 0.6, "demo"),
            )
        self.conn.commit()

    def odometer(self) -> dict:
        row = self.conn.execute("SELECT * FROM odometer ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else {"total_km": 0, "manual_km": 0, "gps_km": 0, "obd_km": 0}

    def set_odometer(self, km: float) -> dict:
        cur = self.odometer()
        self.conn.execute(
            "INSERT INTO odometer(updated_at, manual_km, gps_km, obd_km, total_km, notes) VALUES (?,?,?,?,?,?)",
            (time.time(), float(km), cur.get("gps_km") or 0, cur.get("obd_km") or 0, float(km), "ajuste manual"),
        )
        self.conn.commit()
        return self.snapshot()

    def tick(self, speed: float, dt: float) -> None:
        # acumula km
        if dt > 0 and speed > 0.5:
            dkm = speed / 3600.0 * dt
            self._trip_km += dkm
            if self._trip_km >= 0.2:
                self._add_distance(self._trip_km, source="fused")
                self._trip_km = 0.0
        # DTC → histórico
        dtcs = self.store.get_meta("dtcs") or []
        if isinstance(dtcs, list):
            for code in dtcs:
                self._log_dtc(str(code))
        # bateria: queda na partida
        self._battery_tick()
        self.store.set_meta("health", self.snapshot())

    def _add_distance(self, dkm: float, source: str) -> None:
        cur = self.odometer()
        gps = (cur.get("gps_km") or 0) + (dkm if source in {"gps", "fused"} else 0)
        obd = (cur.get("obd_km") or 0) + (dkm if source in {"obd", "fused"} else 0)
        total = (cur.get("total_km") or 0) + dkm
        self.conn.execute(
            "UPDATE odometer SET gps_km=?, obd_km=?, total_km=?, updated_at=? WHERE id=?",
            (gps, obd, total, time.time(), cur["id"]),
        )
        self.conn.commit()

    def _log_dtc(self, code: str) -> None:
        if not code:
            return
        row = self.conn.execute(
            "SELECT id FROM dtc_history WHERE code=? AND cleared_at IS NULL ORDER BY first_seen DESC LIMIT 1",
            (code,),
        ).fetchone()
        now = time.time()
        if row:
            self.conn.execute("UPDATE dtc_history SET last_seen=? WHERE id=?", (now, row["id"]))
        else:
            self.conn.execute(
                "INSERT INTO dtc_history(code, first_seen, last_seen) VALUES (?,?,?)",
                (code, now, now),
            )
        self.conn.commit()

    def clear_dtc_history(self, code: str | None = None) -> None:
        now = time.time()
        if code:
            self.conn.execute("UPDATE dtc_history SET cleared_at=? WHERE code=? AND cleared_at IS NULL", (now, code))
        else:
            self.conn.execute("UPDATE dtc_history SET cleared_at=? WHERE cleared_at IS NULL", (now,))
        self.conn.commit()

    def _battery_tick(self) -> None:
        v = self.store.value("battery_voltage")
        if v is None:
            v = self.store.value("module_voltage")
        rpm = self.store.value("rpm") or 0
        if v is None:
            return
        v = float(v)
        now = time.time()
        # partida: RPM sai de ~0 e tensão cai
        if rpm < 200:
            self._engine_was_off = True
            self._crank_armed = True
            self._crank_min = v if self._crank_min is None else min(self._crank_min, v)
        if self._engine_was_off and self._crank_armed and rpm >= 400:
            dip = self._crank_min if self._crank_min is not None else v
            self.conn.execute(
                "INSERT INTO battery_events(ts, kind, voltage, notes) VALUES (?,?,?,?)",
                (now, "crank", dip, "queda na partida"),
            )
            self.conn.commit()
            self._crank_armed = False
            self._engine_was_off = False
            self._crank_min = None
        # tendência em repouso (motor off, minutos)
        if rpm < 100 and now % 30 < 0.6:
            self.conn.execute(
                "INSERT INTO battery_events(ts, kind, voltage, notes) VALUES (?,?,?,?)",
                (now, "rest", v, "repouso"),
            )
            self.conn.commit()

    def mark_service(self, item_id: str, km: float | None = None) -> dict:
        odo = self.odometer()["total_km"]
        at = km if km is not None else odo
        self.conn.execute(
            "UPDATE maintenance SET last_km=?, last_at=? WHERE item_id=?",
            (at, time.time(), item_id),
        )
        self.conn.commit()
        return self.snapshot()

    def items(self) -> list[dict]:
        odo = self.odometer()["total_km"] or 0
        now = time.time()
        out = []
        for r in self.conn.execute("SELECT * FROM maintenance").fetchall():
            d = dict(r)
            next_km = (d["last_km"] or 0) + (d["interval_km"] or 0)
            due_km = next_km - odo
            due_days = None
            if d.get("interval_days") and d.get("last_at"):
                due_days = ((d["last_at"] + d["interval_days"] * 86400) - now) / 86400
            status = "ok"
            if (due_km is not None and due_km <= 0) or (due_days is not None and due_days <= 0):
                status = "overdue"
            elif (due_km is not None and due_km <= 1000) or (due_days is not None and due_days <= 30):
                status = "soon"
            d.update({"odo": odo, "next_km": next_km, "due_km": round(due_km, 1),
                      "due_days": None if due_days is None else round(due_days, 1), "status": status})
            out.append(d)
        order = {"overdue": 0, "soon": 1, "ok": 2}
        out.sort(key=lambda d: (order.get(d["status"], 9), d.get("due_km") or 0))
        return out

    def battery(self) -> dict:
        events = [dict(r) for r in self.conn.execute(
            "SELECT * FROM battery_events ORDER BY ts DESC LIMIT 80"
        ).fetchall()]
        cranks = [e for e in events if e["kind"] == "crank"]
        rests = [e for e in events if e["kind"] == "rest"]
        last_crank = cranks[0]["voltage"] if cranks else None
        last_rest = rests[0]["voltage"] if rests else None
        warn = None
        if last_crank is not None and last_crank < 10.0:
            warn = "queda alta na partida — bateria/terminais"
        elif last_rest is not None and last_rest < 12.2:
            warn = "tensão de repouso baixa — recarregar/substituir"
        # tendência: últimos 5 repousos
        trend = "estável"
        if len(rests) >= 4:
            recent = [e["voltage"] for e in rests[:4]]
            if recent[0] < recent[-1] - 0.15:
                trend = "caindo"
        return {
            "last_crank": last_crank,
            "last_rest": last_rest,
            "warning": warn,
            "trend": trend,
            "events": events[:20],
        }

    def dtc_history(self, limit: int = 40) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM dtc_history ORDER BY last_seen DESC LIMIT ?", (limit,)
        ).fetchall()]

    def snapshot(self) -> dict[str, Any]:
        items = self.items()
        due = sum(1 for i in items if i["status"] != "ok")
        batt = self.battery()
        return {
            "odometer": self.odometer(),
            "items": items,
            "due_count": due,
            "battery": {k: batt[k] for k in ("last_crank", "last_rest", "warning", "trend")},
            "open_dtcs": self.dtc_history(10),
        }

    def seed_demo(self) -> None:
        n = self.conn.execute("SELECT COUNT(*) c FROM battery_events").fetchone()["c"]
        if n:
            return
        now = time.time()
        # tendência de repouso levemente a cair, partida típica
        for i in range(8):
            self.conn.execute(
                "INSERT INTO battery_events(ts, kind, voltage, notes) VALUES (?,?,?,?)",
                (now - (8 - i) * 86400, "rest", 12.62 - i * 0.03, "repouso demo"),
            )
        self.conn.execute(
            "INSERT INTO battery_events(ts, kind, voltage, notes) VALUES (?,?,?,?)",
            (now - 3600, "crank", 10.8, "partida demo"),
        )
        # um DTC antigo já apagado
        self.conn.execute(
            "INSERT INTO dtc_history(code, first_seen, last_seen, cleared_at, description) VALUES (?,?,?,?,?)",
            ("P0420", now - 20 * 86400, now - 15 * 86400, now - 14 * 86400, "catalisador (histórico)"),
        )
        self.conn.commit()

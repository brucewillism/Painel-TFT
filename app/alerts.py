"""Alertas: temperatura alta, tensão baixa/alta e RPM alto."""

from __future__ import annotations

import time
from typing import Any

from .store import DataStore


def evaluate(store: DataStore, cfg: dict) -> list[dict[str, Any]]:
    limits = cfg.get("alerts", {})
    alerts: list[dict[str, Any]] = []
    now = time.time()

    coolant = store.value("coolant_temp")
    limit_c = float(limits.get("coolant_temp_c", 105))
    if coolant is not None and float(coolant) >= limit_c:
        alerts.append({
            "id": "coolant_high",
            "level": "critical",
            "title": "Temperatura alta",
            "message": f"Motor a {float(coolant):.0f} °C (limite {limit_c:.0f} °C)",
            "ts": now,
        })

    voltage = store.value("battery_voltage")
    if voltage is None:
        voltage = store.value("module_voltage")
    if voltage is not None:
        low = float(limits.get("voltage_low_v", 11.8))
        high = float(limits.get("voltage_high_v", 15.2))
        v = float(voltage)
        if v <= low:
            alerts.append({
                "id": "voltage_low",
                "level": "critical",
                "title": "Bateria baixa",
                "message": f"{v:.1f} V (mínimo {low:.1f} V)",
                "ts": now,
            })
        elif v >= high:
            alerts.append({
                "id": "voltage_high",
                "level": "warn",
                "title": "Tensão alta",
                "message": f"{v:.1f} V (máximo {high:.1f} V)",
                "ts": now,
            })

    rpm = store.value("rpm")
    rpm_lim = float(limits.get("rpm_high", 6200))
    if rpm is not None and float(rpm) >= rpm_lim:
        alerts.append({
            "id": "rpm_high",
            "level": "warn",
            "title": "RPM alto",
            "message": f"{float(rpm):.0f} rpm (limite {rpm_lim:.0f})",
            "ts": now,
        })

    cvt = store.value("cvt_temp")
    if cvt is not None:
        lim = float(limits.get("cvt_temp_c", 120))
        if float(cvt) >= lim:
            alerts.append({
                "id": "cvt_temp_high",
                "level": "critical",
                "title": "Fluido da CVT quente",
                "message": f"CVT a {float(cvt):.0f} °C (limite {lim:.0f} °C)",
                "ts": now,
            })

    # autonomia baixa: sugere o posto alcançável mais perto
    reach = store.value("fuel_range_km")
    range_lim = float(limits.get("range_km", 40))
    if reach is not None and float(reach) <= range_lim:
        station = store.get_meta("nearest_station") or {}
        if station.get("name"):
            eta = station.get("eta_min")
            extra = f"{station['name']}"
            if station.get("distance_km") is not None:
                extra += f" a {station['distance_km']:.1f} km"
            if eta is not None:
                extra += f", {eta} min"
            if station.get("badge") == "reachable":
                msg = f"Autonomia {float(reach):.0f} km. Posto mais perto ao alcance: {extra}."
            elif station.get("badge") == "at-risk":
                msg = f"Autonomia {float(reach):.0f} km. {extra} — chegada no limite."
            else:
                msg = f"Autonomia {float(reach):.0f} km. Verifique os postos no mapa."
        else:
            msg = f"Autonomia estimada {float(reach):.0f} km. Abra o mapa de postos."
        alerts.append({
            "id": "range_low",
            "level": "warn",
            "title": "Combustível no limite",
            "message": msg,
            "ts": now,
        })

    if store.get_meta("mil"):
        dtcs = store.get_meta("dtcs") or []
        alerts.append({
            "id": "mil",
            "level": "warn",
            "title": "Luz de injeção",
            "message": f"{len(dtcs)} código(s) de falha armazenado(s)",
            "ts": now,
        })

    store.set_meta("alerts", alerts)
    return alerts

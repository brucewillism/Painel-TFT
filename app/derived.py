"""Valores derivados: consumo, relação da CVT (ou marcha manual) e distância."""

from __future__ import annotations

import math
import time
from typing import Any

from .store import DataStore

# Lancer 2.0 (4B11) 5 marchas — só usado com transmission: manual
LANCER_GEARS = {
    1: 3.538,
    2: 1.913,
    3: 1.218,
    4: 0.888,
    5: 0.687,
}
MANUAL_FINAL_DRIVE = 4.235
TIRE_CIRCUMFERENCE_M = 2.025  # 205/60R16 aproximado

# Jatco JF011E / F1CJA — CVT típica do Lancer 2.0. Relações nominais de
# polia e diferencial; o valor real varia com desgaste e programação.
CVT_PULLEY_LOW = 2.349   # partida (relação "curta")
CVT_PULLEY_HIGH = 0.394  # overdrive (relação "longa")
CVT_FINAL_DRIVE = 6.386

FUEL_SPEC = {
    "gasoline": {"density": 740.0, "afr": 14.7},
    "ethanol": {"density": 789.0, "afr": 9.0},
    "flex": {"density": 753.0, "afr": 13.2},
    "diesel": {"density": 840.0, "afr": 14.5},
}


def gear_params(cfg: dict | None = None) -> tuple[dict[int, float], float, float]:
    """Relações, diferencial e circunferência do pneu (perfil, com fallback do Lancer)."""
    ratios = dict(LANCER_GEARS)
    final = MANUAL_FINAL_DRIVE
    circ = TIRE_CIRCUMFERENCE_M
    prof = (cfg or {}).get("_profile") or {}
    gears = prof.get("gears") or (cfg or {}).get("gears") or {}
    if gears.get("ratios"):
        ratios = {i + 1: float(r) for i, r in enumerate(gears["ratios"])}
    if gears.get("final_drive"):
        final = float(gears["final_drive"])
    if gears.get("tire_circumference_m"):
        circ = float(gears["tire_circumference_m"])
    return ratios, final, circ


def cvt_params(cfg: dict | None = None) -> tuple[float, float, float]:
    prof = (cfg or {}).get("_profile") or {}
    cvt = prof.get("cvt") or (cfg or {}).get("cvt") or {}
    return (
        float(cvt.get("pulley_low") or CVT_PULLEY_LOW),
        float(cvt.get("pulley_high") or CVT_PULLEY_HIGH),
        float(cvt.get("final_drive") or CVT_FINAL_DRIVE),
    )


def transmission_mode(cfg: dict) -> str:
    raw = (cfg.get("transmission") or "cvt")
    if isinstance(raw, dict):
        raw = raw.get("type", "cvt")
    return str(raw).lower().strip() or "cvt"


def fuel_params(fuel_type: str, ethanol_percent: float | None, flex_default: float = 27.0) -> tuple[float, float]:
    """Retorna (densidade g/L, AFR) conforme o combustível."""
    kind = (fuel_type or "flex").lower()
    if kind == "flex":
        eth = ethanol_percent if ethanol_percent is not None else flex_default
        eth = max(0.0, min(100.0, eth))
        gas = FUEL_SPEC["gasoline"]
        alc = FUEL_SPEC["ethanol"]
        t = eth / 100.0
        density = gas["density"] * (1 - t) + alc["density"] * t
        afr = gas["afr"] * (1 - t) + alc["afr"] * t
        return density, afr
    spec = FUEL_SPEC.get(kind, FUEL_SPEC["gasoline"])
    return spec["density"], spec["afr"]


def instant_lph(maf_g_s: float, density: float, afr: float) -> float | None:
    if maf_g_s is None or maf_g_s < 0 or density <= 0 or afr <= 0:
        return None
    grams_fuel_s = maf_g_s / afr
    liters_s = grams_fuel_s / density
    return liters_s * 3600.0


def instant_l100km(lph: float, speed_kmh: float) -> float | None:
    if lph is None or speed_kmh is None or speed_kmh < 3:
        return None
    return lph / speed_kmh * 100.0


def estimate_gear(rpm: float, speed_kmh: float,
                  gears: dict | None = None, final_drive: float | None = None,
                  tire_circ: float | None = None) -> int | None:
    """Estima a marcha. Padrão: 5 marchas do Lancer; o perfil pode trocar as relações."""
    if rpm is None or speed_kmh is None or speed_kmh < 3 or rpm < 400:
        return 0
    speed_m_s = speed_kmh / 3.6
    if speed_m_s <= 0:
        return 0
    ratios = gears or LANCER_GEARS
    final = final_drive if final_drive is not None else MANUAL_FINAL_DRIVE
    circ = tire_circ if tire_circ is not None else TIRE_CIRCUMFERENCE_M
    inferred = (rpm * circ) / (speed_m_s * 60.0 * final)
    best = None
    best_err = 1e9
    for gear, ratio in ratios.items():
        err = abs(math.log(inferred / ratio)) if inferred > 0 and ratio > 0 else 1e9
        if err < best_err:
            best_err = err
            best = gear
    if best is None or best_err > 0.18:
        return None
    return best


def cvt_metrics(rpm: float, speed_kmh: float,
                tire_circ: float | None = None, pulley_low: float | None = None,
                pulley_high: float | None = None, final_drive: float | None = None) -> dict[str, float] | None:
    """Relação efetiva da CVT a partir de RPM e velocidade.

    Retorna None parado ou com sinal ruim. Campos:
      rpm_per_kmh  — rotações do motor por km/h (intuição rápida)
      overall      — voltas do motor por volta da roda
      pulley       — relação das polias (overall / diferencial típico JF011E)
      position     — 0.0 = LOW (curta, arrancada), 1.0 = HIGH (longa, cruzeiro)
    """
    if rpm is None or speed_kmh is None or speed_kmh < 3 or rpm < 400:
        return None
    speed_m_s = speed_kmh / 3.6
    if speed_m_s <= 0:
        return None
    circ = tire_circ if tire_circ is not None else TIRE_CIRCUMFERENCE_M
    plow = pulley_low if pulley_low is not None else CVT_PULLEY_LOW
    phigh = pulley_high if pulley_high is not None else CVT_PULLEY_HIGH
    cfinal = final_drive if final_drive is not None else CVT_FINAL_DRIVE
    rpm_per_kmh = rpm / speed_kmh
    overall = (rpm * circ) / (speed_m_s * 60.0)
    pulley = overall / cfinal
    span = math.log(plow / phigh)
    if pulley <= 0:
        position = 0.5
    else:
        # pulley alto (2.35) → position 0 (LOW); pulley baixo (0.39) → 1 (HIGH)
        position = math.log(plow / max(pulley, 1e-6)) / span
        position = max(0.0, min(1.0, position))
    return {
        "rpm_per_kmh": rpm_per_kmh,
        "overall": overall,
        "pulley": pulley,
        "position": position,
    }


class DerivedComputer:
    """Integra consumo, relação da transmissão e distância da viagem."""

    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = cfg
        self._last_ts = time.time()
        self._trip_distance_km = 0.0
        self._trip_fuel_l = 0.0
        self._trip_started = time.time()
        self._max_speed = 0.0
        self._fuel_since_fill = float((cfg.get("fuel") or {}).get("used_since_fill", 0) or 0)
        self._samples: list[tuple[float, float, float]] = []  # (ts, speed, lph)
        self._window_s = float((cfg.get("fuel") or {}).get("rolling_window_s", 900))

    def reset_trip(self) -> None:
        self._trip_distance_km = 0.0
        self._trip_fuel_l = 0.0
        self._trip_started = time.time()
        self._max_speed = 0.0
        self._publish()

    def reset_fill(self, liters: float | None = None) -> dict:
        """Marca um abastecimento (tanque cheio ou litros informados)."""
        fuel_cfg = self.cfg.setdefault("fuel", {})
        tank = float(fuel_cfg.get("tank_liters", 50) or 50)
        filled = tank if liters is None else max(0.0, min(tank, float(liters)))
        fuel_cfg["manual_liters"] = filled
        self._fuel_since_fill = 0.0
        self.store.set_meta("fuel_used_since_fill", 0.0)
        return {"manual_liters": filled, "tank_liters": tank}

    def tick(self) -> None:
        now = time.time()
        dt = max(0.0, min(now - self._last_ts, 2.0))
        self._last_ts = now

        fuel_cfg = self.cfg.get("fuel", {})
        eth = self.store.value("ethanol_percent")
        density, afr = fuel_params(
            fuel_cfg.get("type", "flex"),
            eth,
            float(fuel_cfg.get("flex_ethanol_percent", 27)),
        )

        maf = self.store.value("maf")
        speed = self.store.value("speed")
        rpm = self.store.value("rpm")
        fuel_rate = self.store.value("fuel_rate")

        lph = None
        if fuel_rate is not None:
            lph = float(fuel_rate)
        elif maf is not None:
            lph = instant_lph(float(maf), density, afr)

        l100 = instant_l100km(lph, float(speed) if speed is not None else 0) if lph is not None else None

        if speed is not None and dt > 0:
            spd = max(0.0, float(speed))
            self._trip_distance_km += spd * dt / 3600.0
            self._max_speed = max(self._max_speed, spd)
        if lph is not None and dt > 0:
            self._trip_fuel_l += lph * dt / 3600.0

        if lph is not None:
            self.store.update("instant_lph", round(lph, 2), "L/h", "derived", "Vazão instantânea")
        if l100 is not None:
            self.store.update("instant_consumption", round(l100, 1), "L/100km", "derived", "Consumo instantâneo")
        elif lph is not None:
            self.store.update("instant_consumption", None, "L/100km", "derived", "Consumo instantâneo")

        elapsed_h = max((now - self._trip_started) / 3600.0, 1e-6)
        avg = (self._trip_fuel_l / self._trip_distance_km * 100.0) if self._trip_distance_km > 0.2 else None
        if avg is not None:
            self.store.update("avg_consumption", round(avg, 1), "L/100km", "derived", "Consumo médio")

        if lph is not None and dt > 0:
            self._fuel_since_fill += lph * dt / 3600.0
            self.store.set_meta("fuel_used_since_fill", round(self._fuel_since_fill, 4))
            self._samples.append((now, float(speed) if speed is not None else 0.0, float(lph)))
            cut = now - self._window_s
            self._samples = [s for s in self._samples if s[0] >= cut]
            self._publish_rolling()

        self._update_transmission(rpm, speed)
        self._publish()
        self.store.update("trip_time_s", int(now - self._trip_started), "s", "derived", "Tempo de viagem")
        self.store.update("avg_speed", round(self._trip_distance_km / elapsed_h, 1), "km/h", "derived", "Velocidade média")
        self.store.update("max_speed", round(self._max_speed, 0), "km/h", "derived", "Velocidade máxima")

    def _publish_rolling(self) -> None:
        """Consumo recente: janela rolante, separado em cidade (<50 km/h) e estrada."""
        city_fuel = city_dist = hwy_fuel = hwy_dist = 0.0
        samples = self._samples
        for i in range(1, len(samples)):
            t0, v0, l0 = samples[i - 1]
            t1, v1, l1 = samples[i]
            dt = max(0.0, t1 - t0)
            if dt <= 0 or dt > 5:
                continue
            speed = 0.5 * (v0 + v1)
            lph = 0.5 * (l0 + l1)
            dist = speed * dt / 3600.0
            fuel = lph * dt / 3600.0
            if speed < 50:
                city_fuel += fuel
                city_dist += dist
            else:
                hwy_fuel += fuel
                hwy_dist += dist
        city = (city_fuel / city_dist * 100.0) if city_dist > 0.3 else None
        hwy = (hwy_fuel / hwy_dist * 100.0) if hwy_dist > 0.5 else None
        total_fuel = city_fuel + hwy_fuel
        total_dist = city_dist + hwy_dist
        roll = (total_fuel / total_dist * 100.0) if total_dist > 0.4 else None
        share = (city_dist / total_dist) if total_dist > 0.4 else 0.55
        if city is not None:
            self.store.update("city_consumption", round(city, 1), "L/100km", "derived", "Consumo cidade")
        if hwy is not None:
            self.store.update("hwy_consumption", round(hwy, 1), "L/100km", "derived", "Consumo estrada")
        if roll is not None:
            self.store.update("rolling_consumption", round(roll, 1), "L/100km", "derived", "Consumo recente")
        self.store.set_meta("city_share", round(share, 3))

        from .range import remaining_liters, blended_l100, range_km
        liters, src = remaining_liters(self.store, self.cfg, self._fuel_since_fill)
        l100 = blended_l100(city, hwy, roll or self.store.value("avg_consumption"), share)
        reach = range_km(liters, l100) if l100 else None
        self.store.update("fuel_remaining", round(liters, 2), "L", "derived", "Combustível restante")
        if reach is not None:
            self.store.update("fuel_range_km", round(reach, 1), "km", "derived", "Autonomia estimada")
        self.store.set_meta("fuel_source", src)

    def _update_transmission(self, rpm: Any, speed: Any) -> None:
        mode = transmission_mode(self.cfg)
        self.store.set_meta("transmission", mode)
        rpm_f = float(rpm) if rpm is not None else 0.0
        speed_f = float(speed) if speed is not None else 0.0
        gears, final, circ = gear_params(self.cfg)
        if mode in {"manual", "auto"}:
            gear = estimate_gear(rpm_f, speed_f, gears=gears, final_drive=final, tire_circ=circ)
            label = "Marcha estimada" if mode == "manual" else "Marcha (automático)"
            self.store.update("gear", gear, "", "derived", label)
            # limpa indicadores de CVT para a UI esconder
            self.store.update("cvt_ratio", None, "", "derived", "Relação da polia")
            self.store.update("cvt_overall", None, "", "derived", "Relação total")
            self.store.update("cvt_rpm_per_kmh", None, "rpm/km/h", "derived", "RPM por km/h")
            self.store.update("cvt_position", None, "", "derived", "Posição CVT")
            return

        plow, phigh, cfinal = cvt_params(self.cfg)
        metrics = cvt_metrics(rpm_f, speed_f, tire_circ=circ,
                              pulley_low=plow, pulley_high=phigh, final_drive=cfinal)
        # Na CVT não afirmamos "marcha" (mesmo no modo Sport com degraus
        # simulados o número 1–6 seria só cosmética). A UI mostra a relação.
        self.store.update("gear", None, "", "derived", "Marcha estimada")
        if metrics is None:
            self.store.update("cvt_ratio", None, "", "derived", "Relação da polia")
            self.store.update("cvt_overall", None, "", "derived", "Relação total")
            self.store.update("cvt_rpm_per_kmh", None, "rpm/km/h", "derived", "RPM por km/h")
            self.store.update("cvt_position", None, "", "derived", "Posição CVT")
            return
        self.store.update("cvt_ratio", round(metrics["pulley"], 3), "", "derived", "Relação da polia")
        self.store.update("cvt_overall", round(metrics["overall"], 2), "", "derived", "Relação total")
        self.store.update("cvt_rpm_per_kmh", round(metrics["rpm_per_kmh"], 1), "rpm/km/h", "derived", "RPM por km/h")
        self.store.update("cvt_position", round(metrics["position"], 3), "", "derived", "Posição CVT")

    def _publish(self) -> None:
        self.store.update("trip_distance", round(self._trip_distance_km, 2), "km", "derived", "Distância da viagem")
        self.store.update("trip_fuel", round(self._trip_fuel_l, 3), "L", "derived", "Combustível da viagem")

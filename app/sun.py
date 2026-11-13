"""Nascer e pôr do sol aproximados (NOAA / Spencer) a partir de lat/lon — sem API."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def _julian(d: date) -> float:
    return d.toordinal() + 1721424.5


def sun_times(lat: float, lon: float, on: date | None = None) -> dict:
    """Devolve nascer/pôr no fuso America/Sao_Paulo. Civil dawn ≈ −0.833°."""
    day = on or datetime.now(TZ).date()
    # Algoritmo compacto (declinação + equação do tempo).
    n = day.timetuple().tm_yday
    decl = 23.44 * math.sin(math.radians(360.0 / 365.0 * (n - 81)))
    # equação do tempo, minutos
    b = math.radians(360.0 / 365.0 * (n - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    lat_r = math.radians(lat)
    decl_r = math.radians(decl)
    try:
        ha = math.degrees(math.acos(
            (math.sin(math.radians(-0.833)) - math.sin(lat_r) * math.sin(decl_r))
            / (math.cos(lat_r) * math.cos(decl_r))
        ))
    except ValueError:
        # sol da meia-noite / noite polar — não acontece em SP
        ha = 90.0
    solar_noon_min = 12 * 60 - 4 * lon - eot
    rise_min = solar_noon_min - 4 * ha
    set_min = solar_noon_min + 4 * ha

    def at(mins: float) -> datetime:
        # noon acima está em UTC aproximado (longitude já compensada)
        utc = datetime.combine(day, time(0, 0), tzinfo=timezone.utc) + timedelta(minutes=mins)
        return utc.astimezone(TZ)

    rise, sett = at(rise_min), at(set_min)
    return {
        "date": day.isoformat(),
        "sunrise": rise.strftime("%H:%M"),
        "sunset": sett.strftime("%H:%M"),
        "sunrise_hour": rise.hour + rise.minute / 60.0,
        "sunset_hour": sett.hour + sett.minute / 60.0,
    }


def is_night(lat: float | None, lon: float | None, now: datetime | None = None) -> bool:
    now = now or datetime.now(TZ)
    if lat is None or lon is None:
        h = now.hour + now.minute / 60.0
        return h >= 18 or h < 6
    times = sun_times(float(lat), float(lon), now.date())
    h = now.hour + now.minute / 60.0
    return h >= times["sunset_hour"] or h < times["sunrise_hour"]

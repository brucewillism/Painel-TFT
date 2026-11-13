"""Autonomia até o posto: combustível restante, consumo recente, rotas e trânsito."""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

# Postos fictícios ao redor da Av. Paulista (simulador).
_MOCK_STATIONS = [
    {"id": "mock-1", "name": "Posto Paulista", "brand": "Shell", "lat": -23.5614, "lon": -46.6565},
    {"id": "mock-2", "name": "Posto Pinheiros", "brand": "Ipiranga", "lat": -23.5670, "lon": -46.6820},
    {"id": "mock-3", "name": "Posto Moema", "brand": "Petrobras", "lat": -23.6010, "lon": -46.6620},
    {"id": "mock-4", "name": "Posto Ibirapuera", "brand": "Raízen", "lat": -23.5870, "lon": -46.6570},
    {"id": "mock-5", "name": "Posto Guarulhos", "brand": "Shell", "lat": -23.4540, "lon": -46.5330},
    {"id": "mock-6", "name": "Posto São Bernardo", "brand": "Ipiranga", "lat": -23.6930, "lon": -46.5650},
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def remaining_liters(store: DataStore, cfg: dict, fuel_used_since_fill: float) -> tuple[float, str]:
    """Litros no tanque: PID 0x2F × capacidade, ou 'tanque cheio' manual − gasto."""
    fuel_cfg = cfg.get("fuel") or {}
    tank = float(fuel_cfg.get("tank_liters", 50) or 50)
    level = store.value("fuel_level")
    if level is not None:
        return max(0.0, tank * float(level) / 100.0), "pid"
    filled = fuel_cfg.get("manual_liters")
    if filled is None:
        filled = tank
    return max(0.0, float(filled) - max(0.0, fuel_used_since_fill)), "manual"


def blended_l100(city: float | None, hwy: float | None, trip_avg: float | None,
                 city_share: float = 0.55) -> float | None:
    """Média ponderada cidade/estrada; cai no consumo da viagem se ainda não houver janela."""
    if city is not None and hwy is not None:
        share = min(1.0, max(0.0, city_share))
        return city * share + hwy * (1.0 - share)
    if city is not None:
        return city
    if hwy is not None:
        return hwy
    return trip_avg


def range_km(liters: float, l100: float | None) -> float | None:
    if l100 is None or l100 <= 0.05:
        return None
    return max(0.0, liters / (l100 / 100.0))


def fuel_at_arrival(liters: float, distance_km: float, l100: float,
                    extra_min: float, idle_l_per_min: float) -> float:
    used = distance_km * (l100 / 100.0) + max(0.0, extra_min) * idle_l_per_min
    return liters - used


def badge_for(fuel_left: float, reserve: float) -> str:
    if fuel_left <= 0:
        return "unreachable"
    if fuel_left < reserve:
        return "at-risk"
    return "reachable"


def traffic_extra_min(base_s: float | None, traffic_s: float | None) -> float:
    if base_s is None or traffic_s is None:
        return 0.0
    return max(0.0, (traffic_s - base_s) / 60.0)


class RangeService:
    """Busca postos (Overpass, com cache) e calcula rota + trânsito até cada um."""

    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = cfg
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: dict[str, Any] = {}
        self._last_fetch = 0.0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="range", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last or self._empty())

    def refresh(self, force: bool = False) -> dict[str, Any]:
        return self._compute(force=force)

    def _loop(self) -> None:
        # primeira passagem um pouco depois do GPS fix
        if self._stop.wait(2.0):
            return
        while not self._stop.is_set():
            try:
                self._compute(force=False)
            except Exception as exc:
                log.debug("range tick: %s", exc)
            if self._stop.wait(20.0):
                return

    def _rcfg(self) -> dict:
        return self.cfg.get("range") or {}

    def _empty(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "remaining_l": None,
            "fuel_source": None,
            "tank_l": float((self.cfg.get("fuel") or {}).get("tank_liters", 50)),
            "l100": None,
            "city_l100": None,
            "hwy_l100": None,
            "range_km": None,
            "stations": [],
            "routing": None,
            "traffic": False,
            "traffic_note": "Ainda sem cálculo.",
            "online": False,
        }

    def _compute(self, force: bool = False) -> dict[str, Any]:
        fuel_cfg = self.cfg.get("fuel") or {}
        tank = float(fuel_cfg.get("tank_liters", 50) or 50)
        used = float(self.store.get_meta("fuel_used_since_fill", 0.0) or 0.0)
        liters, fuel_src = remaining_liters(self.store, self.cfg, used)
        city = self.store.value("city_consumption")
        hwy = self.store.value("hwy_consumption")
        trip = self.store.value("rolling_consumption") or self.store.value("avg_consumption")
        share = float(self.store.get_meta("city_share", 0.55) or 0.55)
        l100 = blended_l100(
            float(city) if city is not None else None,
            float(hwy) if hwy is not None else None,
            float(trip) if trip is not None else None,
            share,
        )
        if l100 is None:
            l100 = float(fuel_cfg.get("fallback_l100", 9.5))
            l100_src = "default"
        else:
            l100_src = "rolling"
        reach = range_km(liters, l100)
        self.store.update("fuel_remaining", round(liters, 2), "L", "range", "Combustível restante")
        if reach is not None:
            self.store.update("fuel_range_km", round(reach, 1), "km", "range", "Autonomia estimada")

        lat = self.store.value("gps_lat")
        lon = self.store.value("gps_lon")
        rcfg = self._rcfg()
        sim = (self.cfg.get("source") or "simulator") == "simulator"
        stations = []
        online = False
        routing_name = "offline"
        traffic_on = False
        traffic_note = "Sem internet ou chave de trânsito — usando só o consumo médio."

        if lat is not None and lon is not None:
            stations, online = self._stations(float(lat), float(lon), sim=sim, force=force)
            routed, routing_name, traffic_on, traffic_note = self._route_all(
                float(lat), float(lon), stations, liters, l100, sim=sim,
            )
            stations = routed

        # posto alcançável mais perto (por duração, depois distância)
        reachable = [s for s in stations if s.get("badge") == "reachable"]
        risky = [s for s in stations if s.get("badge") == "at-risk"]
        pick = None
        pool = reachable or risky
        if pool:
            pick = min(pool, key=lambda s: (s.get("duration_s") is None, s.get("duration_s") or 1e9, s.get("distance_km") or 1e9))
        self.store.set_meta("nearest_station", pick)
        self.store.set_meta("fuel_source", fuel_src)

        out = {
            "enabled": bool(rcfg.get("enabled", True)),
            "remaining_l": round(liters, 2),
            "fuel_source": fuel_src,
            "tank_l": tank,
            "l100": round(l100, 1) if l100 is not None else None,
            "l100_source": l100_src,
            "city_l100": round(float(city), 1) if city is not None else None,
            "hwy_l100": round(float(hwy), 1) if hwy is not None else None,
            "city_share": round(share, 2),
            "range_km": round(reach, 1) if reach is not None else None,
            "stations": stations,
            "nearest": pick,
            "routing": routing_name,
            "traffic": traffic_on,
            "traffic_note": traffic_note,
            "online": online,
            "origin": {"lat": lat, "lon": lon},
            "ts": time.time(),
        }
        with self._lock:
            self._last = out
        return out

    def _stations(self, lat: float, lon: float, sim: bool, force: bool) -> tuple[list[dict], bool]:
        rcfg = self._rcfg()
        radius = int(rcfg.get("radius_m", 15000))
        if sim and not rcfg.get("force_overpass"):
            out = []
            for s in _MOCK_STATIONS:
                item = dict(s)
                item["distance_air_km"] = round(haversine_km(lat, lon, s["lat"], s["lon"]), 2)
                out.append(item)
            out.sort(key=lambda s: s["distance_air_km"])
            return out[: int(rcfg.get("max_stations", 8))], False

        cached = self._load_cache(lat, lon, radius)
        if cached and not force:
            return cached, False

        fetched = self._overpass(lat, lon, radius)
        if fetched is not None:
            self._save_cache(lat, lon, radius, fetched)
            return fetched, True
        if cached:
            return cached, False
        return [], False

    def _cache_path(self) -> Path:
        raw = (self._rcfg().get("cache_path") or "data/stations-cache.json")
        p = Path(raw)
        if not p.is_absolute():
            from .config import ROOT
            p = ROOT / p
        return p

    def _load_cache(self, lat: float, lon: float, radius: int) -> list[dict] | None:
        path = self._cache_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        ttl = float(self._rcfg().get("cache_ttl_h", 24)) * 3600
        if time.time() - float(data.get("ts") or 0) > ttl:
            return None
        clat, clon = data.get("lat"), data.get("lon")
        if clat is None or clon is None:
            return None
        if haversine_km(lat, lon, clat, clon) * 1000 > radius * 0.6:
            return None
        return list(data.get("stations") or [])

    def _save_cache(self, lat: float, lon: float, radius: int, stations: list[dict]) -> None:
        path = self._cache_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "ts": time.time(), "lat": lat, "lon": lon, "radius_m": radius, "stations": stations,
            }, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            log.debug("cache postos: %s", exc)

    def _overpass(self, lat: float, lon: float, radius: int) -> list[dict] | None:
        url = self._rcfg().get("overpass_url") or "https://overpass-api.de/api/interpreter"
        query = (
            f"[out:json][timeout:15];"
            f"(node[\"amenity\"=\"fuel\"](around:{radius},{lat:.5f},{lon:.5f});"
            f"way[\"amenity\"=\"fuel\"](around:{radius},{lat:.5f},{lon:.5f}););"
            f"out center tags;"
        )
        try:
            req = urllib.request.Request(
                url,
                data=("data=" + urllib.parse.quote(query)).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "lancer-painel/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            log.info("Overpass indisponível: %s", exc)
            return None
        out = []
        for el in payload.get("elements") or []:
            tags = el.get("tags") or {}
            elat = el.get("lat") or (el.get("center") or {}).get("lat")
            elon = el.get("lon") or (el.get("center") or {}).get("lon")
            if elat is None or elon is None:
                continue
            name = tags.get("name") or tags.get("brand") or tags.get("operator") or "Posto"
            item = {
                "id": f"osm-{el.get('type', 'n')}{el.get('id')}",
                "name": name,
                "brand": tags.get("brand") or tags.get("operator") or "",
                "lat": float(elat),
                "lon": float(elon),
                "distance_air_km": round(haversine_km(lat, lon, float(elat), float(elon)), 2),
            }
            out.append(item)
        out.sort(key=lambda s: s["distance_air_km"])
        return out[: int(self._rcfg().get("max_stations", 8))]

    def _route_all(self, lat: float, lon: float, stations: list[dict], liters: float,
                   l100: float, sim: bool) -> tuple[list[dict], str, bool, str]:
        rcfg = self._rcfg()
        provider = (rcfg.get("routing") or "osrm").lower()
        tomtom = (rcfg.get("tomtom_key") or os.environ.get("LANCER_TOMTOM_KEY") or "").strip()
        here = (rcfg.get("here_key") or os.environ.get("LANCER_HERE_KEY") or "").strip()
        idle = float((self.cfg.get("fuel") or {}).get("idle_l_per_min", 0.025))
        reserve = float((self.cfg.get("fuel") or {}).get("reserve_liters", 3))
        traffic_on = False
        name = "haversine"
        note = "Sem internet ou chave de trânsito — usando só o consumo médio e a distância em linha (ou última rota em cache)."

        use_mock = sim and not rcfg.get("force_online_routing")
        if use_mock:
            name = "simulator"
            traffic_on = bool(rcfg.get("simulate_traffic", True))
            note = ("Simulador: trânsito fictício aplicado em alguns postos, para ver o consumo extra em congestionamento."
                    if traffic_on else "Simulador sem trânsito fictício — só o consumo médio.")
        elif provider == "tomtom" and tomtom:
            name = "tomtom"
        elif provider == "here" and here:
            name = "here"
        elif not use_mock:
            name = "osrm"

        out = []
        any_online = False
        for s in stations:
            route = None
            if use_mock:
                route = self._mock_route(lat, lon, s, traffic_on)
            elif name == "tomtom":
                route = self._tomtom_route(lat, lon, s["lat"], s["lon"], tomtom)
            elif name == "here":
                route = self._here_route(lat, lon, s["lat"], s["lon"], here)
            elif name == "osrm":
                route = self._osrm_route(lat, lon, s["lat"], s["lon"])
            if route is None:
                # fallback offline
                dist = haversine_km(lat, lon, s["lat"], s["lon"]) * 1.25  # fator viário tosco
                dur = (dist / 28.0) * 3600.0
                route = {"distance_km": dist, "duration_s": dur, "base_duration_s": dur,
                         "traffic": False, "geometry": None, "provider": "haversine"}
            else:
                any_online = route.get("provider") not in {"haversine", "simulator"}
            extra = traffic_extra_min(route.get("base_duration_s"), route.get("duration_s"))
            fuel = fuel_at_arrival(liters, route["distance_km"], l100, extra, idle)
            item = dict(s)
            item.update({
                "distance_km": round(route["distance_km"], 2),
                "duration_s": int(route["duration_s"]),
                "eta_min": max(1, int(math.ceil(route["duration_s"] / 60.0))) if route["duration_s"] > 0 else 0,
                "base_duration_s": int(route.get("base_duration_s") or route["duration_s"]),
                "traffic_extra_min": round(extra, 1),
                "fuel_at_arrival_l": round(fuel, 2),
                "badge": badge_for(fuel, reserve),
                "geometry": route.get("geometry"),
                "traffic": bool(route.get("traffic")),
            })
            out.append(item)

        if use_mock:
            pass
        elif any_online and name in {"tomtom", "here"}:
            traffic_on = True
            note = f"Duração com trânsito ao vivo ({name}). Consumo extra nos minutos de congestionamento."
        elif any_online and name == "osrm":
            traffic_on = False
            note = "Rota OSRM (sem trânsito ao vivo). Para ajustar pelo trânsito, configure uma chave TomTom ou HERE."
        else:
            name = "haversine"
            traffic_on = False
            note = "Sem internet ou chave de trânsito — usando só o consumo médio e uma distância estimada."

        out.sort(key=lambda s: (s.get("badge") != "reachable", s.get("duration_s") or 1e9))
        return out, name, traffic_on, note

    def _mock_route(self, lat: float, lon: float, station: dict, traffic: bool) -> dict:
        dist = haversine_km(lat, lon, station["lat"], station["lon"]) * 1.3
        base = (dist / 32.0) * 3600.0
        # alguns postos “mais congestionados”
        factor = 1.0
        if traffic and station.get("id") in {"mock-1", "mock-4", "mock-5"}:
            factor = 1.35
        elif traffic and station.get("id") in {"mock-3"}:
            factor = 1.15
        dur = base * factor
        geom = {
            "type": "LineString",
            "coordinates": [[lon, lat], [station["lon"], station["lat"]]],
        }
        return {
            "distance_km": dist, "duration_s": dur, "base_duration_s": base,
            "traffic": factor > 1.01, "geometry": geom, "provider": "simulator",
        }

    def _osrm_route(self, lat1, lon1, lat2, lon2) -> dict | None:
        base = (self._rcfg().get("osrm_url") or "https://router.project-osrm.org").rstrip("/")
        url = f"{base}/route/v1/driving/{lon1:.6f},{lat1:.6f};{lon2:.6f},{lat2:.6f}?overview=simplified&geometries=geojson"
        data = _http_json(url, timeout=8)
        if not data or data.get("code") != "Ok":
            return None
        routes = data.get("routes") or []
        if not routes:
            return None
        r = routes[0]
        return {
            "distance_km": float(r["distance"]) / 1000.0,
            "duration_s": float(r["duration"]),
            "base_duration_s": float(r["duration"]),
            "traffic": False,
            "geometry": r.get("geometry"),
            "provider": "osrm",
        }

    def _tomtom_route(self, lat1, lon1, lat2, lon2, key: str) -> dict | None:
        url = (
            f"https://api.tomtom.com/routing/1/calculateRoute/"
            f"{lat1:.6f},{lon1:.6f}:{lat2:.6f},{lon2:.6f}/json"
            f"?key={urllib.parse.quote(key)}&traffic=true&routeRepresentation=polyline"
        )
        data = _http_json(url, timeout=8)
        if not data:
            return None
        try:
            summary = data["routes"][0]["summary"]
            delay = float(summary.get("trafficDelayInSeconds") or 0)
            travel = float(summary.get("travelTimeInSeconds") or 0)
            base = travel - delay if travel >= delay else travel
            return {
                "distance_km": float(summary["lengthInMeters"]) / 1000.0,
                "duration_s": travel,
                "base_duration_s": base,
                "traffic": delay > 5,
                "geometry": None,
                "provider": "tomtom",
            }
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def _here_route(self, lat1, lon1, lat2, lon2, key: str) -> dict | None:
        url = (
            "https://router.hereapi.com/v8/routes?"
            + urllib.parse.urlencode({
                "transportMode": "car",
                "origin": f"{lat1:.6f},{lon1:.6f}",
                "destination": f"{lat2:.6f},{lon2:.6f}",
                "return": "summary",
                "departureTime": "now",
                "apiKey": key,
            })
        )
        data = _http_json(url, timeout=8)
        if not data:
            return None
        try:
            s = data["routes"][0]["sections"][0]["summary"]
            # HERE: duration vs durationTypical (sem trânsito pesado)
            dur = float(s.get("duration") or 0)
            typ = float(s.get("typicalDuration") or s.get("baseDuration") or dur)
            return {
                "distance_km": float(s["length"]) / 1000.0,
                "duration_s": dur,
                "base_duration_s": typ,
                "traffic": dur > typ + 5,
                "geometry": None,
                "provider": "here",
            }
        except (KeyError, IndexError, TypeError, ValueError):
            return None


def _http_json(url: str, timeout: int = 8) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "lancer-painel/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        log.info("HTTP rota falhou: %s", exc)
        return None

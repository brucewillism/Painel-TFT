"""Carrega config.yaml e permite override por ambiente PAINEL_* ou LANCER_*."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _env_overrides() -> dict:
    mapping = {
        "LANCER_SOURCE": ("source", str),
        "LANCER_HOST": ("host", str),
        "LANCER_PORT": ("port", int),
        "LANCER_OBD_PORT": ("obd.port", str),
        "LANCER_CAN_CHANNEL": ("can.channel", str),
        "LANCER_GPS_ENABLED": ("gps.enabled", lambda v: v.lower() in {"1", "true", "yes"}),
        "LANCER_FUEL_TYPE": ("fuel.type", str),
        "LANCER_TRANSMISSION": ("transmission", str),
        "LANCER_DB": ("trip.db_path", str),
        "LANCER_TOMTOM_KEY": ("range.tomtom_key", str),
        "LANCER_HERE_KEY": ("range.here_key", str),
        "LANCER_COMPANION_PIN": ("companion.pin", str),
        "PAINEL_SOURCE": ("source", str),
        "PAINEL_HOST": ("host", str),
        "PAINEL_PORT": ("port", int),
        "PAINEL_PROFILE": ("profile", str),
        "PAINEL_PHOTO_KEY": ("car_photo.api_key", str),
        "LANCER_PHOTO_KEY": ("car_photo.api_key", str),
        "PAINEL_COMPANION_PIN": ("companion.pin", str),
    }
    out: dict = {}
    for env, (path, caster) in mapping.items():
        raw = os.environ.get(env)
        if raw is None:
            continue
        cursor = out
        parts = path.split(".")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = caster(raw)
    return out


def load(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else Path(os.environ.get("LANCER_CONFIG", DEFAULT_PATH))
    if not cfg_path.is_absolute():
        cfg_path = ROOT / cfg_path
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    data = _deep_merge(data, _env_overrides())
    data["_root"] = str(ROOT)
    data["_config_path"] = str(cfg_path)
    # Resolve relative paths against project root.
    for key in ("trip.db_path", "map.tiles_dir", "map.mbtiles_path", "range.cache_path"):
        parts = key.split(".")
        cursor = data
        for part in parts[:-1]:
            cursor = cursor.get(part, {})
        value = cursor.get(parts[-1])
        if value:
            p = Path(value)
            if not p.is_absolute():
                cursor[parts[-1]] = str(ROOT / p)
    return data

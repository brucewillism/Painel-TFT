"""Ilustrações de fallback por tipo de carroceria (PNG recortado + zonas)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ROOT

BODIES_DIR = ROOT / "app" / "static" / "img" / "bodies"
BODIES = ("sedan", "hatch", "suv", "pickup", "coupe", "wagon")


def normalize_body(body: str | None) -> str:
    b = (body or "sedan").lower().strip()
    return b if b in BODIES else "sedan"


def side_png(body: str | None) -> Path | None:
    p = BODIES_DIR / f"{normalize_body(body)}.png"
    return p if p.is_file() else None


def side_svg(body: str | None) -> Path | None:
    p = BODIES_DIR / f"{normalize_body(body)}.svg"
    return p if p.is_file() else None


def top_svg(body: str | None) -> Path | None:
    p = BODIES_DIR / f"{normalize_body(body)}-top.svg"
    return p if p.is_file() else None


def load_meta(body: str | None) -> dict[str, Any]:
    p = BODIES_DIR / f"{normalize_body(body)}.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def illustration(body: str | None) -> dict[str, Any] | None:
    """Metadados da ilustração lateral, ou None se o PNG não existir."""
    b = normalize_body(body)
    png = side_png(b)
    if not png:
        return None
    meta = load_meta(b)
    zones = meta.get("zones") or {}
    return {
        "ready": True,
        "body": b,
        "url": f"/static/img/bodies/{b}.png",
        "zones": zones,
        "side_on": bool(meta.get("side_on", True)),
        "wheels_confident": bool(meta.get("wheels_confident") or (len(zones.get("wheels") or []) == 2)),
        "image_w": meta.get("image_w"),
        "image_h": meta.get("image_h"),
        "source": meta.get("source") or "ai-illustration",
    }

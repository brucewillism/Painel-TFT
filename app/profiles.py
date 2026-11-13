"""Perfis de veículo: valores específicos do carro, separados da config do painel."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT, _deep_merge

log = logging.getLogger(__name__)

PROFILES_DIR = ROOT / "profiles"
STATE_PATH = ROOT / "data" / "vehicle-state.json"
BODIES = ("sedan", "hatch", "suv", "pickup", "coupe", "wagon")

# Campos do perfil que entram na config efetiva do painel.
_CFG_KEYS = (
    "fuel", "transmission", "cvt", "shift", "alerts",
)


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def default_profile() -> dict[str, Any]:
    p = PROFILES_DIR / "_default.yaml"
    data = _load_yaml(p) if p.is_file() else {"id": "generic", "body": "sedan", "name": "Veículo"}
    data.setdefault("id", "generic")
    return data


def list_profiles() -> list[dict[str, Any]]:
    """Lista perfis (já mesclados com o genérico), sem o arquivo _default isolado."""
    base = default_profile()
    out = []
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        raw = _load_yaml(path)
        merged = _deep_merge(base, raw)
        merged["id"] = raw.get("id") or path.stem
        merged["_file"] = path.name
        out.append(merged)
    # também oferece o genérico como escolha
    g = dict(base)
    g["id"] = base.get("id") or "generic"
    g["_file"] = "_default.yaml"
    if not any(p["id"] == g["id"] for p in out):
        out.insert(0, g)
    return out


def get_profile(profile_id: str | None) -> dict[str, Any]:
    base = default_profile()
    if not profile_id or profile_id in {"auto", "generic", "default"}:
        if profile_id in {None, "auto"}:
            return dict(base)
        g = dict(base)
        g["id"] = "generic"
        return g
    for p in list_profiles():
        if p["id"] == profile_id or p.get("_file") == f"{profile_id}.yaml":
            return p
    log.warning("Perfil %s não encontrado; usando o genérico.", profile_id)
    return dict(base)


def load_state() -> dict[str, Any]:
    if STATE_PATH.is_file():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(patch: dict[str, Any]) -> dict[str, Any]:
    cur = load_state()
    cur.update({k: v for k, v in patch.items() if v is not None})
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


def setup_completed() -> bool:
    st = load_state()
    return bool(st.get("setup_completed"))


def apply_to_config(cfg: dict, profile: dict | None = None) -> dict:
    """Mescla o perfil na config em memória (não grava o yaml)."""
    prof = profile or active_profile(cfg)
    cfg = dict(cfg)
    cfg["profile_id"] = prof.get("id")
    cfg["_profile"] = prof
    if prof.get("transmission"):
        cfg["transmission"] = prof["transmission"]
    for key in ("fuel", "cvt", "shift", "alerts"):
        if isinstance(prof.get(key), dict):
            cfg[key] = _deep_merge(dict(cfg.get(key) or {}), prof[key])
    # veículo exibido
    veh = dict(cfg.get("vehicle") or {})
    for k in ("make", "manufacturer"):
        pass
    veh["manufacturer"] = prof.get("make") or veh.get("manufacturer") or ""
    veh["model"] = prof.get("model") or veh.get("model") or prof.get("name") or "Veículo"
    if prof.get("year_from") and not veh.get("year"):
        veh["year"] = prof.get("year_from")
    if prof.get("trim"):
        veh["trim"] = prof["trim"]
    if prof.get("engine"):
        veh["engine"] = prof["engine"]
    if prof.get("body"):
        veh["body"] = prof["body"]
    veh["paint"] = (load_state().get("paint") or prof.get("paint") or veh.get("paint") or "#c41e3a")
    cfg["vehicle"] = veh
    # pintura da UI
    ui = dict(cfg.get("ui") or {})
    if not load_state().get("paint") and prof.get("paint"):
        # não sobrescreve cor já escolhida no app
        if not ui.get("car_color") or ui.get("car_color") == "#b1121a":
            pass
    st_paint = load_state().get("paint")
    if st_paint:
        ui["car_color"] = st_paint
    elif prof.get("paint") and not ui.get("car_color"):
        ui["car_color"] = prof["paint"]
    cfg["ui"] = ui
    return cfg


def active_profile(cfg: dict | None = None) -> dict[str, Any]:
    st = load_state()
    pid = st.get("profile_id") or (cfg or {}).get("profile") or "auto"
    if pid in {None, "", "auto"}:
        return get_profile("generic")
    return get_profile(pid)


def tire_circumference_m(prof: dict) -> float | None:
    gears = prof.get("gears") or {}
    if gears.get("tire_circumference_m"):
        return float(gears["tire_circumference_m"])
    # estima a partir de "215/45R18"
    spec = str(gears.get("tire") or "")
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s*R\s*(\d+)", spec, re.I)
    if not m:
        return None
    w, aspect, rim = int(m.group(1)), int(m.group(2)), int(m.group(3))
    sidewall_mm = w * (aspect / 100.0)
    diam_mm = sidewall_mm * 2 + rim * 25.4
    return round(3.14159265 * diam_mm / 1000.0, 3)


def match_profile(identity: dict, profiles: list[dict] | None = None) -> dict[str, Any] | None:
    """Escolhe o perfil que melhor casa com make/model/year/WMI do VIN."""
    profiles = profiles or list_profiles()
    make = _norm(identity.get("make") or identity.get("manufacturer") or "")
    model = _norm(identity.get("model") or "")
    year = identity.get("year")
    wmi = (identity.get("wmi") or "").upper()
    scored: list[tuple[int, dict]] = []
    for p in profiles:
        if p.get("id") in {"generic", "generic-coupe", "generic-wagon"} and not p.get("make"):
            # genéricos só como último recurso
            continue
        score = 0
        pm = _norm(p.get("make") or "")
        po = _norm(p.get("model") or "")
        if pm and pm in make or (pm and make in pm):
            score += 4
        if po and po in model or (po and model in po):
            score += 6
        y0, y1 = p.get("year_from"), p.get("year_to")
        if year and y0 and y1 and y0 <= year <= y1:
            score += 3
        elif year and y0 and abs(year - y0) <= 2:
            score += 1
        hints = p.get("vin_hints") or {}
        if wmi and wmi in [str(x).upper() for x in (hints.get("wmi") or [])]:
            score += 3
        if year and year in (hints.get("years") or []):
            score += 1
        if score >= 6:
            scored.append((score, p))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def body_from_class(text: str | None) -> str | None:
    if not text:
        return None
    t = text.lower()
    if any(k in t for k in ("pickup", "pick-up", "truck", "picape")):
        return "pickup"
    if any(k in t for k in ("suv", "sport utility", "crossover", "utilitário esportivo")):
        return "suv"
    if any(k in t for k in ("hatch", "hatchback")):
        return "hatch"
    if any(k in t for k in ("wagon", "estate", "perua", "touring", "variant")):
        return "wagon"
    if any(k in t for k in ("coupe", "coupé", "cupê", "convertible", "cabriolet", "roadster")):
        return "coupe"
    if any(k in t for k in ("sedan", "saloon", "sedã")):
        return "sedan"
    return None


def _norm(s: str) -> str:
    s = (s or "").lower()
    for a, b in (("á", "a"), ("ã", "a"), ("â", "a"), ("é", "e"), ("ê", "e"),
                 ("í", "i"), ("ó", "o"), ("ô", "o"), ("ú", "u"), ("ç", "c")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # tira sufixos corporativos comuns
    for w in (" motors", " motor", " automobiles", " automoveis", " do brasil",
              " north america", " canada", " corporation", " ltd", " sa"):
        s = s.replace(w, " ")
    return " ".join(s.split())



def hero_public(prof: dict) -> dict[str, Any] | None:
    """Expõe o herói 2D do HUD (URL servida + âncoras normalizadas)."""
    h = prof.get("hud_hero")
    if not h:
        return None
    if isinstance(h, str):
        h = {"image": h}

    def to_url(raw: str) -> str:
        raw = str(raw or "").replace("\\", "/").lstrip("./")
        if raw.startswith("/media/") or raw.startswith("/static/"):
            return raw
        for prefix in ("data/vehicles/", "vehicles/"):
            if raw.startswith(prefix):
                return "/media/vehicles/" + raw[len(prefix):]
        return "/media/vehicles/" + raw.lstrip("/")

    image = h.get("image") or h.get("path") or ""
    if not image:
        return None
    out: dict[str, Any] = {
        "image": to_url(image),
        "anchors": h.get("anchors") or {},
    }
    if h.get("luma"):
        out["luma"] = to_url(h["luma"])
    if h.get("core"):
        out["core"] = to_url(h["core"])
    if "ground" in h:
        try:
            out["ground"] = float(h["ground"])
        except (TypeError, ValueError):
            pass
    if h.get("aspect"):
        try:
            out["aspect"] = float(h["aspect"])
        except (TypeError, ValueError):
            pass
    return out


def public_view(prof: dict) -> dict[str, Any]:
    """Recorte seguro para a API/UI."""
    return {
        "id": prof.get("id"),
        "name": prof.get("name"),
        "make": prof.get("make"),
        "model": prof.get("model"),
        "year_from": prof.get("year_from"),
        "year_to": prof.get("year_to"),
        "trim": prof.get("trim"),
        "body": prof.get("body") or "sedan",
        "engine": prof.get("engine"),
        "transmission": prof.get("transmission"),
        "fuel": prof.get("fuel"),
        "tank_liters": (prof.get("fuel") or {}).get("tank_liters"),
        "shift": prof.get("shift"),
        "paint": prof.get("paint"),
        "notes": prof.get("notes"),
        "art": prof.get("art") or {},
        "sample_vin": prof.get("sample_vin"),
        "hud_hero": hero_public(prof),
    }

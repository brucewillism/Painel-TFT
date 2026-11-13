"""Leitura e decodificação offline do VIN (ISO 3779 / OBD Mode 09 PID 02)."""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger(__name__)

_TRANSLIT = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

# Posição 10 do VIN: ciclo de 30 anos. A partir de 2010 o código recomeça em A.
_YEAR_OFFSET = {
    "A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5, "G": 6, "H": 7,
    "J": 8, "K": 9, "L": 10, "M": 11, "N": 12, "P": 13, "R": 14,
    "S": 15, "T": 16, "V": 17, "W": 18, "X": 19, "Y": 20,
    "1": 21, "2": 22, "3": 23, "4": 24, "5": 25, "6": 26, "7": 27,
    "8": 28, "9": 29,
}

# WMI offline (ISO 3780). Recorte focado no mercado brasileiro + marcas globais.
# Não é exaustivo; o NHTSA vPIC (quando houver internet) completa make/model.
_WMI = {
    # Mitsubishi
    "JA3": ("Mitsubishi Motors", "Japão"),
    "JA4": ("Mitsubishi Motors", "Japão"),
    "JMB": ("Mitsubishi Motors", "Japão"),
    "JMY": ("Mitsubishi Motors", "Japão"),
    "JMA": ("Mitsubishi Motors", "Japão"),
    "MM0": ("Mitsubishi Motors (Thailand)", "Tailândia"),
    "MMB": ("Mitsubishi Motors (Thailand)", "Tailândia"),
    "MMC": ("Mitsubishi Motors (Thailand)", "Tailândia"),
    "4A3": ("Mitsubishi Motors North America", "EUA"),
    "4A4": ("Mitsubishi Motors North America", "EUA"),
    "6MM": ("Mitsubishi Motors Australia", "Austrália"),
    "93Y": ("MMC Automotores do Brasil", "Brasil"),
    "93X": ("MMC Automotores do Brasil", "Brasil"),
    "93Z": ("MMC Automotores do Brasil", "Brasil"),
    # Brasil (primeiro dígito 9, bloco 93–9E)
    "9BD": ("Fiat Automóveis", "Brasil"),
    "9BF": ("Ford Brasil", "Brasil"),
    "9BG": ("General Motors do Brasil", "Brasil"),
    "9BW": ("Volkswagen do Brasil", "Brasil"),
    "9BR": ("Toyota do Brasil", "Brasil"),
    "93H": ("Honda Automóveis do Brasil", "Brasil"),
    "94D": ("Honda Automóveis do Brasil", "Brasil"),
    "988": ("Jeep / FCA (Goiana)", "Brasil"),
    "9C2": ("Honda (motos / auto)", "Brasil"),
    "936": ("Peugeot Citroën do Brasil", "Brasil"),
    "935": ("Renault do Brasil", "Brasil"),
    "94T": ("Toyota do Brasil", "Brasil"),
    "9BH": ("Hyundai CAOA", "Brasil"),
    "9UJ": ("Hyundai CAOA", "Brasil"),
    "9UH": ("Nissan do Brasil", "Brasil"),
    "94N": ("Nissan do Brasil", "Brasil"),
    "9DF": ("Chery / CAOA", "Brasil"),
    # Argentina / Mercosul
    "8AP": ("Volkswagen Argentina", "Argentina"),
    "8AD": ("Fiat Argentina", "Argentina"),
    "8AF": ("Ford Argentina", "Argentina"),
    "8AJ": ("Toyota Argentina", "Argentina"),
    "8AW": ("Renault Argentina", "Argentina"),
    "8AG": ("General Motors Argentina", "Argentina"),
    "8A1": ("Renault Argentina", "Argentina"),
    # Japão
    "JHM": ("Honda", "Japão"),
    "JHL": ("Honda", "Japão"),
    "JT2": ("Toyota", "Japão"),
    "JT3": ("Toyota", "Japão"),
    "JT4": ("Toyota", "Japão"),
    "JT6": ("Toyota", "Japão"),
    "JT8": ("Toyota", "Japão"),
    "JTJ": ("Lexus", "Japão"),
    "JN1": ("Nissan", "Japão"),
    "JN8": ("Nissan", "Japão"),
    "JM1": ("Mazda", "Japão"),
    "JF1": ("Subaru", "Japão"),
    "JS1": ("Suzuki", "Japão"),
    "JSA": ("Suzuki", "Japão"),
    # Coreia
    "KMH": ("Hyundai", "Coreia do Sul"),
    "KNA": ("Kia", "Coreia do Sul"),
    "KND": ("Kia", "Coreia do Sul"),
    # Europa
    "WVW": ("Volkswagen", "Alemanha"),
    "WBA": ("BMW", "Alemanha"),
    "WBS": ("BMW M", "Alemanha"),
    "WAU": ("Audi", "Alemanha"),
    "WDB": ("Mercedes-Benz", "Alemanha"),
    "WDD": ("Mercedes-Benz", "Alemanha"),
    "VF1": ("Renault", "França"),
    "VF3": ("Peugeot", "França"),
    "VF7": ("Citroën", "França"),
    "ZFA": ("Fiat", "Itália"),
    "SAJ": ("Jaguar", "Reino Unido"),
    "SAL": ("Land Rover", "Reino Unido"),
    # EUA / México
    "1G1": ("Chevrolet", "EUA"),
    "1G6": ("Cadillac", "EUA"),
    "1FA": ("Ford", "EUA"),
    "1FT": ("Ford", "EUA"),
    "1C4": ("Chrysler / Jeep", "EUA"),
    "1C6": ("Ram", "EUA"),
    "1HG": ("Honda", "EUA"),
    "1N4": ("Nissan", "EUA"),
    "2HG": ("Honda", "Canadá"),
    "2T1": ("Toyota", "Canadá"),
    "3N1": ("Nissan", "México"),
    "3VW": ("Volkswagen", "México"),
    "3G1": ("Chevrolet", "México"),
    "3FA": ("Ford", "México"),
    "3C4": ("Chrysler / Jeep", "México"),
}

# Classe de carroceria (texto livre, NHTSA BodyClass ou similar) → body do painel.
# O mapeamento fino está em profiles.body_from_class.

# Dicas offline de modelo para WMI + faixa de ano (só os perfis de exemplo + clássicos BR).
_MODEL_HINTS = [
    # wmi, year0, year1, make, model, body
    ({"93Y", "93X", "93Z", "JA3", "JA4", "4A3"}, 2007, 2018, "Mitsubishi", "Lancer", "sedan"),
    ({"9BG", "9GN", "3G1"}, 2012, 2019, "Chevrolet", "Onix", "hatch"),
    ({"9BG", "9GN"}, 2020, 2026, "Chevrolet", "Onix", "hatch"),
    ({"988", "1C4", "3C4"}, 2016, 2026, "Jeep", "Compass", "suv"),
    ({"9BR", "MR0", "AHT"}, 2005, 2026, "Toyota", "Hilux", "pickup"),
]

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_vin(raw: str | None) -> str | None:
    if not raw:
        return None
    vin = re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()
    # caracteres I, O, Q não existem em VIN
    if len(vin) != 17 or not _VIN_RE.match(vin):
        return None
    return vin


def check_digit(vin: str) -> str:
    total = 0
    for i, ch in enumerate(vin):
        val = int(ch) if ch.isdigit() else _TRANSLIT.get(ch, 0)
        total += val * _WEIGHTS[i]
    rem = total % 11
    return "X" if rem == 10 else str(rem)


def check_digit_ok(vin: str) -> bool:
    vin = vin.upper()
    if len(vin) != 17:
        return False
    return check_digit(vin) == vin[8]


def year_from_code(code: str, now_year: int | None = None) -> int | None:
    if not code:
        return None
    off = _YEAR_OFFSET.get(code.upper())
    if off is None:
        return None
    import datetime
    current = now_year or datetime.date.today().year
    candidates = [1980 + off, 2010 + off]
    # 2040+ entra no próximo ciclo; ainda não é o caso para um Lancer 2016.
    valid = [y for y in candidates if 1980 <= y <= current + 1]
    return max(valid) if valid else candidates[-1]


def build_vin(wmi: str, vds: str, year: int, plant: str, serial: str) -> str:
    """Monta um VIN de 17 com dígito verificador válido (para o simulador/testes)."""
    wmi = wmi.upper()[:3].ljust(3, "X")
    vds = re.sub(r"[^A-Z0-9]", "", vds.upper())[:5].ljust(5, "A")
    # ano → código (ciclo 2010)
    off = year - 2010 if year >= 2010 else year - 1980
    inv = {v: k for k, v in _YEAR_OFFSET.items()}
    year_c = inv.get(off, "G")
    plant = (plant or "A")[0].upper()
    serial = re.sub(r"[^A-Z0-9]", "", serial.upper())[-6:].rjust(6, "0")
    body = f"{wmi}{vds}0{year_c}{plant}{serial}"
    return body[:8] + check_digit(body) + body[9:]


def decode_vin(vin: str | None, fallback: dict | None = None, now_year: int | None = None) -> dict[str, Any]:
    """Decodifica o VIN offline. Sempre preenche o que o fallback souber."""
    fb = dict(fallback or {})
    out: dict[str, Any] = {
        "vin": None,
        "valid": False,
        "check_digit_ok": False,
        "wmi": None,
        "manufacturer": fb.get("manufacturer") or fb.get("make") or "",
        "make": fb.get("make") or fb.get("manufacturer") or "",
        "country": fb.get("country"),
        "year": fb.get("year"),
        "plant": None,
        "serial": None,
        "model": fb.get("model") or "",
        "trim": fb.get("trim") or "",
        "engine": fb.get("engine") or "",
        "transmission": fb.get("transmission") or "",
        "body": fb.get("body"),
        "facelift": bool(fb.get("facelift", False)),
        "source": "fallback",
        "label": None,
        "vpic": None,
    }
    clean = normalize_vin(vin)
    if not clean:
        out["label"] = _label(out)
        out["note"] = "VIN não lido (clone ELM327 às vezes falha no Mode 09). Usando o modelo configurado."
        return out

    out["vin"] = clean
    out["valid"] = True
    out["check_digit_ok"] = check_digit_ok(clean)
    out["wmi"] = clean[:3]
    mfr, country = _WMI.get(clean[:3], (out["manufacturer"], _country_from_wmi(clean[:3])))
    out["manufacturer"] = mfr
    out["country"] = country
    out["year"] = year_from_code(clean[9], now_year) or out["year"]
    out["plant"] = clean[10]
    out["serial"] = clean[11:]
    out["source"] = "obd"
    out["make"] = _short_make(out["manufacturer"]) or out.get("make")
    hinted = _hint_model(out["wmi"], out.get("year"))
    if hinted:
        if not out.get("model"):
            out["model"] = hinted[1]
        if not out.get("make"):
            out["make"] = hinted[0]
        out["body"] = out.get("body") or hinted[2]
        if hinted[1] == "Lancer":
            out["facelift"] = (out.get("year") or 0) >= 2016
    # compat: Lancer 2007–2017 se o WMI é Mitsubishi e o modelo ainda está vazio
    year = out["year"] or 0
    mfr = out["manufacturer"] or ""
    if not out.get("model") and "Mitsubishi" in mfr and 2007 <= year <= 2018:
        out["model"] = "Lancer"
        out["body"] = out.get("body") or "sedan"
        out["facelift"] = year >= 2016
    if not out.get("engine"):
        out["engine"] = fb.get("engine") or ""
    out["label"] = _label(out)
    if not out["check_digit_ok"]:
        out["note"] = "Dígito verificador do VIN não confere; a leitura pode ter vindo corrompida."
    return out


def _country_from_wmi(wmi: str) -> str | None:
    if not wmi:
        return None
    c = wmi[0]
    if c == "J":
        return "Japão"
    if c == "9":
        return "Brasil" if wmi[1] in "345" else "América do Sul"
    if c == "8":
        return "Argentina"
    if c in "45":
        return "EUA"
    if c == "1":
        return "EUA"
    if c == "2":
        return "Canadá"
    if c == "3":
        return "México"
    if c == "6":
        return "Austrália"
    if c == "M":
        return "Tailândia"
    if c == "K":
        return "Coreia do Sul"
    if c == "W":
        return "Alemanha"
    if c == "V":
        return "França"
    if c == "Z":
        return "Itália"
    if c == "S":
        return "Reino Unido"
    return None


def _short_make(manufacturer: str | None) -> str:
    if not manufacturer:
        return ""
    m = manufacturer
    # "MMC Automotores do Brasil" / "Mitsubishi Motors …" → Mitsubishi
    if "Mitsubishi" in m or m.startswith("MMC"):
        return "Mitsubishi"
    for prefix in ("General Motors", "GM "):
        if m.startswith(prefix) or "General Motors" in m:
            return "Chevrolet"
    mapping = {
        "Fiat": "Fiat", "Ford": "Ford", "Volkswagen": "Volkswagen", "Toyota": "Toyota",
        "Honda": "Honda", "Jeep": "Jeep", "Hyundai": "Hyundai", "Nissan": "Nissan",
        "Renault": "Renault", "Peugeot": "Peugeot", "Citroën": "Citroën", "Citroen": "Citroën",
        "BMW": "BMW", "Mercedes": "Mercedes-Benz", "Audi": "Audi", "Kia": "Kia",
        "Chevrolet": "Chevrolet", "Chrysler": "Chrysler",
    }
    for k, v in mapping.items():
        if k.lower() in m.lower():
            return v
    return m.split("(")[0].strip()


def _hint_model(wmi: str | None, year: int | None):
    if not wmi:
        return None
    w = wmi.upper()
    y = year or 0
    for wmis, y0, y1, make, model, body in _MODEL_HINTS:
        if w in wmis and (not y or y0 <= y <= y1):
            return (make, model, body)
    return None


def _label(info: dict[str, Any]) -> str:
    make = info.get("make") or _short_make(info.get("manufacturer")) or info.get("manufacturer") or ""
    model = info.get("model") or ""
    bits = [b for b in (make, model) if b]
    if not bits:
        bits = ["Veículo"]
    if info.get("year"):
        bits.append(str(info["year"]))
    extra = []
    if info.get("engine"):
        extra.append(str(info["engine"]))
    if info.get("transmission"):
        trans = str(info["transmission"]).lower()
        extra.append({"cvt": "CVT", "auto": "automático", "manual": "manual"}.get(trans, trans))
    if info.get("trim"):
        extra.append(str(info["trim"]))
    line = " ".join(bits)
    if extra:
        line += " · " + " ".join(extra)
    return line


def parse_mode09_pid02(payload: bytes | list[int] | str) -> str | None:
    """Extrai 17 caracteres de uma resposta Mode 09 PID 02 (vários formatos)."""
    if payload is None:
        return None
    if isinstance(payload, str):
        text = payload
        # tenta ASCII direto
        maybe = normalize_vin(re.sub(r"[^A-Za-z0-9]", "", text))
        if maybe:
            return maybe
        hexes = re.findall(r"[0-9A-Fa-f]{2}", text)
        try:
            payload = bytes(int(h, 16) for h in hexes)
        except ValueError:
            return None
    data = bytes(payload)
    # remove cabeçalhos 49 02 [01/02/03] comuns no ELM
    chars: list[int] = []
    i = 0
    while i < len(data):
        if data[i] == 0x49 and i + 1 < len(data) and data[i + 1] == 0x02:
            i += 2
            if i < len(data) and data[i] in (0x00, 0x01, 0x02, 0x03):
                i += 1
            continue
        chars.append(data[i])
        i += 1
    raw = bytes(b for b in chars if 32 <= b < 127)
    return normalize_vin(raw.decode("ascii", errors="ignore"))


def identity_from_config(cfg: dict) -> dict[str, Any]:
    veh = dict(cfg.get("vehicle") or {})
    prof = cfg.get("_profile") or {}
    trans = veh.get("transmission") or cfg.get("transmission") or prof.get("transmission") or ""
    year = veh.get("year") or prof.get("year_from")
    return {
        "manufacturer": veh.get("manufacturer") or prof.get("make") or "",
        "make": veh.get("make") or prof.get("make") or veh.get("manufacturer") or "",
        "country": veh.get("country") or prof.get("region") or "",
        "year": int(year) if year else None,
        "model": veh.get("model") or prof.get("model") or "",
        "trim": veh.get("trim") or prof.get("trim") or "",
        "engine": veh.get("engine") or prof.get("engine") or "",
        "transmission": trans,
        "body": veh.get("body") or prof.get("body"),
        "facelift": bool(veh.get("facelift", False)),
    }


def resolve_identity(cfg: dict, vin: str | None, *, online: bool = False) -> dict[str, Any]:
    fallback = identity_from_config(cfg)
    configured = (cfg.get("vehicle") or {}).get("vin")
    # VIN lido da ECU tem prioridade; senão o configurado; senão só o fallback.
    info = decode_vin(vin or configured, fallback=fallback)
    if online and info.get("vin"):
        try:
            vpic = lookup_vpic(info["vin"], cfg=cfg)
        except Exception as exc:
            log.info("vPIC indisponível: %s", exc)
            vpic = None
        if vpic:
            info = apply_vpic(info, vpic)
            info["label"] = _label(info)
    # casa com um perfil conhecido
    try:
        from .profiles import body_from_class, match_profile
        if not info.get("body") and vpic_body(info):
            info["body"] = body_from_class(vpic_body(info))
        matched = match_profile(info)
        if matched:
            info["suggested_profile"] = matched.get("id")
            info["body"] = info.get("body") or matched.get("body")
            if not fallback.get("model") and not info.get("model"):
                info["model"] = matched.get("model") or info.get("model")
    except Exception:
        pass
    info["label"] = _label(info)
    return info


def vpic_body(info: dict) -> str | None:
    vp = info.get("vpic") or {}
    return vp.get("BodyClass") or vp.get("VehicleType") or info.get("body_class")


def lookup_vpic(vin: str, cfg: dict | None = None, timeout: float = 4.0) -> dict | None:
    """Consulta opcional ao NHTSA vPIC (DecodeVinValues). Resultado é cacheado."""
    vin = normalize_vin(vin)
    if not vin:
        return None
    from pathlib import Path
    import json
    import urllib.request
    root = Path((cfg or {}).get("_root") or Path(__file__).resolve().parent.parent)
    cache_path = Path((cfg or {}).get("vin_cache") or (root / "data" / "vin-cache.json"))
    cache: dict = {}
    if cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    if vin in cache and isinstance(cache[vin], dict) and cache[vin].get("Make"):
        return cache[vin]
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "PainelTFT/0.3 (vehicle dashboard)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    results = payload.get("Results") or []
    if not results:
        return None
    row = results[0]
    # descarta campos vazios
    slim = {k: v for k, v in row.items() if v and str(v).strip() not in {"", "Not Applicable", "0"}}
    cache[vin] = slim
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return slim


def apply_vpic(info: dict, vpic: dict) -> dict:
    info = dict(info)
    info["vpic"] = vpic
    make = vpic.get("Make") or vpic.get("Manufacturer")
    if make:
        info["make"] = _short_make(make) or make.title()
        if not info.get("manufacturer") or info["manufacturer"] == "":
            info["manufacturer"] = make.title()
    model = vpic.get("Model")
    if model:
        info["model"] = model
    try:
        year = int(str(vpic.get("ModelYear") or "").strip())
        if 1980 <= year <= 2040:
            info["year"] = year
    except (TypeError, ValueError):
        pass
    body = vpic.get("BodyClass") or vpic.get("VehicleType")
    if body:
        info["body_class"] = body
        from .profiles import body_from_class
        mapped = body_from_class(body)
        if mapped:
            info["body"] = mapped
    if vpic.get("Trim"):
        info["trim"] = vpic["Trim"]
    if vpic.get("DisplacementL"):
        info["engine"] = info.get("engine") or f"{vpic['DisplacementL']} L"
    info["source"] = "obd+vpic" if info.get("vin") else "vpic"
    return info

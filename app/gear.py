"""Marcha / posição do câmbio: inferida, CAN ou GPIO.

Marcha e luzes NÃO vêm do OBD2 padrão — preciso de inferência, de um
quadro CAN (MCP2515) ou de um pino GPIO. Veja o README.
"""

from __future__ import annotations

import logging
from typing import Any

from . import gpio_reverse
from .derived import estimate_gear, gear_params, transmission_mode

log = logging.getLogger(__name__)

PRNDL = ("P", "R", "N", "D", "L")


def _profile(cfg: dict | None) -> dict:
    return (cfg or {}).get("_profile") or {}


def gear_source_kind(cfg: dict | None) -> str:
    prof = _profile(cfg)
    raw = prof.get("gear_source") or (cfg or {}).get("gear_source") or "inferred"
    kind = str(raw).strip().lower()
    if kind in {"can", "gpio", "inferred", "obd"}:
        return "inferred" if kind == "obd" else kind
    return "inferred"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value > 0.5
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def infer_prndl(
    *,
    speed: float = 0.0,
    rpm: float = 0.0,
    reverse: bool = False,
    parking_brake: bool = False,
    moving_kmh: float = 2.5,
    stall_rpm: float = 400.0,
) -> str:
    """P/R/N/D (L só entra via CAN/GPIO).

    Parado com motor desligado ou freio de mão: P.
    Parado com o motor em marcha lenta: N.
    Em movimento para frente: D. Ré se houver sinal de ré.
    """
    if reverse:
        return "R"
    spd = float(speed or 0.0)
    rev = float(rpm or 0.0)
    if spd < moving_kmh:
        if parking_brake or rev < stall_rpm:
            return "P"
        return "N"
    return "D"


def infer_manual(
    *,
    speed: float = 0.0,
    rpm: float = 0.0,
    reverse: bool = False,
    parking_brake: bool = False,
    ratios: dict[int, float] | None = None,
    final_drive: float | None = None,
    tire_circ: float | None = None,
) -> str | int:
    """Parado: P/N/R. Em movimento: 1–6 (estimativa por RPM/velocidade)."""
    if reverse:
        return "R"
    if float(speed or 0.0) < 2.5:
        return infer_prndl(speed=speed, rpm=rpm, reverse=False, parking_brake=parking_brake)
    gear = estimate_gear(float(rpm or 0.0), float(speed or 0.0), ratios, final_drive, tire_circ)
    if gear is None or gear == 0:
        return "N"
    return int(gear)


def decode_can_value(data: bytes | list[int], spec: dict[str, Any] | None) -> int | None:
    """Extrai um inteiro de um quadro CAN (byte/máscara/shift do perfil)."""
    if not spec or data is None:
        return None
    raw = bytes(data)
    byte = int(spec.get("byte", 0))
    if byte < 0 or byte >= len(raw):
        return None
    mask = int(spec.get("mask", 0xFF))
    shift = int(spec.get("shift", 0))
    return (raw[byte] & mask) >> shift


def map_can_gear(value: int | None, mapping: dict | None) -> str | int | None:
    if value is None:
        return None
    mapping = mapping or {}
    # chaves podem ser int ou str
    if value in mapping:
        out = mapping[value]
    elif str(value) in mapping:
        out = mapping[str(value)]
    else:
        out = None
    if out is None:
        return None
    if isinstance(out, int):
        return out
    text = str(out).strip().upper()
    if text in PRNDL:
        return text
    if text.isdigit():
        return int(text)
    return text


def read_gpio_level(pin: int | None, active_low: bool = False) -> bool | None:
    if pin is None:
        return None
    level = gpio_reverse.poll_pin(int(pin))
    if level is None:
        return None
    return (not level) if active_low else bool(level)


def resolve_gpio(cfg: dict | None, pin_reader=None) -> str | int | None:
    """Lê o mapa de pinos do perfil (P/R/N/D/L ou 1–6) ou só o pino de ré."""
    prof = _profile(cfg)
    spec = prof.get("gear_gpio") or (cfg or {}).get("gear_gpio") or {}
    reader = pin_reader or (lambda pin, active_low=False: read_gpio_level(pin, active_low))
    default_low = bool(spec.get("active_low", False))
    pins = spec.get("pins") or {}
    # pins: { "P": 5, "R": 6, ... } ou { "R": {pin: 6, active_low: true} }
    for name in list(PRNDL) + [str(i) for i in range(1, 7)]:
        entry = pins.get(name) or pins.get(name.lower())
        if entry is None:
            continue
        if isinstance(entry, dict):
            pin, active_low = entry.get("pin"), entry.get("active_low", default_low)
        else:
            pin, active_low = entry, default_low
        if pin is None:
            continue
        try:
            on = reader(int(pin), bool(active_low))
        except TypeError:
            on = reader(int(pin))
        if on:
            return int(name) if name.isdigit() else name
    # atalho: só um pino de ré (reaproveita cameras.reverse_gpio se não houver mapa)
    rev = spec.get("reverse_pin")
    if rev is None:
        rev = ((cfg or {}).get("cameras") or {}).get("reverse_gpio")
    if rev is not None:
        try:
            on = reader(int(rev), bool(spec.get("reverse_active_low", default_low)))
        except TypeError:
            on = reader(int(rev))
        if on:
            return "R"
    return None


def resolve_can(cfg: dict | None, frame: dict | None) -> str | int | None:
    """frame = {id: int, data: bytes} — um quadro, ou lista deles."""
    prof = _profile(cfg)
    spec = prof.get("gear_can") or (cfg or {}).get("gear_can") or {}
    want = spec.get("id")
    if want is None:
        return None
    want = int(want)
    frames = frame if isinstance(frame, list) else ([frame] if frame else [])
    for fr in frames:
        if not fr:
            continue
        fid = fr.get("id") if isinstance(fr, dict) else None
        if fid is None:
            continue
        if int(fid) != want:
            continue
        data = fr.get("data") if isinstance(fr, dict) else None
        value = decode_can_value(data, spec)
        return map_can_gear(value, spec.get("map") or {})
    return None


def resolve_gear(
    cfg: dict | None,
    *,
    speed: float = 0.0,
    rpm: float = 0.0,
    reverse: bool = False,
    parking_brake: bool = False,
    can_frame=None,
    pin_reader=None,
) -> dict[str, Any]:
    """Resolve a marcha conforme gear_source do perfil.

    Retorna {value, source, kind} onde value é 'P'/'R'/'N'/'D'/'L' ou 1–6.
    """
    kind = gear_source_kind(cfg)
    source = kind
    value: str | int | None = None
    if kind == "can":
        value = resolve_can(cfg, can_frame)
        if value is None:
            # fallback seguro para não deixar o HUD em branco
            value = infer_prndl(speed=speed, rpm=rpm, reverse=reverse, parking_brake=parking_brake)
            source = "inferred"
    elif kind == "gpio":
        value = resolve_gpio(cfg, pin_reader=pin_reader)
        if value is None:
            value = infer_prndl(speed=speed, rpm=rpm, reverse=reverse, parking_brake=parking_brake)
            source = "inferred"
    else:
        trans = transmission_mode(cfg or {})
        if trans == "manual":
            ratios, final, circ = gear_params(cfg)
            value = infer_manual(
                speed=speed, rpm=rpm, reverse=reverse, parking_brake=parking_brake,
                ratios=ratios, final_drive=final, tire_circ=circ,
            )
        else:
            value = infer_prndl(speed=speed, rpm=rpm, reverse=reverse, parking_brake=parking_brake)
        source = "inferred"
    return {"value": value, "source": source, "kind": kind, "label": _label(value)}


def _label(value: str | int | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, int):
        return str(value)
    return str(value).upper()


class GearSource:
    """Publica `gear` e `gear_label` no store a cada tick do agendador."""

    def __init__(self, store, cfg: dict, can_source=None) -> None:
        self.store = store
        self.cfg = cfg
        self.can_source = can_source

    def bind_config(self, cfg: dict) -> None:
        self.cfg = cfg

    def _can_frames(self):
        src = self.can_source
        if src is None:
            return None
        for attr in ("last_frames", "recent_frames", "frames"):
            if hasattr(src, attr):
                return getattr(src, attr)
        if hasattr(src, "peek_frame"):
            return src.peek_frame()
        return None

    def tick(self) -> dict[str, Any]:
        speed = self.store.value("speed") or 0.0
        rpm = self.store.value("rpm") or 0.0
        reverse = bool(self.store.get_meta("reverse") or (self.store.value("reverse") or 0))
        parking = bool(self.store.value("parking_brake") or 0)
        out = resolve_gear(
            self.cfg,
            speed=float(speed),
            rpm=float(rpm),
            reverse=reverse,
            parking_brake=parking,
            can_frame=self._can_frames(),
        )
        self.store.update("gear", out["value"], "", "gear", "Marcha")
        self.store.update("gear_label", out["label"], "", "gear", "Marcha")
        self.store.set_meta("gear", out)
        prof = (self.cfg or {}).get("_profile") or {}
        drive = prof.get("drive") or (self.cfg or {}).get("drive") or "fwd"
        self.store.set_meta("drive", drive)
        trans = (prof.get("transmission") or (self.cfg or {}).get("transmission") or "cvt")
        self.store.set_meta("transmission", trans)
        return out

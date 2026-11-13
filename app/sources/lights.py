"""Fonte de luzes e telltales: simulador, GPIO (optacoplador) ou CAN.

Farol, seta, lanterna e freio de mão NÃO são PIDs OBD2. O check engine
(MIL) vem do Mode 01 PID 01 (meta `mil`). Veja o README para a fiação
do módulo PC817 (12 V → GPIO com segurança).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .. import gpio_reverse
from ..gear import decode_can_value

log = logging.getLogger(__name__)

# id estável → rótulo pt-BR do HUD
TELLTALES = (
    ("low_beam", "Farol baixo"),
    ("high_beam", "Farol alto"),
    ("parking_lights", "Lanterna"),
    ("turn_left", "Seta esquerda"),
    ("turn_right", "Seta direita"),
    ("parking_brake", "Freio de mão"),
    ("check_engine", "Check engine"),
    ("door_open", "Porta aberta"),
    ("seatbelt", "Cinto"),
)

TELLTALE_IDS = tuple(t[0] for t in TELLTALES)

# aliases aceitos no YAML / store
_ALIASES = {
    "lowbeam": "low_beam",
    "headlights": "low_beam",
    "headlight": "low_beam",
    "dipped": "low_beam",
    "highbeam": "high_beam",
    "fullbeam": "high_beam",
    "lanterna": "parking_lights",
    "parking": "parking_lights",
    "position": "parking_lights",
    "sidelight": "parking_lights",
    "left": "turn_left",
    "right": "turn_right",
    "handbrake": "parking_brake",
    "brake_park": "parking_brake",
    "mil": "check_engine",
    "cel": "check_engine",
    "door": "door_open",
    "doors": "door_open",
    "seatbelt_off": "seatbelt",  # lâmpada acende com o cinto solto
    "belt": "seatbelt",
}


def canonical(name: str) -> str | None:
    key = str(name or "").strip().lower()
    if key in TELLTALE_IDS:
        return key
    return _ALIASES.get(key)


def lights_config(cfg: dict | None) -> dict:
    return dict((cfg or {}).get("lights") or {})


def lights_backend(cfg: dict | None) -> str:
    """sim | gpio | can. `auto` escolhe conforme a fonte do veículo e os pinos."""
    cfg = cfg or {}
    raw = str((lights_config(cfg).get("source") or "auto")).strip().lower()
    if raw in {"sim", "simulator"}:
        return "sim"
    if raw in {"gpio", "can"}:
        return raw
    # auto
    if str(cfg.get("source") or "").lower() in {"simulator", "sim", ""}:
        return "sim"
    pins = (lights_config(cfg).get("gpio") or {})
    if pins:
        return "gpio"
    if lights_config(cfg).get("can"):
        return "can"
    return "gpio"


def unused_mode(ui_or_cfg: dict | None) -> str:
    ui = (ui_or_cfg or {}).get("ui") if "ui" in (ui_or_cfg or {}) else (ui_or_cfg or {})
    lights = lights_config(ui_or_cfg if "lights" in (ui_or_cfg or {}) else {})
    raw = str((ui or {}).get("unused_telltales") or lights.get("unused") or "dim").lower()
    return "hide" if raw in {"hide", "hidden", "off"} else "dim"


def decode_can_telltale(data: bytes | list[int], spec: dict) -> bool | None:
    value = decode_can_value(data, spec)
    if value is None:
        return None
    # bit presente (máscara já aplicada) → ligado
    return bool(value)


def read_gpio_telltale(spec: dict, pin_reader=None) -> bool | None:
    if not spec:
        return None
    pin = spec.get("pin") if isinstance(spec, dict) else spec
    if pin is None:
        return None
    active_low = bool(spec.get("active_low", True)) if isinstance(spec, dict) else True
    reader = pin_reader or (lambda p, low=False: _default_reader(p, low))
    try:
        return reader(int(pin), active_low)
    except TypeError:
        level = reader(int(pin))
        if level is None:
            return None
        return (not level) if active_low else bool(level)


def _default_reader(pin: int, active_low: bool) -> bool | None:
    # gpiozero, se existir (no Pi); senão sysfs / gpiod via gpio_reverse.
    try:
        from gpiozero import DigitalInputDevice  # type: ignore

        dev = DigitalInputDevice(int(pin), pull_up=active_low)
        try:
            val = bool(dev.value)
        finally:
            try:
                dev.close()
            except Exception:
                pass
        return val
    except Exception:
        pass
    level = gpio_reverse.poll_pin(int(pin))
    if level is None:
        return None
    return (not level) if active_low else bool(level)


def configured_ids(cfg: dict | None, backend: str | None = None) -> set[str]:
    """Telltales que têm fonte configurada (mais o MIL, sempre que houver OBD/sim)."""
    backend = backend or lights_backend(cfg)
    if backend == "sim":
        return set(TELLTALE_IDS)
    out: set[str] = set()
    block = lights_config(cfg).get(backend) or {}
    signals = block.get("signals") if isinstance(block, dict) else None
    src = signals if isinstance(signals, dict) else block
    if isinstance(src, dict):
        for name, spec in src.items():
            if name in {"id", "signals"}:
                continue
            key = canonical(name)
            if not key or spec in (None, False):
                continue
            if isinstance(spec, dict) and spec.get("pin") is None and spec.get("byte") is None and spec.get("mask") is None:
                continue
            out.add(key)
    # MIL vem do OBD, independente do backend
    out.add("check_engine")
    return out


def snapshot_from_store(store, cfg: dict | None = None) -> dict[str, Any]:
    backend = lights_backend(cfg)
    configured = configured_ids(cfg, backend)
    values = {}
    for key in TELLTALE_IDS:
        if key == "check_engine":
            values[key] = bool(store.get_meta("mil") or store.value("check_engine") or 0)
            continue
        raw = store.value(key)
        if raw is None and key == "low_beam":
            raw = store.value("headlights")
        values[key] = bool(raw) if raw is not None else False
    return {
        "backend": backend,
        "unused": unused_mode(cfg),
        "configured": sorted(configured),
        "values": values,
    }


class LightsSource:
    """Atualiza os sinais de luz no store. Tick no agendador (sem thread extra)."""

    def __init__(self, store, cfg: dict, can_source=None, pin_reader: Callable | None = None) -> None:
        self.store = store
        self.cfg = cfg
        self.can_source = can_source
        self.pin_reader = pin_reader
        self.backend = lights_backend(cfg)

    def bind_config(self, cfg: dict) -> None:
        self.cfg = cfg
        self.backend = lights_backend(cfg)

    def _can_frames(self):
        src = self.can_source
        if src is None:
            return []
        for attr in ("last_frames", "recent_frames", "frames"):
            if hasattr(src, attr):
                val = getattr(src, attr)
                if isinstance(val, list):
                    return val
                if val:
                    return [val]
        return []

    def _from_sim(self) -> dict[str, bool]:
        def flag(key: str, *alts: str) -> bool:
            for k in (key,) + alts:
                v = self.store.value(k)
                if v is not None:
                    return bool(v)
            if key == "check_engine":
                return bool(self.store.get_meta("mil"))
            return False

        return {
            "low_beam": flag("low_beam", "headlights"),
            "high_beam": flag("high_beam"),
            "parking_lights": flag("parking_lights"),
            "turn_left": flag("turn_left"),
            "turn_right": flag("turn_right"),
            "parking_brake": flag("parking_brake"),
            "check_engine": flag("check_engine"),
            "door_open": flag("door_open"),
            "seatbelt": flag("seatbelt", "seatbelt_off"),
        }

    def _from_gpio(self) -> dict[str, bool | None]:
        pins = lights_config(self.cfg).get("gpio") or {}
        signals = pins.get("signals") if isinstance(pins.get("signals"), dict) else pins
        out: dict[str, bool | None] = {k: None for k in TELLTALE_IDS}
        for name, spec in (signals or {}).items():
            if name in {"id", "signals"}:
                continue
            key = canonical(name)
            if not key:
                continue
            out[key] = read_gpio_telltale(spec, self.pin_reader)
        out["check_engine"] = bool(self.store.get_meta("mil"))
        return out

    def _from_can(self) -> dict[str, bool | None]:
        spec = lights_config(self.cfg).get("can") or {}
        want = spec.get("id")
        signals = spec.get("signals") or {k: v for k, v in spec.items() if k != "id"}
        out: dict[str, bool | None] = {k: None for k in TELLTALE_IDS}
        data = None
        if want is not None:
            for fr in self._can_frames():
                if fr and int(fr.get("id", -1)) == int(want):
                    data = fr.get("data")
                    break
        if data is not None:
            raw = bytes(data)
            for name, sig in signals.items():
                key = canonical(name)
                if not key or not isinstance(sig, dict):
                    continue
                bit = decode_can_telltale(raw, sig)
                if bit is not None:
                    out[key] = bit
        out["check_engine"] = bool(self.store.get_meta("mil"))
        return out

    def tick(self) -> dict[str, Any]:
        if self.backend == "gpio":
            values = self._from_gpio()
        elif self.backend == "can":
            values = self._from_can()
        else:
            values = self._from_sim()
        labels = dict(TELLTALES)
        for key, on in values.items():
            if on is None:
                continue
            self.store.update(key, 1.0 if on else 0.0, "", "lights", labels.get(key, key))
        snap = snapshot_from_store(self.store, self.cfg)
        # sobrescreve values com o que este tick apurou (inclui None = sem leitura)
        merged = dict(snap["values"])
        for key, on in values.items():
            if on is not None:
                merged[key] = bool(on)
        snap["values"] = merged
        self.store.set_meta("lights", snap)
        return snap

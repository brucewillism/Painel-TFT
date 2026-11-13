"""Tema HUD, presets de cor de destaque e resolução da cor efetiva."""

from __future__ import annotations

from typing import Any

# Reator arc (padrão): ciano "arc reactor" com brilho branco-quente.
ACCENT_PRESETS: dict[str, dict[str, str]] = {
    "arc": {"hex": "#00D8FF", "label": "Reator arc"},
    "red": {"hex": "#E10600", "label": "Vermelho"},
    "matrix": {"hex": "#00FF6A", "label": "Verde Matrix"},
    "amber": {"hex": "#FFB000", "label": "Âmbar"},
    "violet": {"hex": "#B14CFF", "label": "Roxo"},
    "white": {"hex": "#F4FBFF", "label": "Branco"},
}

DEFAULT_THEME = "hud"  # hud | classic  (classic = "Clássico vermelho")
DEFAULT_ACCENT = "arc"
DEFAULT_ACCENT_HEX = ACCENT_PRESETS[DEFAULT_ACCENT]["hex"]

_ACCENT_ALIASES = {
    "cyan": "arc",
    "blue": "arc",
    "reactor": "arc",
    "crimson": "red",
    "orange": "amber",
    "green": "matrix",
    "purple": "violet",
    "roxo": "violet",
}

_THEME_ALIASES = {
    "classic-red": "classic",
    "classico": "classic",
    "clássico": "classic",
    "vermelho": "classic",
    "red-classic": "classic",
    "dark": "hud",
    "wireframe": "hud",
    "reactor": "hud",
}


def normalize_hex(value: str | None, fallback: str = DEFAULT_ACCENT_HEX) -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    if not raw.startswith("#"):
        raw = "#" + raw
    raw = raw.upper()
    if len(raw) == 4 and all(c in "0123456789ABCDEF#" for c in raw):
        raw = "#" + "".join(ch * 2 for ch in raw[1:])
    if len(raw) != 7 or any(c not in "0123456789ABCDEF#" for c in raw):
        return fallback
    return raw


def normalize_theme(value: str | None) -> str:
    theme = str(value or DEFAULT_THEME).strip().lower()
    theme = _THEME_ALIASES.get(theme, theme)
    return "classic" if theme == "classic" else "hud"


def resolve_accent(ui: dict[str, Any] | None) -> tuple[str, str]:
    """Retorna (id do preset ou 'custom', hex #RRGGBB)."""
    ui = ui or {}
    acc = str(ui.get("accent") or DEFAULT_ACCENT).strip().lower()
    acc = _ACCENT_ALIASES.get(acc, acc)
    hex_in = ui.get("accent_hex")
    if acc in ACCENT_PRESETS:
        preset_hex = ACCENT_PRESETS[acc]["hex"].upper()
        if hex_in:
            hx = normalize_hex(str(hex_in), preset_hex)
            if hx != preset_hex:
                return "custom", hx
        return acc, preset_hex
    if hex_in:
        hx = normalize_hex(str(hex_in))
        for key, meta in ACCENT_PRESETS.items():
            if meta["hex"].upper() == hx:
                return key, hx
        return "custom", hx
    if acc == "custom":
        return "custom", normalize_hex(None)
    return DEFAULT_ACCENT, DEFAULT_ACCENT_HEX


def apply_defaults(ui: dict[str, Any] | None) -> dict[str, Any]:
    """Preenche theme/accent/hud_rotate/unused_telltales sem apagar escolhas existentes."""
    out = dict(ui or {})
    out["theme"] = normalize_theme(out.get("theme") or DEFAULT_THEME)
    acc, hx = resolve_accent(out)
    out["accent"], out["accent_hex"] = acc, hx
    if "hud_rotate" not in out:
        out["hud_rotate"] = True
    unused = str(out.get("unused_telltales") or "dim").lower()
    out["unused_telltales"] = "hide" if unused in {"hide", "hidden", "off"} else "dim"
    return out

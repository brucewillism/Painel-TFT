"""Iluminação ambiente WS2812/WS2815 via GPIO (rpi_ws281x) ou preview no simulador."""

from __future__ import annotations

import colorsys
import logging
import time
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)

# Pino GPIO18 (PWM0) é o padrão do rpi_ws281x. WS2815 aceita o mesmo protocolo.
# Use transmissor de nível 3V3→5V (74AHCT125) e fonte 5V dedicada para a fita.


class AmbientLeds:
    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = cfg.get("leds") or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.count = int(self.cfg.get("count", 30))
        self.pin = int(self.cfg.get("pin", 18))
        self.brightness = float(self.cfg.get("brightness", 0.4))
        self.mode = self.cfg.get("mode") or "rpm"  # rpm, music, alerts, static, off
        self.static = self.cfg.get("static_color") or "#e10600"
        self.pixels: list[tuple[int, int, int]] = [(0, 0, 0)] * self.count
        self.strip = None
        self._hw = False
        self._init_hw()

    def _init_hw(self) -> None:
        try:
            from rpi_ws281x import PixelStrip, Color  # type: ignore
            brightness = int(max(0, min(255, self.brightness * 255)))
            strip = PixelStrip(self.count, self.pin, 800000, 10, False, brightness, 0)
            strip.begin()
            self.strip = strip
            self.Color = Color
            self._hw = True
            log.info("rpi_ws281x: %s LEDs no GPIO %s", self.count, self.pin)
        except Exception as exc:
            log.info("LEDs em modo preview (sem rpi_ws281x): %s", exc)
            self._hw = False

    def set_mode(self, mode: str, color: str | None = None, brightness: float | None = None) -> dict:
        if mode in {"rpm", "music", "alerts", "static", "off"}:
            self.mode = mode
        if color:
            self.static = color
        if brightness is not None:
            self.brightness = max(0.0, min(1.0, float(brightness)))
        return self.snapshot()

    def tick(self, audio_level: float | None = None) -> dict:
        if not self.enabled or self.mode == "off":
            self.pixels = [(0, 0, 0)] * self.count
            self._push()
            return self.snapshot()
        if self.mode == "static":
            c = _hex(self.static)
            self.pixels = [c] * self.count
        elif self.mode == "rpm":
            self.pixels = self._rpm()
        elif self.mode == "music":
            lvl = audio_level if audio_level is not None else float(self.store.get_meta("media_level") or 0.3)
            self.pixels = self._music(lvl)
        elif self.mode == "alerts":
            self.pixels = self._alerts()
        self._push()
        snap = self.snapshot()
        self.store.set_meta("leds", snap)
        return snap

    def _rpm(self) -> list[tuple[int, int, int]]:
        rpm = float(self.store.value("rpm") or 0)
        frac = max(0.0, min(1.0, rpm / 6500.0))
        n = int(round(frac * self.count))
        out = []
        for i in range(self.count):
            if i >= n:
                out.append((0, 0, 0))
                continue
            # verde → amarelo → vermelho
            t = i / max(1, self.count - 1)
            if t < 0.6:
                out.append((int(255 * t / 0.6), 200, 0) if t > 0.4 else (0, 200, 40))
            else:
                out.append((255, int(80 * (1 - (t - 0.6) / 0.4)), 0))
        return out

    def _music(self, level: float) -> list[tuple[int, int, int]]:
        level = max(0.0, min(1.0, level))
        n = int(round(level * self.count))
        hue = (time.time() * 0.15) % 1.0
        out = []
        for i in range(self.count):
            if i >= n:
                out.append((0, 0, 0))
                continue
            r, g, b = colorsys.hsv_to_rgb((hue + i / self.count) % 1.0, 0.9, 0.9)
            out.append((int(r * 255), int(g * 255), int(b * 255)))
        return out

    def _alerts(self) -> list[tuple[int, int, int]]:
        alerts = self.store.get_meta("alerts") or []
        if alerts:
            on = int(time.time() * 4) % 2 == 0
            c = (255, 0, 0) if on else (40, 0, 0)
            return [c] * self.count
        return [_hex(self.static)] * self.count

    def _push(self) -> None:
        if not self._hw or not self.strip:
            return
        b = max(0.0, min(1.0, self.brightness))
        for i, (r, g, b_) in enumerate(self.pixels):
            self.strip.setPixelColor(i, self.Color(int(r * b), int(g * b), int(b_ * b)))
        try:
            self.strip.show()
        except Exception:
            pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "hw": self._hw,
            "count": self.count,
            "pin": self.pin,
            "brightness": self.brightness,
            "mode": self.mode,
            "static_color": self.static,
            "pixels": [list(p) for p in self.pixels],
        }


def _hex(s: str) -> tuple[int, int, int]:
    s = (s or "#e10600").lstrip("#")
    if len(s) != 6:
        return (225, 6, 0)
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))

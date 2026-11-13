"""Leitura do sinal de ré (GPIO BCM). Desligado se o pino não estiver configurado.

Tenta, nesta ordem:
  1. libgpiod / gpiod (Pi OS recente)
  2. sysfs (/sys/class/gpio) — legado
  3. None se não houver hardware (simulador, ou o pino ainda não foi ligado)
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_exported: set[int] = set()


def poll_pin(bcm: int) -> bool | None:
    if bcm is None:
        return None
    val = _gpiod(bcm)
    if val is not None:
        return val
    return _sysfs(bcm)


def _gpiod(bcm: int) -> bool | None:
    try:
        import gpiod  # type: ignore
    except ImportError:
        return None
    try:
        # libgpiod 2.x
        if hasattr(gpiod, "request_lines"):
            req = gpiod.request_lines(
                "/dev/gpiochip0",
                consumer="lancer-painel",
                config={bcm: gpiod.LineSettings(direction=gpiod.line.Direction.INPUT)},
            )
            vals = req.get_values()
            req.release()
            return bool(list(vals)[0])
        # libgpiod 1.x
        chip = gpiod.Chip("gpiochip0")
        line = chip.get_line(bcm)
        line.request(consumer="lancer-painel", type=gpiod.LINE_REQ_DIR_IN)
        val = bool(line.get_value())
        line.release()
        chip.close()
        return val
    except Exception as exc:
        log.debug("gpiod pino %s: %s", bcm, exc)
        return None


def _sysfs(bcm: int) -> bool | None:
    base = Path("/sys/class/gpio")
    if not base.is_dir():
        return None
    pin = base / f"gpio{bcm}"
    try:
        if not pin.is_dir() and bcm not in _exported:
            export = base / "export"
            if export.is_file():
                export.write_text(str(bcm))
                _exported.add(bcm)
            direction = pin / "direction"
            if direction.is_file():
                direction.write_text("in")
        value = pin / "value"
        if not value.is_file():
            return None
        return value.read_text().strip() == "1"
    except OSError as exc:
        log.debug("sysfs GPIO %s: %s", bcm, exc)
        return None

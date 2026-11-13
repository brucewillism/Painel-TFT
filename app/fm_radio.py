"""Rádio FM opcional via dongle RTL-SDR (rtl_fm) + presets."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_PRESETS = [
    {"name": "CBN SP", "mhz": 90.5},
    {"name": "Jovem Pan", "mhz": 100.9},
    {"name": "Band FM", "mhz": 96.1},
    {"name": "Mix FM", "mhz": 106.3},
    {"name": "USP FM", "mhz": 93.7},
]


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


class FmRadio:
    def __init__(self, cfg: dict) -> None:
        radio = (cfg.get("media") or {}).get("fm") or {}
        self.enabled = bool(radio.get("enabled", True))
        self.presets = list(radio.get("presets") or DEFAULT_PRESETS)
        self.mhz = float(radio.get("mhz", self.presets[0]["mhz"] if self.presets else 90.5))
        self.playing = False
        self._proc: subprocess.Popen | None = None
        self.device_present = _rtl_present()

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "device_present": self.device_present,
            "backend": "rtl_fm" if (_which("rtl_fm") and self.device_present) else "mock",
            "mhz": round(self.mhz, 1),
            "playing": self.playing,
            "presets": self.presets,
        }

    def tune(self, mhz: float, play: bool | None = None) -> dict[str, Any]:
        self.mhz = max(76.0, min(108.0, float(mhz)))
        if play is True or (play is None and self.playing):
            self._restart()
            self.playing = True
        return self.snapshot()

    def play(self) -> dict[str, Any]:
        self._restart()
        self.playing = True
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        self._kill()
        self.playing = False
        return self.snapshot()

    def _restart(self) -> None:
        self._kill()
        rtl = _which("rtl_fm")
        play = _which("play") or _which("ffplay") or _which("aplay")
        if not rtl or not self.device_present:
            # mock: nada a reproduzir, a UI só mostra a frequência
            return
        freq = f"{self.mhz:.1f}M"
        try:
            # rtl_fm → raw PCM 16-bit → play/ffplay
            fm = subprocess.Popen(
                [rtl, "-f", freq, "-M", "wbfm", "-s", "200000", "-r", "48000", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if play and play.endswith("ffplay"):
                out = subprocess.Popen(
                    ["ffplay", "-nodisp", "-loglevel", "quiet", "-f", "s16le", "-ar", "48000", "-ac", "1", "-"],
                    stdin=fm.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif play and "play" in play:
                out = subprocess.Popen(
                    [play, "-q", "-t", "raw", "-r", "48000", "-e", "signed", "-b", "16", "-c", "1", "-"],
                    stdin=fm.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                out = None
            self._proc = out or fm
        except Exception as exc:
            log.warning("rtl_fm falhou: %s", exc)

    def _kill(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.terminate()
            self._proc.wait(timeout=1)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def shutdown(self) -> None:
        self.stop()


def _rtl_present() -> bool:
    # dongle RTL2832U aparece como 0bda:2838 (e variantes)
    root = __import__("pathlib").Path("/sys/bus/usb/devices")
    if not root.is_dir():
        return False
    for d in root.iterdir():
        vid, pid = d / "idVendor", d / "idProduct"
        if vid.is_file() and pid.is_file():
            try:
                if vid.read_text().strip().lower() == "0bda" and pid.read_text().strip().lower().startswith("283"):
                    return True
            except OSError:
                continue
    return bool(_which("rtl_test"))

"""Shift light e alertas sonoros de RPM (modo Sport/manual do CVT)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)


class ShiftAlerts:
    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = (cfg.get("shift") or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.points = list(self.cfg.get("rpm_points") or [4500, 5200, 5800, 6200])
        self.mode = self.cfg.get("mode") or "bar+beep"  # bar, beep, voice, bar+beep, bar+voice
        self.audio = bool(self.cfg.get("audio", True))
        self._last_level = -1
        self._last_beep = 0.0
        self._paplay = shutil.which("paplay") or shutil.which("aplay") or shutil.which("ffplay")

    def set_points(self, points: list[int]) -> list[int]:
        pts = sorted(int(p) for p in points if p)
        if pts:
            self.points = pts
        return self.points

    def tick(self) -> dict:
        rpm = float(self.store.value("rpm") or 0)
        level = 0
        for i, p in enumerate(self.points, 1):
            if rpm >= p:
                level = i
        if self.enabled and self.audio and "beep" in self.mode and level >= len(self.points) and level != self._last_level:
            self._beep(urgent=True)
        elif self.enabled and self.audio and "beep" in self.mode and level >= max(1, len(self.points) - 1):
            now = time.time()
            gap = 0.18 if level >= len(self.points) else 0.35
            if now - self._last_beep >= gap:
                self._beep(urgent=level >= len(self.points))
        if self.enabled and self.audio and "voice" in self.mode and level >= len(self.points) and level != self._last_level:
            self._voice("troque de marcha")
        self._last_level = level
        snap = {
            "enabled": self.enabled,
            "points": self.points,
            "mode": self.mode,
            "audio": self.audio,
            "rpm": rpm,
            "level": level,
            "max_level": len(self.points),
        }
        self.store.set_meta("shift", snap)
        return snap

    def _beep(self, urgent: bool = False) -> None:
        self._last_beep = time.time()
        # tom gerado por paplay/ffplay se houver; senão só o estado visual
        if not self._paplay:
            return

        def _run():
            try:
                freq = 1400 if urgent else 880
                if "ffplay" in (self._paplay or ""):
                    subprocess.run(
                        [self._paplay, "-nodisp", "-autoexit", "-loglevel", "quiet",
                         "-f", "lavfi", f"sine=frequency={freq}:duration=0.08"],
                        check=False, timeout=1,
                    )
                else:
                    # gera wav curto via python se possível — skip se não
                    pass
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _voice(self, text: str) -> None:
        espeak = shutil.which("espeak") or shutil.which("espeak-ng")
        if not espeak:
            return

        def _run():
            try:
                subprocess.run([espeak, "-v", "pt-br", "-s", "160", text], check=False, timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def snapshot(self) -> dict[str, Any]:
        return self.store.get_meta("shift") or self.tick()

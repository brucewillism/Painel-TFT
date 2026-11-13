"""Integração com dongle USB Carlinkit (CarPlay / Android Auto).

Não embutimos o protocolo da Apple/Google: usamos um driver de código
aberto (node-CarPlay / react-carplay) que fala com o dongle. Este módulo:

  * detecta o dongle na USB
  * lança/encerra o visualizador em tela cheia
  * devolve status para o tile “CarPlay” do painel
  * no simulador (sem dongle) oferece um mock da central

Áudio e microfone: veja o README (roteamento PipeWire/ALSA).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# IDs USB mais comuns em dongles Carlinkit / Autokit / “CPC200-CCPA”.
# Confira o seu com:  lsusb
KNOWN_DONGLES = {
    ("1314", "1520"): "Carlinkit / Autokit",
    ("1314", "1521"): "Carlinkit",
    ("1314", "1522"): "Carlinkit 5.0",
    ("08e9", "0001"): "Carlinkit (var.)",
}


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


def list_usb() -> list[dict[str, str]]:
    devs = []
    root = Path("/sys/bus/usb/devices")
    if not root.is_dir():
        return devs
    for d in root.iterdir():
        vid_f, pid_f = d / "idVendor", d / "idProduct"
        if not (vid_f.is_file() and pid_f.is_file()):
            continue
        try:
            vid = vid_f.read_text().strip().lower()
            pid = pid_f.read_text().strip().lower()
        except OSError:
            continue
        name = KNOWN_DONGLES.get((vid, pid))
        if name:
            devs.append({"vendor": vid, "product": pid, "name": name, "path": str(d)})
    return devs


class CarPlayManager:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg.get("carplay") or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        from .config import ROOT
        self.root = ROOT
        self.launch_script = Path(self.cfg.get("launch", ROOT / "scripts" / "carplay-launch.sh"))
        if not self.launch_script.is_absolute():
            self.launch_script = ROOT / self.launch_script
        self._proc: subprocess.Popen | None = None
        self._started = 0.0

    def status(self) -> dict[str, Any]:
        dongles = list_usb()
        running = bool(self._proc and self._proc.poll() is None)
        driver = self._driver_installed()
        return {
            "enabled": self.enabled,
            "dongle": dongles[0] if dongles else None,
            "dongles": dongles,
            "connected": bool(dongles),
            "driver_installed": driver,
            "running": running,
            "started_at": self._started if running else None,
            "mode": "carplay" if (dongles or running) else "mock",
        }

    def _driver_installed(self) -> bool:
        # node-carplay típico, se o usuário rodou scripts/install-carplay.sh
        candidates = [
            self.root / "vendor" / "node-carplay",
            self.root / "vendor" / "react-carplay",
            Path.home() / "node-carplay",
        ]
        return any(p.is_dir() for p in candidates) or bool(_which("carplay"))

    def launch(self) -> dict[str, Any]:
        if self._proc and self._proc.poll() is None:
            return self.status()
        script = self.launch_script
        env = os.environ.copy()
        env.setdefault("DISPLAY", self.cfg.get("display", ":0"))
        env["LANCER_ROOT"] = str(self.root)
        if script.is_file():
            try:
                self._proc = subprocess.Popen(
                    ["bash", str(script)],
                    cwd=str(self.root),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._started = time.time()
            except Exception as exc:
                log.warning("Falha ao lançar CarPlay: %s", exc)
        return self.status()

    def stop(self) -> dict[str, Any]:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.send_signal(signal.SIGTERM)
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
        self._started = 0
        return self.status()

    def shutdown(self) -> None:
        self.stop()

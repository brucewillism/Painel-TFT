"""Telefone mãos-livres: HFP (oFono/BlueZ), agenda PBAP e registro de chamadas.

No simulador (e quando o oFono não está no ar) a agenda, o registro e as
chamadas são mock — suficientes para a UI de central multimídia. No carro,
o módulo tenta:
  - oFono (org.ofono) para discar / atender / encerrar (HFP)
  - PBAP via obex ou oFono PhonebookAccess para a agenda
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

log = logging.getLogger(__name__)

_MOCK_CONTACTS = [
    {"name": "Ana Souza", "number": "+55 11 98888-1001", "kind": "mobile"},
    {"name": "Bruno Lima", "number": "+55 11 97777-2002", "kind": "mobile"},
    {"name": "Oficina do HL", "number": "+55 11 4004-3003", "kind": "work"},
    {"name": "Casa", "number": "+55 11 3333-4004", "kind": "home"},
    {"name": "Carla Mendes", "number": "+55 21 98888-5005", "kind": "mobile"},
]

_MOCK_LOG = [
    {"name": "Ana Souza", "number": "+55 11 98888-1001", "dir": "in", "ts": 0, "duration": 92},
    {"name": "Oficina do HL", "number": "+55 11 4004-3003", "dir": "out", "ts": 0, "duration": 180},
    {"name": "Bruno Lima", "number": "+55 11 97777-2002", "dir": "missed", "ts": 0, "duration": 0},
]


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


class Phone:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg.get("phone") or {}
        self.enabled = bool(self.cfg.get("enabled", True))
        now = time.time()
        self.contacts = [dict(c) for c in _MOCK_CONTACTS]
        self.log = []
        for i, row in enumerate(_MOCK_LOG):
            item = dict(row)
            item["ts"] = now - (i + 1) * 3600
            self.log.append(item)
        self.call: dict[str, Any] | None = None  # {number, name, dir, started, state}
        self.source = "mock"  # mock | ofono | bluez
        self._detect()

    def _detect(self) -> None:
        if _which("busctl"):
            try:
                r = subprocess.run(
                    ["busctl", "--system", "tree", "org.ofono"],
                    capture_output=True, text=True, timeout=1,
                )
                if r.returncode == 0 and "/" in r.stdout:
                    self.source = "ofono"
                    return
            except Exception:
                pass
        # BlueZ sozinho não faz HFP completo; oFono é o caminho suportado.

    def snapshot(self) -> dict[str, Any]:
        call = None
        if self.call:
            call = dict(self.call)
            if call.get("started"):
                call["elapsed"] = int(time.time() - call["started"])
        return {
            "enabled": self.enabled,
            "source": self.source,
            "contacts": self.contacts,
            "log": self.log[:30],
            "call": call,
        }

    def _lookup(self, number: str) -> str:
        digits = _digits(number)
        for c in self.contacts:
            if _digits(c["number"]) == digits:
                return c["name"]
        return number

    def dial(self, number: str) -> dict[str, Any]:
        number = (number or "").strip()
        if not number:
            raise ValueError("Número vazio")
        self.call = {
            "number": number,
            "name": self._lookup(number),
            "dir": "out",
            "state": "dialing",
            "started": time.time(),
        }
        self._ofono("Dial", number)
        # no mock, após um instante a chamada “atende”
        self.call["state"] = "active"
        return self.snapshot()

    def incoming(self, number: str | None = None, name: str | None = None) -> dict[str, Any]:
        number = number or _MOCK_CONTACTS[0]["number"]
        self.call = {
            "number": number,
            "name": name or self._lookup(number),
            "dir": "in",
            "state": "ringing",
            "started": time.time(),
        }
        return self.snapshot()

    def answer(self) -> dict[str, Any]:
        if not self.call:
            raise ValueError("Nenhuma chamada")
        self.call["state"] = "active"
        self.call["started"] = time.time()
        self._ofono("Answer")
        return self.snapshot()

    def hangup(self) -> dict[str, Any]:
        if self.call:
            duration = int(time.time() - self.call.get("started", time.time()))
            state = self.call.get("state")
            direction = "missed" if (self.call.get("dir") == "in" and state == "ringing") else self.call.get("dir", "out")
            self.log.insert(0, {
                "name": self.call.get("name"),
                "number": self.call.get("number"),
                "dir": direction,
                "ts": time.time(),
                "duration": duration if state == "active" else 0,
            })
        self._ofono("Hangup")
        self.call = None
        return self.snapshot()

    def reject(self) -> dict[str, Any]:
        return self.hangup()

    def _ofono(self, method: str, number: str | None = None) -> None:
        if self.source != "ofono":
            return
        busctl = _which("busctl")
        if not busctl:
            return
        try:
            # Caminho típico: /hfp/org/bluez/hci0/dev_XX_XX_...  — descoberto no tree
            tree = subprocess.run(
                [busctl, "--system", "tree", "org.ofono"],
                capture_output=True, text=True, timeout=1,
            )
            path = None
            for line in tree.stdout.splitlines():
                if "/hfp/" in line or "/ril_" in line or "dev_" in line:
                    for part in line.split():
                        if part.startswith("/"):
                            path = part
                            break
            if not path:
                return
            args = [busctl, "--system", "call", "org.ofono", path, "org.ofono.VoiceCallManager", method]
            if number and method == "Dial":
                args += ["ss", number, "default"]
            subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception as exc:
            log.debug("oFono %s: %s", method, exc)


def _digits(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit())

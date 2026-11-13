"""Agendador de polling com prioridade: RPM/velocidade primeiro, o resto rotaciona.

Clones ELM327 v2.1 sustentam só uns 3–8 PIDs/s no total. Por isso os PIDs
rápidos (RPM, velocidade) são lidos em quase todos os ciclos, os médios
com menor frequência, e os lentos um de cada vez em rodízio.
"""

from __future__ import annotations

import logging
import threading
import time

from . import alerts, cvt_uds
from .derived import DerivedComputer
from .signals import FAST_KEYS, MEDIUM_KEYS, SIGNALS, SLOW_KEYS, key_for_pid
from .sources.base import VehicleSource
from .store import DataStore

log = logging.getLogger(__name__)


class PollScheduler:
    def __init__(self, store: DataStore, source: VehicleSource, derived: DerivedComputer, cfg: dict) -> None:
        self.store = store
        self.source = source
        self.derived = derived
        self.cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._slow_index = 0
        self._cycle = 0
        self._fast: list[int] = []
        self._medium: list[int] = []
        self._slow: list[int] = []
        self.gear = None
        self.lights = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="obd-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def rebuild_queues(self) -> None:
        supported = self.source.supported_pids
        def pids_for(keys: list[str]) -> list[int]:
            out = []
            for key in keys:
                sig = SIGNALS.get(key)
                if sig and sig.pid in supported:
                    out.append(sig.pid)
            return out

        self._fast = pids_for(FAST_KEYS)
        self._medium = pids_for(MEDIUM_KEYS)
        self._slow = pids_for(SLOW_KEYS)
        # qualquer PID suportado que não esteja nas listas entra no rodízio lento
        known = set(self._fast + self._medium + self._slow)
        extra = []
        for pid in sorted(supported):
            if pid in known:
                continue
            if key_for_pid(pid) is None:
                continue
            extra.append(pid)
        self._slow.extend(extra)
        log.info(
            "Filas de polling: fast=%s medium=%s slow=%s",
            [f"{p:02X}" for p in self._fast],
            [f"{p:02X}" for p in self._medium],
            [f"{p:02X}" for p in self._slow],
        )

    def _publish(self, pid: int, value: float | None, source_name: str) -> None:
        if value is None:
            return
        sig = None
        for s in SIGNALS.values():
            if s.pid == pid:
                sig = s
                break
        if sig is None:
            return
        self.store.update(sig.key, value, sig.unit, source_name, sig.label_pt)

    def _loop(self) -> None:
        dtc_every = float(self.cfg.get("scheduler", {}).get("dtc_interval_s", 20))
        last_dtc = 0.0
        last_voltage = 0.0
        last_cvt = 0.0
        while not self._stop.is_set():
            if not self.source.connected:
                if self._stop.wait(0.5):
                    break
                continue
            budget = max(1.0, float(self.source.poll_budget_per_s))
            slot = 1.0 / budget
            t0 = time.time()
            used = 0

            # 1) todos os PIDs rápidos
            for pid in self._fast:
                val = self.source.read_pid(pid)
                self._publish(pid, val, self.source.name)
                used += 1

            # 2) um PID médio por ciclo (rodízio)
            if self._medium:
                pid = self._medium[self._cycle % len(self._medium)]
                val = self.source.read_pid(pid)
                self._publish(pid, val, self.source.name)
                used += 1

            # 3) um (ou mais, se ainda houver orçamento) PID lento
            remaining = max(1, int(budget) - used)
            if self._slow:
                for _ in range(remaining):
                    pid = self._slow[self._slow_index % len(self._slow)]
                    self._slow_index += 1
                    val = self.source.read_pid(pid)
                    self._publish(pid, val, self.source.name)
                    used += 1

            # 4) tensão da bateria (ATRV) com baixa frequência
            now = time.time()
            if now - last_voltage > 1.5:
                volt = self.source.read_battery_voltage()
                if volt is not None:
                    self.store.update("battery_voltage", round(volt, 2), "V", self.source.name, "Tensão da bateria")
                last_voltage = now

            # 5) temp. do fluido da CVT (Mode 22, se habilitado)
            if cvt_uds.is_enabled(self.cfg) and (now - last_cvt) > cvt_uds.params(self.cfg)["interval_s"]:
                try:
                    self.source.read_cvt_temp()
                except Exception as exc:
                    log.debug("CVT temp poll: %s", exc)
                last_cvt = now
                used += 1

            # 6) DTCs
            if now - last_dtc > dtc_every:
                try:
                    self.source.read_dtcs()
                except Exception as exc:
                    log.debug("DTC poll: %s", exc)
                last_dtc = now

            self.derived.tick()
            if self.gear is not None:
                try:
                    self.gear.tick()
                except Exception:
                    log.debug("gear tick failed", exc_info=True)
            if self.lights is not None:
                try:
                    self.lights.tick()
                except Exception:
                    log.debug("lights tick failed", exc_info=True)
            alerts.evaluate(self.store, self.cfg)
            self._cycle += 1

            elapsed = time.time() - t0
            # Mantém o ritmo próximo do orçamento, sem sleep negativo.
            # Um ciclo "completo" mira ~ 1 / (budget / used) mas no ELM
            # o próprio I/O já atrasa; só dormimos o resto do slot mínimo.
            sleep_for = max(0.0, used * slot - elapsed)
            if self._stop.wait(sleep_for if sleep_for > 0 else 0.01):
                break

"""Interface comum das fontes de dados do veículo e do GPS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..store import DataStore


class VehicleSource(ABC):
    """Fonte de PIDs OBD (ELM327, CAN ou simulador)."""

    name: str = "base"

    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = cfg
        self.supported_pids: set[int] = set()
        self.supported_keys: list[str] = []

    @property
    @abstractmethod
    def poll_budget_per_s(self) -> float:
        """Quantos PIDs por segundo esta fonte consegue sustentar."""

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        ...

    @abstractmethod
    def discover(self) -> set[int]:
        """Descobre PIDs Mode 01 suportados."""

    @abstractmethod
    def read_pid(self, pid: int) -> float | None:
        ...

    def read_battery_voltage(self) -> float | None:
        """Sobrescreva se a fonte tiver ATRV ou equivalente."""
        return None

    @abstractmethod
    def read_dtcs(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def clear_dtcs(self) -> bool:
        ...

    def read_cvt_temp(self) -> float | None:
        """Mode 22 na TCM — experimental. Padrão: não suportado."""
        return None

    def read_vin(self) -> str | None:
        """VIN via OBD Mode 09 PID 02. Padrão: não suportado."""
        return None

    def after_discover(self) -> None:
        from ..signals import SIGNALS

        keys = [s.key for s in SIGNALS.values() if s.pid in self.supported_pids]
        self.supported_keys = keys
        self.store.set_meta("supported_pids", sorted(self.supported_pids))
        self.store.set_meta("supported_keys", keys)
        self.store.set_meta("source", self.name)
        self.store.set_meta("vehicle_connected", self.connected)


class GpsSource(ABC):
    name: str = "gps"

    def __init__(self, store: DataStore, cfg: dict) -> None:
        self.store = store
        self.cfg = cfg

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        ...

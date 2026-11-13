"""Armazenamento central thread-safe dos sinais do carro e do GPS."""

from __future__ import annotations

import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Sample:
    value: float | int | str | None
    unit: str = ""
    source: str = ""
    ts: float = field(default_factory=time.time)
    label: str = ""
    stale: bool = False


class DataStore:
    def __init__(self, stale_after_s: float = 5.0) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Sample] = {}
        self._meta: dict[str, Any] = {
            "vehicle_connected": False,
            "gps_connected": False,
            "source": "",
            "supported_pids": [],
            "supported_keys": [],
            "dtcs": [],
            "mil": False,
            "alerts": [],
            "started_at": time.time(),
        }
        self._listeners: list[Callable[[str, Sample], None]] = []
        self._stale_after_s = stale_after_s

    def update(self, key: str, value: Any, unit: str = "", source: str = "", label: str = "") -> None:
        sample = Sample(value=value, unit=unit, source=source, label=label, ts=time.time())
        with self._lock:
            self._data[key] = sample
        for listener in list(self._listeners):
            try:
                listener(key, sample)
            except Exception:
                pass

    def get(self, key: str) -> Sample | None:
        with self._lock:
            sample = self._data.get(key)
            return deepcopy(sample) if sample else None

    def value(self, key: str, default: Any = None) -> Any:
        sample = self.get(key)
        if sample is None or sample.value is None:
            return default
        return sample.value

    def set_meta(self, key: str, value: Any) -> None:
        with self._lock:
            self._meta[key] = value

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return deepcopy(self._meta.get(key, default))

    def on_update(self, listener: Callable[[str, Sample], None]) -> None:
        self._listeners.append(listener)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            signals: dict[str, Any] = {}
            for key, sample in self._data.items():
                stale = (now - sample.ts) > self._stale_after_s
                signals[key] = {
                    "value": sample.value,
                    "unit": sample.unit,
                    "source": sample.source,
                    "ts": sample.ts,
                    "label": sample.label,
                    "stale": stale,
                    "age_s": round(now - sample.ts, 3),
                }
            return {
                "ts": now,
                "signals": signals,
                "meta": deepcopy(self._meta),
            }

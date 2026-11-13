"""Fusão da velocidade GPS (até 10 Hz) com a velocidade OBD."""

from __future__ import annotations

import time
from typing import Any

from .store import DataStore


class SpeedFuse:
    """Prefere GPS recente e com satélites; mistura com OBD para cobrir buracos."""

    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.speed = 0.0
        self.source = "none"
        self.ts = 0.0

    def update(self) -> float:
        now = time.time()
        obd = self.store.value("speed")
        gps = self.store.value("gps_speed")
        sats = self.store.value("gps_sats") or 0
        # idade aproximada pelos samples
        def age(key: str) -> float:
            s = self.store.get(key)
            return now - s.ts if s else 99.0

        gps_ok = gps is not None and age("gps_speed") < 0.4 and sats >= 4
        obd_ok = obd is not None and age("speed") < 1.2
        if gps_ok and obd_ok:
            # GPS mais rápido (10 Hz); OBD ancora o viés do módulo
            w = 0.7
            self.speed = w * float(gps) + (1 - w) * float(obd)
            self.source = "fused"
        elif gps_ok:
            self.speed = float(gps)
            self.source = "gps"
        elif obd_ok:
            self.speed = float(obd)
            self.source = "obd"
        # senão mantém o último
        self.ts = now
        self.store.update("speed_fused", round(self.speed, 2), "km/h", self.source, "Velocidade fundida")
        return self.speed

    def snapshot(self) -> dict[str, Any]:
        return {"speed": round(self.speed, 2), "source": self.source, "ts": self.ts}

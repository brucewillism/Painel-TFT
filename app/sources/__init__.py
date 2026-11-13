"""Fontes de dados do painel (OBD, CAN, GPS, simulador)."""

from .base import VehicleSource, GpsSource
from .simulator import SimulatorVehicleSource, SimulatorGpsSource

__all__ = [
    "VehicleSource",
    "GpsSource",
    "SimulatorVehicleSource",
    "SimulatorGpsSource",
    "build_vehicle_source",
    "build_gps_source",
]


def build_vehicle_source(kind: str, store, cfg: dict):
    kind = (kind or "simulator").lower()
    if kind == "obd":
        from .obd_source import ObdVehicleSource

        return ObdVehicleSource(store, cfg)
    if kind == "can":
        from .can_source import CanVehicleSource

        return CanVehicleSource(store, cfg)
    return SimulatorVehicleSource(store, cfg)


def build_gps_source(kind: str, store, cfg: dict):
    """No simulador o GPS já vem da mesma fonte; com OBD/CAN usa gpsd."""
    if (kind or "simulator").lower() == "simulator":
        return None  # o simulador de veículo também emite GPS
    if not cfg.get("gps", {}).get("enabled", True):
        return None
    from .gps_source import GpsdSource

    return GpsdSource(store, cfg)

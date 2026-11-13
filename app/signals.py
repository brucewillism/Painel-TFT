"""Catálogo de PIDs OBD-II Mode 01, decodificadores e metadados de exibição."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

Decoder = Callable[[list[int]], float | None]


def _u8(b: list[int], i: int = 0) -> int | None:
    return b[i] if len(b) > i else None


def _u16(b: list[int], i: int = 0) -> int | None:
    if len(b) < i + 2:
        return None
    return (b[i] << 8) + b[i + 1]


def dec_percent_255(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else a * 100.0 / 255.0


def dec_temp(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else a - 40.0


def dec_trim(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else (a - 128) * 100.0 / 128.0


def dec_rpm(b: list[int]) -> float | None:
    v = _u16(b)
    return None if v is None else v / 4.0


def dec_speed(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else float(a)


def dec_timing(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else (a - 128) / 2.0


def dec_maf(b: list[int]) -> float | None:
    v = _u16(b)
    return None if v is None else v / 100.0


def dec_map(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else float(a)


def dec_fuel_press(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else a * 3.0


def dec_runtime(b: list[int]) -> float | None:
    v = _u16(b)
    return None if v is None else float(v)


def dec_distance(b: list[int]) -> float | None:
    v = _u16(b)
    return None if v is None else float(v)


def dec_voltage(b: list[int]) -> float | None:
    v = _u16(b)
    return None if v is None else v / 1000.0


def dec_o2_voltage(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else a / 200.0


def dec_o2_trim(b: list[int]) -> float | None:
    if len(b) < 2 or b[1] == 0xFF:
        return None
    return (b[1] - 128) * 100.0 / 128.0


def dec_barometer(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else float(a)


def dec_fuel_type(b: list[int]) -> float | None:
    a = _u8(b)
    return None if a is None else float(a)


def dec_supported_bitmask(b: list[int]) -> float | None:
    """Usado só como placeholder; o bitmask é lido cru em discover()."""
    v = 0
    for i, byte in enumerate(b[:4]):
        v = (v << 8) + byte
    return float(v)


@dataclass(frozen=True)
class Signal:
    key: str
    pid: int
    name: str
    unit: str
    decoder: Decoder
    bytes_needed: int
    group: str  # fast | medium | slow
    label_pt: str
    decimals: int = 0
    min_value: float | None = None
    max_value: float | None = None


# PIDs Mode 01 mais úteis num Lancer 2016 (e genéricos OBD2).
# A descoberta no arranque filtra o que a ECU realmente responde.
SIGNALS: dict[str, Signal] = {}


def _add(sig: Signal) -> None:
    SIGNALS[sig.key] = sig


_add(Signal("engine_load", 0x04, "ENGINE_LOAD", "%", dec_percent_255, 1, "medium", "Carga do motor", 0, 0, 100))
_add(Signal("coolant_temp", 0x05, "COOLANT_TEMP", "°C", dec_temp, 1, "medium", "Temp. do motor", 0, -40, 150))
_add(Signal("stft_b1", 0x06, "SHORT_FUEL_TRIM_1", "%", dec_trim, 1, "slow", "STFT banca 1", 1, -100, 100))
_add(Signal("ltft_b1", 0x07, "LONG_FUEL_TRIM_1", "%", dec_trim, 1, "slow", "LTFT banca 1", 1, -100, 100))
_add(Signal("stft_b2", 0x08, "SHORT_FUEL_TRIM_2", "%", dec_trim, 1, "slow", "STFT banca 2", 1, -100, 100))
_add(Signal("ltft_b2", 0x09, "LONG_FUEL_TRIM_2", "%", dec_trim, 1, "slow", "LTFT banca 2", 1, -100, 100))
_add(Signal("fuel_pressure", 0x0A, "FUEL_PRESSURE", "kPa", dec_fuel_press, 1, "slow", "Pressão de combustível", 0, 0, 765))
_add(Signal("map", 0x0B, "INTAKE_PRESSURE", "kPa", dec_map, 1, "medium", "MAP (admissão)", 0, 0, 255))
_add(Signal("rpm", 0x0C, "RPM", "rpm", dec_rpm, 2, "fast", "RPM", 0, 0, 8000))
_add(Signal("speed", 0x0D, "SPEED", "km/h", dec_speed, 1, "fast", "Velocidade", 0, 0, 260))
_add(Signal("timing_advance", 0x0E, "TIMING_ADVANCE", "°", dec_timing, 1, "slow", "Avanço de ignição", 1, -64, 64))
_add(Signal("intake_temp", 0x0F, "INTAKE_TEMP", "°C", dec_temp, 1, "slow", "Temp. admissão", 0, -40, 80))
_add(Signal("maf", 0x10, "MAF", "g/s", dec_maf, 2, "medium", "MAF", 2, 0, 200))
_add(Signal("throttle", 0x11, "THROTTLE_POS", "%", dec_percent_255, 1, "medium", "Acelerador", 0, 0, 100))
_add(Signal("o2_b1s1_v", 0x14, "O2_B1S1", "V", dec_o2_voltage, 2, "slow", "O2 B1S1 tensão", 3, 0, 1.275))
_add(Signal("o2_b1s2_v", 0x15, "O2_B1S2", "V", dec_o2_voltage, 2, "slow", "O2 B1S2 tensão", 3, 0, 1.275))
_add(Signal("o2_b2s1_v", 0x18, "O2_B2S1", "V", dec_o2_voltage, 2, "slow", "O2 B2S1 tensão", 3, 0, 1.275))
_add(Signal("o2_b2s2_v", 0x19, "O2_B2S2", "V", dec_o2_voltage, 2, "slow", "O2 B2S2 tensão", 3, 0, 1.275))
_add(Signal("runtime", 0x1F, "RUN_TIME", "s", dec_runtime, 2, "slow", "Tempo ligado", 0, 0, 65535))
_add(Signal("distance_mil", 0x21, "DISTANCE_W_MIL", "km", dec_distance, 2, "slow", "Distância com MIL", 0, 0, 65535))
_add(Signal("fuel_level", 0x2F, "FUEL_LEVEL", "%", dec_percent_255, 1, "slow", "Nível de combustível", 0, 0, 100))
_add(Signal("distance_cleared", 0x31, "DISTANCE_SINCE_DTC_CLEAR", "km", dec_distance, 2, "slow", "Distância desde clear", 0, 0, 65535))
_add(Signal("baro", 0x33, "BAROMETRIC_PRESSURE", "kPa", dec_barometer, 1, "slow", "Pressão barométrica", 0, 0, 255))
_add(Signal("module_voltage", 0x42, "CONTROL_MODULE_VOLTAGE", "V", dec_voltage, 2, "medium", "Tensão da ECU", 2, 0, 18))
_add(Signal("ambient_temp", 0x46, "AMBIANT_AIR_TEMP", "°C", dec_temp, 1, "slow", "Temp. ambiente", 0, -40, 60))
_add(Signal("throttle_abs", 0x47, "ABSOLUTE_THROTTLE", "%", dec_percent_255, 1, "slow", "Acelerador absoluto", 0, 0, 100))
_add(Signal("throttle_rel", 0x4C, "RELATIVE_THROTTLE", "%", dec_percent_255, 1, "slow", "Acelerador relativo", 0, 0, 100))
_add(Signal("fuel_type", 0x51, "FUEL_TYPE", "", dec_fuel_type, 1, "slow", "Tipo de combustível", 0, 0, 23))
_add(Signal("ethanol_percent", 0x52, "ETHANOL_PERCENT", "%", dec_percent_255, 1, "slow", "Teor de etanol", 0, 0, 100))
_add(Signal("oil_temp", 0x5C, "OIL_TEMP", "°C", dec_temp, 1, "slow", "Temp. do óleo", 0, -40, 200))
_add(Signal("fuel_rate", 0x5E, "FUEL_RATE", "L/h", lambda b: (None if _u16(b) is None else _u16(b) / 20.0), 2, "medium", "Vazão de combustível", 2, 0, 100))

# PIDs de suporte (descoberta). Não entram no agendamento de display.
SUPPORT_PIDS = (0x00, 0x20, 0x40, 0x60, 0x80, 0xA0)

# Prioridade de varredura (chaves).
FAST_KEYS = ["rpm", "speed"]
MEDIUM_KEYS = ["coolant_temp", "throttle", "engine_load", "module_voltage", "maf", "map"]
SLOW_KEYS = [
    "intake_temp",
    "stft_b1",
    "ltft_b1",
    "stft_b2",
    "ltft_b2",
    "timing_advance",
    "o2_b1s1_v",
    "o2_b1s2_v",
    "o2_b2s1_v",
    "o2_b2s2_v",
    "fuel_level",
    "runtime",
    "ambient_temp",
    "baro",
    "fuel_pressure",
    "distance_mil",
    "distance_cleared",
    "throttle_abs",
    "ethanol_percent",
    "oil_temp",
    "fuel_rate",
    "fuel_type",
]

# battery_voltage é especial: ATRV no ELM327, ou module_voltage no CAN.
VIRTUAL_KEYS = {
    "battery_voltage": "Tensão da bateria",
    "instant_consumption": "Consumo instantâneo",
    "avg_consumption": "Consumo médio",
    "gear": "Marcha estimada",
    "cvt_ratio": "Relação da polia",
    "cvt_overall": "Relação total",
    "cvt_rpm_per_kmh": "RPM por km/h",
    "cvt_position": "Posição CVT",
    "cvt_temp": "Temp. fluido CVT",
    "trip_distance": "Distância da viagem",
    "trip_fuel": "Combustível da viagem",
    "gps_lat": "Latitude",
    "gps_lon": "Longitude",
    "gps_speed": "Velocidade GPS",
    "gps_heading": "Rumo",
    "gps_alt": "Altitude",
    "gps_sats": "Satélites",
}

FUEL_TYPE_NAMES = {
    0: "Não especificado",
    1: "Gasolina",
    2: "Metanol",
    3: "Etanol",
    4: "Diesel",
    5: "GLP",
    6: "GNV",
    7: "Propano",
    8: "Elétrico",
    9: "Bifuel gasolina",
    10: "Bifuel metanol",
    11: "Bifuel etanol",
    12: "Bifuel GLP",
    13: "Bifuel GNV",
    14: "Bifuel propano",
    15: "Bifuel elétrico",
    16: "Bifuel mistura",
    17: "Híbrido gasolina",
    18: "Híbrido etanol",
    19: "Híbrido diesel",
    20: "Híbrido elétrico",
    21: "Híbrido mistura",
    22: "Híbrido regenerativo",
    23: "Bifuel diesel",
}


def decode_mode01(pid: int, data: list[int]) -> float | None:
    for sig in SIGNALS.values():
        if sig.pid == pid:
            return sig.decoder(data)
    return None


def parse_support_bitmask(base_pid: int, payload: list[int]) -> set[int]:
    """Interpreta resposta 41 00 / 20 / 40 / 60 (4 bytes de bitmask)."""
    supported: set[int] = set()
    for i, byte in enumerate(payload[:4]):
        for bit in range(8):
            if byte & (1 << (7 - bit)):
                supported.add(base_pid + 1 + i * 8 + bit)
    return supported


def key_for_pid(pid: int) -> str | None:
    for sig in SIGNALS.values():
        if sig.pid == pid:
            return sig.key
    return None

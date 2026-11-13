"""Testes unitários leves: decodificadores, consumo, CVT, marcha, store e alertas."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.alerts import evaluate
from app.cvt_uds import decode_temp
from app.derived import (
    DerivedComputer,
    cvt_metrics,
    estimate_gear,
    fuel_params,
    instant_l100km,
    instant_lph,
    transmission_mode,
)
from app.signals import dec_rpm, dec_speed, dec_temp, dec_voltage, decode_mode01, parse_support_bitmask
from app.store import DataStore


def test_decoders() -> None:
    assert dec_rpm([0x0C, 0xE4]) == 825.0
    assert dec_speed([0x3C]) == 60
    assert dec_temp([0x80]) == 88
    assert abs(dec_voltage([0x36, 0xB0]) - 14.0) < 0.01
    assert decode_mode01(0x0D, [80]) == 80


def test_support_bitmask() -> None:
    pids = parse_support_bitmask(0x00, [0xFF, 0x00, 0x00, 0x00])
    assert pids == set(range(0x01, 0x09))


def test_consumption_and_manual_gear() -> None:
    density, afr = fuel_params("gasoline", None)
    assert abs(density - 740) < 0.1 and abs(afr - 14.7) < 0.01
    lph = instant_lph(20.0, density, afr)
    assert lph is not None and 6.0 < lph < 7.2
    l100 = instant_l100km(lph, 100.0)
    assert l100 is not None and abs(l100 - lph) < 1e-6
    assert estimate_gear(2000, 50) == 3
    assert estimate_gear(3300, 50) == 2
    assert estimate_gear(800, 0) == 0


def test_cvt_metrics() -> None:
    # Parado: sem relação
    assert cvt_metrics(850, 0) is None
    # Arrancada: RPM alto, velocidade baixa → relação curta (pulley alto, position perto de 0)
    short = cvt_metrics(4000, 30)
    assert short is not None
    assert short["rpm_per_kmh"] == 4000 / 30
    assert short["pulley"] > 1.2
    assert short["position"] < 0.5
    # Cruzeiro: RPM baixo, velocidade alta → relação longa
    tall = cvt_metrics(1800, 100)
    assert tall is not None
    assert tall["rpm_per_kmh"] == 18.0
    assert tall["pulley"] < 0.8
    assert tall["position"] > 0.5
    assert short["overall"] > tall["overall"]


def test_derived_defaults_to_cvt() -> None:
    assert transmission_mode({}) == "cvt"
    assert transmission_mode({"transmission": "manual"}) == "manual"
    store = DataStore()
    comp = DerivedComputer(store, {"transmission": "cvt", "fuel": {"type": "gasoline"}})
    store.update("rpm", 2000, "rpm", "test", "RPM")
    store.update("speed", 80, "km/h", "test", "Velocidade")
    store.update("maf", 8.0, "g/s", "test", "MAF")
    comp.tick()
    assert store.get_meta("transmission") == "cvt"
    assert store.value("gear") is None
    assert store.value("cvt_ratio") is not None
    assert store.value("cvt_rpm_per_kmh") is not None

    store2 = DataStore()
    comp2 = DerivedComputer(store2, {"transmission": "manual", "fuel": {"type": "gasoline"}})
    store2.update("rpm", 2000, "rpm", "test", "RPM")
    store2.update("speed", 50, "km/h", "test", "Velocidade")
    comp2.tick()
    assert store2.value("gear") == 3
    assert store2.value("cvt_ratio") is None


def test_cvt_temp_decode_and_alert() -> None:
    assert decode_temp([140], "a_minus_40") == 100
    assert decode_temp([0x00, 130], "u16_minus_40") == 90
    store = DataStore()
    store.update("cvt_temp", 125, "°C", "test", "Temp. fluido CVT")
    alerts = evaluate(store, {"alerts": {"cvt_temp_c": 120}})
    assert any(a["id"] == "cvt_temp_high" for a in alerts)
    store.update("cvt_temp", 90, "°C", "test", "Temp. fluido CVT")
    alerts = evaluate(store, {"alerts": {"cvt_temp_c": 120}})
    assert not any(a["id"] == "cvt_temp_high" for a in alerts)


def test_store_snapshot() -> None:
    store = DataStore(stale_after_s=5)
    store.update("rpm", 2000, "rpm", "test", "RPM")
    store.set_meta("source", "test")
    snap = store.snapshot()
    assert snap["signals"]["rpm"]["value"] == 2000
    assert snap["meta"]["source"] == "test"
    assert store.value("rpm") == 2000


def test_flex_fuel_between_gas_and_ethanol() -> None:
    d_gas, a_gas = fuel_params("gasoline", None)
    d_eth, a_eth = fuel_params("ethanol", None)
    d_flex, a_flex = fuel_params("flex", 27)
    assert d_eth > d_flex > d_gas
    assert a_eth < a_flex < a_gas


if __name__ == "__main__":
    tests = [
        test_decoders,
        test_support_bitmask,
        test_consumption_and_manual_gear,
        test_cvt_metrics,
        test_derived_defaults_to_cvt,
        test_cvt_temp_decode_and_alert,
        test_store_snapshot,
        test_flex_fuel_between_gas_and_ethanol,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
    raise SystemExit(failed)

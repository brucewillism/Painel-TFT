"""VIN, autonomia, postos, trânsito e PIN do app companheiro."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.companion import CompanionAuth
from app.range import (
    badge_for,
    blended_l100,
    fuel_at_arrival,
    haversine_km,
    range_km,
    remaining_liters,
    traffic_extra_min,
)
from app.store import DataStore
from app.sun import sun_times
from app.vin import build_vin, check_digit_ok, decode_vin, parse_mode09_pid02, resolve_identity


def test_vin_lancer_2016() -> None:
    vin = build_vin("93Y", "AA26C", 2016, "C", "123456")
    assert len(vin) == 17 and check_digit_ok(vin)
    info = decode_vin(vin, now_year=2026)
    assert info["year"] == 2016
    assert info["country"] == "Brasil"
    assert "Mitsubishi" in info["manufacturer"] or "MMC" in info["manufacturer"]
    assert info["model"] == "Lancer"
    assert info["facelift"] is True
    assert info["source"] == "obd"
    assert "2016" in info["label"]
    # payload Mode 09 típico do ELM (várias linhas 49 02 0N)
    payload = bytes([0x49, 0x02, 0x01]) + vin.encode()
    assert parse_mode09_pid02(payload) == vin


def test_vin_fallback_when_missing() -> None:
    cfg = {"vehicle": {"model": "Lancer", "year": 2016, "trim": "HL", "engine": "2.0", "transmission": "cvt", "country": "Brasil"}}
    ident = resolve_identity(cfg, None)
    assert ident["source"] == "fallback"
    assert ident["year"] == 2016
    assert ident["vin"] is None
    assert "Lancer" in ident["label"]


def test_fuel_remaining_pid_and_manual() -> None:
    store = DataStore()
    store.update("fuel_level", 40, "%", "obd", "Combustível")
    lit, src = remaining_liters(store, {"fuel": {"tank_liters": 50}}, 0)
    assert src == "pid" and abs(lit - 20.0) < 1e-6
    # sem PID 0x2F: usa o último abastecimento menos o gasto integrado do MAF
    store2 = DataStore()
    lit2, src2 = remaining_liters(store2, {"fuel": {"tank_liters": 50, "manual_liters": 50}}, 12.5)
    assert src2 == "manual" and abs(lit2 - 37.5) < 1e-6


def test_range_badges_and_traffic_penalty() -> None:
    l100 = blended_l100(11.0, 7.0, None, 0.5)
    assert abs(l100 - 9.0) < 1e-6
    assert abs(range_km(18, 9.0) - 200) < 1e-6
    extra = traffic_extra_min(600, 900)  # +5 min
    assert abs(extra - 5) < 1e-6
    # 100 km a 10 L/100 + 5 min × 0.025 L/min = 10.125 L → sobram 9.875, alcançável
    fuel = fuel_at_arrival(20, 100, 10, extra, 0.025)
    assert badge_for(fuel, 3) == "reachable"
    # 80 km a 10 L/100 = 8 L, tanque 9 L, reserva 3 → no limite
    assert badge_for(fuel_at_arrival(9, 80, 10, 0, 0.02), 3) == "at-risk"
    # não chega
    assert badge_for(fuel_at_arrival(5, 80, 10, 0, 0.02), 3) == "unreachable"


def test_haversine_paulista() -> None:
    # ~1 km na Paulista (pontos do simulador)
    d = haversine_km(-23.5614, -46.6565, -23.5588, -46.6598)
    assert 0.3 < d < 0.8


def test_companion_pin() -> None:
    auth = CompanionAuth({"companion": {"pin": "2016", "enabled": True}})
    assert auth.pair("0000") is None
    ok = auth.pair("2016")
    assert ok and auth.check(ok["token"])
    assert not auth.check("deadbeef")


def test_sun_sao_paulo() -> None:
    t = sun_times(-23.5505, -46.6333)
    assert t["sunrise"] < t["sunset"]
    assert 4.5 < t["sunrise_hour"] < 8
    assert 17 < t["sunset_hour"] < 20


def test_icons_and_pwa_files() -> None:
    js = (ROOT / "app/static/js/icons.js").read_text()
    assert "⌖" not in js
    assert "function svg" in js or "svg(name)" in js
    assert "map:" in js and "phone:" in js
    html = (ROOT / "app/templates/index.html").read_text()
    assert "icons.js" in html
    appjs = (ROOT / "app/static/js/app.js").read_text()
    assert "LancerIcons" in appjs
    assert (ROOT / "app/templates/companion.html").is_file()
    assert (ROOT / "app/static/pwa/manifest.webmanifest").is_file()
    assert (ROOT / "app/static/pwa/sw.js").is_file()
    assert (ROOT / "app/static/pwa/icon-192.png").is_file()


if __name__ == "__main__":
    tests = [
        test_vin_lancer_2016,
        test_vin_fallback_when_missing,
        test_fuel_remaining_pid_and_manual,
        test_range_badges_and_traffic_penalty,
        test_haversine_paulista,
        test_companion_pin,
        test_sun_sao_paulo,
        test_icons_and_pwa_files,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc!r}")
            import traceback
            traceback.print_exc()
    raise SystemExit(failed)

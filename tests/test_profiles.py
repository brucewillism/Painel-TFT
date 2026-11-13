"""Perfis de veículo, VIN→carroceria e parâmetros do perfil."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.derived import estimate_gear, gear_params
from app.profiles import (
    body_from_class,
    default_profile,
    get_profile,
    list_profiles,
    match_profile,
    tire_circumference_m,
)
from app.vin import build_vin, decode_vin, resolve_identity


def test_default_and_sample_profiles() -> None:
    ids = {p["id"] for p in list_profiles()}
    assert "lancer-2016-cvt" in ids
    assert "onix-2022-hatch" in ids
    assert "compass-2021-suv" in ids
    assert "hilux-2022-pickup" in ids
    g = default_profile()
    assert g.get("fuel", {}).get("tank_liters")
    lancer = get_profile("lancer-2016-cvt")
    assert lancer["transmission"] == "cvt"
    assert lancer["fuel"]["tank_liters"] == 50
    assert lancer["body"] == "sedan"
    assert lancer["cvt"]["did"] == 0x2101
    assert lancer["gears"]["final_drive"] == 4.235
    onix = get_profile("onix-2022-hatch")
    assert onix["body"] == "hatch" and onix["fuel"]["tank_liters"] == 44
    assert get_profile("missing-id")["id"] in {"generic", None} or "fuel" in get_profile("missing-id")


def test_vin_lancer_maps_to_sedan_and_profile() -> None:
    vin = build_vin("93Y", "AA26C", 2016, "C", "123456")
    info = decode_vin(vin, now_year=2026)
    assert info["year"] == 2016
    assert info["body"] == "sedan"
    assert info["model"] == "Lancer"
    assert "Mitsubishi" in (info.get("make") or info.get("manufacturer") or "")
    matched = match_profile(info)
    assert matched and matched["id"] == "lancer-2016-cvt"


def test_body_from_class_mapping() -> None:
    assert body_from_class("Sedan/Saloon") == "sedan"
    assert body_from_class("Hatchback") == "hatch"
    assert body_from_class("Sport Utility Vehicle (SUV)/Multi-Purpose Vehicle (MPV)") == "suv"
    assert body_from_class("Pickup") == "pickup"
    assert body_from_class("Coupe") == "coupe"
    assert body_from_class("Wagon") == "wagon"
    assert body_from_class("Crossover") == "suv"
    assert body_from_class("") is None


def test_match_hilux_and_onix() -> None:
    h = match_profile({"make": "Toyota", "model": "Hilux", "year": 2022, "wmi": "9BR"})
    assert h and h["id"] == "hilux-2022-pickup" and h["body"] == "pickup"
    o = match_profile({"make": "Chevrolet", "model": "Onix", "year": 2022, "wmi": "9BG"})
    assert o and o["id"] == "onix-2022-hatch"


def test_resolve_without_vin_is_generic_unless_configured() -> None:
    ident = resolve_identity({"vehicle": {}}, None)
    assert ident["source"] == "fallback"
    assert ident["vin"] is None
    # sem fallback de modelo, o rótulo não deve forçar Lancer
    assert "Lancer" not in (ident.get("label") or "")
    ident2 = resolve_identity(
        {"vehicle": {"model": "Lancer", "year": 2016, "trim": "HL", "engine": "2.0", "transmission": "cvt", "country": "Brasil"}},
        None,
    )
    assert "Lancer" in ident2["label"]


def test_tire_circumference_and_gear_params() -> None:
    circ = tire_circumference_m({"gears": {"tire": "215/45R18"}})
    assert circ and 1.9 < circ < 2.2
    cfg = {"_profile": get_profile("lancer-2016-cvt")}
    ratios, final, c = gear_params(cfg)
    assert ratios[1] == 3.538 and final == 4.235
    # 2000 rpm @ 50 km/h ainda cai na 3ª com as relações do Lancer
    assert estimate_gear(2000, 50, gears=ratios, final_drive=final, tire_circ=c) == 3


def test_body_art_files_exist() -> None:
    folder = ROOT / "app" / "static" / "img" / "bodies"
    for b in ("sedan", "hatch", "suv", "pickup", "coupe", "wagon"):
        side = (folder / f"{b}.svg").read_text(encoding="utf-8")
        top = (folder / f"{b}-top.svg").read_text(encoding="utf-8")
        assert 'class="paint"' in side and 'class="headlight"' in side
        assert 'class="glass' in side or "windshield" in side
        assert "wheel-front" in side and "wheel-rear" in side
        assert 'class="paint"' in top and "zone-engine" in top
        # janelas de verdade, não só um bloco
        assert "windshield" in side



def test_body_illustrations_exist() -> None:
    """Fallback lateral é PNG recortado com duas rodas detectadas."""
    import json
    from PIL import Image
    folder = ROOT / "app" / "static" / "img" / "bodies"
    for b in ("sedan", "hatch", "suv", "pickup", "coupe", "wagon"):
        png = folder / f"{b}.png"
        meta_p = folder / f"{b}.json"
        assert png.is_file(), png
        assert meta_p.is_file(), meta_p
        im = Image.open(png)
        assert im.mode == "RGBA"
        # recorte com transparência de verdade
        extrema = im.getextrema()
        assert extrema[3][0] == 0
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        zones = meta["zones"]
        assert meta.get("side_on") or zones.get("side_on")
        assert meta.get("wheels_confident") or zones.get("wheels_confident")
        wheels = zones.get("wheels") or []
        assert len(wheels) == 2
        assert abs(wheels[0]["x"] - wheels[1]["x"]) > 0.3
        assert all(w["y"] > 0.55 for w in wheels)


def test_photo_year_scoring() -> None:
    from app.car_photo import _model_years_in_title, _match_score
    assert "2016" in _model_years_in_title(
        "2016 Mitsubishi Lancer (CF MY16) ES Sport sedan (2016-11-13) 02.jpg"
    )
    assert "2016" not in _model_years_in_title(
        "1995-1996 Mitsubishi Lancer 1.6 GLXi Automatic Sedan (17-09-2016) 01.jpg"
    )
    ident = {"year": 2016, "make": "Mitsubishi", "model": "Lancer", "body": "sedan"}
    three_q = {
        "title": "2016 Mitsubishi Lancer (CF MY16) ES Sport sedan (2016-11-13) 02.jpg",
        "width": 3537, "height": 1784,
    }
    side = {
        "title": "Mitsubishi Lancer (2008) – left side view.jpg",
        "width": 4032, "height": 3024,
    }
    front = {
        "title": "2017 Mitsubishi Lancer 2.4 ES AWC, front left side.jpg",
        "width": 5224, "height": 3172,
    }
    evo = {"title": "EVO IX in Voltex Kit.jpg", "width": 4928, "height": 3264}
    old = {
        "title": "1995-1996 Mitsubishi Lancer 1.6 GLXi Automatic Sedan (17-09-2016) 01.jpg",
        "width": 2048, "height": 1536,
    }
    sportback = {
        "title": "Mitsubishi Lancer VIII Sportback side 20100725.jpg",
        "width": 2466, "height": 972,
    }
    depan = {
        "title": "Mitsubishi Lancer GLX (depan), Denpasar.jpg",
        "width": 2592, "height": 1720,
        "description": "Front side view of Mitsubishi Lancer GLX at Jalan Sesetan, Denpasar, Bali",
    }
    aircraft = {
        "title": "A right side view of a B-1B Lancer aircraft on display during an air show.jpg",
        "width": 2840, "height": 1830,
    }
    dodge = {
        "title": "Old Dodge Lancer parked on Gallier Street - Side View Mirror Rocket.jpg",
        "width": 5184, "height": 3888,
    }
    assert _match_score(three_q, ident) > _match_score(evo, ident)
    assert _match_score(three_q, ident) > _match_score(old, ident)
    assert _match_score(side, ident) > _match_score(three_q, ident)
    assert _match_score(side, ident) > _match_score(front, ident)
    assert _match_score(side, ident) > _match_score(depan, ident)
    assert _match_score(sportback, ident) > _match_score(three_q, ident)
    assert _match_score(sportback, ident) > _match_score(depan, ident)
    assert _match_score(side, ident) > _match_score(aircraft, ident)
    assert _match_score(side, ident) > _match_score(dodge, ident)


if __name__ == "__main__":
    tests = [
        test_default_and_sample_profiles,
        test_vin_lancer_maps_to_sedan_and_profile,
        test_body_from_class_mapping,
        test_match_hilux_and_onix,
        test_resolve_without_vin_is_generic_unless_configured,
        test_tire_circumference_and_gear_params,
        test_body_art_files_exist,
        test_body_illustrations_exist,
        test_photo_year_scoring,
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

"""Tema HUD, inferência de marcha, fonte de luzes e cor de destaque."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.gear import (
    decode_can_value,
    infer_manual,
    infer_prndl,
    map_can_gear,
    resolve_can,
    resolve_gear,
    resolve_gpio,
)
from app.sources.lights import (
    LightsSource,
    configured_ids,
    decode_can_telltale,
    lights_backend,
    read_gpio_telltale,
)
from app.store import DataStore
from app.theme import (
    ACCENT_PRESETS,
    DEFAULT_ACCENT,
    DEFAULT_ACCENT_HEX,
    apply_defaults,
    normalize_hex,
    normalize_theme,
    resolve_accent,
)


def test_default_accent_is_arc_reactor() -> None:
    assert DEFAULT_ACCENT == "arc"
    assert DEFAULT_ACCENT_HEX == "#00D8FF"
    ui = apply_defaults({})
    assert ui["theme"] == "hud"
    assert ui["accent"] == "arc"
    assert ui["accent_hex"] == "#00D8FF"
    assert ui["hud_rotate"] is True
    assert ui["unused_telltales"] == "dim"


def test_theme_classic_and_aliases() -> None:
    assert normalize_theme("classic") == "classic"
    assert normalize_theme("Clássico") == "classic"
    assert normalize_theme("dark") == "hud"
    ui = apply_defaults({"theme": "classic", "accent": "red", "accent_hex": "#E10600"})
    assert ui["theme"] == "classic"
    assert ui["accent"] == "red"
    assert ui["accent_hex"] == "#E10600"


def test_accent_presets_and_custom() -> None:
    for key in ("arc", "red", "matrix", "amber", "violet", "white"):
        acc, hx = resolve_accent({"accent": key})
        assert acc == key
        assert hx == ACCENT_PRESETS[key]["hex"].upper()
    acc, hx = resolve_accent({"accent": "custom", "accent_hex": "7f00ff"})
    assert acc == "custom" and hx == "#7F00FF"
    acc, hx = resolve_accent({"accent": "arc", "accent_hex": "#00FF6A"})
    assert acc == "custom" and hx == "#00FF6A"
    assert normalize_hex("00d8ff") == "#00D8FF"
    assert normalize_hex("xyz", "#00D8FF") == "#00D8FF"


def test_infer_prndl() -> None:
    assert infer_prndl(speed=0, rpm=0) == "P"
    assert infer_prndl(speed=0, rpm=200) == "P"
    assert infer_prndl(speed=0, rpm=750) == "N"
    assert infer_prndl(speed=0, rpm=750, parking_brake=True) == "P"
    assert infer_prndl(speed=40, rpm=2000) == "D"
    assert infer_prndl(speed=5, rpm=900, reverse=True) == "R"
    assert infer_prndl(speed=0, rpm=0, reverse=True) == "R"


def test_infer_manual_keeps_numeric_gears() -> None:
    assert infer_manual(speed=0, rpm=0) == "P"
    assert infer_manual(speed=0, rpm=850) == "N"
    assert infer_manual(speed=10, rpm=2000, reverse=True) == "R"
    # relações padrão do Lancer: 2000 rpm a 50 km/h ≈ 3ª
    assert infer_manual(speed=50, rpm=2000) == 3
    assert infer_manual(speed=50, rpm=3300) == 2


def test_resolve_gear_sources() -> None:
    cfg = {"transmission": "cvt", "gear_source": "inferred", "_profile": {"gear_source": "inferred"}}
    out = resolve_gear(cfg, speed=0, rpm=0)
    assert out["value"] == "P" and out["source"] == "inferred"
    out = resolve_gear(cfg, speed=80, rpm=2200)
    assert out["value"] == "D" and out["label"] == "D"

    can_cfg = {
        "transmission": "cvt",
        "gear_source": "can",
        "_profile": {
            "gear_source": "can",
            "gear_can": {"id": 0x1D0, "byte": 0, "mask": 0x0F, "shift": 0,
                         "map": {0: "P", 1: "R", 2: "N", 3: "D", 4: "L"}},
        },
    }
    frame = {"id": 0x1D0, "data": bytes([0x03, 0x00])}
    out = resolve_gear(can_cfg, speed=10, rpm=1500, can_frame=frame)
    assert out["value"] == "D" and out["source"] == "can"
    # quadro ausente → fallback inferido
    out = resolve_gear(can_cfg, speed=0, rpm=800, can_frame=None)
    assert out["value"] == "N" and out["source"] == "inferred"

    pins = {"P": False, "R": False, "N": False, "D": True}

    def reader(pin, active_low=False):
        table = {5: "P", 6: "R", 13: "N", 19: "D"}
        return pins[table[pin]]

    gpio_cfg = {
        "gear_source": "gpio",
        "_profile": {"gear_source": "gpio", "gear_gpio": {"pins": {"P": 5, "R": 6, "N": 13, "D": 19}}},
    }
    out = resolve_gear(gpio_cfg, speed=0, rpm=800, pin_reader=reader)
    assert out["value"] == "D" and out["source"] == "gpio"


def test_can_decode_helpers() -> None:
    assert decode_can_value(bytes([0xA5, 0x10]), {"byte": 0, "mask": 0x0F}) == 0x05
    assert map_can_gear(4, {4: "L"}) == "L"
    assert resolve_can(
        {"_profile": {"gear_can": {"id": 0x10, "byte": 1, "mask": 0xFF, "map": {7: 5}}}},
        {"id": 0x10, "data": bytes([0, 7])},
    ) == 5
    assert resolve_gpio({"_profile": {"gear_gpio": {"pins": {}}}}, pin_reader=lambda *_: False) is None


def test_lights_sim_backend_and_mil() -> None:
    store = DataStore()
    cfg = {"source": "simulator", "lights": {"source": "auto"}}
    assert lights_backend(cfg) == "sim"
    assert "low_beam" in configured_ids(cfg)
    assert "check_engine" in configured_ids(cfg)
    store.update("low_beam", 1, "", "sim", "Farol baixo")
    store.update("turn_left", 1, "", "sim", "Seta")
    store.set_meta("mil", True)
    src = LightsSource(store, cfg)
    snap = src.tick()
    assert snap["backend"] == "sim"
    assert snap["values"]["low_beam"] is True
    assert snap["values"]["turn_left"] is True
    assert snap["values"]["check_engine"] is True
    assert snap["values"]["high_beam"] is False


def test_lights_gpio_configured_and_active_low() -> None:
    levels = {5: 0, 6: 1}  # ativo-baixo: 0 = ligado

    def reader(pin, active_low=True):
        raw = levels[pin]
        return (raw == 0) if active_low else (raw == 1)

    cfg = {
        "source": "obd",
        "lights": {
            "source": "gpio",
            "gpio": {
                "low_beam": {"pin": 5, "active_low": True},
                "high_beam": {"pin": 6, "active_low": True},
                # pin null = não configurado
                "turn_left": {"pin": None, "active_low": True},
            },
        },
    }
    assert lights_backend(cfg) == "gpio"
    conf = configured_ids(cfg)
    assert "low_beam" in conf and "high_beam" in conf
    assert "turn_left" not in conf
    assert "check_engine" in conf
    store = DataStore()
    store.set_meta("mil", False)
    src = LightsSource(store, cfg, pin_reader=reader)
    snap = src.tick()
    assert snap["values"]["low_beam"] is True
    assert snap["values"]["high_beam"] is False
    assert snap["values"]["check_engine"] is False


def test_lights_can_and_telltale_helpers() -> None:
    data = bytes([0x11, 0x00])  # bit0 e bit4
    assert decode_can_telltale(data, {"byte": 0, "mask": 0x01}) is True
    assert decode_can_telltale(data, {"byte": 0, "mask": 0x02}) is False
    assert read_gpio_telltale({"pin": None}) is None

    cfg = {
        "source": "can",
        "lights": {
            "source": "can",
            "can": {"id": 0x210, "signals": {"low_beam": {"byte": 0, "mask": 0x01},
                                             "turn_left": {"byte": 0, "mask": 0x10}}},
        },
    }
    store = DataStore()

    class FakeCan:
        last_frames = [{"id": 0x210, "data": data}]

    src = LightsSource(store, cfg, can_source=FakeCan())
    snap = src.tick()
    assert snap["values"]["low_beam"] is True
    assert snap["values"]["turn_left"] is True


def test_apply_defaults_preserves_custom_hex() -> None:
    ui = apply_defaults({"theme": "hud", "accent": "custom", "accent_hex": "#123456",
                         "hud_rotate": False, "unused_telltales": "hide"})
    assert ui["accent_hex"] == "#123456"
    assert ui["hud_rotate"] is False
    assert ui["unused_telltales"] == "hide"


def test_kenney_car_kit_bundled() -> None:
    """Modelos CC0 do Kenney Car Kit vêm offline, um por tipo de carroceria."""
    root = ROOT / "app" / "static" / "models" / "kenney-car"
    kenney = {
        "hatch": "hatchback-sports.glb",
        "suv": "suv.glb",
        "pickup": "truck.glb",
        "coupe": "sedan-sports.glb",
        "wagon": "van.glb",
    }
    for glb in kenney.values():
        path = root / glb
        assert path.is_file(), path
        assert path.stat().st_size > 10_000
    assert (root / "Textures" / "colormap.png").is_file()
    sedan = ROOT / "app" / "static" / "models" / "innerscene" / "sedan.glb"
    assert sedan.is_file() and sedan.stat().st_size > 100_000
    licenses = (ROOT / "LICENSES").read_text(encoding="utf-8")
    assert "Kenney" in licenses
    assert "CC0" in licenses
    assert "Car Kit" in licenses
    assert "Innerscene" in licenses
    for name in list(kenney.values()) + ["sedan.glb"]:
        assert name in licenses
    js = (ROOT / "app" / "static" / "js" / "hud-car.js").read_text(encoding="utf-8")
    assert "innerscene/sedan.glb" in js
    for body, glb in kenney.items():
        assert body in js and glb in js


def test_lancer_hud_hero_bundled() -> None:
    """Ilustração 2D do Lancer 2016: PNG com alfa, perfil e créditos."""
    from PIL import Image
    from app.profiles import get_profile, public_view

    folder = ROOT / "data" / "vehicles" / "2016_Mitsubishi_Lancer"
    png = folder / "hud-wireframe.png"
    luma = folder / "hud-wireframe-luma.png"
    core = folder / "hud-wireframe-core.png"
    assert png.is_file() and png.stat().st_size > 50_000
    assert luma.is_file() and core.is_file()
    im = Image.open(png)
    assert im.mode == "RGBA"
    assert im.size[0] >= 1000 and im.size[1] >= 500
    extrema = im.getextrema()
    assert extrema[3][0] == 0
    assert extrema[3][1] > 200
    yaml_text = (ROOT / "profiles" / "lancer-2016-cvt.yaml").read_text(encoding="utf-8")
    assert "hud_hero:" in yaml_text
    assert "hud-wireframe.png" in yaml_text
    prof = get_profile("lancer-2016-cvt")
    hero = public_view(prof).get("hud_hero")
    assert hero and hero["image"].startswith("/media/vehicles/")
    assert "hud-wireframe.png" in hero["image"]
    for name in ("motor", "cvt", "battery", "wheels"):
        a = hero["anchors"][name]
        assert 0.0 <= float(a["x"]) <= 1.0
        assert 0.0 <= float(a["y"]) <= 1.0
    licenses = (ROOT / "LICENSES").read_text(encoding="utf-8")
    assert "EurovisionNim" in licenses
    assert "CC BY-SA 4.0" in licenses
    assert "hud-wireframe.png" in licenses
    assert "gerada por IA" in licenses or "gerada por IA" in (ROOT / "README.md").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "js" / "hud-car.js").read_text(encoding="utf-8")
    assert "setHero" in js
    css = (ROOT / "app" / "static" / "css" / "hud.css").read_text(encoding="utf-8")
    assert "hud-hero" in css
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "/media/vehicles" in main

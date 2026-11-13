"""Testes da central: tema, câmeras, mídia, telefone, FM e CarPlay (mocks)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from app.carplay import KNOWN_DONGLES, CarPlayManager
from app.fm_radio import FmRadio
from app.media import MediaPlayer
from app.phone import Phone
from app.config import load


def test_config_accent_default_arc() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    assert cfg["ui"]["theme"] == "hud"
    assert cfg["ui"]["accent"] == "arc"
    assert cfg["ui"]["accent_hex"].upper() == "#00D8FF"
    assert cfg["phone"]["enabled"] is True
    assert cfg["carplay"]["enabled"] is True
    assert cfg["media"]["eq"] == [0, 0, 0, 0, 0]
    assert any(abs(p["mhz"] - 90.5) < 0.01 for p in cfg["media"]["fm"]["presets"])
    loaded = load(ROOT / "config.yaml")
    assert loaded["ui"]["accent"] == "arc"
    assert cfg["lights"]["source"] == "auto"
    assert cfg.get("gear_source") == "inferred"


def test_phone_mock_dial_answer_hangup() -> None:
    phone = Phone({"phone": {"enabled": True, "ofono": True}})
    assert phone.source in {"mock", "ofono", "bluez"}
    snap = phone.snapshot()
    assert len(snap["contacts"]) >= 4
    assert any(c["name"] == "Ana Souza" for c in snap["contacts"])
    assert snap["log"]
    out = phone.dial("+55 11 98888-1001")
    assert out["call"]["state"] in {"dialing", "active"}
    assert out["call"]["name"] == "Ana Souza"
    phone.hangup()
    assert phone.snapshot()["call"] is None
    inc = phone.incoming("+55 11 97777-2002")
    assert inc["call"]["state"] in {"incoming", "ringing"}
    ans = phone.answer()
    assert ans["call"]["state"] == "active"
    phone.hangup()
    assert phone.snapshot()["call"] is None


def test_carplay_status_mock_and_known_dongles() -> None:
    # Carlinkit / CPC200 IDs documentados
    assert ("1314", "1520") in KNOWN_DONGLES
    assert ("1314", "1521") in KNOWN_DONGLES
    assert ("08e9", "0001") in KNOWN_DONGLES
    mgr = CarPlayManager({"carplay": {"enabled": True}})
    st = mgr.status()
    assert st["enabled"] is True
    assert st["mode"] in {"mock", "carplay"}
    assert "driver_installed" in st
    assert st["connected"] in {True, False}
    # Sem dongle neste ambiente, launch não deve quebrar
    launched = mgr.launch()
    assert "running" in launched
    mgr.stop()
    assert mgr.status()["running"] is False


def test_fm_mock_tune() -> None:
    fm = FmRadio({"media": {"fm": {"enabled": True, "mhz": 90.5, "presets": [
        {"name": "CBN SP", "mhz": 90.5},
        {"name": "Jovem Pan", "mhz": 100.9},
    ]}}})
    snap = fm.snapshot()
    assert snap["mhz"] == 90.5
    assert snap["backend"] in {"mock", "rtl_fm"}
    tuned = fm.tune(100.9, play=True)
    assert tuned["mhz"] == 100.9
    assert tuned["playing"] is True
    stopped = fm.stop()
    assert stopped["playing"] is False


def test_media_library_and_eq() -> None:
    player = MediaPlayer({"media": {"music_dir": "data/music", "volume": 70, "eq": [0, 0, 0, 0, 0], "radio": []}})
    snap = player.snapshot()
    assert snap["volume"] == 70
    assert snap["eq"] == [0, 0, 0, 0, 0]
    assert len(snap["library"]) >= 1
    bands = player.set_eq([2, 0, -1, 3, 0])
    assert bands["eq"] == [2, 0, -1, 3, 0]
    vol = player.set_volume(40)
    assert vol["volume"] == 40
    player.shutdown()


def test_cameras_placeholder_jpeg() -> None:
    from app.cameras import CameraHub
    hub = CameraHub({"cameras": {
        "enabled": True, "width": 320, "height": 180, "fps": 4, "jpeg_quality": 40,
        "devices": [
            {"id": "front", "label": "Frente", "device": "/dev/video99"},
            {"id": "rear", "label": "Ré", "device": "/dev/video98", "reverse": True},
        ],
        "birdseye": {"enabled": True, "calib_dir": "data/birdseye"},
    }})
    hub.start()
    try:
        cams = hub.list()
        assert {c["id"] for c in cams} == {"front", "rear"}
        assert hub.reverse_cam_id() == "rear"
        # feeds de teste (dispositivo inexistente → placeholder)
        import time
        time.sleep(0.25)
        jpeg = hub.jpeg("front")
        assert jpeg and jpeg[:2] == b"\xff\xd8"
        hub.set_reverse(True)
        assert hub.reverse is True
        eye = hub.birdseye_jpeg()
        # pode ainda estar vazio no primeiro tick
        if eye:
            assert eye[:2] == b"\xff\xd8"
    finally:
        hub.stop()


def test_frontend_has_home_and_carplay() -> None:
    html = (ROOT / "app/templates/index.html").read_text()
    for token in ("page-home", "page-car", "page-cameras", "page-media",
                  "page-phone", "page-radio", "page-carplay", "set-accent",
                  "headunit.css", "car.js"):
        assert token in html, token
    css = (ROOT / "app/static/css/headunit.css").read_text()
    assert "data-accent" in (ROOT / "app/static/css/app.css").read_text() or "--accent" in css
    html = (ROOT / "app/templates/index.html").read_text()
    assert "hud-gauges" in html and "three.min.js" in html
    assert (ROOT / "app/static/vendor/three.min.js").is_file()
    assert (ROOT / "app/static/css/hud.css").is_file()
    assert "mode-carplay" in css
    js = (ROOT / "app/static/js/app.js").read_text()
    assert "CARPLAY" in js
    assert "applyAccent" in js


if __name__ == "__main__":
    tests = [
        test_config_accent_default_arc,
        test_phone_mock_dial_answer_hangup,
        test_carplay_status_mock_and_known_dongles,
        test_fm_mock_tune,
        test_media_library_and_eq,
        test_cameras_placeholder_jpeg,
        test_frontend_has_home_and_carplay,
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

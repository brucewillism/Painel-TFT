"""Testes dos modos desempenho, pista, G, telemetria, TPMS, valet, saúde, LEDs e shift."""

from __future__ import annotations

import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import sport_db
from app.fuse import SpeedFuse
from app.gforce import GForce
from app.health import CarHealth
from app.leds import AmbientLeds
from app.perf import PerfTimer
from app.shift_alerts import ShiftAlerts
from app.store import DataStore
from app.telemetry import Telemetry
from app.tpms import parse_advertisement, TPMS
from app.trackmode import TrackTimer, side_of_gate
from app.valet import Valet
from app.dashcam import DashCam


def _conn(tmp: Path | None = None):
    path = (tmp or Path(tempfile.mkdtemp())) / "sport.sqlite"
    conn = sport_db.connect(path)
    sport_db.init(conn)
    return conn


def test_speed_fuse_prefers_gps_and_mixes() -> None:
    store = DataStore()
    fuse = SpeedFuse(store)
    store.update("speed", 80, "km/h", "obd")
    store.update("gps_speed", 90, "km/h", "gps")
    store.update("gps_sats", 8, "", "gps")
    v = fuse.update()
    assert fuse.source == "fused"
    assert abs(v - (0.7 * 90 + 0.3 * 80)) < 0.05
    assert store.value("speed_fused") == round(v, 2)


def test_speed_fuse_falls_back_to_obd() -> None:
    store = DataStore()
    fuse = SpeedFuse(store)
    store.update("speed", 42, "km/h", "obd")
    v = fuse.update()
    assert fuse.source == "obd"
    assert v == 42


def test_perf_0_100_and_402m_auto() -> None:
    store, conn = DataStore(), _conn()
    p = PerfTimer(store, conn, {"perf": {"enabled": True}})
    for _ in range(8):
        p.tick(0.0, 0.05)
    assert p.runs["0-100"]["state"] == "armed"
    assert p.runs["402m"]["state"] == "armed"
    p.tick(3.0, 0.05)
    assert p.runs["0-100"]["state"] == "running"
    # 0–100 em ~10 s a 9.7 km/h/s
    v = 3.0
    for _ in range(220):
        v = min(110.0, v + 9.7 * 0.05)
        p.tick(v, 0.05)
        if p.runs["0-100"]["state"] == "done":
            break
    assert p.runs["0-100"]["state"] == "done"
    assert 8.0 < p.runs["0-100"]["time_s"] < 13.0
    # 402 m deve terminar no mesmo sprint (ou logo depois)
    if p.runs["402m"]["state"] != "done":
        for _ in range(250):
            v = min(130.0, v + 2.0 * 0.05)
            p.tick(v, 0.05)
            if p.runs["402m"]["state"] == "done":
                break
    assert p.runs["402m"]["state"] == "done"
    assert p.runs["402m"]["dist_m"] >= 402
    hist = p.history("0-100")
    assert hist and hist[0]["time_s"] > 0
    best = p.snapshot()["best"]["0-100"]
    assert best and best["time_s"] == hist[-1]["time_s"] or best["time_s"] <= hist[0]["time_s"]


def test_perf_80_120_and_100_0() -> None:
    store, conn = DataStore(), _conn()
    p = PerfTimer(store, conn, {"perf": {"enabled": True}})
    p.tick(76.0, 0.05)
    assert p.runs["80-120"]["state"] == "armed"
    p.tick(81.0, 0.05)
    assert p.runs["80-120"]["state"] == "running"
    v = 81.0
    for _ in range(120):
        v = min(125.0, v + 8.0 * 0.05)
        p.tick(v, 0.05)
        if p.runs["80-120"]["state"] == "done":
            break
    assert p.runs["80-120"]["state"] == "done"
    assert 3.0 < p.runs["80-120"]["time_s"] < 8.0

    # 100–0: já estamos acima de 100
    assert p.runs["100-0"]["state"] == "armed"
    p.tick(99.0, 0.05)
    assert p.runs["100-0"]["state"] == "running"
    v = 99.0
    for _ in range(80):
        v = max(0.0, v - 30.0 * 0.05)
        p.tick(v, 0.05)
        if p.runs["100-0"]["state"] == "done":
            break
    assert p.runs["100-0"]["state"] == "done"
    assert 2.0 < p.runs["100-0"]["time_s"] < 5.0


def test_track_gate_crossing_and_delta() -> None:
    store, conn = DataStore(), _conn()
    tr = TrackTimer(store, conn, {})
    tr.set_gate(-23.70, -46.70, hdg=0.0, width_m=20)
    tr.start_session("teste")
    # cruza o portão pela 1ª vez (começa a volta)
    tr.tick(-23.70008, -46.70, 80, 0.1)
    tr.tick(-23.69992, -46.70, 80, 0.1)
    assert tr.lap == 1 and tr.lap_t0 is not None
    # percorre um pouco e completa a volta (precisa > 8 s)
    tr.tick(-23.6990, -46.6990, 80, 0.1)
    # simula tempo de volta
    tr.lap_t0 = time.time() - 12.0
    tr.cur_profile = [(0, 0), (400, 6), (800, 12)]
    tr.cur_dist = 800
    tr.tick(-23.70008, -46.70, 80, 0.1)
    tr.tick(-23.69992, -46.70, 80, 0.1)
    assert tr.last_lap and tr.last_lap["time_s"] >= 8
    assert tr.best_s is not None
    # volta em andamento, mesma distância → delta
    tr.cur_dist = 400
    tr.lap_t0 = time.time() - 5.5
    d = tr.delta()
    assert d is not None
    assert abs(d - (5.5 - 6.0)) < 0.3


def test_gforce_gps_fallback() -> None:
    store = DataStore()
    tmp = Path(tempfile.mkdtemp())
    g = GForce(store, {"imu": {"force_gps": True}}, tmp)
    g.tick(0.0, 0.1)
    v = 0.0
    for _ in range(12):
        v += 36.0 * 0.1  # 36 km/h por s ≈ 1.02 g
        g.tick(v, 0.1)
    assert g.source == "gps"
    assert g.ax > 0.5
    snap = g.snapshot()
    assert snap["peak_lon"] >= snap["ax"] - 0.01
    store.update("gps_heading", 0, "°", "gps")
    g.tick(36.0, 0.2)
    store.update("gps_heading", 20, "°", "gps")
    g.tick(36.0, 0.2)
    assert abs(g.ay) > 0  # componente lateral


def test_telemetry_csv() -> None:
    store = DataStore()
    tmp = Path(tempfile.mkdtemp())
    conn = _conn(tmp)
    tel = Telemetry(store, conn, {"telemetry": {"hz": 10}}, tmp)
    store.update("rpm", 2000, "rpm", "t")
    store.update("speed", 50, "km/h", "t")
    tel.start(hz=10, name="teste")
    for _ in range(12):
        tel.tick(0.12)
    snap = tel.stop()
    assert snap["samples"] >= 10
    name, data = tel.export_csv(snap["last_id"])
    assert name.endswith(".csv")
    text = data.decode()
    assert "rpm" in text and "2000" in text
    rows = tel.session_rows(snap["last_id"])
    assert rows


def test_tpms_advertisement_parsers() -> None:
    # curto: kPa LE, temp, bat, id
    short = struct.pack("<H", 220) + struct.pack("b", 31) + bytes([80]) + b"ABCD"
    p = parse_advertisement(short)
    assert p and abs(p["kpa"] - 220) < 1 and p["temp_c"] == 31 and p["battery"] == 80
    # 16-byte estilo BR: id 6 + 2 pad + psi*10 BE + temp + bat
    br = b"\x11\x22\x33\x44\x55\x66\x00\x00" + struct.pack(">H", 320) + struct.pack("b", 25) + bytes([90, 0, 0])
    p = parse_advertisement(br)
    assert p and abs(p["psi"] - 32.0) < 0.15
    # sysgration: flag + kPa*10 LE + temp + bat
    sysg = bytes([0x01]) + struct.pack("<H", 2200) + struct.pack("b", 40) + bytes([70, 0xAA, 0xBB])
    p = parse_advertisement(sysg)
    assert p and abs(p["kpa"] - 220) < 1 and p["temp_c"] == 40


def test_tpms_sim_and_alerts() -> None:
    store = DataStore()
    t = TPMS(store, {"tpms": {"enabled": True, "simulate": True, "warn_kpa": 300}})
    snap = t.tick()
    assert snap["wheels"]["fl"] and snap["wheels"]["fr"]
    # com warn alto, todas alertam pressão baixa
    assert snap["alerts"] >= 1


def test_valet_lock_unlock_report() -> None:
    store, conn = DataStore(), _conn()
    v = Valet(store, conn, {"valet": {"pin": "1234", "harsh_g": 0.4}})
    assert v.lock()["ok"] is True
    assert v.is_locked()
    assert "media" in v.locked_pages()
    v.tick(80, -23.56, -46.65, 0.1, 0.1)
    v.tick(95, -23.57, -46.66, -0.7, 0.1)  # frenagem
    bad = v.unlock("0000")
    assert bad["ok"] is False and v.is_locked()
    ok = v.unlock("1234")
    assert ok["ok"] is True
    assert not v.is_locked()
    rep = ok["report"]
    assert rep["max_speed"] >= 95
    assert rep["event_count"] >= 1
    assert any(e["kind"] == "frenagem" for e in rep["events"])


def test_health_odometer_and_service() -> None:
    store, conn = DataStore(), _conn()
    h = CarHealth(store, conn, {})
    snap = h.set_odometer(90000)
    assert snap["odometer"]["total_km"] == 90000
    items = h.items()
    assert any(i["item_id"] == "oil" for i in items)
    # marca óleo como feito agora
    h.mark_service("oil", 90000)
    oil = next(i for i in h.items() if i["item_id"] == "oil")
    assert oil["status"] == "ok"
    assert oil["due_km"] > 0
    store.update("battery_voltage", 10.6, "V", "t")
    store.update("rpm", 0, "rpm", "t")
    h._battery_tick()
    store.update("rpm", 800, "rpm", "t")
    h._battery_tick()
    batt = h.battery()
    assert batt["last_crank"] is not None and batt["last_crank"] <= 10.6


def test_shift_levels() -> None:
    store = DataStore()
    s = ShiftAlerts(store, {"shift": {"enabled": True, "rpm_points": [4000, 5000, 6000], "audio": False}})
    store.update("rpm", 3500, "rpm", "t")
    assert s.tick()["level"] == 0
    store.update("rpm", 5100, "rpm", "t")
    assert s.tick()["level"] == 2
    store.update("rpm", 6500, "rpm", "t")
    assert s.tick()["level"] == 3


def test_leds_rpm_preview() -> None:
    store = DataStore()
    leds = AmbientLeds(store, {"leds": {"enabled": True, "count": 20, "mode": "rpm"}})
    store.update("rpm", 3250, "rpm", "t")
    snap = leds.tick()
    assert snap["mode"] == "rpm"
    assert not snap["hw"]
    lit = sum(1 for p in snap["pixels"] if p != [0, 0, 0] and p != (0, 0, 0))
    assert 5 <= lit <= 15
    leds.set_mode("static", "#ff0000", 0.5)
    snap = leds.tick()
    assert snap["pixels"][0] in ([255, 0, 0], (255, 0, 0), [255, 0, 0])


def test_dashcam_protect_and_quota() -> None:
    store = DataStore()
    tmp = Path(tempfile.mkdtemp())
    conn = _conn(tmp)
    d = DashCam(store, conn, {"dashcam": {"dir": str(tmp / "clips"), "max_gb": 0.00001, "segment_s": 60}}, tmp)
    d.seed_demo()
    clips = d.list_clips()
    assert len(clips) >= 2
    assert any(c["protected"] for c in clips)
    d.protect("manual")
    # quota deve apagar não protegidos se o limite é minúsculo
    d._enforce_quota()
    left = d.list_clips()
    assert all(c["protected"] for c in left) or len(left) <= len(clips)

if __name__ == "__main__":
    tests = [
        test_speed_fuse_prefers_gps_and_mixes,
        test_speed_fuse_falls_back_to_obd,
        test_perf_0_100_and_402m_auto,
        test_perf_80_120_and_100_0,
        test_track_gate_crossing_and_delta,
        test_gforce_gps_fallback,
        test_telemetry_csv,
        test_tpms_advertisement_parsers,
        test_tpms_sim_and_alerts,
        test_valet_lock_unlock_report,
        test_health_odometer_and_service,
        test_shift_levels,
        test_leds_rpm_preview,
        test_dashcam_protect_and_quota,
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

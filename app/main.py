"""Aplicação FastAPI do painel TFT — API, WebSocket e UI estática."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import ROOT, load
from .derived import DerivedComputer
from .scheduler import PollScheduler
from .sources import build_gps_source, build_vehicle_source
from .sources.lights import LightsSource
from .gear import GearSource
from .theme import apply_defaults as apply_ui_defaults
from .store import DataStore
from .tiles import tile_response, tiles_available
from .trips import TripLogger
from .cameras import CameraHub
from .media import MediaPlayer
from .phone import Phone
from .carplay import CarPlayManager
from .fm_radio import FmRadio
from .vin import resolve_identity
from .range import RangeService
from .companion import CompanionAuth, is_local, token_from_request, settings_digest
from .sun import sun_times
from .sport import SportHub
from . import sport_api
from . import vehicle_api
from . import profiles as vehicle_profiles

logging.basicConfig(
    level=os.environ.get("LANCER_LOG", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("lancer")

STATIC = Path(__file__).resolve().parent / "static"
TEMPLATES = Path(__file__).resolve().parent / "templates"


class AppState:
    cfg: dict
    store: DataStore
    vehicle: Any
    gps: Any
    derived: DerivedComputer
    scheduler: PollScheduler
    trips: TripLogger
    settings: dict
    cameras: CameraHub
    media: MediaPlayer
    phone: Phone
    carplay: CarPlayManager
    fm: FmRadio
    range: RangeService
    auth: CompanionAuth
    sport: SportHub


state = AppState()


def _default_settings(cfg: dict) -> dict:
    return {
        "units": dict(cfg.get("units") or {}),
        "alerts": dict(cfg.get("alerts") or {}),
        "ui": apply_ui_defaults(dict(cfg.get("ui") or {})),
        "fuel": dict(cfg.get("fuel") or {}),
        "source": cfg.get("source", "simulator"),
        "transmission": cfg.get("transmission", "cvt"),
        "cvt": dict(cfg.get("cvt") or {}),
        "vehicle": dict(cfg.get("vehicle") or {}),
        "range": {k: v for k, v in (cfg.get("range") or {}).items() if k not in {"tomtom_key", "here_key"}},
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load()
    state.cfg = cfg
    state.settings = _default_settings(cfg)
    state.store = DataStore()
    state.store.set_meta("version", __version__)
    state.derived = DerivedComputer(state.store, cfg)
    state.vehicle = build_vehicle_source(cfg.get("source", "simulator"), state.store, cfg)
    ok = state.vehicle.connect()
    log.info("Fonte do veículo: %s conectada=%s", state.vehicle.name, ok)
    try:
        state.vehicle.discover()
    except Exception as exc:
        log.warning("Descoberta de PIDs falhou: %s", exc)

    vin = None
    try:
        vin = state.vehicle.read_vin()
    except Exception as exc:
        log.warning("Leitura do VIN falhou: %s", exc)
    # tenta vPIC se houver rede; depois aplica perfil salvo / sugere
    ident = resolve_identity(cfg, vin, online=True)
    state.store.set_meta("vehicle", ident)
    try:
        cfg = vehicle_profiles.apply_to_config(cfg)
        state.cfg = cfg
        vehicle_api.boot(state, cfg, ident)
        ident = state.store.get_meta("vehicle") or ident
        if getattr(state, "derived", None):
            state.derived.cfg = cfg
    except Exception:
        log.exception("Falha ao aplicar perfil de veículo")
    log.info("Veículo: %s (fonte=%s, vin=%s, perfil=%s)", ident.get("label"), ident.get("source"), ident.get("vin"), ident.get("profile_id") or ident.get("suggested_profile"))

    state.gps = build_gps_source(cfg.get("source", "simulator"), state.store, cfg)
    if state.gps is not None:
        state.gps.start()

    state.scheduler = PollScheduler(state.store, state.vehicle, state.derived, cfg)
    state.scheduler.rebuild_queues()
    state.scheduler.start()

    trip_cfg = cfg.get("trip", {})
    state.trips = TripLogger(
        state.store,
        trip_cfg.get("db_path", str(ROOT / "data" / "trips.sqlite")),
        float(trip_cfg.get("log_interval_s", 1.0)),
    )
    state.trips.start(auto=bool(trip_cfg.get("auto_start", True)))
    state.cameras = CameraHub(cfg)
    state.cameras.start()
    state.media = MediaPlayer(cfg)
    state.phone = Phone(cfg)
    state.carplay = CarPlayManager(cfg)
    state.fm = FmRadio(cfg)
    state.auth = CompanionAuth(cfg)
    state.range = RangeService(state.store, cfg)
    state.range.start()
    state.sport = SportHub(state.store, cfg)
    state.sport.start()

    can_src = state.vehicle if getattr(state.vehicle, "name", "") == "can" else None
    state.gear = GearSource(state.store, cfg, can_source=can_src)
    state.lights = LightsSource(state.store, cfg, can_source=can_src)
    state.scheduler.gear = state.gear
    state.scheduler.lights = state.lights
    try:
        state.gear.tick()
        state.lights.tick()
    except Exception:
        pass
    sport_api.bind(lambda: state)
    _publish_settings()
    log.info("Painel TFT v%s pronto (fonte=%s)", __version__, state.vehicle.name)
    try:
        yield
    finally:
        log.info("Encerrando painel…")
        try:
            state.scheduler.stop()
        except Exception:
            pass
        try:
            state.trips.stop()
        except Exception:
            pass
        try:
            if state.gps:
                state.gps.stop()
        except Exception:
            pass
        try:
            state.vehicle.disconnect()
        except Exception:
            pass
        try:
            state.cameras.stop()
        except Exception:
            pass
        try:
            state.media.shutdown()
        except Exception:
            pass
        try:
            state.carplay.shutdown()
        except Exception:
            pass
        try:
            state.fm.shutdown()
        except Exception:
            pass
        try:
            state.range.stop()
        except Exception:
            pass
        try:
            state.sport.stop()
        except Exception:
            pass


app = FastAPI(title="Painel TFT", version=__version__, lifespan=lifespan)
app.include_router(sport_api.router)
app.include_router(vehicle_api.router)
vehicle_api.bind(lambda: state)
sport_api.bind(lambda: state)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
VEHICLES_MEDIA = ROOT / "data" / "vehicles"
if VEHICLES_MEDIA.is_dir():
    app.mount("/media/vehicles", StaticFiles(directory=str(VEHICLES_MEDIA)), name="vehicle-media")



@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/app", response_class=HTMLResponse)
@app.get("/app/", response_class=HTMLResponse)
def companion_page() -> HTMLResponse:
    html = (TEMPLATES / "companion.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/app/manifest.webmanifest")
def companion_manifest():
    path = STATIC / "pwa" / "manifest.webmanifest"
    return FileResponse(path, media_type="application/manifest+json")


@app.get("/app/sw.js")
def companion_sw():
    path = STATIC / "pwa" / "sw.js"
    return FileResponse(path, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": __version__,
        "source": state.store.get_meta("source"),
        "vehicle_connected": state.store.get_meta("vehicle_connected"),
        "gps_connected": state.store.get_meta("gps_connected"),
        "uptime_s": round(time.time() - state.store.get_meta("started_at", time.time()), 1),
    }


@app.get("/api/snapshot")
def snapshot() -> dict:
    if getattr(state, "cameras", None):
        state.store.set_meta("reverse", state.cameras.reverse)
        state.store.set_meta("reverse_cam", state.cameras.reverse_cam_id())
    return state.store.snapshot()


@app.get("/api/status")
def status() -> dict:
    snap = state.store.snapshot()
    return {
        "health": health(),
        "supported_pids": snap["meta"].get("supported_pids", []),
        "supported_keys": snap["meta"].get("supported_keys", []),
        "alerts": snap["meta"].get("alerts", []),
        "mil": snap["meta"].get("mil", False),
        "tiles": tiles_available(state.cfg),
        "settings": state.settings,
        "trip_id": snap["meta"].get("trip_id"),
        "cameras": state.cameras.list() if getattr(state, "cameras", None) else [],
        "reverse": bool(getattr(state, "cameras", None) and state.cameras.reverse),
        "media": state.media.snapshot() if getattr(state, "media", None) else {},
        "phone": state.phone.snapshot() if getattr(state, "phone", None) else {},
        "carplay": state.carplay.status() if getattr(state, "carplay", None) else {},
        "fm": state.fm.snapshot() if getattr(state, "fm", None) else {},
        "vehicle": state.store.get_meta("vehicle") or {},
        "range": (state.range.snapshot() if getattr(state, "range", None) else {}),

        "valet": (state.sport.valet.snapshot() if getattr(state, "sport", None) else {}),
    }


@app.get("/api/dtcs")
def get_dtcs() -> dict:
    try:
        dtcs = state.vehicle.read_dtcs()
    except Exception as exc:
        raise HTTPException(500, f"Falha ao ler DTCs: {exc}") from exc
    return {"dtcs": dtcs, "mil": state.store.get_meta("mil", False)}


class ClearDtcBody(BaseModel):
    confirm: bool = False


@app.post("/api/dtcs/clear")
def clear_dtcs(body: ClearDtcBody) -> dict:
    if not body.confirm:
        raise HTTPException(400, "Envie {\"confirm\": true} para apagar os códigos.")
    ok = state.vehicle.clear_dtcs()
    if not ok:
        raise HTTPException(500, "A ECU não confirmou a limpeza dos códigos.")
    return {"ok": True, "dtcs": [], "mil": False}


@app.get("/api/settings")
def get_settings() -> dict:
    return state.settings


class SettingsPatch(BaseModel):
    units: dict | None = None
    alerts: dict | None = None
    ui: dict | None = None
    fuel: dict | None = None
    transmission: str | None = None


def _publish_settings() -> None:
    if not getattr(state, "settings", None) or not getattr(state, "store", None):
        return
    state.store.set_meta("settings", state.settings)
    state.store.set_meta("ui", state.settings.get("ui") or {})
    state.store.set_meta("settings_rev", settings_digest(state.settings))



def _valet_active() -> bool:
    sport = getattr(state, "sport", None)
    return bool(sport and sport.valet.is_locked())


def _deny_valet(area: str) -> None:
    if _valet_active():
        raise HTTPException(403, f"modo valet: {area} bloqueado")


def _allow_write(request: Request) -> bool:
    host = request.client.host if request.client else None
    if is_local(host):
        return True
    if not getattr(state, "auth", None):
        return False
    token = token_from_request(request.headers.get("authorization"), request.headers.get("cookie"))
    return state.auth.check(token)


@app.put("/api/settings")
def put_settings(body: SettingsPatch, request: Request) -> dict:
    _deny_valet("ajustes")
    if not _allow_write(request):
        raise HTTPException(401, "Pareie o app com o PIN para alterar os ajustes.")
    if body.units:
        state.settings["units"].update(body.units)
        state.cfg.setdefault("units", {}).update(body.units)
    if body.alerts:
        state.settings["alerts"].update(body.alerts)
        state.cfg.setdefault("alerts", {}).update(body.alerts)
    if body.ui:
        ui = dict(body.ui)
        if isinstance(ui.get("gauges"), dict):
            state.settings["ui"].setdefault("gauges", {}).update(ui.pop("gauges"))
            state.cfg.setdefault("ui", {}).setdefault("gauges", {}).update(state.settings["ui"]["gauges"])
        state.settings["ui"].update(ui)
        state.settings["ui"] = apply_ui_defaults(state.settings["ui"])
        state.cfg.setdefault("ui", {}).update(state.settings["ui"])
        brightness = ui.get("brightness")
        if brightness is not None:
            _set_brightness(int(brightness))
    if body.fuel:
        state.settings["fuel"].update(body.fuel)
        state.cfg.setdefault("fuel", {}).update(body.fuel)
    if body.transmission:
        mode = body.transmission.lower().strip()
        if mode not in {"cvt", "manual"}:
            raise HTTPException(400, "transmission deve ser 'cvt' ou 'manual'.")
        state.settings["transmission"] = mode
        state.cfg["transmission"] = mode
    _publish_settings()
    return state.settings


def _set_brightness(percent: int) -> None:
    percent = max(0, min(100, percent))
    root = Path("/sys/class/backlight")
    if not root.exists():
        return
    for dev in root.iterdir():
        maxf = dev / "max_brightness"
        cur = dev / "brightness"
        if not (maxf.exists() and cur.exists()):
            continue
        try:
            mx = int(maxf.read_text().strip())
            cur.write_text(str(int(mx * percent / 100)))
            return
        except OSError:
            continue


@app.get("/api/trips")
def list_trips() -> dict:
    return {"trips": state.trips.list_trips(), "current": state.store.get_meta("trip_id")}


@app.post("/api/trips/start")
def start_trip() -> dict:
    state.derived.reset_trip()
    # encerra a atual (se houver) e começa outra
    state.trips.end_trip()
    trip_id = state.trips.start_trip()
    return {"ok": True, "trip_id": trip_id}


@app.post("/api/trips/end")
def end_trip() -> dict:
    state.trips.end_trip()
    return {"ok": True}


@app.get("/api/trips/{trip_id}/gpx")
def trip_gpx(trip_id: int) -> Response:
    gpx = state.trips.export_gpx(trip_id)
    if gpx is None:
        raise HTTPException(404, "Viagem não encontrada")
    return Response(
        content=gpx,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="lancer-viagem-{trip_id}.gpx"'},
    )


@app.get("/api/trips/{trip_id}/trail")
def trip_trail(trip_id: int, limit: int = Query(2000, ge=10, le=20000)) -> dict:
    samples = state.trips.trip_samples(trip_id)
    if len(samples) > limit:
        step = max(1, len(samples) // limit)
        samples = samples[::step]
    trail = [
        {"lat": s["lat"], "lon": s["lon"], "ts": s["ts"], "speed": s["speed"]}
        for s in samples
        if s.get("lat") is not None and s.get("lon") is not None
    ]
    return {"trip_id": trip_id, "points": trail}


@app.get("/api/map/config")
def map_config() -> dict:
    info = tiles_available(state.cfg)
    return {
        **info,
        "offline_url": "/tiles/{z}/{x}/{y}.png",
        "online_url": state.cfg.get("map", {}).get("online_url"),
        "attribution": state.cfg.get("map", {}).get("online_attribution", ""),
        "default_lat": state.cfg.get("map", {}).get("default_lat", -23.55),
        "default_lon": state.cfg.get("map", {}).get("default_lon", -46.63),
        "default_zoom": state.cfg.get("map", {}).get("default_zoom", 15),
    }


@app.get("/tiles/{z}/{x}/{y}.png")
def get_tile(z: int, x: int, y: int) -> Response:
    return tile_response(state.cfg, z, x, y)




@app.get("/api/cameras")
def api_cameras() -> dict:
    if not getattr(state, "cameras", None):
        return {"cameras": [], "reverse": False, "birdseye": False}
    return {
        "cameras": state.cameras.list(),
        "reverse": state.cameras.reverse,
        "reverse_cam": state.cameras.reverse_cam_id(),
        "birdseye": True,
        "birdseye_calibrated": state.cameras.birdseye_calibrated(),
        "gpio": state.cfg.get("cameras", {}).get("reverse_gpio"),
    }


@app.get("/api/cameras/{cam_id}/stream")
def api_camera_stream(cam_id: str):
    from fastapi.responses import StreamingResponse

    if cam_id == "birdseye":
        def gen_eye():
            while True:
                jpeg = state.cameras.birdseye_jpeg() or b""
                if jpeg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                time.sleep(1 / max(4, state.cameras.fps // 2))
        return StreamingResponse(gen_eye(), media_type="multipart/x-mixed-replace; boundary=frame")

    if cam_id not in {c["id"] for c in state.cameras.list()}:
        raise HTTPException(404, "Câmera desconhecida")

    def gen():
        while True:
            jpeg = state.cameras.jpeg(cam_id) or b""
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(1 / max(2, state.cameras.fps))

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/cameras/reverse")
def api_reverse_override(value: bool = Query(...)) -> dict:
    """Hook manual / teste do sinal de ré (o GPIO também escreve este estado)."""
    state.cameras.set_reverse(value)
    state.store.set_meta("reverse", value)
    return {"reverse": value}


@app.get("/api/media")
def api_media() -> dict:
    return state.media.snapshot()


class MediaCmd(BaseModel):
    action: str
    track_id: str | None = None
    radio: int | None = None
    source: str | None = None
    volume: int | None = None
    eq: list[int] | None = None


@app.post("/api/media")
def api_media_cmd(body: MediaCmd) -> dict:
    _deny_valet("mídia")
    m = state.media
    try:
        if body.action == "play":
            if body.track_id:
                return m.play_track(body.track_id)
            if body.radio is not None:
                return m.play_radio(int(body.radio))
            return m.play()
        if body.action == "pause":
            return m.pause()
        if body.action == "stop":
            return m.stop()
        if body.action == "next":
            return m.next()
        if body.action == "prev":
            return m.prev()
        if body.action == "source" and body.source:
            return m.set_source(body.source)
        if body.action == "volume" and body.volume is not None:
            return m.set_volume(int(body.volume))
        if body.action == "eq" and body.eq is not None:
            return m.set_eq(body.eq)
    except KeyError as exc:
        raise HTTPException(404, f"Item não encontrado: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    raise HTTPException(400, f"Ação desconhecida: {body.action}")


@app.get("/api/media/cover/{track_id}")
def api_media_cover(track_id: str):
    from fastapi.responses import Response
    data = state.media.library.cover_bytes(track_id)
    if not data:
        raise HTTPException(404, "Sem capa")
    raw, mime = data
    return Response(content=raw, media_type=mime)



class PhoneCmd(BaseModel):
    action: str
    number: str | None = None
    name: str | None = None


@app.get("/api/phone")
def api_phone() -> dict:
    return state.phone.snapshot()


@app.post("/api/phone")
def api_phone_cmd(body: PhoneCmd) -> dict:
    if body.action not in {"hangup", "reject", "answer"}:
        _deny_valet("telefone")
    p = state.phone
    try:
        if body.action == "dial":
            return p.dial(body.number or "")
        if body.action == "answer":
            return p.answer()
        if body.action == "hangup" or body.action == "reject":
            return p.hangup()
        if body.action == "incoming":
            return p.incoming(body.number, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    raise HTTPException(400, f"Ação desconhecida: {body.action}")


@app.get("/api/carplay")
def api_carplay() -> dict:
    return state.carplay.status()


@app.post("/api/carplay/launch")
def api_carplay_launch() -> dict:
    _deny_valet("CarPlay")
    return state.carplay.launch()


@app.post("/api/carplay/stop")
def api_carplay_stop() -> dict:
    return state.carplay.stop()


class FmCmd(BaseModel):
    action: str
    mhz: float | None = None


@app.get("/api/fm")
def api_fm() -> dict:
    return state.fm.snapshot()


@app.post("/api/fm")
def api_fm_cmd(body: FmCmd) -> dict:
    _deny_valet("rádio")
    if body.action == "tune" and body.mhz is not None:
        return state.fm.tune(body.mhz, play=True)
    if body.action == "play":
        return state.fm.play()
    if body.action == "stop":
        return state.fm.stop()
    raise HTTPException(400, f"Ação desconhecida: {body.action}")


class PinBody(BaseModel):
    pin: str


@app.post("/api/companion/auth")
def companion_auth(body: PinBody, response: Response) -> dict:
    result = state.auth.pair(body.pin)
    if not result:
        raise HTTPException(401, "PIN incorreto")
    response.set_cookie(
        "lancer_token", result["token"],
        max_age=result["expires_in"], httponly=False, samesite="lax", path="/",
    )
    return {"ok": True, **result}


@app.get("/api/companion/sun")
def companion_sun() -> dict:
    lat = state.store.value("gps_lat")
    lon = state.store.value("gps_lon")
    if lat is None or lon is None:
        lat = (state.cfg.get("map") or {}).get("default_lat", -23.5505)
        lon = (state.cfg.get("map") or {}).get("default_lon", -46.6333)
    return sun_times(float(lat), float(lon))


@app.get("/api/vehicle")
def api_vehicle() -> dict:
    return state.store.get_meta("vehicle") or {}


@app.get("/api/range")
def api_range() -> dict:
    return state.range.snapshot()


@app.post("/api/range/refresh")
def api_range_refresh() -> dict:
    return state.range.refresh(force=True)


class FillBody(BaseModel):
    full: bool = True
    liters: float | None = None


@app.post("/api/fuel/fill")
def api_fuel_fill(body: FillBody, request: Request) -> dict:
    if not _allow_write(request):
        raise HTTPException(401, "Pareie o app com o PIN para registrar o abastecimento.")
    liters = None if body.full else body.liters
    out = state.derived.reset_fill(liters)
    state.settings.setdefault("fuel", {}).update({"manual_liters": out["manual_liters"]})
    state.cfg.setdefault("fuel", {}).update({"manual_liters": out["manual_liters"]})
    _publish_settings()
    try:
        state.range.refresh(force=False)
    except Exception:
        pass
    return out


@app.post("/api/shutdown")
def shutdown() -> dict:
    """Desligamento seguro do Raspberry Pi (chamado no corte de ignição ou pelo menu)."""
    if os.environ.get("LANCER_ALLOW_SHUTDOWN") != "1":
        return {"ok": False, "message": "Defina LANCER_ALLOW_SHUTDOWN=1 para permitir o desligamento."}
    # Agenda o halt depois de responder à UI.
    os.system("nohup bash -c 'sleep 1; sudo systemctl poweroff' >/dev/null 2>&1 &")
    return {"ok": True, "message": "Desligando…"}


class DemoDtcBody(BaseModel):
    code: str = "P0420"
    description: str = "Eficiência do catalisador abaixo do limiar (Banca 1)"


@app.post("/api/demo/dtc")
def demo_dtc(body: DemoDtcBody) -> dict:
    if not hasattr(state.vehicle, "inject_dtc"):
        raise HTTPException(400, "Só disponível no modo simulador.")
    state.vehicle.inject_dtc(body.code, body.description)
    return {"ok": True, "dtcs": state.vehicle.read_dtcs()}


@app.websocket("/ws")
async def ws_snapshot(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            snap = state.store.snapshot()
            await ws.send_text(json.dumps(snap, default=str))
            await asyncio.sleep(0.08)  # ~12,5 Hz; a UI interpola os ponteiros
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close()
        except Exception:
            return


def run() -> None:
    import uvicorn

    cfg = load()
    uvicorn.run(
        "app.main:app",
        host=cfg.get("host", "0.0.0.0"),
        port=int(cfg.get("port", 8080)),
        log_level="info",
    )


if __name__ == "__main__":
    run()

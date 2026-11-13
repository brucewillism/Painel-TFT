"""Rotas HTTP dos modos desempenho, pista, telemetria, dash cam, saúde, LEDs, TPMS e valet."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

router = APIRouter()
_get_state: Callable | None = None


def bind(get_state: Callable) -> None:
    global _get_state
    _get_state = get_state


def hub():
    if not _get_state:
        raise HTTPException(503, "painel ainda inicializando")
    st = _get_state()
    h = getattr(st, "sport", None)
    if h is None:
        raise HTTPException(503, "módulos esportivos indisponíveis")
    return h


class PointsBody(BaseModel):
    points: list[int]


class GateBody(BaseModel):
    lat: float | None = None
    lon: float | None = None
    hdg: float | None = None
    width_m: float = 18
    here: bool = False


class SessionName(BaseModel):
    name: str | None = None
    hz: float | None = None


class OdoBody(BaseModel):
    km: float


class ServiceBody(BaseModel):
    item_id: str
    km: float | None = None


class LedBody(BaseModel):
    mode: str | None = None
    color: str | None = None
    brightness: float | None = None


class BindBody(BaseModel):
    wheel: str
    sensor_id: str


class PinBody(BaseModel):
    pin: str = ""
    new_pin: str | None = None


class CamBody(BaseModel):
    camera_id: str | None = None


@router.get("/api/sport")
def sport_snapshot() -> dict:
    return hub().snapshot()


@router.get("/api/perf")
def perf_get() -> dict:
    return {"perf": hub().perf.snapshot(), "history": hub().perf.history()}


@router.post("/api/perf/reset")
def perf_reset(kind: str | None = None) -> dict:
    hub().perf.reset(kind)
    return hub().perf.snapshot()


@router.post("/api/perf/clear")
def perf_clear(kind: str | None = None) -> dict:
    """Apaga o histórico de arrancadas (e opcionalmente só um tipo)."""
    hub().perf.clear_history(kind)
    return {"ok": True, "history": hub().perf.history()}


@router.post("/api/sim/sprint")
def sim_sprint() -> dict:
    st = _get_state()
    veh = getattr(st, "vehicle", None)
    if veh is None or not hasattr(veh, "start_sprint"):
        raise HTTPException(400, "sprint só no simulador")
    veh.start_sprint()
    hub().perf.reset()
    return {"ok": True}


@router.post("/api/sim/crank")
def sim_crank() -> dict:
    st = _get_state()
    veh = getattr(st, "vehicle", None)
    if veh is None or not hasattr(veh, "start_crank"):
        raise HTTPException(400, "partida só no simulador")
    veh.start_crank()
    return {"ok": True}


@router.post("/api/sim/ignition")
def sim_ignition() -> dict:
    st = _get_state()
    veh = getattr(st, "vehicle", None)
    if veh is None or not hasattr(veh, "start_ignition"):
        raise HTTPException(400, "ignição só no simulador")
    veh.start_ignition()
    return {"ok": True}


@router.post("/api/sim/launch")
def sim_launch() -> dict:
    st = _get_state()
    veh = getattr(st, "vehicle", None)
    if veh is None or not hasattr(veh, "start_launch_0_100"):
        raise HTTPException(400, "arrancada só no simulador")
    veh.start_launch_0_100()
    try:
        hub().perf.reset()
    except Exception:
        pass
    return {"ok": True}


@router.get("/api/track")
def track_get() -> dict:
    h = hub()
    return {"track": h.track.snapshot(), "sessions": h.track.sessions()}


@router.post("/api/track/gate")
def track_gate(body: GateBody) -> dict:
    t = hub().track
    if body.here or body.lat is None or body.lon is None:
        gate = t.set_gate_here()
        if not gate:
            raise HTTPException(400, "sem posição GPS")
    else:
        gate = t.set_gate(body.lat, body.lon, body.hdg, body.width_m)
    return {"gate": gate}


@router.post("/api/track/start")
def track_start(body: SessionName | None = None) -> dict:
    return hub().track.start_session((body.name if body else None) or "Sessão")


@router.post("/api/track/stop")
def track_stop() -> dict:
    return hub().track.stop_session()


@router.get("/api/track/sessions/{sid}")
def track_session(sid: int) -> dict:
    return {"session_id": sid, "laps": hub().track.session_laps(sid)}


@router.get("/api/gforce")
def gforce_get() -> dict:
    return hub().gforce.snapshot()


@router.post("/api/gforce/reset")
def gforce_reset() -> dict:
    hub().gforce.reset_peaks()
    return hub().gforce.snapshot()


@router.post("/api/gforce/calibrate")
def gforce_calibrate() -> dict:
    return hub().gforce.calibrate(1.5)


@router.get("/api/telemetry")
def telem_get() -> dict:
    h = hub()
    return {"telemetry": h.telem.snapshot(), "sessions": h.telem.sessions()}


@router.post("/api/telemetry/start")
def telem_start(body: SessionName | None = None) -> dict:
    return hub().telem.start(hz=body.hz if body else None, name=body.name if body else None)


@router.post("/api/telemetry/stop")
def telem_stop() -> dict:
    return hub().telem.stop()


@router.get("/api/telemetry/{sid}/csv")
def telem_csv(sid: int):
    try:
        name, data = hub().telem.export_csv(sid)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/api/telemetry/{sid}/rows")
def telem_rows(sid: int, limit: int = 4000) -> dict:
    return {"rows": hub().telem.session_rows(sid, limit)}


@router.get("/api/dashcam")
def dash_get() -> dict:
    h = hub()
    return {"dashcam": h.dash.status(), "clips": h.dash.list_clips()}


@router.post("/api/dashcam/start")
def dash_start(body: CamBody | None = None) -> dict:
    return hub().dash.start(body.camera_id if body else None)


@router.post("/api/dashcam/stop")
def dash_stop() -> dict:
    return hub().dash.stop()


@router.post("/api/dashcam/protect")
def dash_protect() -> dict:
    return hub().dash.protect("manual")


@router.post("/api/dashcam/{cid}/protect")
def dash_protect_id(cid: int) -> dict:
    return hub().dash.protect_id(cid)


@router.get("/api/dashcam/{cid}/file")
def dash_file(cid: int):
    p = hub().dash.clip_path(cid)
    if not p:
        raise HTTPException(404, "clipe não encontrado")
    media = "video/mp4" if p.suffix.lower() == ".mp4" else "application/octet-stream"
    return FileResponse(p, media_type=media, filename=p.name)


@router.post("/api/shift")
def shift_set(body: PointsBody) -> dict:
    h = hub()
    h.shift.set_points(body.points)
    return h.shift.tick()


@router.get("/api/health/car")
def health_get() -> dict:
    h = hub().health
    return {
        "health": h.snapshot(),
        "dtc_history": h.dtc_history(),
        "battery": h.battery(),
    }


@router.post("/api/health/odometer")
def health_odo(body: OdoBody) -> dict:
    return hub().health.set_odometer(body.km)


@router.post("/api/health/service")
def health_service(body: ServiceBody) -> dict:
    return hub().health.mark_service(body.item_id, body.km)


@router.get("/api/leds")
def leds_get() -> dict:
    return hub().leds.snapshot()


@router.post("/api/leds")
def leds_set(body: LedBody) -> dict:
    return hub().leds.set_mode(body.mode or "static", body.color, body.brightness)


@router.get("/api/tpms")
def tpms_get() -> dict:
    return hub().tpms.snapshot()


@router.post("/api/tpms/bind")
def tpms_bind(body: BindBody) -> dict:
    try:
        return hub().tpms.bind_wheel(body.wheel, body.sensor_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/valet")
def valet_get() -> dict:
    return hub().valet.snapshot()


@router.post("/api/valet/lock")
def valet_lock(body: PinBody | None = None) -> dict:
    pin = (body.pin if body else "") or None
    return hub().valet.lock(pin)


@router.post("/api/valet/unlock")
def valet_unlock(body: PinBody) -> dict:
    return hub().valet.unlock(body.pin)


@router.post("/api/valet/pin")
def valet_pin(body: PinBody) -> dict:
    if not body.new_pin:
        raise HTTPException(400, "novo PIN obrigatório")
    return hub().valet.change_pin(body.pin, body.new_pin)

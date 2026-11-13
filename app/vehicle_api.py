"""API de perfis, assistente de configuração, arte do carro e fotos."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from .config import ROOT
from . import body_art
from . import car_photo
from . import profiles as P
from . import vin as V

log = logging.getLogger(__name__)
router = APIRouter()
_get_state: Callable | None = None
BODIES_DIR = ROOT / "app" / "static" / "img" / "bodies"
UPLOADS = ROOT / "data" / "uploads"


def bind(get_state: Callable) -> None:
    global _get_state
    _get_state = get_state


def st():
    if not _get_state:
        raise HTTPException(503, "painel inicializando")
    return _get_state()


class SelectProfile(BaseModel):
    id: str
    paint: str | None = None
    body: str | None = None
    art_mode: str | None = None
    setup_completed: bool | None = True
    name: str | None = None


class OverlayBody(BaseModel):
    zones: dict


class PhotoSelect(BaseModel):
    index: int | None = None
    pageid: int | str | None = None
    force: bool = False


class DetectBody(BaseModel):
    vin: str | None = None
    online: bool = True


def _identity():
    s = st()
    return s.store.get_meta("vehicle") or {}


def _apply_profile(prof: dict, paint: str | None = None) -> dict:
    s = st()
    patch = {"profile_id": prof["id"]}
    if paint:
        patch["paint"] = paint
    if prof.get("body"):
        patch["body"] = prof["body"]
    P.save_state(patch)
    s.cfg = P.apply_to_config(s.cfg, prof)
    if paint:
        s.cfg.setdefault("ui", {})["car_color"] = paint
        s.settings = getattr(s, "settings", {}) or {}
        s.settings.setdefault("ui", {})["car_color"] = paint
    # identidade exibida
    ident = dict(_identity())
    ident["make"] = prof.get("make") or ident.get("make")
    ident["manufacturer"] = prof.get("make") or ident.get("manufacturer")
    ident["model"] = prof.get("model") or ident.get("model") or prof.get("name")
    ident["trim"] = prof.get("trim") or ident.get("trim")
    ident["engine"] = prof.get("engine") or ident.get("engine")
    ident["transmission"] = prof.get("transmission") or ident.get("transmission")
    ident["body"] = prof.get("body") or ident.get("body")
    ident["profile_id"] = prof["id"]
    ident["label"] = V._label(ident)
    ident["hud_hero"] = P.hero_public(prof)
    s.store.set_meta("vehicle", ident)
    s.store.set_meta("profile", P.public_view(prof))
    s.store.set_meta("body", ident.get("body") or "sedan")
    # shift points
    sport = getattr(s, "sport", None)
    pts = (prof.get("shift") or {}).get("rpm_points")
    if sport and pts:
        try:
            sport.shift.set_points(pts)
        except Exception:
            pass
    # health intervals (não apaga o histórico; só atualiza intervalos)
    if sport and prof.get("maintenance"):
        try:
            _sync_maintenance(sport.health, prof["maintenance"])
        except Exception:
            log.exception("manutenção do perfil")
    return ident


def _sync_maintenance(health, items: list[dict]) -> None:
    conn = health.conn
    for it in items:
        row = conn.execute("SELECT id FROM maintenance WHERE item_id=?", (it["id"],)).fetchone()
        if row:
            conn.execute(
                "UPDATE maintenance SET name=?, interval_km=?, interval_days=? WHERE item_id=?",
                (it.get("name"), it.get("interval_km"), it.get("interval_days"), it["id"]),
            )
        else:
            import time
            odo = health.odometer().get("total_km") or 0
            conn.execute(
                "INSERT INTO maintenance(item_id, name, interval_km, interval_days, last_km, last_at, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (it["id"], it.get("name"), it.get("interval_km"), it.get("interval_days"),
                 odo - (it.get("interval_km") or 0) * 0.7, time.time(), "perfil"),
            )
    conn.commit()


@router.get("/api/vehicle/profiles")
def api_profiles():
    return {"profiles": [P.public_view(p) for p in P.list_profiles()], "bodies": list(P.BODIES)}


@router.get("/api/vehicle")
def api_vehicle():
    s = st()
    state = P.load_state()
    ident = _identity()
    prof = P.active_profile(s.cfg)
    key = car_photo.search_key(ident)
    photo = car_photo.load_meta(key) if key and key != "car" else {}
    return {
        "identity": ident,
        "profile": P.public_view(prof),
        "state": {
            "profile_id": state.get("profile_id"),
            "setup_completed": bool(state.get("setup_completed")),
            "paint": state.get("paint") or (s.cfg.get("ui") or {}).get("car_color"),
            "art_mode": state.get("art_mode") or (prof.get("art") or {}).get("mode") or "auto",
            "body": state.get("body") or ident.get("body") or prof.get("body") or "sedan",
            "custom_side": state.get("custom_side"),
            "custom_top": state.get("custom_top"),
        },
        "photo": {
            "ready": bool(photo.get("abs_path") or photo.get("path")),
            "attribution": photo.get("attribution"),
            "license": photo.get("license"),
            "source_url": photo.get("source_url"),
            "zones": photo.get("zones") or state.get("zones"),
            "candidates": photo.get("candidates") or [],
            "selected": photo.get("selected"),
            "bg_removed": photo.get("bg_removed"),
        },
        "needs_setup": not P.setup_completed(),
        "suggested_profile": ident.get("suggested_profile"),
        "illustration": body_art.illustration(
            state.get("body") or ident.get("body") or prof.get("body") or "sedan"
        ),
    }


@router.post("/api/vehicle/profile")
def api_select_profile(body: SelectProfile):
    if body.id == "auto":
        ident = _identity()
        matched = P.match_profile(ident)
        prof = matched or P.get_profile("generic")
    else:
        prof = P.get_profile(body.id)
        if body.id not in {prof.get("id"), "generic"} and prof.get("id") == "generic" and body.id != "generic":
            raise HTTPException(404, f"perfil desconhecido: {body.id}")
    if body.body and body.body in P.BODIES:
        prof = dict(prof)
        prof["body"] = body.body
        P.save_state({"body": body.body})
    if body.name:
        # apelido local, não altera o yaml
        P.save_state({"display_name": body.name})
    ident = _apply_profile(prof, body.paint)
    if body.art_mode:
        P.save_state({"art_mode": body.art_mode})
    if body.setup_completed:
        P.save_state({"setup_completed": True})
        st().store.set_meta("needs_setup", False)
    # dispara busca de foto em background
    if (body.art_mode or "auto") in {"auto", "photo"} and ident.get("model"):
        threading.Thread(target=_bg_photo, args=(ident,), daemon=True).start()
    return api_vehicle()


@router.post("/api/vehicle/detect")
def api_detect(body: DetectBody | None = None):
    s = st()
    raw = (body.vin if body else None) or (s.store.get_meta("vehicle") or {}).get("vin")
    # tenta ler da ECU se não veio
    if not raw:
        try:
            raw = s.vehicle.read_vin()
        except Exception:
            raw = None
    ident = V.resolve_identity(s.cfg, raw, online=bool(body.online if body else True))
    matched = P.match_profile(ident)
    if matched:
        ident["suggested_profile"] = matched["id"]
        ident["body"] = ident.get("body") or matched.get("body")
        ident["label"] = V._label(ident)
    s.store.set_meta("vehicle", ident)
    return {"identity": ident, "suggested": P.public_view(matched) if matched else None}


@router.get("/api/vehicle/photos")
def api_photos():
    ident = _identity()
    key = car_photo.search_key(ident)
    return car_photo.load_meta(key)


@router.post("/api/vehicle/photos/search")
def api_photo_search():
    ident = _identity()
    if not ident.get("model") and not ident.get("make"):
        raise HTTPException(400, "identifique o veículo (VIN ou perfil) antes de buscar foto")
    cands = car_photo.collect_candidates(ident, st().cfg, limit=5)
    return {"candidates": cands, "query": car_photo.search_key(ident)}


@router.post("/api/vehicle/photos/select")
def api_photo_select(body: PhotoSelect):
    ident = _identity()
    key = car_photo.search_key(ident)
    meta = car_photo.load_meta(key)
    cands = meta.get("candidates") or []
    if not cands:
        cands = car_photo.collect_candidates(ident, st().cfg, limit=5)
    chosen = None
    if body.pageid is not None:
        chosen = next((c for c in cands if str(c.get("pageid")) == str(body.pageid)), None)
    elif body.index is not None and 0 <= body.index < len(cands):
        chosen = cands[body.index]
    elif cands:
        chosen = cands[0]
    if not chosen:
        raise HTTPException(404, "candidato não encontrado")
    try:
        result = car_photo.fetch_and_prepare(ident, chosen, st().cfg)
    except Exception as exc:
        raise HTTPException(502, f"falha ao baixar/processar a foto: {exc}") from exc
    P.save_state({"art_mode": "photo", "photo_key": key, "zones": result.get("zones")})
    st().store.set_meta("art_rev", (st().store.get_meta("art_rev") or 0) + 1)
    return result


@router.put("/api/vehicle/overlays")
def api_overlays(body: OverlayBody):
    ident = _identity()
    key = car_photo.search_key(ident)
    meta = car_photo.load_meta(key)
    meta["zones"] = body.zones
    if key and key != "car":
        car_photo.save_meta(key, meta)
    P.save_state({"zones": body.zones})
    return {"ok": True, "zones": body.zones}


@router.post("/api/vehicle/art/upload")
async def api_art_upload(
    side: UploadFile | None = File(default=None),
    top: UploadFile | None = File(default=None),
    view: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    state = P.load_state()
    pid = state.get("profile_id") or "custom"
    saved = {}
    pairs = []
    if side:
        pairs.append(("side", side))
    if top:
        pairs.append(("top", top))
    if file and view in {"side", "top"}:
        pairs.append((view, file))
    if not pairs:
        raise HTTPException(400, "envie side e/ou top (PNG ou SVG)")
    for which, up in pairs:
        raw = await up.read()
        name = up.filename or f"{which}.png"
        ext = Path(name).suffix.lower() or ".png"
        if ext not in {".png", ".svg", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(400, f"formato não suportado: {ext}")
        dest = UPLOADS / f"{pid}-{which}{ext}"
        dest.write_bytes(raw)
        saved[which] = str(dest.relative_to(ROOT))
        P.save_state({f"custom_{which}": saved[which]})
    P.save_state({"art_mode": "custom"})
    st().store.set_meta("art_rev", (st().store.get_meta("art_rev") or 0) + 1)
    return {"ok": True, "files": saved}


@router.get("/api/vehicle/art/{view}")
def api_art(view: str, body: str | None = None, mode: str | None = None):
    if view not in {"side", "top"}:
        raise HTTPException(404, "view deve ser side ou top")
    state = P.load_state()
    art_mode = mode or state.get("art_mode") or "auto"
    ident = _identity()
    # foto (só vista lateral)
    if view == "side" and art_mode in {"auto", "photo"}:
        key = state.get("photo_key") or car_photo.search_key(ident)
        png = car_photo.cached_png(key) if key else None
        if png:
            return FileResponse(png, media_type="image/png", headers={"Cache-Control": "no-cache"})
        if art_mode == "photo":
            raise HTTPException(404, "foto ainda não disponível")
    # custom
    if art_mode in {"custom", "auto"}:
        rel = state.get(f"custom_{view}")
        if rel:
            p = ROOT / rel
            if p.is_file():
                media = "image/svg+xml" if p.suffix.lower() == ".svg" else "image/png"
                return FileResponse(p, media_type=media, headers={"Cache-Control": "no-cache"})
        if art_mode == "custom":
            raise HTTPException(404, "arte personalizada ausente")
    # ilustração PNG por tipo de carroceria (lateral); SVG só se o PNG faltar
    b = (body or state.get("body") or ident.get("body") or "sedan").lower()
    if b not in P.BODIES:
        b = "sedan"
    if view == "side":
        png = body_art.side_png(b)
        if png:
            return FileResponse(png, media_type="image/png", headers={"Cache-Control": "no-cache"})
        svg = body_art.side_svg(b)
        if svg:
            return FileResponse(svg, media_type="image/svg+xml")
        raise HTTPException(404, f"silhueta {b} não encontrada")
    svg = body_art.top_svg(b)
    if not svg:
        raise HTTPException(404, f"silhueta {b}-top.svg não encontrada")
    return FileResponse(svg, media_type="image/svg+xml")


@router.get("/gallery", response_class=HTMLResponse)
def gallery():
    from .config import ROOT
    tiles = []
    labels = {"sedan": "Sedã", "hatch": "Hatch", "suv": "SUV",
              "pickup": "Picape", "coupe": "Cupê", "wagon": "Perua"}
    paints = {"sedan": "#b1121a", "hatch": "#1c3a6e", "suv": "#2e3a2e",
              "pickup": "#5a5c60", "coupe": "#1a1a1e", "wagon": "#3a2a1a"}
    for b, lab in labels.items():
        png = body_art.side_png(b)
        if png:
            url = f"/static/img/bodies/{b}.png"
            tiles.append(
                '<figure style="--car-paint:%s">'
                '<div class="stage"><div class="fit">'
                '<img src="%s" alt="%s">'
                '<div class="tint" style="mask-image:url(\'%s\');'
                '-webkit-mask-image:url(\'%s\')"></div>'
                '</div></div><figcaption>%s</figcaption></figure>'
                % (paints[b], url, lab, url, url, lab)
            )
        else:
            svg = (BODIES_DIR / f"{b}.svg").read_text(encoding="utf-8")
            svg = svg.replace('<?xml version="1.0" encoding="UTF-8"?>', "").strip()
            tiles.append(
                f'<figure style="--car-paint:{paints[b]}"><div class="stage">{svg}</div>'
                f"<figcaption>{lab}</figcaption></figure>"
            )
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Painel TFT — tipos de carroceria</title>
<style>
  html,body{{margin:0;background:#0a0404;color:#f2e8e8;font-family:Rajdhani,Segoe UI,sans-serif}}
  h1{{font-family:Orbitron,sans-serif;font-size:18px;letter-spacing:.14em;color:#e10600;
      text-align:center;margin:12px 0 8px}}
  .grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:8px 16px 20px}}
  figure{{margin:0;background:linear-gradient(180deg,#160808,#0a0404);border:1px solid #3a1515;
          padding:8px;display:flex;flex-direction:column;min-width:0;overflow:hidden}}
  .stage{{height:200px;display:flex;align-items:center;justify-content:center;overflow:hidden}}
  .stage svg{{width:100%;height:190px;display:block}}
  .fit{{position:relative;display:inline-block;max-height:190px;max-width:100%}}
  .fit img{{max-height:190px;max-width:100%;height:auto;width:auto;display:block}}
  .tint{{position:absolute;inset:0;pointer-events:none;background:var(--car-paint,#b1121a);
         mix-blend-mode:color;opacity:.5;
         mask-size:100% 100%;mask-repeat:no-repeat;mask-mode:alpha;
         -webkit-mask-size:100% 100%;-webkit-mask-repeat:no-repeat}}
  figcaption{{text-align:center;letter-spacing:.12em;font-size:13px;color:#e10600;font-weight:700}}
</style></head>
<body>
  <h1>PAINEL TFT · TIPOS DE CARROCERIA</h1>
  <div class="grid">{''.join(tiles)}</div>
</body></html>"""
    return HTMLResponse(html)


def _bg_photo(ident: dict) -> None:
    try:
        car_photo.ensure_photo(ident, st().cfg)
        st().store.set_meta("art_rev", (st().store.get_meta("art_rev") or 0) + 1)
    except Exception:
        log.exception("foto em background")


def boot(state, cfg, ident: dict) -> None:
    """Chamado no lifespan: aplica perfil salvo, sugere, dispara foto."""
    stt = P.load_state()
    if stt.get("profile_id"):
        prof = P.get_profile(stt["profile_id"])
        ident2 = _apply_profile(prof, stt.get("paint"))
        ident = ident2 or ident
    else:
        matched = P.match_profile(ident)
        if matched:
            ident["suggested_profile"] = matched["id"]
            ident["body"] = ident.get("body") or matched.get("body")
            ident["label"] = V._label(ident)
            state.store.set_meta("vehicle", ident)
    state.store.set_meta("needs_setup", not P.setup_completed())
    state.store.set_meta("body", ident.get("body") or stt.get("body") or "sedan")
    if ident.get("make") and ident.get("model"):
        threading.Thread(target=_bg_photo, args=(ident,), daemon=True).start()

"""Foto do carro: busca no Wikimedia Commons, cache, remoção de fundo e zonas de overlay."""

from __future__ import annotations

import json
import logging
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import ROOT

log = logging.getLogger(__name__)

UA = "PainelTFT/0.3 (vehicle dashboard; https://localhost; pt-BR)"
COMMONS = "https://commons.wikimedia.org/w/api.php"
CACHE = ROOT / "data" / "vehicles"


def _cfg(cfg: dict | None) -> dict:
    return dict((cfg or {}).get("car_photo") or {})


def cache_dir(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key)[:80] or "car"
    d = CACHE / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def meta_path(key: str) -> Path:
    return cache_dir(key) / "meta.json"


def load_meta(key: str) -> dict:
    p = meta_path(key)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_meta(key: str, data: dict) -> dict:
    p = meta_path(key)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def search_key(identity: dict) -> str:
    bits = [str(identity.get("year") or ""), identity.get("make") or "", identity.get("model") or ""]
    return " ".join(b for b in bits if b).strip() or "car"



def search_commons(identity: dict, limit: int = 12) -> list[dict[str, Any]]:
    """Busca no Commons: várias páginas, categorias da geração e consultas de perfil lateral."""
    seen: set[str] = set()
    found: list[dict] = []
    for q in _search_queries(identity):
        if q.startswith("cat:"):
            items = _category_files(q[4:], limit=80)
        else:
            items = []
            for offset in (0, 20):
                items.extend(_commons_query(q, limit=20, offset=offset))
        for item in items:
            pid = str(item.get("pageid") or item.get("url"))
            if pid in seen:
                continue
            seen.add(pid)
            found.append(item)
        # percorre todas as consultas e categorias; não para na primeira página
    found.sort(key=lambda it: (_match_score(it, identity), it.get("width") or 0), reverse=True)
    return found[:limit]


def _search_queries(identity: dict) -> list[str]:
    year = identity.get("year") or ""
    make = identity.get("make") or identity.get("manufacturer") or ""
    model = identity.get("model") or ""
    body = identity.get("body") or ""
    q: list[str] = []
    if make and model:
        q.append(f'{make} {model} "side view"')
        q.append(f'{make} {model} "left side view"')
        q.append(f'{make} {model} "right side view"')
        q.append(f"{make} {model} profile")
        q.append(f"{make} {model} lateral")
    if year and make and model:
        q.append(f"{year} {make} {model}")
        q.append(f"{make} {model} {year}")
        if body:
            q.append(f"{year} {make} {model} {body}")
        y = None
        try:
            y = int(year)
        except (TypeError, ValueError):
            pass
        if y:
            q.append(f"{make} {model} ({y} facelift)")
            q.append(f"{make} {model} ({y - 1} facelift)")
    for cat in _category_hints(identity):
        q.append("cat:" + cat)
    # dedup preserving order
    out, seen = [], set()
    for item in q:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _category_hints(identity: dict) -> list[str]:
    make = (identity.get("make") or identity.get("manufacturer") or "").strip()
    model = (identity.get("model") or "").strip()
    year = identity.get("year")
    cats: list[str] = []
    if make and model:
        cats.append(f"{make} {model}")
        if year:
            cats.append(f"{make} {model} ({year})")
            cats.append(f"{make} {model} ({year} facelift)")
            cats.append(f"{make} {model} (tenth generation)")
        try:
            y = int(year) if year else 0
        except (TypeError, ValueError):
            y = 0
        # Lancer X / CY0 cobre 2007–2017 (inclui o facelift 2015 e o HL 2016)
        if make.lower() == "mitsubishi" and "lancer" in model.lower():
            if not y or 2007 <= y <= 2017:
                cats.extend([
                    "Mitsubishi Lancer CY0",
                    "Mitsubishi Lancer (2007)",
                    "Mitsubishi Lancer (2015 facelift)",
                    "Mitsubishi Lancer (tenth generation)",
                    "Mitsubishi Lancer Fortis",
                    "Mitsubishi Lancer EX (CY0)",
                    "Mitsubishi Lancer Sportback",
                ])
    return cats


def _category_files(cat: str, limit: int = 50) -> list[dict]:
    """Lista ficheiros de uma categoria do Commons (um nível)."""
    title = cat if cat.lower().startswith("category:") else f"Category:{cat}"
    members: list[str] = []
    cont = None
    try:
        while len(members) < limit * 2:
            params = {
                "action": "query", "format": "json",
                "list": "categorymembers", "cmtitle": title,
                "cmtype": "file", "cmlimit": "100",
            }
            if cont:
                params["cmcontinue"] = cont
            url = COMMONS + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for m in (data.get("query") or {}).get("categorymembers") or []:
                if (m.get("title") or "").startswith("File:"):
                    members.append(m["title"])
            cont = (data.get("continue") or {}).get("cmcontinue")
            if not cont:
                break
    except Exception as exc:
        log.info("categoria %s falhou: %s", cat, exc)
        return []
    if not members:
        return []
    out: list[dict] = []
    for i in range(0, min(len(members), 80), 20):
        chunk = members[i:i + 20]
        params = {
            "action": "query", "format": "json",
            "titles": "|".join(chunk),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime|dimensions",
            "iiurlwidth": "1600",
        }
        url = COMMONS + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=18) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            continue
        for page in (data.get("query") or {}).get("pages", {}).values():
            item = _item_from_page(page)
            if item:
                out.append(item)
        if len(out) >= limit:
            break
    return out[:limit]


def _side_score(it: dict) -> float:
    w, h = it.get("width") or 0, it.get("height") or 1
    aspect = w / max(1, h)
    it["aspect"] = round(aspect, 3)
    # fotos de perfil já recortadas são bem largas; 4:3 também pode ser perfil
    # com muito céu/chão, então o aspecto original pesa pouco (o recorte decide).
    if 2.2 <= aspect <= 3.4:
        return 2.0 + min(w / 2000.0, 1.0)
    if 1.6 <= aspect < 2.2:
        return 1.0
    return 0.2



def _model_years_in_title(title: str) -> set[str]:
    """Anos que parecem ser do modelo, não da data da foto (17-09-2016, 2016-11-13, 20160723)."""
    cleaned = re.sub(r"\(\s*\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\s*\)", " ", title)
    cleaned = re.sub(r"\b(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:19|20)\d{6}\b", " ", cleaned)
    return set(re.findall(r"\b((?:19|20)\d{2})\b", cleaned))


def _blob(it: dict) -> str:
    return " ".join(
        str(it.get(k) or "") for k in ("title", "description", "credit")
    ).lower()


def _match_score(it: dict, identity: dict) -> float:
    """Prefere perfil lateral verdadeiro; penaliza 3/4, frente, traseira e interior."""
    score = _side_score(it)
    text = _blob(it)
    title = (it.get("title") or "").lower()
    year = str(identity.get("year") or "")
    make = (identity.get("make") or identity.get("manufacturer") or "").lower()
    model = (identity.get("model") or "").lower()
    body = (identity.get("body") or "").lower()
    years_in_title = _model_years_in_title(title)

    if make:
        score += 2.0 if make in text else -12.0
    if model and model in text:
        score += 2.0
    if body and body in text:
        score += 1.0
    # Dodge Lancer, B-1B Lancer, etc.
    if re.search(
        r"\b(dodge|chrysler|plymouth|aircraft|airplane|aeroplane|bomber|"
        r"b-1|b1b|boeing|rockwell|helicopter|motorcycle)\b",
        text,
    ):
        score -= 20.0

    if year and year in years_in_title:
        score += 3.0
    elif year:
        try:
            y = int(year)
            nearby = sum(1 for n in (y - 2, y - 1, y + 1, y + 2) if str(n) in years_in_title)
            score += 1.2 * nearby
            if years_in_title:
                oldest = min(int(v) for v in years_in_title)
                delta = abs(oldest - y)
                # mesma geração (Lancer X 2007–2017) não é descartada
                if delta >= 20:
                    score -= 12.0
                elif delta >= 15:
                    score -= 8.0
                elif delta >= 12:
                    score -= 3.0
                elif delta >= 8:
                    score -= 1.0
            else:
                # sem ano no título: leve penalidade (ex. Sportback 2010 ainda compete)
                score -= 1.5
        except ValueError:
            pass

    if make == "mitsubishi" and "lancer" in model:
        if re.search(r"\b(cy0|fortis|sportback|tenth generation|2015 facelift|cf my)\b", text):
            score += 2.5

    # "front side view" / "depan" são 3/4, não perfil
    frontish = re.search(
        r"\b(front left|front right|rear left|rear right|3/4|three[\s-]?quarter|quarter|"
        r"front side|rear side|back side|front view|rear view|back view|"
        r"depan|belakang|frente|traseira|avant|arri[eè]re|vorne|hinten|dietro)\b",
        text,
    )
    true_side = bool(
        re.search(r"\b(left|right)\s+side\s+view\b", text)
        or re.search(r"\b(side profile|perfil lateral|vista lateral)\b", text)
        or (re.search(r"\bside view\b", text) and not frontish)
    )
    if true_side and not frontish:
        score += 8.0
    elif re.search(r"\b(side|profile|lateral|perfil)\b", title) and not frontish:
        score += 5.0
    elif re.search(r"\b(side|profile|lateral|perfil)\b", text) and not frontish:
        score += 2.5
    if frontish:
        # "front left side.jpg" / "Front side view" / depan
        if re.search(r"\b(front left|front right|rear left|rear right|3/4|three[\s-]?quarter)\b", text):
            score -= 6.0
        else:
            score -= 8.0
    elif re.search(r"\b(interior|inside|engine|badge|logo|emblem|cropped)\b", text):
        score -= 4.0

    model_is_evo = "evolution" in model or re.search(r"\bevo\b", model)
    if not model_is_evo and re.search(r"\bevo\b|evolution|voltex|rally|wrc|tuned|body kit", text):
        score -= 8.0
    return score


def _commons_query(search: str, limit: int = 8, offset: int = 0) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": search,
        "gsrnamespace": "6",  # File
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime|dimensions",
        "iiurlwidth": "1600",
    }
    if offset:
        params["gsroffset"] = str(offset)
    url = COMMONS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=14) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.info("busca Commons falhou (%s): %s", search, exc)
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for page in pages.values():
        item = _item_from_page(page)
        if item:
            out.append(item)
    return out


def _item_from_page(page: dict) -> dict | None:
    infos = page.get("imageinfo") or []
    if not infos:
        return None
    info = infos[0]
    mime = (info.get("mime") or "").lower()
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    w, h = info.get("width") or 0, info.get("height") or 0
    if w < 400 or h < 200:
        return None
    meta = info.get("extmetadata") or {}

    def _m(key, field="value"):
        v = meta.get(key) or {}
        return (v.get(field) if isinstance(v, dict) else v) or ""

    title = page.get("title") or ""
    desc = _strip_html(_m("ImageDescription"))
    low = (title + " " + desc).lower()
    if any(k in low for k in ("logo", "interior", "engine", "motor bay", "badge", "emblem", "steering", "dealership")):
        return None
    return {
        "pageid": page.get("pageid"),
        "title": title.replace("File:", ""),
        "url": info.get("thumburl") or info.get("url"),
        "fullurl": info.get("url"),
        "descriptionurl": info.get("descriptionurl"),
        "width": w,
        "height": h,
        "mime": mime,
        "description": desc,
        "license": _strip_html(_m("LicenseShortName") or _m("License")),
        "license_url": _m("LicenseUrl"),
        "artist": _strip_html(_m("Artist")),
        "credit": _strip_html(_m("Credit") or _m("Attribution")),
        "attribution": _attribution(_m("Artist"), _m("LicenseShortName") or _m("License"), info.get("descriptionurl")),
    }


def search_fallback(identity: dict, cfg: dict | None, limit: int = 5) -> list[dict]:
    """Provedor opcional com chave (Unsplash). Só roda se configurado."""
    conf = _cfg(cfg)
    provider = (conf.get("fallback_provider") or "").lower()
    key = conf.get("api_key") or conf.get("unsplash_key") or ""
    if provider not in {"unsplash"} or not key:
        return []
    q = search_key(identity) + " car side"
    url = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode({
        "query": q, "per_page": limit, "orientation": "landscape",
    })
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Authorization": f"Client-ID {key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log.info("Unsplash falhou: %s", exc)
        return []
    out = []
    for it in data.get("results") or []:
        u = (it.get("urls") or {}).get("regular") or (it.get("urls") or {}).get("full")
        if not u:
            continue
        user = (it.get("user") or {}).get("name") or "Unsplash"
        out.append({
            "pageid": it.get("id"),
            "title": it.get("description") or it.get("alt_description") or q,
            "url": u,
            "fullurl": u,
            "descriptionurl": it.get("links", {}).get("html"),
            "width": it.get("width"),
            "height": it.get("height"),
            "mime": "image/jpeg",
            "license": "Unsplash License",
            "artist": user,
            "attribution": f"Foto: {user} / Unsplash",
        })
    return out


def collect_candidates(identity: dict, cfg: dict | None = None, limit: int = 8) -> list[dict]:
    items = search_commons(identity, limit=max(limit, 16))
    if len(items) < 3:
        items.extend(search_fallback(identity, cfg, limit=limit))
    # persiste a lista para o app escolher
    key = search_key(identity)
    meta = load_meta(key)
    meta["query"] = key
    meta["identity"] = {k: identity.get(k) for k in ("vin", "make", "model", "year", "body")}
    meta["candidates"] = items[:limit]
    save_meta(key, meta)
    return items[:limit]


def fetch_and_prepare(identity: dict, candidate: dict, cfg: dict | None = None) -> dict:
    """Baixa, remove fundo, normaliza orientação, estima overlays e cacheia PNG."""
    key = search_key(identity)
    d = cache_dir(key)
    raw_path = d / "source.jpg"
    out_path = d / "car.png"
    url = candidate.get("url") or candidate.get("fullurl")
    if not url:
        raise ValueError("candidato sem URL")
    _download(url, raw_path)
    cut = remove_background(raw_path, out_path)
    used = cut if cut and cut.is_file() else raw_path
    # se rembg gerou PNG, used é out_path; senão copiamos o original
    if used != out_path:
        _copy_as_png(used, out_path)
    flipped = normalize_orientation(out_path)
    zones = estimate_zones(out_path)
    meta = load_meta(key)
    try:
        from PIL import Image as _Im
        iw, ih = _Im.open(out_path).size
    except Exception:
        iw = ih = 0
    zones.setdefault("image", {"w": iw, "h": ih})
    meta.update({
        "query": key,
        "selected": candidate,
        "path": str(out_path.relative_to(ROOT)) if out_path.is_relative_to(ROOT) else str(out_path),
        "abs_path": str(out_path),
        "flipped": flipped,
        "zones": zones,
        "side_on": bool(zones.get("side_on")),
        "wheels_confident": bool(zones.get("wheels_confident")),
        "bg_removed": bool(cut),
        "image_w": iw,
        "image_h": ih,
        "attribution": candidate.get("attribution"),
        "license": candidate.get("license"),
        "license_url": candidate.get("license_url"),
        "artist": candidate.get("artist"),
        "source_url": candidate.get("descriptionurl") or candidate.get("fullurl"),
    })
    save_meta(key, meta)
    return meta


def fetch_best(identity: dict, cfg: dict | None = None, candidates: list | None = None, tries: int = 6) -> dict | None:
    """Prepara as melhores candidatas até achar um perfil lateral confiável."""
    cands = list(candidates or collect_candidates(identity, cfg, limit=12))
    if not cands:
        return None
    cands.sort(key=lambda c: _match_score(c, identity), reverse=True)
    best = None
    best_q = -999.0
    last = None
    for cand in cands[: max(1, tries)]:
        try:
            meta = fetch_and_prepare(identity, cand, cfg)
        except Exception:
            log.exception("falha ao preparar %s", cand.get("title"))
            continue
        last = meta
        q = _cutout_quality(meta)
        log.info("candidata %s  q=%.2f  side=%s  aspecto=%s",
                 (cand.get("title") or "")[:60], q, meta.get("side_on"),
                 (meta.get("zones") or {}).get("aspect"))
        if q > best_q:
            best, best_q = meta, q
    if not best:
        return None
    win_id = (best.get("selected") or {}).get("pageid")
    last_id = (last.get("selected") or {}).get("pageid") if last else None
    if last_id != win_id and best.get("selected"):
        try:
            best = fetch_and_prepare(identity, best["selected"], cfg)
        except Exception:
            log.exception("reprocessar vencedor")
    key = search_key(identity)
    merged = load_meta(key)
    merged.update(best or {})
    merged["candidates"] = cands
    save_meta(key, merged)
    return merged


def _cutout_quality(meta: dict) -> float:
    z = meta.get("zones") or {}
    img = z.get("image") or {}
    w, h = img.get("w") or meta.get("image_w") or 0, img.get("h") or meta.get("image_h") or 1
    aspect = w / max(1, h)
    q = 0.0
    if 2.3 <= aspect <= 3.2:
        q += 6.0 + max(0.0, 1.0 - abs(aspect - 2.75)) * 4.0
    elif 2.15 <= aspect < 2.3 or 3.2 < aspect <= 3.5:
        q += 2.0
    if z.get("wheels_confident"):
        q += 5.0
    if z.get("side_on"):
        q += 4.0
    q -= float(z.get("corner_junk") or 0) * 5.0
    return q


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp, dest.open("wb") as fh:
        fh.write(resp.read())
    return dest


def _copy_as_png(src: Path, dest: Path) -> Path:
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG")
    return dest



_REMBG_SESSION = None


def _rembg_session():
    """Sessão rembg com o modelo pequeno u2netp (documentado no README para o Pi)."""
    global _REMBG_SESSION
    if _REMBG_SESSION is not None:
        return _REMBG_SESSION
    try:
        from rembg import new_session  # type: ignore
        _REMBG_SESSION = new_session("u2netp")
        return _REMBG_SESSION
    except Exception as exc:
        log.info("sessão u2netp indisponível (%s); rembg usa o padrão", exc)
        return None


def remove_background(src: Path, dest: Path) -> Path | None:
    """Remove o fundo com rembg/u2net, se instalado. Senão retorna None."""
    try:
        from rembg import remove  # type: ignore
        from PIL import Image
        import io
    except Exception as exc:
        log.info("rembg não instalado (%s). A foto fica com o fundo original.", exc)
        return None
    try:
        raw = src.read_bytes()
        # u2netp (~4.7 MB) — cabe no Pi; não usar o modelo bria (~1 GB)
        session = _rembg_session()
        out = remove(raw, session=session) if session is not None else remove(raw)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(out)
        # recorta o bounding box do alfa para o carro ocupar a tela
        im = Image.open(io.BytesIO(out)).convert("RGBA")
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
            pad = max(8, min(im.size) // 30)
            canvas = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
            canvas.paste(im, (pad, pad))
            canvas = _keep_main_subject(canvas)
            # o TFT tem 800×480; 1600 px de largura já é o bastante
            if canvas.width > 1600:
                nh = max(1, int(1600 * canvas.height / canvas.width))
                canvas = canvas.resize((1600, nh), Image.Resampling.LANCZOS)
            canvas.save(dest, "PNG")
        return dest
    except Exception as exc:
        log.warning("rembg falhou: %s", exc)
        return None





def _trim_edge_stubs(keep):
    """Corta protuberâncias laterais (meio-fio, grades) que não chegam ao soleira."""
    import numpy as np
    ys, xs = np.where(keep > 0)
    if len(xs) < 50:
        return keep
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    bottoms = []
    for x in range(x0 + int(bw * 0.35), x0 + int(bw * 0.65)):
        col = np.where(keep[:, x] > 0)[0]
        if len(col):
            bottoms.append(int(col.max()))
    if not bottoms:
        return keep
    typ_bottom = int(np.median(bottoms))
    out = keep.copy()
    for start, end, step in ((x1, x0 + int(bw * 0.72), -1), (x0, x1 - int(bw * 0.72), 1)):
        for x in range(start, end, step):
            col = np.where(out[:, x] > 0)[0]
            if len(col) == 0:
                continue
            if typ_bottom - int(col.max()) > bh * 0.08:
                out[:, x] = 0
            else:
                break
    return out


def _keep_main_subject(im):
    """Mantém só o maior componente, preenche buracos pequenos e re-recorta."""
    try:
        import numpy as np
        from PIL import Image
        import cv2
    except Exception:
        return im
    try:
        arr = np.array(im)
        alpha = arr[:, :, 3]
        mask = (alpha > 30).astype("uint8")
        # erosão mais forte quebra pontes (meio-fio, limpador, outro carro ao fundo)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
        eroded = cv2.erode(mask, k, iterations=2)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(eroded, 8)
        if n <= 1:
            keep = mask
        else:
            areas = stats[1:, cv2.CC_STAT_AREA]
            main = 1 + int(areas.argmax())
            keep = (labels == main).astype("uint8")
            keep = cv2.dilate(keep, k, iterations=2)
            keep = cv2.bitwise_and(keep, mask)
        # preenche buracos internos (não o fundo)
        inv = (1 - keep) * 255
        padded = cv2.copyMakeBorder(inv, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=255)
        ff = padded.copy()
        cv2.floodFill(ff, None, (0, 0), 0)
        holes = ff[1:-1, 1:-1] > 0
        keep = np.where(holes, 1, keep).astype("uint8")
        # fecha frestas pequenas
        close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, close_k)
        keep = _trim_edge_stubs(keep)
        arr[:, :, 3] = np.where(keep.astype(bool), alpha, 0)
        out = Image.fromarray(arr, "RGBA")
        bbox = out.getbbox()
        if not bbox:
            return im
        out = out.crop(bbox)
        pad = max(8, min(out.size) // 30)
        canvas = Image.new("RGBA", (out.width + pad * 2, out.height + pad * 2), (0, 0, 0, 0))
        canvas.paste(out, (pad, pad))
        return canvas
    except Exception:
        return im


def normalize_orientation(path: Path, face: str = "left") -> bool:
    """Vira a foto se o 'nariz' parece estar do lado errado. face='left' = frente à esquerda."""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return False
    im = Image.open(path).convert("RGBA")
    arr = np.array(im)
    alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full(arr.shape[:2], 255)
    # máscara
    mask = alpha > 20
    # perfil da silhueta: soma de pixels por coluna
    cols = mask.sum(axis=0)
    if cols.sum() < 100:
        return False
    # frente costuma ser mais 'afiada' (a ocupação cresce mais rápido numa ponta)
    n = len(cols)
    left = cols[: n // 3]
    right = cols[n * 2 // 3 :]
    # ponta = primeira coluna com massa significativa vs última
    def tip_sharpness(seg, from_start: bool) -> float:
        s = seg if from_start else seg[::-1]
        total = s.sum() or 1
        # índice onde chega a 15% da massa
        acc = 0
        for i, v in enumerate(s):
            acc += v
            if acc >= 0.15 * total:
                return 1.0 / (i + 1)
        return 0.0
    left_tip = tip_sharpness(left, True)
    right_tip = tip_sharpness(right, False)
    # também: a frente costuma ter o farol mais claro na faixa média
    h, w = mask.shape
    mid = arr[int(h * 0.35): int(h * 0.7), :, :3].astype("int16")
    mid_mask = mask[int(h * 0.35): int(h * 0.7), :]
    lum = mid.mean(axis=2)
    left_lum = lum[:, : w // 4][mid_mask[:, : w // 4]].mean() if mid_mask[:, : w // 4].any() else 0
    right_lum = lum[:, w * 3 // 4 :][mid_mask[:, w * 3 // 4 :]].mean() if mid_mask[:, w * 3 // 4 :].any() else 0
    # decide: se a ponta direita é bem mais afiada e o brilho está à direita, está virado
    faces_right = (right_tip > left_tip * 1.15) or (right_lum > left_lum + 18 and right_tip >= left_tip * 0.9)
    should_flip = faces_right if face == "left" else (not faces_right)
    if should_flip:
        im.transpose(Image.FLIP_LEFT_RIGHT).save(path, "PNG")
        return True
    return False



def estimate_zones(path: Path) -> dict[str, Any]:
    """Estima rodas e zonas de luz; declara se a imagem é um perfil lateral confiável."""
    try:
        from PIL import Image
        import numpy as np
    except Exception:
        return _default_zones()
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    arr = np.array(im)
    alpha = arr[:, :, 3] if arr.shape[2] == 4 else np.full((h, w), 255, np.uint8)
    mask = alpha > 30
    wheels = _detect_wheels(arr, mask)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return _default_zones()
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    aspect = w / max(1, h)
    bbox = {"x": x0 / w, "y": y0 / h, "w": bw / w, "h": bh / h}
    confident = _wheels_confident(wheels, bbox, w, h)
    junk = _hood_clutter(mask, x0, x1, y0, y1)
    side_on = (2.25 <= aspect <= 3.4) and confident and junk < 0.40
    mid_y = y0 + int(bh * 0.42)
    box_h = max(8, int(bh * 0.16))
    box_w = max(10, int(bw * 0.10))
    hl = {"x": (x0 + int(bw * 0.02)) / w, "y": (mid_y - box_h / 2) / h,
          "w": box_w / w, "h": box_h / h}
    tl = {"x": (x1 - int(bw * 0.02) - box_w) / w, "y": (mid_y - box_h / 3) / h,
          "w": box_w / w, "h": box_h / h}
    turn_fl = dict(hl, y=hl["y"] + hl["h"] * 0.55, h=hl["h"] * 0.45, w=hl["w"] * 0.7)
    turn_rl = dict(tl, y=tl["y"] + tl["h"] * 0.5, h=tl["h"] * 0.45, w=tl["w"] * 0.7)
    return {
        "units": "fraction",
        "bbox": bbox,
        "image": {"w": w, "h": h},
        "aspect": round(aspect, 3),
        "side_on": side_on,
        "wheels_confident": confident,
        "corner_junk": round(junk, 3),  # na verdade hood clutter
        # só devolve rodas quando o perfil é lateral e a detecção é firme
        "wheels": wheels if (side_on and confident) else [],
        "headlight": hl,
        "taillight": tl,
        "turn_fl": turn_fl,
        "turn_rl": turn_rl,
    }


def _wheels_confident(wheels: list[dict], bbox: dict, w: int, h: int) -> bool:
    if len(wheels) != 2:
        return False
    a, b = wheels[0], wheels[1]
    if abs(a["y"] - b["y"]) > 0.08:
        return False
    ra, rb = float(a.get("r") or 0), float(b.get("r") or 0)
    if min(ra, rb) < 0.02 or max(ra, rb) / min(ra, rb) > 1.35:
        return False
    if a["y"] < 0.58 or b["y"] < 0.58:
        return False
    y1 = bbox["y"] + bbox["h"]
    for wh in wheels:
        rh = wh.get("r_h") or (wh["r"] * w / max(1, h))
        bottom = wh["y"] + rh
        if y1 - bottom > 0.18:
            return False
    dx = abs(a["x"] - b["x"])
    if dx < 0.32 or dx > 0.78:
        return False
    # as duas rodas devem ficar perto das pontas do recorte (perfil, não 3/4)
    xs = sorted((a["x"], b["x"]))
    left, width = bbox["x"], max(bbox["w"], 0.01)
    right = left + width
    if (xs[0] - left) / width > 0.36:
        return False
    if (right - xs[1]) / width > 0.36:
        return False
    return True


def _hood_clutter(mask, x0, x1, y0, y1) -> float:
    """Preenchimento do capô/traseira na faixa alta: alto quando outro carro sobra atrás."""
    import numpy as np
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    upper = mask[y0:y0 + max(1, int(bh * 0.38)), :]
    b1 = upper[:, x0 + int(bw * 0.10):x0 + int(bw * 0.32)]
    b2 = upper[:, x0 + int(bw * 0.68):x0 + int(bw * 0.90)]
    m1 = float(b1.mean()) if b1.size else 0.0
    m2 = float(b2.mean()) if b2.size else 0.0
    # o capô limpo é vazio em cima; o teto/aerofólio preenche o outro lado — usamos o mínimo
    return min(m1, m2)


def _detect_wheels(arr, mask) -> list[dict]:
    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    h, w = mask.shape
    gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
    roi = gray.copy()
    roi[mask == False] = 255
    y0 = int(h * 0.40)
    crop = cv2.GaussianBlur(roi[y0:, :], (7, 7), 1.2)
    min_r = max(8, int(h * 0.055))
    max_r = max(min_r + 4, int(h * 0.16))
    circles = cv2.HoughCircles(
        crop, cv2.HOUGH_GRADIENT, dp=1.2, minDist=int(w * 0.18),
        param1=80, param2=18, minRadius=min_r, maxRadius=max_r,
    )
    if circles is None:
        return []
    yy, xx = np.ogrid[:h, :w]
    scored = []
    for c in circles[0]:
        cx, cy, r = float(c[0]), float(c[1]) + y0, float(c[2])
        if not (0.06 < cx / w < 0.94 and 0.42 < cy / h < 0.88):
            continue
        if (cy + r) / h > 1.02:
            continue
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (d2 <= (r * 0.95) ** 2) & (d2 >= (r * 0.65) ** 2) & mask
        if ring.sum() < 20:
            continue
        ring_m = float(gray[ring].mean())
        # pneu = anel escuro; farol / porta não
        if ring_m > 115:
            continue
        scored.append((ring_m, {"x": cx / w, "y": cy / h, "r": r / w, "r_h": r / h}))
    if not scored:
        return []
    scored.sort(key=lambda s: s[0])  # anel do pneu mais escuro primeiro
    picked = [scored[0][1]]
    for _, cand in scored[1:]:
        if all(abs(cand["x"] - p["x"]) >= 0.22 for p in picked):
            picked.append(cand)
        if len(picked) == 2:
            break
    picked.sort(key=lambda c: c["x"])
    return picked


def _heuristic_wheels(mask, w, h) -> list[dict]:
    import numpy as np
    # duas posições típicas no terço inferior da silhueta
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return _default_zones()["wheels"]
    x0, x1 = xs.min(), xs.max()
    y1 = ys.max()
    bw = x1 - x0
    r = 0.09 * w
    cy = (y1 / h) - (r / h) * 0.15
    return [
        {"x": (x0 + 0.18 * bw) / w, "y": cy, "r": r / w, "r_h": r / h},
        {"x": (x0 + 0.82 * bw) / w, "y": cy, "r": r / w, "r_h": r / h},
    ]


def _default_zones() -> dict:
    return {
        "units": "fraction",
        "wheels": [
            {"x": 0.22, "y": 0.78, "r": 0.09, "r_h": 0.18},
            {"x": 0.78, "y": 0.78, "r": 0.09, "r_h": 0.18},
        ],
        "headlight": {"x": 0.04, "y": 0.42, "w": 0.10, "h": 0.12},
        "taillight": {"x": 0.86, "y": 0.44, "w": 0.10, "h": 0.12},
        "turn_fl": {"x": 0.06, "y": 0.52, "w": 0.07, "h": 0.07},
        "turn_rl": {"x": 0.87, "y": 0.54, "w": 0.07, "h": 0.07},
    }


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").replace("&nbsp;", " ").strip()


def _attribution(artist: str, license_name: str, url: str | None) -> str:
    artist = _strip_html(artist) or "autor desconhecido"
    license_name = _strip_html(license_name) or "licença livre"
    bits = [f"{artist}", license_name]
    if url:
        bits.append(url)
    return " · ".join(bits)


def cached_png(key: str) -> Path | None:
    p = cache_dir(key) / "car.png"
    return p if p.is_file() else None


def ensure_photo(identity: dict, cfg: dict | None = None, force: bool = False) -> dict | None:
    """Se já houver PNG em cache, devolve o meta; senão busca, escolhe o 1º e prepara."""
    key = search_key(identity)
    if not key or key == "car":
        return None
    meta = load_meta(key)
    png = cached_png(key)
    if png and meta.get("path") and not force:
        return meta
    try:
        cands = meta.get("candidates") or collect_candidates(identity, cfg, limit=12)
        if not cands:
            return None
        return fetch_best(identity, cfg, candidates=cands, tries=6)
    except Exception:
        log.exception("Falha ao obter foto de %s", key)
        return None

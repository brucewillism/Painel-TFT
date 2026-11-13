"""Servidor de tiles offline: diretório z/x/y.png ou arquivo MBTiles."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import Response

# cache simples de conexão MBTiles (só leitura)
_mbtiles_conn: sqlite3.Connection | None = None
_mbtiles_path: str | None = None


def _mbtiles(path: str) -> sqlite3.Connection | None:
    global _mbtiles_conn, _mbtiles_path
    p = Path(path)
    if not p.is_file():
        return None
    if _mbtiles_conn is not None and _mbtiles_path == str(p):
        return _mbtiles_conn
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False)
    _mbtiles_conn = conn
    _mbtiles_path = str(p)
    return conn


def tile_response(cfg: dict, z: int, x: int, y: int) -> Response:
    """Procura o tile no diretório local e, se faltar, no MBTiles.

    O esquema de diretório é o padrão OSM/XYZ: tiles/{z}/{x}/{y}.png
    MBTiles usa TMS (Y invertido); convertemos automaticamente.
    """
    tiles_dir = Path(cfg.get("map", {}).get("tiles_dir", ""))
    if tiles_dir:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            f = tiles_dir / str(z) / str(x) / f"{y}{ext}"
            if f.is_file():
                media = "image/webp" if ext == ".webp" else ("image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png")
                return Response(content=f.read_bytes(), media_type=media, headers={"Cache-Control": "public, max-age=86400"})

    mb = cfg.get("map", {}).get("mbtiles_path")
    if mb:
        conn = _mbtiles(mb)
        if conn is not None:
            # tms_y = (2^z - 1) - y
            tms_y = (2**z - 1) - y
            row = conn.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, tms_y),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (z, x, y),
                ).fetchone()
            if row and row[0]:
                data = row[0]
                media = "image/jpeg" if data[:2] == b"\xff\xd8" else "image/png"
                if data[:4] == b"\x89PNG":
                    media = "image/png"
                return Response(content=data, media_type=media, headers={"Cache-Control": "public, max-age=86400"})

    raise HTTPException(status_code=404, detail="tile not found")


def tiles_available(cfg: dict) -> dict:
    tiles_dir = Path(cfg.get("map", {}).get("tiles_dir", ""))
    has_dir = bool(tiles_dir) and any(tiles_dir.glob("*/*/*.*"))
    mb = Path(cfg.get("map", {}).get("mbtiles_path", ""))
    has_mb = mb.is_file()
    return {
        "directory": has_dir,
        "mbtiles": has_mb,
        "offline_ok": has_dir or has_mb,
        "online_url": cfg.get("map", {}).get("online_url"),
    }

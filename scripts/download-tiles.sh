#!/usr/bin/env bash
# Baixa tiles do OpenStreetMap para uso offline (respeite a política de uso
# da OSMF: https://operations.osmfoundation.org/policies/tiles/ ).
# Uso:
#   scripts/download-tiles.sh -23.60 -46.70 -23.52 -46.60 12 16
#                    sul     oeste   norte  leste  zmin zmax
# Alternativa recomendada: gere um arquivo MBTiles com o Mobile Atlas Creator
# (MOBAC) ou com o tilemaker e coloque em data/region.mbtiles.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${TILES_DIR:-$ROOT/app/static/tiles}"

if [[ $# -lt 6 ]]; then
  cat <<H
Uso: $0 SUL OESTE NORTE LESTE ZMIN ZMAX
Exemplo (Av. Paulista, São Paulo, zoom 12–16):
  $0 -23.58 -46.67 -23.55 -46.63 12 16

Os tiles vão para: $OUT/{z}/{x}/{y}.png
Depois o painel serve em /tiles/{z}/{x}/{y}.png e usa isso offline.

Para uma região maior, prefira um MBTiles:
  1. Instale o MOBAC ou use https://github.com/systemed/tilemaker
  2. Exporte a região em formato MBTiles (esquema TMS ou XYZ)
  3. Copie o arquivo para $ROOT/data/region.mbtiles
  4. Reinicie o painel
H
  exit 1
fi

SOUTH="$1"; WEST="$2"; NORTH="$3"; EAST="$4"; ZMIN="$5"; ZMAX="$6"
mkdir -p "$OUT"

python3 - "$OUT" "$SOUTH" "$WEST" "$NORTH" "$EAST" "$ZMIN" "$ZMAX" << 'PY'
import math, sys, time, urllib.request, pathlib

out, south, west, north, east = sys.argv[1], *map(float, sys.argv[2:6])
zmin, zmax = map(int, sys.argv[6:8])
out = pathlib.Path(out)

def lonlat_to_tile(lat, lon, z):
    lat_rad = math.radians(lat)
    n = 2.0 ** z
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile

ua = "lancer-painel/0.1 (offline cache; personal vehicle dashboard)"
count = 0
for z in range(zmin, zmax + 1):
    x0, y1 = lonlat_to_tile(south, west, z)
    x1, y0 = lonlat_to_tile(north, east, z)
    if x0 > x1: x0, x1 = x1, x0
    if y0 > y1: y0, y1 = y1, y0
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            dest = out / str(z) / str(x) / f"{y}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and dest.stat().st_size > 0:
                continue
            url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    dest.write_bytes(r.read())
                count += 1
                print(f"ok {z}/{x}/{y}")
                time.sleep(0.15)  # seja gentil com os servidores OSM
            except Exception as exc:
                print(f"falha {z}/{x}/{y}: {exc}")
print(f"baixados: {count}")
PY

#!/usr/bin/env python3
"""Calibração experimental do modo 360° (visão de cima).

Usa um tabuleiro de xadrez (checkerboard) filmado por cada câmera USB, no
lugar em que ela fica no carro, e grava a homolografia (matriz 3×3) que
projeta o chão para uma vista de topo. Depois o painel tenta costurar os
quadros ao vivo.

Isto PRECISA ser feito com as câmeras já instaladas no Lancer: a geometria
muda com altura, ângulo e lente. O resultado é um andaime — não substitui
um kit 360 comercial calibrado de fábrica.

Uso (no Pi, com as câmeras ligadas e o OpenCV instalado):

    pip install opencv-python-headless
    python3 scripts/calibrate-birdseye.py --camera front --device /dev/video0
    python3 scripts/calibrate-birdseye.py --camera rear  --device /dev/video1
    python3 scripts/calibrate-birdseye.py --camera left  --device /dev/video2
    python3 scripts/calibrate-birdseye.py --camera right --device /dev/video3

Teclas na janela:  [espaço] captura quando o tabuleiro for detectado
                   [s]      salva e sai
                   [q]      sai sem salvar

O JSON vai para data/birdseye/<id>.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("Instale o OpenCV:  pip install opencv-python-headless", file=sys.stderr)
        return 2

    parser = argparse.ArgumentParser(description="Calibra uma câmera para o modo 360°.")
    parser.add_argument("--camera", required=True, help="id: front, rear, left, right")
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--cols", type=int, default=7, help="cantos internos na horizontal")
    parser.add_argument("--rows", type=int, default=5, help="cantos internos na vertical")
    parser.add_argument("--square", type=float, default=0.025, help="lado do quadrado, em metros")
    parser.add_argument("--out-size", type=int, default=400)
    parser.add_argument("--outdir", default=str(ROOT / "data" / "birdseye"))
    args = parser.parse_args()

    pattern = (args.cols, args.rows)
    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"Não abriu {args.device}", file=sys.stderr)
        return 1

    last_H = None
    last_size = None
    print("Posicione o tabuleiro no chão, na área coberta por esta câmera.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        vis = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCorners(gray, pattern, None)
        if found:
            cv2.drawChessboardCorners(vis, pattern, corners, found)
            cv2.putText(vis, "DETECTADO  -  espaco para capturar", (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imshow("calibrate-birdseye", vis)
        key = cv2.waitKey(20) & 0xFF
        if key == ord("q"):
            last_H = None
            break
        if key == ord(" ") and found:
            # destino: um retângulo na vista de topo
            h, w = frame.shape[:2]
            last_size = (w, h)
            src = corners.reshape(-1, 2).astype("float32")
            # usa os 4 cantos do tabuleiro
            pts_src = _four_corners(src, args.cols, args.rows)
            margin = 80
            s = args.out_size
            pts_dst = __import__("numpy").array(
                [[margin, margin], [s - margin, margin],
                 [s - margin, s - margin], [margin, s - margin]],
                dtype="float32",
            )
            last_H = cv2.getPerspectiveTransform(pts_src, pts_dst)
            print("Homolografia capturada. Aperte S para salvar.")
        if key == ord("s") and last_H is not None:
            outdir = Path(args.outdir)
            outdir.mkdir(parents=True, exist_ok=True)
            dest = outdir / f"{args.camera}.json"
            dest.write_text(json.dumps({
                "camera": args.camera,
                "device": args.device,
                "image_size": list(last_size),
                "output_size": [args.out_size, args.out_size],
                "chessboard": [args.cols, args.rows],
                "square_m": args.square,
                "homography": last_H.tolist(),
            }, indent=2))
            print("Salvo em", dest)
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0 if last_H is not None else 1


def _four_corners(pts, cols, rows):
    import numpy as np
    # cantos do tabuleiro na ordem TL, TR, BR, BL
    idx = [0, cols - 1, cols * rows - 1, cols * (rows - 1)]
    return np.array([pts[i] for i in idx], dtype="float32")


if __name__ == "__main__":
    raise SystemExit(main())

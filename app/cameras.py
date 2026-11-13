"""Câmeras USB/UVC + ré (MJPEG) e andaime do modo 360°."""

from __future__ import annotations

import io
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

_FONT = None


def _font(size: int):
    global _FONT
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for c in candidates:
        if Path(c).is_file():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _jpeg(img: Image.Image, quality: int = 55) -> bytes:
    buf = io.BytesIO()
    img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=quality, optimize=False)
    return buf.getvalue()


def _placeholder(label: str, cam_id: str, width: int, height: int, quality: int, tick: float) -> bytes:
    """Feed de teste (simulador / câmera ausente). Leve, sem OpenCV."""
    img = Image.new("RGB", (width, height), (8, 0, 0))
    d = ImageDraw.Draw(img)
    # grade em movimento
    offset = int((tick * 40) % 40)
    for x in range(-offset, width, 40):
        d.line([(x, 0), (x, height)], fill=(50, 0, 0), width=1)
    for y in range(-offset, height, 40):
        d.line([(0, y), (width, y)], fill=(50, 0, 0), width=1)
    # “horizonte”
    y0 = int(height * 0.45 + 8 * math.sin(tick))
    d.rectangle([0, y0, width, height], fill=(18, 4, 4))
    # carimbo
    font_l = _font(max(18, height // 10))
    font_s = _font(max(11, height // 18))
    d.rectangle([12, 12, width - 12, 54], outline=(225, 10, 10), width=2)
    d.text((22, 18), f"CAM {label.upper()}", fill=(255, 40, 40), font=font_l)
    d.text((22, height - 36), "SIMULADOR  ·  SEM /dev/video", fill=(160, 80, 80), font=font_s)
    hh = int(tick) // 3600
    mm = (int(tick) // 60) % 60
    ss = int(tick) % 60
    d.text((width - 150, 20), f"{hh:02d}:{mm:02d}:{ss:02d}", fill=(255, 180, 180), font=font_s)
    # marcador central
    cx, cy = width // 2, height // 2 + int(6 * math.sin(tick * 2))
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], outline=(255, 20, 20), width=2)
    return _jpeg(img, quality)


def _birdseye_placeholder(width: int, height: int, quality: int, tick: float, calibrated: bool) -> bytes:
    img = Image.new("RGB", (width, height), (6, 0, 0))
    d = ImageDraw.Draw(img)
    # piso
    for i in range(-8, 20):
        y = int(height * 0.2 + i * 22 + (tick * 15) % 22)
        d.line([(0, y), (width, y)], fill=(40, 0, 0), width=1)
    # “carro” no centro (retângulo estilizado)
    cx, cy = width // 2, height // 2
    d.rounded_rectangle([cx - 28, cy - 52, cx + 28, cy + 52], radius=8, outline=(220, 20, 20), width=2)
    d.polygon([(cx - 18, cy - 52), (cx, cy - 64), (cx + 18, cy - 52)], outline=(220, 20, 20))
    font = _font(16)
    title = "360°  ·  CALIBRADO" if calibrated else "360°  ·  MODO ANDAIME"
    d.text((16, 12), title, fill=(255, 50, 50), font=font)
    if not calibrated:
        d.text((16, height - 48), "Calibre com scripts/calibrate-birdseye.py", fill=(160, 80, 80), font=_font(13))
        d.text((16, height - 28), "A costura real precisa ser feita no carro.", fill=(160, 80, 80), font=_font(13))
    # quatro “áreas” de câmera
    for name, box in (
        ("FRENTE", (cx - 70, 40, cx + 70, cy - 70)),
        ("RÉ", (cx - 70, cy + 70, cx + 70, height - 20)),
        ("ESQ", (16, cy - 50, cx - 40, cy + 50)),
        ("DIR", (cx + 40, cy - 50, width - 16, cy + 50)),
    ):
        d.rectangle(list(box), outline=(120, 20, 20), width=1)
        d.text((box[0] + 6, box[1] + 4), name, fill=(180, 60, 60), font=_font(11))
    return _jpeg(img, quality)


class _CamWorker:
    def __init__(self, spec: dict, width: int, height: int, fps: int, quality: int):
        self.spec = spec
        self.id = spec["id"]
        self.label = spec.get("label", self.id)
        self.device = spec.get("device")
        self.width = width
        self.height = height
        self.fps = max(2, fps)
        self.quality = quality
        self._lock = threading.Lock()
        self._jpeg = b""
        self._live = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = time.time()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=f"cam-{self.id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def snapshot(self) -> bytes:
        with self._lock:
            return self._jpeg

    @property
    def live(self) -> bool:
        return self._live

    def _loop(self) -> None:
        cap = None
        device = self.device
        if device and Path(str(device)).exists():
            cap = self._open(str(device))
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            t0 = time.time()
            tick = t0 - self._t0
            frame = None
            if cap is not None:
                frame = self._read(cap)
            if frame is not None:
                self._live = True
                data = frame
            else:
                self._live = False
                data = _placeholder(self.label, self.id, self.width, self.height, self.quality, tick)
            with self._lock:
                self._jpeg = data
            leftover = interval - (time.time() - t0)
            if leftover > 0:
                self._stop.wait(leftover)
        self._close(cap)

    def _open(self, device: str):
        try:
            import cv2
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            if not cap.isOpened():
                cap.release()
                return None
            log.info("Câmera %s aberta em %s (OpenCV)", self.id, device)
            return ("cv2", cap)
        except Exception as exc:
            log.debug("OpenCV indisponível para %s: %s", device, exc)
        # ffmpeg fallback: um processo que emite JPEG concatenados é complexo;
        # tentamos um snapshot periódico.
        return ("ffmpeg", device)

    def _read(self, cap) -> bytes | None:
        kind, handle = cap
        if kind == "cv2":
            ok, frame = handle.read()
            if not ok or frame is None:
                return None
            try:
                import cv2
                frame = cv2.resize(frame, (self.width, self.height))
                ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                if not ok:
                    return None
                return buf.tobytes()
            except Exception:
                return None
        if kind == "ffmpeg":
            try:
                import subprocess
                r = subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-f", "v4l2", "-i", handle, "-frames:v", "1",
                        "-vf", f"scale={self.width}:{self.height}",
                        "-q:v", "6", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
                    ],
                    capture_output=True, timeout=2,
                )
                if r.returncode == 0 and r.stdout:
                    return r.stdout
            except Exception:
                return None
        return None

    def _close(self, cap) -> None:
        if not cap:
            return
        kind, handle = cap
        if kind == "cv2":
            try:
                handle.release()
            except Exception:
                pass


class CameraHub:
    def __init__(self, cfg: dict) -> None:
        cam_cfg = cfg.get("cameras") or {}
        self.enabled = bool(cam_cfg.get("enabled", True))
        self.width = int(cam_cfg.get("width", 640))
        self.height = int(cam_cfg.get("height", 360))
        self.fps = int(cam_cfg.get("fps", 12))
        self.quality = int(cam_cfg.get("jpeg_quality", 55))
        self.reverse_gpio = cam_cfg.get("reverse_gpio")
        self.reverse_active_low = bool(cam_cfg.get("reverse_active_low", False))
        self.devices = list(cam_cfg.get("devices") or [])
        self.calib_dir = Path(cam_cfg.get("birdseye", {}).get("calib_dir", "data/birdseye"))
        if not self.calib_dir.is_absolute():
            from .config import ROOT
            self.calib_dir = ROOT / self.calib_dir
        self._workers: dict[str, _CamWorker] = {}
        self._reverse = False
        self._stop = threading.Event()
        self._gpio_thread: threading.Thread | None = None
        self._eye_jpeg = b""
        self._eye_lock = threading.Lock()

    def start(self) -> None:
        if not self.enabled:
            return
        for spec in self.devices[:4]:
            w = _CamWorker(spec, self.width, self.height, self.fps, self.quality)
            w.start()
            self._workers[spec["id"]] = w
        self._gpio_thread = threading.Thread(target=self._gpio_loop, name="reverse-gpio", daemon=True)
        self._gpio_thread.start()
        threading.Thread(target=self._eye_loop, name="birdseye", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        for w in self._workers.values():
            w.stop()

    def set_reverse(self, value: bool) -> None:
        self._reverse = bool(value)

    @property
    def reverse(self) -> bool:
        return self._reverse

    def list(self) -> list[dict[str, Any]]:
        out = []
        for spec in self.devices:
            w = self._workers.get(spec["id"])
            dev = spec.get("device")
            out.append({
                "id": spec["id"],
                "label": spec.get("label", spec["id"]),
                "reverse": bool(spec.get("reverse")),
                "device": dev,
                "live": bool(w.live) if w else False,
                "present": bool(dev and Path(str(dev)).exists()),
            })
        return out

    def jpeg(self, cam_id: str) -> bytes | None:
        w = self._workers.get(cam_id)
        if not w:
            return None
        data = w.snapshot()
        return data or None

    def birdseye_jpeg(self) -> bytes:
        with self._eye_lock:
            return self._eye_jpeg

    def birdseye_calibrated(self) -> bool:
        if not self.calib_dir.is_dir():
            return False
        files = list(self.calib_dir.glob("*.json"))
        return len(files) >= 2  # pelo menos duas câmeras calibradas

    def reverse_cam_id(self) -> str | None:
        for spec in self.devices:
            if spec.get("reverse"):
                return spec["id"]
        return None

    def _gpio_loop(self) -> None:
        pin = self.reverse_gpio
        if pin is None or pin == "":
            return
        from .gpio_reverse import poll_pin
        log.info("GPIO da ré: BCM %s (active_low=%s)", pin, self.reverse_active_low)
        while not self._stop.wait(0.05):
            raw = poll_pin(int(pin))
            if raw is None:
                continue
            self._reverse = (not raw) if self.reverse_active_low else bool(raw)

    def _eye_loop(self) -> None:
        interval = 1.0 / max(4, self.fps // 2)
        t0 = time.time()
        while not self._stop.wait(interval):
            tick = time.time() - t0
            calibrated = self.birdseye_calibrated()
            frame = None
            if calibrated:
                frame = self._try_stitch()
            if frame is None:
                frame = _birdseye_placeholder(self.width, self.height, self.quality, tick, calibrated)
            with self._eye_lock:
                self._eye_jpeg = frame

    def _try_stitch(self) -> bytes | None:
        """Tenta a costura real se OpenCV e as homolografias estiverem presentes."""
        try:
            import json
            import numpy as np
            import cv2
        except Exception:
            return None
        pieces = []
        for spec in self.devices:
            calib = self.calib_dir / f"{spec['id']}.json"
            if not calib.is_file():
                continue
            w = self._workers.get(spec["id"])
            if not w or not w.snapshot():
                continue
            try:
                meta = json.loads(calib.read_text())
                H = np.array(meta["homography"], dtype=np.float32)
                out_w, out_h = meta.get("output_size", [400, 400])
                raw = w.snapshot()
                arr = np.frombuffer(raw, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                warped = cv2.warpPerspective(img, H, (int(out_w), int(out_h)))
                pieces.append(warped)
            except Exception as exc:
                log.debug("stitch %s: %s", spec["id"], exc)
        if not pieces:
            return None
        canvas = pieces[0]
        for p in pieces[1:]:
            if p.shape != canvas.shape:
                p = cv2.resize(p, (canvas.shape[1], canvas.shape[0]))
            mask = (p > 0).any(axis=2)
            canvas[mask] = p[mask]
        ok, buf = cv2.imencode(".jpg", canvas, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
        return buf.tobytes() if ok else None

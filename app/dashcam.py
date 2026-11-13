"""Dash cam: gravar câmera escolhida com overlay (ffmpeg), loop e proteção de clip."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .store import DataStore

log = logging.getLogger(__name__)


class DashCam:
    def __init__(self, store: DataStore, conn, cfg: dict, root: Path) -> None:
        self.store = store
        self.conn = conn
        self.cfg = cfg.get("dashcam") or {}
        self.root = root
        self.dir = Path(self.cfg.get("dir") or (root / "data/dashcam"))
        if not self.dir.is_absolute():
            self.dir = root / self.dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_gb = float(self.cfg.get("max_gb", 8))
        self.segment_s = int(self.cfg.get("segment_s", 60))
        self.g_protect = float(self.cfg.get("g_protect", 0.8))
        self.cam_id = self.cfg.get("camera_id") or "cam0"
        self.running = False
        self.proc: subprocess.Popen | None = None
        self.current: Path | None = None
        self.started_at = 0.0
        self._ffmpeg = shutil.which("ffmpeg")

    def status(self) -> dict[str, Any]:
        clips = self.list_clips()
        used = sum(c["size"] for c in clips)
        return {
            "running": self.running,
            "camera_id": self.cam_id,
            "ffmpeg": bool(self._ffmpeg),
            "dir": str(self.dir),
            "used_mb": round(used / 1e6, 1),
            "max_gb": self.max_gb,
            "segment_s": self.segment_s,
            "g_protect": self.g_protect,
            "current": self.current.name if self.current else None,
        }

    def start(self, camera_id: str | None = None) -> dict:
        if camera_id:
            self.cam_id = camera_id
        if self.running:
            return self.status()
        self.running = True
        self.started_at = time.time()
        self._roll_segment()
        self.store.set_meta("dashcam", self.status())
        return self.status()

    def stop(self) -> dict:
        self.running = False
        self._close_current(protect=False)
        self.store.set_meta("dashcam", self.status())
        return self.status()

    def tick(self) -> None:
        if not self.running:
            return
        if self.current and (time.time() - self.started_at) >= self.segment_s:
            self._roll_segment()
        g = abs(float(self.store.value("g_lon") or 0)) + abs(float(self.store.value("g_lat") or 0))
        if g >= self.g_protect:
            self.protect("evento G")
        self._enforce_quota()
        self.store.set_meta("dashcam", self.status())

    def _roll_segment(self) -> None:
        self._close_current(protect=False)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = self.dir / f"clip-{ts}.mp4"
        self.current = path
        self.started_at = time.time()
        self.conn.execute(
            "INSERT INTO dash_clips(started_at, path, camera_id, protected) VALUES (?,?,?,0)",
            (self.started_at, str(path), self.cam_id),
        )
        self.conn.commit()
        self._spawn_ffmpeg(path)

    def _overlay_text(self) -> str:
        s = self.store
        def _n(key, default=0.0):
            val = s.value(key)
            try:
                return float(val)
            except (TypeError, ValueError):
                return default
        v = _n("speed_fused", None)
        if v is None:
            v = _n("speed", 0)
        rpm = _n("rpm", 0)
        gl = _n("g_lon", 0)
        ga = _n("g_lat", 0)
        lat, lon = s.value("gps_lat"), s.value("gps_lon")
        gps = f"{float(lat):.5f},{float(lon):.5f}" if lat is not None and lon is not None else "--"
        return f"{v:.0f} km/h  {rpm:.0f} rpm  G {gl:+.2f}/{ga:+.2f}  {gps}"

    def _spawn_ffmpeg(self, path: Path) -> None:
        self._kill_proc()
        if not self._ffmpeg:
            # simulador: gera um placeholder MPEG curto depois, no close
            return
        # tenta dispositivo v4l; se falhar, gera teste com overlay
        text = self._overlay_text().replace("'", "")
        dev = self._v4l()
        if dev:
            cmd = [
                self._ffmpeg, "-y", "-f", "v4l2", "-i", dev,
                "-vf", f"drawtext=text='{text}':x=16:y=16:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.5",
                "-t", str(self.segment_s + 2), "-an", "-c:v", "libx264", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", str(path),
            ]
        else:
            cmd = [
                self._ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x120000:s=640x360:r=15",
                "-vf", f"drawtext=text='DASH CAM  {text}':x=16:y=h-40:fontsize=20:fontcolor=white",
                "-t", str(min(8, self.segment_s)), "-an", "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", str(path),
            ]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            log.warning("ffmpeg dash cam: %s", exc)
            self.proc = None

    def _v4l(self) -> str | None:
        import glob
        cams = sorted(glob.glob("/dev/video*"))
        return cams[0] if cams else None

    def _kill_proc(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.kill()
        self.proc = None

    def _close_current(self, protect: bool) -> None:
        self._kill_proc()
        if not self.current:
            return
        path = self.current
        if not path.is_file() and self._ffmpeg:
            # gera um stub curto para o simulador, se o ffmpeg não gravou
            self._write_stub(path)
        elif not path.is_file():
            self._write_stub(path)
        size = path.stat().st_size if path.is_file() else 0
        self.conn.execute(
            "UPDATE dash_clips SET ended_at=?, size=?, protected=MAX(protected, ?) WHERE path=?",
            (time.time(), size, int(protect), str(path)),
        )
        self.conn.commit()
        self.current = None

    def _write_stub(self, path: Path) -> None:
        """MP4 mínimo ou arquivo de texto se não houver ffmpeg."""
        if self._ffmpeg:
            text = self._overlay_text().replace("'", "")
            try:
                subprocess.run(
                    [self._ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x1a0000:s=640x360:d=2:r=8",
                     "-vf", f"drawtext=text='CLIP  {text}':x=20:y=160:fontsize=22:fontcolor=white",
                     "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "2", str(path)],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12,
                )
                if path.is_file():
                    return
            except Exception:
                pass
        path.write_bytes(b"DASHCAM-STUB " + self._overlay_text().encode("utf-8", "replace"))

    def protect(self, reason: str = "manual") -> dict:
        if self.current:
            self.conn.execute(
                "UPDATE dash_clips SET protected=1, reason=? WHERE path=?",
                (reason, str(self.current)),
            )
            self.conn.commit()
        else:
            # protege o último
            row = self.conn.execute("SELECT id FROM dash_clips ORDER BY started_at DESC LIMIT 1").fetchone()
            if row:
                self.conn.execute("UPDATE dash_clips SET protected=1, reason=? WHERE id=?", (reason, row["id"]))
                self.conn.commit()
        return self.status()

    def protect_id(self, cid: int) -> dict:
        self.conn.execute("UPDATE dash_clips SET protected=1, reason='manual' WHERE id=?", (cid,))
        self.conn.commit()
        return self.status()

    def list_clips(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM dash_clips ORDER BY started_at DESC LIMIT 80")
        out = []
        for r in cur.fetchall():
            d = dict(r)
            p = Path(d["path"]) if d.get("path") else None
            d["exists"] = bool(p and p.is_file())
            d["size"] = d.get("size") or (p.stat().st_size if d["exists"] else 0)
            out.append(d)
        return out

    def clip_path(self, cid: int) -> Path | None:
        row = self.conn.execute("SELECT path FROM dash_clips WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        p = Path(row["path"])
        return p if p.is_file() else None

    def _enforce_quota(self) -> None:
        limit = self.max_gb * 1e9
        rows = self.conn.execute(
            "SELECT id, path, size, protected FROM dash_clips ORDER BY started_at ASC"
        ).fetchall()
        total = sum((r["size"] or 0) for r in rows)
        for r in rows:
            if total <= limit:
                break
            if r["protected"]:
                continue
            p = Path(r["path"]) if r["path"] else None
            if p and p.is_file():
                try:
                    sz = p.stat().st_size
                    p.unlink()
                    total -= sz
                except Exception:
                    pass
            self.conn.execute("DELETE FROM dash_clips WHERE id=?", (r["id"],))
        self.conn.commit()

    def seed_demo(self) -> None:
        n = self.conn.execute("SELECT COUNT(*) c FROM dash_clips").fetchone()["c"]
        if n:
            return
        now = time.time()
        for i, (name, prot, reason) in enumerate((
            ("clip-demo-1.mp4", 0, None),
            ("clip-demo-evento.mp4", 1, "evento G 0.92"),
            ("clip-demo-2.mp4", 0, None),
        )):
            p = self.dir / name
            if not p.is_file():
                self._write_stub(p)
            size = p.stat().st_size if p.is_file() else 0
            self.conn.execute(
                "INSERT INTO dash_clips(started_at, ended_at, path, camera_id, size, protected, reason) "
                "VALUES (?,?,?,?,?,?,?)",
                (now - 600 + i * 90, now - 540 + i * 90, str(p), "cam0", size, prot, reason),
            )
        self.conn.commit()

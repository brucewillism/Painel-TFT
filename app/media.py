"""Multimídia: pasta local, rádio, Bluetooth A2DP/AVRCP (BlueZ) e volume."""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

AUDIO_EXT = {".mp3", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wav", ".opus"}


def _which(*names: str) -> str | None:
    from shutil import which
    for n in names:
        p = which(n)
        if p:
            return p
    return None


class MediaLibrary:
    def __init__(self, music_dir: str | Path) -> None:
        self.dir = Path(music_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._tracks: list[dict[str, Any]] = []
        self.scan()

    def scan(self) -> list[dict[str, Any]]:
        tracks = []
        if self.dir.is_dir():
            for path in sorted(self.dir.rglob("*")):
                if path.suffix.lower() not in AUDIO_EXT or not path.is_file():
                    continue
                tracks.append(self._meta(path))
        self._tracks = tracks
        return tracks

    def _meta(self, path: Path) -> dict[str, Any]:
        tid = hashlib.sha1(str(path).encode()).hexdigest()[:12]
        info = {
            "id": tid,
            "path": str(path),
            "title": path.stem,
            "artist": "Desconhecido",
            "album": path.parent.name if path.parent != self.dir else "",
            "duration": 0,
            "cover": False,
        }
        try:
            from mutagen import File
            audio = File(path, easy=True)
            if audio is not None:
                info["title"] = (audio.get("title") or [info["title"]])[0]
                info["artist"] = (audio.get("artist") or [info["artist"]])[0]
                info["album"] = (audio.get("album") or [info["album"]])[0]
                info["duration"] = int(getattr(audio, "info", type("x", (), {"length": 0})).length or 0)
            raw = File(path)
            pics = []
            if raw is not None:
                pics = getattr(raw, "pictures", None) or []
                if not pics and hasattr(raw, "tags") and raw.tags:
                    for key in raw.tags.keys() if hasattr(raw.tags, "keys") else []:
                        if "APIC" in str(key) or "covr" in str(key).lower():
                            pics = [True]
                            break
            info["cover"] = bool(pics)
        except Exception as exc:
            log.debug("meta %s: %s", path, exc)
        return info

    def tracks(self) -> list[dict[str, Any]]:
        return list(self._tracks)

    def by_id(self, tid: str) -> dict[str, Any] | None:
        for t in self._tracks:
            if t["id"] == tid:
                return t
        return None

    def cover_bytes(self, tid: str) -> tuple[bytes, str] | None:
        tr = self.by_id(tid)
        if not tr:
            return None
        try:
            from mutagen import File
            raw = File(tr["path"])
            if raw is None:
                return None
            pics = getattr(raw, "pictures", None) or []
            if pics:
                p = pics[0]
                mime = getattr(p, "mime", "image/jpeg") or "image/jpeg"
                return bytes(p.data), mime
            tags = getattr(raw, "tags", None)
            if tags:
                for key, val in tags.items():
                    if "APIC" in str(key):
                        arr = val if not isinstance(val, list) else val[0]
                        return bytes(arr.data), getattr(arr, "mime", "image/jpeg")
        except Exception:
            return None
        return None


class MediaPlayer:
    """Player local (mpv/ffplay) + rádio + mock/BlueZ AVRCP + volume."""

    def __init__(self, cfg: dict) -> None:
        media = cfg.get("media") or {}
        from .config import ROOT
        music_dir = media.get("music_dir", "data/music")
        p = Path(music_dir)
        if not p.is_absolute():
            p = ROOT / p
        self.library = MediaLibrary(p)
        self.radio_list = list(media.get("radio") or [])
        self.bluetooth_enabled = bool(media.get("bluetooth", True))
        self.volume = int(media.get("volume", 70))
        self.eq_bands = list(media.get("eq") or [0, 0, 0, 0, 0])
        if len(self.eq_bands) < 5:
            self.eq_bands += [0] * (5 - len(self.eq_bands))
        self.eq_bands = [max(-12, min(12, int(x))) for x in self.eq_bands[:5]]
        self.source = "local"  # local | radio | bluetooth
        self.status = "stopped"  # playing | paused | stopped
        self.track: dict[str, Any] | None = None
        self.position = 0.0
        self._index = 0
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._mock_bt = {
            "title": "Faixa do celular",
            "artist": "Bluetooth (mock)",
            "album": "A2DP",
            "status": "paused",
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            pos = self.position
            if self.status == "playing" and self._started_at:
                pos = self.position + (time.time() - self._started_at)
            tr = dict(self.track) if self.track else None
            if tr and "path" in tr:
                tr = {k: tr[k] for k in tr if k != "path"}
            return {
                "source": self.source,
                "status": self.status,
                "volume": self.volume,
                "track": tr,
                "position": int(pos),
                "radio": self.radio_list,
                "library": [{k: t[k] for k in t if k != "path"} for t in self.library.tracks()],
                "bluetooth": self._bt_info(),
                "eq": self.eq_bands,
                "eq_labels": ["60 Hz", "230 Hz", "910 Hz", "4 kHz", "14 kHz"],
            }

    def play_track(self, tid: str) -> dict[str, Any]:
        tr = self.library.by_id(tid)
        if not tr:
            raise KeyError(tid)
        with self._lock:
            self.source = "local"
            self._index = max(0, next((i for i, t in enumerate(self.library.tracks()) if t["id"] == tid), 0))
            self._start_file(tr["path"])
            self.track = tr
            self.status = "playing"
            self.position = 0
            self._started_at = time.time()
        return self.snapshot()

    def play_radio(self, index: int) -> dict[str, Any]:
        if index < 0 or index >= len(self.radio_list):
            raise KeyError(index)
        sta = self.radio_list[index]
        with self._lock:
            self.source = "radio"
            self._start_file(sta["url"], stream=True)
            self.track = {"id": f"radio-{index}", "title": sta["name"], "artist": "Rádio", "album": "", "duration": 0, "cover": False}
            self.status = "playing"
            self.position = 0
            self._started_at = time.time()
        return self.snapshot()

    def play(self) -> dict[str, Any]:
        with self._lock:
            if self.source == "bluetooth":
                self._bt_cmd("Play")
                self.status = "playing"
                return self.snapshot()
            if self.status == "paused" and self._proc and self._proc.poll() is None:
                self._proc.send_signal(signal.SIGCONT)
                self.status = "playing"
                self._started_at = time.time()
                return self.snapshot()
            tracks = self.library.tracks()
            if tracks:
                tr = tracks[self._index % len(tracks)]
                self.source = "local"
                self._start_file(tr["path"])
                self.track = tr
                self.status = "playing"
                self.position = 0
                self._started_at = time.time()
        return self.snapshot()

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if self.source == "bluetooth":
                self._bt_cmd("Pause")
                self.status = "paused"
                return self.snapshot()
            if self._proc and self._proc.poll() is None:
                self._proc.send_signal(signal.SIGSTOP)
            if self.status == "playing" and self._started_at:
                self.position += time.time() - self._started_at
            self.status = "paused"
            self._started_at = 0
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._kill()
            self.status = "stopped"
            self.position = 0
            self._started_at = 0
        return self.snapshot()

    def next(self) -> dict[str, Any]:
        with self._lock:
            if self.source == "bluetooth":
                self._bt_cmd("Next")
                return self.snapshot()
            if self.source == "radio":
                idx = 0
                if self.track and str(self.track.get("id", "")).startswith("radio-"):
                    idx = int(self.track["id"].split("-")[1])
                idx = (idx + 1) % max(1, len(self.radio_list))
        if self.source == "radio":
            return self.play_radio(idx)
        tracks = self.library.tracks()
        if not tracks:
            return self.snapshot()
        with self._lock:
            self._index = (self._index + 1) % len(tracks)
            tid = tracks[self._index]["id"]
        return self.play_track(tid)

    def prev(self) -> dict[str, Any]:
        with self._lock:
            if self.source == "bluetooth":
                self._bt_cmd("Previous")
                return self.snapshot()
            if self.source == "radio":
                idx = 0
                if self.track and str(self.track.get("id", "")).startswith("radio-"):
                    idx = int(self.track["id"].split("-")[1])
                idx = (idx - 1) % max(1, len(self.radio_list))
        if self.source == "radio":
            return self.play_radio(idx)
        tracks = self.library.tracks()
        if not tracks:
            return self.snapshot()
        with self._lock:
            self._index = (self._index - 1) % len(tracks)
            tid = tracks[self._index]["id"]
        return self.play_track(tid)

    def set_source(self, source: str) -> dict[str, Any]:
        if source not in {"local", "radio", "bluetooth"}:
            raise ValueError(source)
        with self._lock:
            if source != self.source:
                self._kill()
                self.status = "stopped"
            self.source = source
            if source == "bluetooth":
                info = self._bt_info()
                self.track = {
                    "id": "bt",
                    "title": info.get("title") or "Bluetooth",
                    "artist": info.get("artist") or "",
                    "album": info.get("album") or "",
                    "duration": 0,
                    "cover": False,
                }
        return self.snapshot()

    def set_volume(self, volume: int) -> dict[str, Any]:
        volume = max(0, min(100, int(volume)))
        with self._lock:
            self.volume = volume
        self._apply_volume(volume)
        return self.snapshot()

    def set_eq(self, bands: list) -> dict[str, Any]:
        vals = [max(-12, min(12, int(x))) for x in list(bands)[:5]]
        while len(vals) < 5:
            vals.append(0)
        with self._lock:
            self.eq_bands = vals
        # PipeWire/Pulse: tentamos um equalizer sink se existir; senão fica só no estado.
        self._apply_eq(vals)
        return self.snapshot()

    def _apply_eq(self, bands: list[int]) -> None:
        # Placeholder honesto: um EQ de 5 bandas no PipeWire exige um filtro
        # (easyeffects, lsp-plugins). Gravamos o estado; a UI sempre reflete.
        return

    def shutdown(self) -> None:
        self._kill()

    def _start_file(self, uri: str, stream: bool = False) -> None:
        self._kill()
        # No ambiente de teste/simulador sem pulso, o ffplay ainda pode rodar
        # descartando o áudio (-nodisp). Se falhar, o estado segue “playing”
        # (mock) para a UI funcionar no box e no carro.
        cmd = None
        mpv = _which("mpv")
        ffplay = _which("ffplay")
        if mpv:
            cmd = [mpv, "--no-video", "--really-quiet", f"--volume={self.volume}", uri]
        elif ffplay:
            cmd = [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", str(self.volume), uri]
        if not cmd:
            log.info("Nenhum player (mpv/ffplay); estado de mídia em mock.")
            return
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            log.warning("player falhou (%s); seguindo em mock.", exc)
            self._proc = None

    def _kill(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.send_signal(signal.SIGCONT)
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=1)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def _apply_volume(self, volume: int) -> None:
        frac = volume / 100.0
        attempts = [
            ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{frac:.2f}"],
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
            ["amixer", "-q", "sset", "Master", f"{volume}%"],
        ]
        for cmd in attempts:
            if not _which(cmd[0]):
                continue
            try:
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
                return
            except Exception:
                continue

    def _bt_info(self) -> dict[str, Any]:
        if not self.bluetooth_enabled:
            return {"available": False}
        real = self._bt_query()
        if real:
            return real
        # mock para o simulador / quando não há celular pareado
        return {"available": False, "mock": True, **self._mock_bt}

    def _bt_query(self) -> dict[str, Any] | None:
        """Lê org.bluez.MediaPlayer1 via busctl (sem dependência D-Bus pesada)."""
        busctl = _which("busctl")
        if not busctl:
            return None
        try:
            # procura um player em /org/bluez
            tree = subprocess.run(
                [busctl, "--system", "tree", "org.bluez"],
                capture_output=True, text=True, timeout=1,
            )
            if tree.returncode != 0:
                return None
            player = None
            for line in tree.stdout.splitlines():
                if "player" in line.lower() and "/" in line:
                    parts = line.split()
                    for p in parts:
                        if p.startswith("/") and "player" in p:
                            player = p
                            break
            if not player:
                return None

            def get(prop: str) -> str:
                r = subprocess.run(
                    [busctl, "--system", "get-property", "org.bluez", player, "org.bluez.MediaPlayer1", prop],
                    capture_output=True, text=True, timeout=1,
                )
                return r.stdout.strip() if r.returncode == 0 else ""

            status = get("Status")
            # Track é um dicionário a{sv}; tentamos Title/Artist via um dump simples
            title = get("Track")
            return {
                "available": True,
                "mock": False,
                "path": player,
                "status": status,
                "raw_track": title,
                "title": "Bluetooth",
                "artist": "",
                "album": "",
            }
        except Exception as exc:
            log.debug("BlueZ query: %s", exc)
            return None

    def _bt_cmd(self, method: str) -> None:
        busctl = _which("busctl")
        info = self._bt_query()
        if not busctl or not info or not info.get("path"):
            # mock
            if method == "Play":
                self._mock_bt["status"] = "playing"
            elif method == "Pause":
                self._mock_bt["status"] = "paused"
            return
        try:
            subprocess.run(
                [busctl, "--system", "call", "org.bluez", info["path"], "org.bluez.MediaPlayer1", method],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1,
            )
        except Exception as exc:
            log.debug("BlueZ %s: %s", method, exc)

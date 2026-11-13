#!/usr/bin/env python3
"""Grava o painel real (800×480) numa arrancada 0–100 a partir da ignição."""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "screenshots"
VIDEO = OUT_DIR / "demo-0-100.mp4"
STILL_IDLE = OUT_DIR / "demo-0-100-idle.png"
STILL_LAUNCH = OUT_DIR / "demo-0-100-mid.png"
STILL_RESULT = OUT_DIR / "demo-0-100-result.png"
PORT = 8091
BASE = f"http://127.0.0.1:{PORT}"
TMP_DIR = Path("/tmp/painel-demo-0100")


def http(url: str, data: bytes | None = None, method: str | None = None, timeout: float = 8):
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    if not raw:
        return {}
    try:
        return json.loads(raw.decode())
    except Exception:
        return {"raw": raw}


def wait_up(timeout: float = 20) -> None:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        try:
            http(f"{BASE}/api/snapshot")
            return
        except Exception as exc:
            last = exc
            time.sleep(0.2)
    raise SystemExit(f"servidor não subiu: {last}")


def post(path: str) -> dict:
    return http(f"{BASE}{path}", data=b"{}", method="POST")


def snapshot() -> dict:
    return http(f"{BASE}/api/snapshot")


def perf() -> dict:
    return http(f"{BASE}/api/perf")


def val(snap: dict, key: str):
    item = (snap.get("signals") or {}).get(key)
    if item is None and key == "voltage":
        item = (snap.get("signals") or {}).get("battery_voltage")
    if isinstance(item, dict):
        return item.get("value")
    return item


def start_server() -> subprocess.Popen:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    log = (TMP_DIR / "uvicorn.log").open("w")
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ],
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "LANCER_SOURCE": "simulator"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    wait_up()
    return proc


def transcode(src: Path, dest: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-movflags", "+faststart",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probe(path: Path) -> dict:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,codec_type,width,height,avg_frame_rate,nb_frames,pix_fmt,r_frame_rate",
        "-show_entries", "format=duration,format_name",
        "-of", "json",
        str(path),
    ])
    return json.loads(raw)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    vid_dir = TMP_DIR / "pw-video"
    if vid_dir.exists():
        for p in vid_dir.glob("*"):
            p.unlink()
    vid_dir.mkdir(parents=True, exist_ok=True)

    server = start_server()
    marks: dict[str, float] = {}
    try:
        post("/api/sim/ignition")
        post("/api/perf/clear")
        post("/api/perf/reset")
        ign = None
        for _ in range(40):
            time.sleep(0.1)
            ign = snapshot()
            volt = float(val(ign, "voltage") or 0)
            rpm = float(val(ign, "rpm") or 0)
            if rpm < 50 and 12.1 <= volt <= 12.7:
                break
        print("ignition", "rpm", val(ign, "rpm"), "volt", val(ign, "voltage"), "spd", val(ign, "speed"), "cool", val(ign, "coolant_temp"))

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                    "--font-render-hinting=none",
                    "--use-gl=angle",
                    "--use-angle=swiftshader",
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                ],
            )
            context = browser.new_context(
                viewport={"width": 800, "height": 480},
                device_scale_factor=1,
                record_video_dir=str(vid_dir),
                record_video_size={"width": 800, "height": 480},
            )
            page = context.new_page()
            t_rec = time.monotonic()
            page.goto(f"{BASE}/?page=gauges", wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_function("() => window.LancerHUDCar && LancerHUDCar.loaded()", timeout=8000)
            except Exception as exc:
                print("car load wait", exc)
            page.wait_for_timeout(200)
            # intro (~3,25 s) + ignição visível com ponteiros no zero
            page.wait_for_timeout(6800)
            marks["after_intro"] = time.monotonic() - t_rec

            post("/api/sim/crank")
            marks["crank"] = time.monotonic() - t_rec
            page.wait_for_timeout(2000)
            # marcha lenta ~3,3 s
            page.wait_for_timeout(3300)
            marks["idle"] = time.monotonic() - t_rec
            page.screenshot(path=str(STILL_IDLE), type="png")

            post("/api/sim/launch")
            marks["launch"] = time.monotonic() - t_rec
            mid_taken = False
            result_t = None
            deadline = time.time() + 14
            while time.time() < deadline:
                snap = snapshot()
                spd = float(val(snap, "speed") or 0)
                if not mid_taken and 48 <= spd <= 72:
                    page.screenshot(path=str(STILL_LAUNCH), type="png")
                    marks["mid"] = time.monotonic() - t_rec
                    mid_taken = True
                pf = (perf().get("perf") or {}).get("runs") or {}
                run = pf.get("0-100") or {}
                if run.get("state") == "done" and run.get("time_s") is not None:
                    result_t = float(run["time_s"])
                    marks["done"] = time.monotonic() - t_rec
                    # encerra 80–120 e 402 m para não ficarem RUNNING no resultado
                    http(f"{BASE}/api/perf/reset?kind=80-120", data=b"{}", method="POST")
                    http(f"{BASE}/api/perf/reset?kind=402m", data=b"{}", method="POST")
                    break
                page.wait_for_timeout(80)
            if not mid_taken:
                page.screenshot(path=str(STILL_LAUNCH), type="png")
                marks["mid"] = time.monotonic() - t_rec
            # um instante com 100 km/h no painel, depois a tela de desempenho
            page.wait_for_timeout(500)
            page.evaluate("() => window.LancerUI && window.LancerUI.showPage('perf')")
            page.wait_for_timeout(400)
            marks["perf"] = time.monotonic() - t_rec
            page.wait_for_timeout(2800)
            page.screenshot(path=str(STILL_RESULT), type="png")
            marks["result"] = time.monotonic() - t_rec
            try:
                fps = page.evaluate("() => window.LancerHUD ? LancerHUD.fps() : 0")
                print("hud_fps", fps)
                marks["fps"] = fps
            except Exception as exc:
                print("hud_fps error", exc)
            # seguro extra para o hold de 2–3 s já estar no vídeo
            page.wait_for_timeout(400)

            rec = page.video
            context.close()
            webm = Path(rec.path()) if rec else None
            browser.close()

        if not webm or not webm.is_file():
            # playwright sometimes finalizes path after close
            files = list(vid_dir.glob("*.webm")) + list(vid_dir.glob("*.mp4"))
            if not files:
                raise SystemExit(f"sem vídeo gravado em {vid_dir}")
            webm = files[0]
        print("raw video", webm, "bytes", webm.stat().st_size)
        transcode(webm, VIDEO)
        info = probe(VIDEO)
        stream = (info.get("streams") or [{}])[0]
        fmt = info.get("format") or {}
        duration = float(fmt.get("duration") or 0)
        nb = stream.get("nb_frames")
        fps = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or ""
        print("mp4", VIDEO)
        print("duration", duration)
        print("codec", stream.get("codec_name"), stream.get("pix_fmt"), stream.get("width"), "x", stream.get("height"))
        print("fps", fps, "frames", nb)
        print("0-100", result_t)
        print("marks", marks)
        (TMP_DIR / "meta.json").write_text(json.dumps({
            "duration": duration, "frames": nb, "fps": fps,
            "time_s": result_t, "marks": marks,
            "codec": stream.get("codec_name"), "pix_fmt": stream.get("pix_fmt"),
            "stills": [str(STILL_IDLE), str(STILL_LAUNCH), str(STILL_RESULT)],
            "video": str(VIDEO),
        }, indent=2), encoding="utf-8")
        if duration < 20 or duration > 50:
            print("WARNING duration outside 25-40s target:", duration)
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())

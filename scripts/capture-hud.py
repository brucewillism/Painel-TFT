#!/usr/bin/env python3
"""Captura telas do HUD (800×480) e mede o FPS no Chromium headless."""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots"
PORT = int(os.environ.get("HUD_PORT", "8092"))
BASE = f"http://127.0.0.1:{PORT}"

def http(url, data=None, method=None, timeout=8):
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw.decode()) if raw else {}

def wait_up():
    t0 = time.time()
    while time.time() - t0 < 25:
        try:
            http(f"{BASE}/api/snapshot")
            return
        except Exception:
            time.sleep(0.2)
    raise SystemExit("server down")

def main() -> int:
    log = Path("/tmp/painel-hud-cap.log").open("w")
    proc = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(ROOT),
        env={**os.environ, "LANCER_SOURCE": "simulator"},
        stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        wait_up()
        # arrancada até ~80 km/h para o HUD ficar vivo
        http(f"{BASE}/api/perf/clear", data=b"{}")
        http(f"{BASE}/api/perf/reset", data=b"{}")
        http(f"{BASE}/api/sim/ignition", data=b"{}")
        time.sleep(0.4)
        http(f"{BASE}/api/sim/crank", data=b"{}")
        time.sleep(2.0)
        http(f"{BASE}/api/sim/launch", data=b"{}")
        # espera chegar na faixa 55-85
        for _ in range(80):
            snap = http(f"{BASE}/api/snapshot")
            sig = snap.get("signals") or {}
            spd = (sig.get("speed") or {}).get("value") or 0
            if 62 <= float(spd) <= 88:
                break
            time.sleep(0.15)
        print("speed for shots", spd)

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                channel="chrome", headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage",
                      "--hide-scrollbars", "--use-gl=angle",
                      "--use-angle=swiftshader", "--enable-webgl",
                      "--ignore-gpu-blocklist"],
            )
            page = browser.new_page(viewport={"width": 800, "height": 480}, device_scale_factor=1)
            page.goto(f"{BASE}/?page=gauges&nointro=1", wait_until="networkidle", timeout=25000)
            page.wait_for_function(
                "() => window.LancerHUDCar && LancerHUDCar.loaded()",
                timeout=15000,
            )
            page.wait_for_timeout(2000)
            samples = []
            for _ in range(4):
                page.wait_for_timeout(600)
                samples.append(page.evaluate(
                    "() => window.LancerHUDCar ? LancerHUDCar.fps() : (window.LancerHUD ? LancerHUD.fps() : 0)"
                ))
            fps = sum(samples) / max(1, len(samples))
            print("fps samples", samples, "avg", fps)
            webgl = page.evaluate("""() => {
              const c = document.getElementById('hud-car-canvas');
              if (!c) return {ok:false, reason:'no canvas'};
              const gl = c.getContext('webgl') || c.getContext('webgl2');
              return {ok: !!gl, vendor: gl && (gl.getParameter(gl.VENDOR)+' '+gl.getParameter(gl.RENDERER)),
                      w: c.width, h: c.height};
            }""")
            print("fps", fps, "webgl", webgl)
            page.evaluate("() => { if (window.LancerHUDCar) { LancerHUDCar.setRotate(false); LancerHUDCar.setYaw(0.10); } }")
            page.wait_for_timeout(250)
            page.screenshot(path=str(OUT / "gauges.png"), type="png")
            (OUT / "hud-fps.json").write_text(json.dumps({"fps": fps, "webgl": webgl}, indent=2))

            for name, hexv, acc in [
                ("hud-matrix.png", "#00FF6A", "matrix"),
                ("hud-amber.png", "#FFB000", "amber"),
            ]:
                http(f"{BASE}/api/settings", data=json.dumps({
                    "ui": {"theme": "hud", "accent": acc, "accent_hex": hexv}
                }).encode(), method="PUT")
                page.wait_for_timeout(600)
                page.screenshot(path=str(OUT / name), type="png")

            # volta ao ciano e espera o 0-100 terminar para a tela de desempenho
            http(f"{BASE}/api/settings", data=json.dumps({
                "ui": {"theme": "hud", "accent": "arc", "accent_hex": "#00D8FF"}
            }).encode(), method="PUT")
            for _ in range(40):
                pf = (http(f"{BASE}/api/perf").get("perf") or {}).get("runs") or {}
                if (pf.get("0-100") or {}).get("state") == "done":
                    break
                time.sleep(0.25)
            http(f"{BASE}/api/perf/reset?kind=80-120", data=b"{}")
            http(f"{BASE}/api/perf/reset?kind=402m", data=b"{}")
            page.wait_for_timeout(400)
            page.evaluate("() => window.LancerUI && LancerUI.showPage('perf')")
            page.wait_for_timeout(700)
            page.screenshot(path=str(OUT / "perf.png"), type="png")
            page.evaluate("() => window.LancerUI && LancerUI.showPage('map')")
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / "map.png"), type="png")
            browser.close()
        print("shots written")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    sys.exit(main())

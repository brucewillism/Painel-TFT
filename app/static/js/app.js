(function () {
  "use strict";

  var pages = ["home", "gauges", "car", "sensors", "map", "cameras", "media", "phone", "radio", "carplay", "trip", "dtcs", "perf", "track", "gforce", "telemetry", "dashcam", "health", "leds", "valet", "settings"];
  var current = 0;
  var settings = {};
  var lastSnap = null;
  var tripId = null;
  var gauges = {};
  var lastSpeedInt = null;
  var introPlaying = false;
  var cvtPosDisplay = 0;
  var sensorKeys = [
    ["rpm", "RPM"],
    ["speed", "Velocidade"],
    ["coolant_temp", "Temp. motor"],
    ["intake_temp", "Temp. admissão"],
    ["ambient_temp", "Temp. ambiente"],
    ["engine_load", "Carga"],
    ["throttle", "Acelerador"],
    ["maf", "MAF"],
    ["map", "MAP"],
    ["battery_voltage", "Bateria"],
    ["module_voltage", "Tensão ECU"],
    ["stft_b1", "STFT B1"],
    ["ltft_b1", "LTFT B1"],
    ["timing_advance", "Avanço"],
    ["o2_b1s1_v", "O2 B1S1"],
    ["o2_b1s2_v", "O2 B1S2"],
    ["fuel_level", "Combustível"],
    ["runtime", "Tempo ligado"],
    ["baro", "Barômetro"],
    ["cvt_ratio", "Relação CVT"],
    ["cvt_overall", "Relação total"],
    ["cvt_rpm_per_kmh", "RPM/km/h"],
    ["cvt_temp", "Temp. fluido CVT"],
    ["gear", "Marcha"],
    ["instant_consumption", "Cons. inst."],
    ["avg_consumption", "Cons. médio"],
    ["trip_distance", "Viagem"],
    ["gps_speed", "Vel. GPS"],
    ["gps_sats", "Satélites"],
    ["gps_alt", "Altitude"],
  ];

  function $(id) { return document.getElementById(id); }
  function qs(sel) { return document.querySelector(sel); }
  function params() { return new URLSearchParams(location.search); }
  function isCvt() { return (settings.transmission || "cvt") !== "manual"; }
  function perfOn() { return document.body.classList.contains("perf"); }

  function sig(snap, key) {
    return snap && snap.signals && snap.signals[key] ? snap.signals[key] : null;
  }
  function val(snap, key, def) {
    var s = sig(snap, key);
    return s && s.value != null ? s.value : def;
  }
  function fmt(n, d) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toFixed(d == null ? 0 : d);
  }
  function toSpeed(kmh) {
    if (kmh == null) return null;
    return (settings.units && settings.units.speed === "mph") ? kmh * 0.621371 : kmh;
  }
  function speedUnit() { return (settings.units && settings.units.speed === "mph") ? "mph" : "km/h"; }
  function toTemp(c) {
    if (c == null) return null;
    return (settings.units && settings.units.temperature === "f") ? c * 9 / 5 + 32 : c;
  }
  function tempUnit() { return (settings.units && settings.units.temperature === "f") ? "°F" : "°C"; }

  function applyPerformance() {
    var on = false;
    if (params().get("perf") === "1") on = true;
    else if (settings.ui && settings.ui.performance_mode) on = true;
    document.body.classList.toggle("perf", !!on);
  }

  var ACCENT_PRESETS = {
    arc: "#00D8FF",
    red: "#E10600",
    matrix: "#00FF6A",
    amber: "#FFB000",
    violet: "#B14CFF",
    white: "#F4FBFF"
  };

  function mixHex(a, b, t) {
    function p(h) {
      h = String(h || "").replace("#", "");
      if (h.length === 3) h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2];
      return [parseInt(h.slice(0,2),16)||0, parseInt(h.slice(2,4),16)||0, parseInt(h.slice(4,6),16)||0];
    }
    var A = p(a), B = p(b);
    return "#" + [0,1,2].map(function (i) {
      var v = Math.round(A[i] + (B[i] - A[i]) * t);
      return ("0" + Math.max(0, Math.min(255, v)).toString(16)).slice(-2);
    }).join("");
  }

  function applyAccent() {
    var ui = settings.ui || {};
    var acc = ui.accent || "arc";
    var hex = ui.accent_hex || ACCENT_PRESETS[acc] || ACCENT_PRESETS.arc;
    if (hex && hex.charAt(0) !== "#") hex = "#" + hex;
    var theme = (ui.theme === "classic") ? "classic" : "hud";
    document.body.classList.remove("theme-hud", "theme-classic", "theme-dark");
    document.body.classList.add(theme === "classic" ? "theme-classic" : "theme-hud");
    document.body.setAttribute("data-theme", theme);
    document.body.setAttribute("data-accent", acc);
    var hi = mixHex(hex, "#ffffff", 0.72);
    var dim = mixHex(hex, "#001018", 0.62);
    document.body.style.setProperty("--accent", hex);
    document.body.style.setProperty("--accent-hi", hi);
    document.body.style.setProperty("--accent-dim", dim);
    document.body.style.setProperty("--cyan", hex);
    document.body.style.setProperty("--glow", "0 0 14px " + hex + "b0, 0 0 28px " + hex + "55");
    if (window.LancerHUDCar) LancerHUDCar.setAccent(hex);
    if (window.LancerHUDCar) LancerHUDCar.setRotate(ui.hud_rotate !== false);
    var btn = $("hud-rotate-toggle");
    if (btn) {
      var paused = ui.hud_rotate === false;
      btn.classList.toggle("paused", paused);
      btn.setAttribute("aria-pressed", paused ? "true" : "false");
    }
    applyCarPaint();
    applyGaugeLayout();
    if (window.LancerHUDCar) setTimeout(function () { LancerHUDCar.resize(); }, 40);
  }

  function applyCarPaint() {
    var color = (settings.ui && settings.ui.car_color) || "#b1121a";
    document.body.style.setProperty("--car-paint", color);
  }

  function applyGaugeLayout() {
    var g = (settings.ui && settings.ui.gauges) || {};
    var page = $("page-gauges");
    if (!page) return;
    var on = function (key, def) { return g[key] == null ? def : !!g[key]; };
    page.classList.toggle("hide-rpm", !on("rpm", true));
    page.classList.toggle("hide-side", !on("temp", true) && !on("volt", true));
    if ($("gauge-temp")) $("gauge-temp").parentElement.style.display = on("temp", true) ? "" : "none";
    if ($("gauge-volt")) $("gauge-volt").parentElement.style.display = on("volt", true) ? "" : "none";
    page.classList.toggle("hide-cvt", !on("cvt", true));
    page.classList.toggle("hide-bars", !on("bars", true));
  }

  function clockTick() {
    var now = new Date();
    var hh = now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/Sao_Paulo" });
    $("clock").textContent = hh;
    if ($("home-clock")) $("home-clock").textContent = hh;
    applyNightMode(now);
  }
  var sunTimes = null;
  function applyNightMode(now) {
    var mode = (settings.ui && settings.ui.night_mode) || "auto";
    var on = mode === "on";
    var h = Number(now.toLocaleString("en-US", { hour: "numeric", hour12: false, timeZone: "America/Sao_Paulo" }));
    var min = now.getMinutes ? now.getMinutes() : 0;
    var hm = h + min / 60;
    if (mode === "auto") {
      on = h >= 18 || h < 6;
    } else if (mode === "sunset") {
      if (sunTimes && sunTimes.sunset_hour != null) {
        on = hm >= sunTimes.sunset_hour || hm < sunTimes.sunrise_hour;
      } else {
        on = h >= 18 || h < 6;
      }
    }
    document.body.classList.toggle("night", on);
  }

  function showPage(name, dir) {
    if (window.LancerExtras && LancerExtras.restricted(name, lastSnap)) {
      name = "valet";
    }
    var idx = pages.indexOf(name);
    if (idx < 0 || idx === current && qs(".page.active")) {
      // still allow first call
    }
    var prev = current;
    var goingRight = dir != null ? dir > 0 : idx > prev;
    if (dir == null && idx === prev) goingRight = true;
    current = idx;
    document.querySelectorAll(".page").forEach(function (p) {
      var isNew = p.dataset.page === name;
      if (isNew) {
        p.classList.remove("exit-left", "exit-right");
        p.classList.add("active");
      } else if (p.classList.contains("active")) {
        p.classList.remove("active");
        p.classList.add(goingRight ? "exit-left" : "exit-right");
      }
    });
    document.querySelectorAll(".tabbar button").forEach(function (b) {
      b.classList.toggle("active", b.dataset.page === name);
    });
    document.body.classList.toggle("mode-carplay", name === "carplay");
    document.body.setAttribute("data-page", name);
    if (window.LancerHUDCar) {
      LancerHUDCar.setPageActive(name === "gauges" && document.body.classList.contains("theme-hud"));
      if (name === "gauges") setTimeout(function () { LancerHUDCar.resize(); }, 50);
    }
    if (name === "map") setTimeout(function () {
      LancerMap.invalidate();
      if ($("range-panel") && !$("range-panel").hidden) loadRange(true);
    }, 340);
    if (window.LancerCameras) {
      if (name === "cameras") LancerCameras.activate();
      else LancerCameras.deactivate();
    }
    if (window.LancerExtras && LancerExtras.maybeLists) LancerExtras.maybeLists(name);
  }

  function initSwipe() {
    var startX = 0, startY = 0, tracking = false;
    var el = $("pages");
    el.addEventListener("touchstart", function (e) {
      if (!e.changedTouches.length) return;
      tracking = true;
      startX = e.changedTouches[0].screenX;
      startY = e.changedTouches[0].screenY;
    }, { passive: true });
    el.addEventListener("touchend", function (e) {
      if (!tracking || !e.changedTouches.length) return;
      tracking = false;
      var dx = e.changedTouches[0].screenX - startX;
      var dy = e.changedTouches[0].screenY - startY;
      if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy)) return;
      if (dx < 0 && current < pages.length - 1) showPage(pages[current + 1], 1);
      else if (dx > 0 && current > 0) showPage(pages[current - 1], -1);
    }, { passive: true });
  }

  function initShiftBar() {
    var bar = $("shift-bar");
    bar.innerHTML = "";
    for (var i = 0; i < 12; i++) {
      var s = document.createElement("div");
      s.className = "shift-seg";
      bar.appendChild(s);
    }
  }

  function updateShiftBar(rpm) {
    var segs = $("shift-bar").children;
    var pts = (lastSnap && lastSnap.meta && lastSnap.meta.shift && lastSnap.meta.shift.points) || [4500, 5200, 5800, 6200];
    var start = pts[0] || 3500, red = pts[pts.length - 1] || 6500;
    var t = rpm == null ? 0 : (rpm - start) / (red - start);
    t = LancerGauges.clamp(t, 0, 1);
    var lit = Math.round(t * segs.length);
    var near = rpm != null && rpm >= 6000;
    for (var i = 0; i < segs.length; i++) {
      var el = segs[i];
      var on = i < lit;
      el.classList.toggle("on", on);
      el.classList.toggle("hot", on && i >= 8);
      el.classList.toggle("pulse", on && near && i >= 9);
    }
  }

  function initGauges() {
    gauges.rpm = new LancerGauges.Gauge($("gauge-rpm"), {
      min: 0, max: 8000, unit: "x1000", label: "RPM", redFrom: 6500, yellowFrom: 5500, major: 8, color: "#e10600",
    });
    gauges.temp = new LancerGauges.Gauge($("gauge-temp"), {
      min: 40, max: 130, unit: "°C", label: "MOTOR", redFrom: 105, yellowFrom: 95, major: 6, decimals: 0, color: "#ff2a2a",
    });
    gauges.volt = new LancerGauges.Gauge($("gauge-volt"), {
      min: 10, max: 16, unit: "V", label: "BATERIA", redFrom: 15.2, yellowFrom: 14.8, major: 6, decimals: 1, color: "#ff5a5a",
    });
    var last = performance.now();
    function loop(now) {
      var dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      gauges.rpm.tick(dt);
      gauges.temp.tick(dt);
      gauges.volt.tick(dt);
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  }

  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  async function playIntro() {
    var q = params();
    if (q.get("nointro") === "1") return;
    var intro = $("intro");
    intro.hidden = false;
    introPlaying = true;
    if ($("intro-trans")) $("intro-trans").textContent = isCvt() ? "CVT" : "MANUAL";
    if (window.LancerCar && $("intro-car")) {
      LancerCar.mountIntro($("intro-car"));
      LancerCar.introOn();
    }
    try { await document.fonts.ready; } catch (e) {}
    // zera os ponteiros atrás do cartão de abertura
    Object.keys(gauges).forEach(function (k) {
      gauges[k].setFollow(0.2);
      gauges[k].opts.display = gauges[k].opts.min;
      gauges[k].setTarget(gauges[k].opts.min);
    });
    await wait(1100);
    // revela o painel e faz a varredura visível (0 → máx → descanso)
    intro.hidden = true;
    showPage("gauges", 1);
    await wait(400);
    Object.keys(gauges).forEach(function (k) {
      gauges[k].setFollow(0.1);
      gauges[k].setTarget(gauges[k].opts.max);
    });
    await wait(900);
    Object.keys(gauges).forEach(function (k) { gauges[k].setTarget(gauges[k].opts.min); });
    await wait(850);
    Object.keys(gauges).forEach(function (k) { gauges[k].setFollow(0.18); });
    introPlaying = false;
    if (!params().get("page")) showPage("home", 1);
  }

  function renderSensors(snap) {
    var grid = $("sensors-grid");
    var keys = sensorKeys.filter(function (pair) {
      if (pair[0] === "gear") return !isCvt();
      if (pair[0].indexOf("cvt_") === 0) return isCvt();
      return true;
    });
    if (grid.dataset.mode !== (isCvt() ? "cvt" : "man")) {
      grid.innerHTML = keys.map(function (pair) {
        return '<div class="sensor-card" id="sc-' + pair[0] + '">' +
          '<div class="label">' + pair[1] + '</div>' +
          '<div class="value" id="sv-' + pair[0] + '">—</div>' +
          '<div class="unit" id="su-' + pair[0] + '"></div></div>';
      }).join("");
      grid.dataset.mode = isCvt() ? "cvt" : "man";
    }
    keys.forEach(function (pair) {
      var key = pair[0];
      var s = sig(snap, key);
      var card = $("sc-" + key);
      var el = $("sv-" + key);
      var un = $("su-" + key);
      if (!s || !el) return;
      card.classList.toggle("stale", !!s.stale);
      var v = s.value;
      var unit = s.unit || "";
      if (key === "speed" || key === "gps_speed") { v = toSpeed(v); unit = speedUnit(); }
      if (key.indexOf("temp") >= 0) { v = toTemp(v); unit = tempUnit(); }
      if (key === "runtime") { el.textContent = formatHms(v); un.textContent = ""; return; }
      if (key === "gear") {
        el.textContent = v === 0 ? "N" : (v == null ? "—" : String(v));
        un.textContent = "";
        return;
      }
      var dec = 0;
      if (unit === "V" || unit === "g/s") dec = 2;
      if (unit === "L/100km" || key === "cvt_ratio" || key === "cvt_overall" || key === "cvt_rpm_per_kmh") dec = key === "cvt_ratio" ? 3 : 1;
      if (key.indexOf("o2_") === 0) dec = 2;
      el.textContent = fmt(v, dec);
      un.textContent = unit;
    });
  }

  function formatHms(s) {
    if (s == null) return "—";
    s = Math.max(0, Math.floor(s));
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
  }

  function applySnapshot(snap) {
    lastSnap = snap;
    var meta = snap.meta || {};
    if (meta.transmission) settings.transmission = meta.transmission;
    $("pill-vehicle").dataset.ok = meta.vehicle_connected ? "1" : "0";
    $("pill-gps").dataset.ok = meta.gps_connected ? "1" : "0";
    $("pill-source").textContent = (meta.source || "—").toUpperCase();

    var alerts = meta.alerts || [];
    var chip = $("alert-chip");
    if (alerts.length) {
      chip.hidden = false;
      chip.textContent = alerts[0].title.toUpperCase();
      document.body.classList.add("alert-on");
    } else {
      chip.hidden = true;
      document.body.classList.remove("alert-on");
    }

    if (window.LancerExtras) LancerExtras.update(snap);
    var rpm = val(snap, "rpm", 0);
    var speed = toSpeed(val(snap, "speed_fused", null) != null ? val(snap, "speed_fused", 0) : val(snap, "speed", 0)) || 0;
    var temp = toTemp(val(snap, "coolant_temp", null));
    var volt = val(snap, "battery_voltage", null);
    if (volt == null) volt = val(snap, "module_voltage", null);

    if (!introPlaying) {
      gauges.rpm.setTarget(rpm);
      if (temp != null) { gauges.temp.setTarget(temp); gauges.temp.opts.unit = tempUnit(); }
      if (volt != null) gauges.volt.setTarget(volt);
    }
    updateShiftBar(rpm);

    var speedInt = Math.round(speed);
    $("speed-value").textContent = fmt(speed, 0);
    $("speed-unit").textContent = speedUnit();
    if (lastSpeedInt != null && speedInt !== lastSpeedInt) {
      var el = $("speed-value");
      el.classList.remove("pop");
      void el.offsetWidth;
      el.classList.add("pop");
    }
    lastSpeedInt = speedInt;

    updateDrive(snap);

    $("inst-cons").textContent = val(snap, "instant_consumption", null) != null ? fmt(val(snap, "instant_consumption"), 1) + " L/100" : "—";
    $("avg-cons").textContent = val(snap, "avg_consumption", null) != null ? fmt(val(snap, "avg_consumption"), 1) + " L/100" : "—";
    $("trip-dist").textContent = fmt(val(snap, "trip_distance", 0), 1) + " km";

    setBar("throttle", val(snap, "throttle", 0), "%");
    setBar("load", val(snap, "engine_load", 0), "%");
    var fuel = val(snap, "fuel_level", null);
    setBar("fuel", fuel == null ? 0 : fuel, fuel == null ? "" : "%", fuel == null);

    renderSensors(snap);
    renderTrip(snap);

    var lat = val(snap, "gps_lat", null);
    var lon = val(snap, "gps_lon", null);
    LancerMap.update(lat, lon, val(snap, "gps_heading", 0));
    $("hud-gps-speed").textContent = fmt(toSpeed(val(snap, "gps_speed", null)), 0) + " " + speedUnit();
    $("hud-heading").textContent = fmt(val(snap, "gps_heading", null), 0) + "°";
    $("hud-alt").textContent = fmt(val(snap, "gps_alt", null), 0) + " m";
    $("hud-sats").textContent = fmt(val(snap, "gps_sats", null), 0);
    $("hud-coords").textContent = (lat != null && lon != null) ? lat.toFixed(5) + ", " + lon.toFixed(5) : "sem fix";

    if (meta.settings_rev && meta.settings_rev !== applySnapshot._rev) {
      applySnapshot._rev = meta.settings_rev;
      if (meta.settings) settings = meta.settings;
      else if (meta.ui) {
        settings.ui = meta.ui;
      }
      applyPerformance();
      applyAccent();
      applyNightMode(new Date());
    }
    if (window.LancerHUD) {
      LancerHUD.update(snap, {
        units: settings.units,
        transmission: settings.transmission || (meta.transmission),
        redline: (settings.alerts && settings.alerts.rpm_high) ? settings.alerts.rpm_high + 1800 : 8000
      });
    }
    if (window.LancerCar) LancerCar.update(snap);
    renderVehicle(meta.vehicle);
    if (snap.signals && snap.signals.fuel_range_km && $("range-km")) {
      var rk = snap.signals.fuel_range_km.value;
      $("range-km").textContent = rk != null ? fmt(rk, 0) + " km" : "— km";
    }
    var rev = !!(meta.reverse);
    if (window.LancerCameras) {
      var entered = LancerCameras.setReverse(rev);
      if (entered && pages[current] !== "cameras") {
        snap._savedPage = pages[current];
        showPage("cameras", 1);
        LancerCameras.show("rear");
      } else if (!rev && pages[current] === "cameras" && document.body.dataset.autoReverse === "1") {
        document.body.dataset.autoReverse = "";
        showPage("gauges", -1);
      }
      if (entered) document.body.dataset.autoReverse = "1";
    }
  }

  function updateDrive(snap) {
    var cvtBlock = $("cvt-block");
    var badge = $("gear-badge");
    if (!isCvt()) {
      cvtBlock.hidden = true;
      badge.hidden = false;
      var gear = val(snap, "gear", null);
      badge.textContent = gear === 0 ? "N" : (gear == null ? "—" : String(gear));
      $("cvt-temp-stat").hidden = true;
      return;
    }
    cvtBlock.hidden = false;
    badge.hidden = true;
    var ratio = val(snap, "cvt_ratio", null);
    var rpk = val(snap, "cvt_rpm_per_kmh", null);
    var pos = val(snap, "cvt_position", null);
    $("cvt-ratio").textContent = ratio == null ? "IDLE" : Number(ratio).toFixed(3);
    $("cvt-sub").textContent = rpk == null ? "parado" : fmt(rpk, 1) + " rpm/km/h";
    if (pos == null) pos = 0;
    cvtPosDisplay = LancerGauges.lerp(cvtPosDisplay, pos, 0.18);
    $("cvt-fill").style.width = (cvtPosDisplay * 100) + "%";
    $("cvt-needle").style.left = (cvtPosDisplay * 100) + "%";

    var ct = val(snap, "cvt_temp", null);
    var stat = $("cvt-temp-stat");
    if (ct != null) {
      stat.hidden = false;
      $("cvt-temp-val").textContent = fmt(toTemp(ct), 0) + " " + tempUnit();
    } else {
      stat.hidden = true;
    }
  }

  function setBar(name, value, suffix, empty) {
    var v = empty ? 0 : LancerGauges.clamp(value || 0, 0, 100);
    $("bar-" + name).style.width = v + "%";
    $("val-" + name).textContent = empty ? "—" : fmt(value, 0) + suffix;
  }

  function renderTrip(snap) {
    $("t-distance").textContent = fmt(val(snap, "trip_distance", 0), 2);
    $("t-time").textContent = formatHms(val(snap, "trip_time_s", 0));
    $("t-avg").textContent = fmt(val(snap, "avg_consumption", null), 1);
    $("t-inst").textContent = fmt(val(snap, "instant_consumption", null), 1);
    $("t-avgspeed").textContent = fmt(toSpeed(val(snap, "avg_speed", null)), 1);
    $("t-maxspeed").textContent = fmt(toSpeed(val(snap, "max_speed", null)), 0);
    $("t-fuel").textContent = fmt(val(snap, "trip_fuel", null), 2);
    tripId = (snap.meta && snap.meta.trip_id) || tripId;
    $("t-id").textContent = tripId == null ? "—" : String(tripId);
  }

  function connectWs() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    var ws = new WebSocket(proto + "://" + location.host + "/ws");
    ws.onmessage = function (ev) {
      try { applySnapshot(JSON.parse(ev.data)); } catch (e) {}
    };
    ws.onclose = function () { setTimeout(connectWs, 1000); };
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }

  function confirmModal(title, text) {
    return new Promise(function (resolve) {
      $("modal-title").textContent = title;
      $("modal-text").textContent = text;
      $("modal").hidden = false;
      function done(ok) {
        $("modal").hidden = true;
        $("modal-ok").removeEventListener("click", onOk);
        $("modal-cancel").removeEventListener("click", onCancel);
        resolve(ok);
      }
      function onOk() { done(true); }
      function onCancel() { done(false); }
      $("modal-ok").addEventListener("click", onOk);
      $("modal-cancel").addEventListener("click", onCancel);
    });
  }

  async function loadStatus() {
    var res = await fetch("/api/status");
    var data = await res.json();
    settings = data.settings || {};
    tripId = data.trip_id;
    fillSettingsForm();
    applyPerformance();
    applyAccent();
    return data;
  }

  function fillSettingsForm() {
    $("set-speed-unit").value = (settings.units && settings.units.speed) || "kmh";
    $("set-temp-unit").value = (settings.units && settings.units.temperature) || "c";
    $("set-fuel").value = (settings.fuel && settings.fuel.type) || "flex";
    $("set-night").value = (settings.ui && settings.ui.night_mode) || "auto";
    $("set-coolant").value = (settings.alerts && settings.alerts.coolant_temp_c) || 105;
    $("set-vlow").value = (settings.alerts && settings.alerts.voltage_low_v) || 11.8;
    $("set-rpm").value = (settings.alerts && settings.alerts.rpm_high) || 6200;
    $("set-cvt-temp").value = (settings.alerts && settings.alerts.cvt_temp_c) || 120;
    $("set-bright").value = (settings.ui && settings.ui.brightness) || 80;
    $("bright-val").textContent = $("set-bright").value;
    $("set-trans").value = settings.transmission || "cvt";
    $("set-perf").value = (settings.ui && settings.ui.performance_mode) ? "on" : "off";
    if ($("set-theme")) $("set-theme").value = (settings.ui && settings.ui.theme) === "classic" ? "classic" : "hud";
    if ($("set-hud-rotate")) $("set-hud-rotate").value = (settings.ui && settings.ui.hud_rotate === false) ? "off" : "on";
    if ($("set-unused-tt")) $("set-unused-tt").value = (settings.ui && settings.ui.unused_telltales) === "hide" ? "hide" : "dim";
    var acc = (settings.ui && settings.ui.accent) || "arc";
    if ($("set-accent")) {
      if (ACCENT_PRESETS[acc] || acc === "custom") $("set-accent").value = acc;
      else $("set-accent").value = "custom";
    }
    if ($("set-accent-hex")) $("set-accent-hex").value = (settings.ui && settings.ui.accent_hex) || ACCENT_PRESETS[acc] || "#00D8FF";
    if ($("set-car-color")) $("set-car-color").value = (settings.ui && settings.ui.car_color) || "#b1121a";
    paintAccentSwatches();
    var gg = (settings.ui && settings.ui.gauges) || {};
    ["rpm","temp","volt","cvt","bars"].forEach(function (k) {
      var el = $("g-" + k);
      if (el) el.checked = gg[k] == null ? true : !!gg[k];
    });
    $("label-cvt-alert").style.display = ($("set-trans").value === "cvt") ? "" : "none";
  }

  async function saveSettings() {
    var body = {
      units: { speed: $("set-speed-unit").value, temperature: $("set-temp-unit").value },
      fuel: { type: $("set-fuel").value },
      ui: {
        night_mode: $("set-night").value,
        brightness: Number($("set-bright").value),
        performance_mode: $("set-perf").value === "on",
        theme: ($("set-theme") && $("set-theme").value) || "hud",
        accent: ($("set-accent") && $("set-accent").value) || "arc",
        accent_hex: ($("set-accent-hex") && $("set-accent-hex").value) || "#00D8FF",
        car_color: ($("set-car-color") && $("set-car-color").value) || "#b1121a",
        hud_rotate: !($("set-hud-rotate") && $("set-hud-rotate").value === "off"),
        unused_telltales: ($("set-unused-tt") && $("set-unused-tt").value) || "dim",
        gauges: {
          rpm: $("g-rpm") ? $("g-rpm").checked : true,
          temp: $("g-temp") ? $("g-temp").checked : true,
          volt: $("g-volt") ? $("g-volt").checked : true,
          cvt: $("g-cvt") ? $("g-cvt").checked : true,
          bars: $("g-bars") ? $("g-bars").checked : true
        }
      },
      alerts: {
        coolant_temp_c: Number($("set-coolant").value),
        voltage_low_v: Number($("set-vlow").value),
        rpm_high: Number($("set-rpm").value),
        cvt_temp_c: Number($("set-cvt-temp").value),
      },
      transmission: $("set-trans").value,
    };
    var res = await fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    settings = await res.json();
    applyNightMode(new Date());
    applyPerformance();
    applyAccent();
    applyCarPaint();
    applyGaugeLayout();
    $("label-cvt-alert").style.display = isCvt() ? "" : "none";
    if ($("sensors-grid")) $("sensors-grid").dataset.mode = "";
  }

  async function refreshDtcs() {
    var res = await fetch("/api/dtcs");
    var data = await res.json();
    $("mil-lamp").dataset.on = data.mil ? "1" : "0";
    var list = $("dtc-list");
    if (!data.dtcs || !data.dtcs.length) {
      list.innerHTML = '<li class="dtc-empty">Nenhum código armazenado.</li>';
      return;
    }
    list.innerHTML = data.dtcs.map(function (d) {
      return '<li><div class="code">' + (d.code || "") + '</div>' +
        '<div class="desc">' + (d.description || "Sem descrição") + '</div>' +
        '<div class="st">' + (d.status || "") + '</div></li>';
    }).join("");
  }

  function initHome() {
    var tiles = [
      ["gauges", "PAINEL", "gauges"],
      ["map", "MAPA", "map"],
      ["carplay", "CARPLAY", "carplay"],
      ["media", "MÚSICA", "media"],
      ["phone", "TELEFONE", "phone"],
      ["cameras", "CÂMERAS", "cameras"],
      ["radio", "RÁDIO", "radio"],
      ["settings", "AJUSTES", "settings"],
      ["car", "CARRO", "car"],
      ["sensors", "SENSORES", "sensors"],
      ["trip", "VIAGEM", "trip"],
      ["dtcs", "FALHAS", "dtcs"],
      ["perf", "PERF", "perf"],
      ["track", "PISTA", "track"],
      ["gforce", "G-FORCE", "gforce"],
      ["telemetry", "LOG", "telemetry"],
      ["dashcam", "DASH", "dashcam"],
      ["health", "SAÚDE", "health"],
      ["leds", "LED", "leds"],
      ["valet", "VALET", "valet"],
    ];
    var grid = $("home-grid");
    if (!grid) return;
    grid.innerHTML = tiles.map(function (row) {
      var extra = row[0] === "carplay" ? " tile-carplay" : "";
      var ico = (window.LancerIcons && LancerIcons.svg(row[2])) || "";
      return '<button class="tile' + extra + '" data-page="' + row[0] + '">' + ico + row[1] + "</button>";
    }).join("");
    grid.querySelectorAll(".tile").forEach(function (b) {
      b.addEventListener("click", function () { showPage(b.getAttribute("data-page")); });
    });
  }

  function paintAccentSwatches() {
    var box = $("set-accent-swatches");
    if (!box) return;
    var cur = ($("set-accent-hex") && $("set-accent-hex").value) || "";
    box.innerHTML = Object.keys(ACCENT_PRESETS).map(function (id) {
      var hex = ACCENT_PRESETS[id];
      var on = cur.toLowerCase() === hex.toLowerCase() ? " on" : "";
      return '<button type="button" class="swatch' + on + '" data-id="' + id + '" data-hex="' + hex + '" style="--c:' + hex + '" title="' + id + '"></button>';
    }).join("");
    box.querySelectorAll(".swatch").forEach(function (b) {
      b.addEventListener("click", function () {
        $("set-accent").value = b.getAttribute("data-id");
        $("set-accent-hex").value = b.getAttribute("data-hex");
        paintAccentSwatches();
        saveSettings();
      });
    });
  }

  function initHud() {
    if (!window.LancerHUD) return;
    var ui = settings.ui || {};
    var body = "sedan";
    var v = (window._vehicleInfo) || {};
    if (v.body) body = v.body;
    if (v.art && v.art.body) body = v.art.body;
    LancerHUD.init({
      accent: ui.accent_hex || ACCENT_PRESETS[ui.accent] || "#00D8FF",
      body: body,
      hero: v.hud_hero || null,
      rotate: ui.hud_rotate !== false,
      perf: !!ui.performance_mode,
      onRotateChange: function (on) {
        if ($("set-hud-rotate")) $("set-hud-rotate").value = on ? "on" : "off";
        if (settings.ui) settings.ui.hud_rotate = on;
        fetch("/api/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ui: { hud_rotate: on } })
        });
      }
    });
  }

  async function init() {
    initShiftBar();
    initGauges();
    initSwipe();
    initHome();
    if (window.LancerCar) {
      LancerCar.mount($("car-stage"), $("car-top"));
    }
    if (window.LancerCameras) LancerCameras.init();
    if (window.LancerMedia) LancerMedia.init();
    document.querySelectorAll(".tabbar button").forEach(function (b) {
      b.addEventListener("click", function () { showPage(b.dataset.page); });
    });
    $("set-bright").addEventListener("input", function () { $("bright-val").textContent = $("set-bright").value; });
    $("set-trans").addEventListener("change", function () {
      $("label-cvt-alert").style.display = $("set-trans").value === "cvt" ? "" : "none";
    });
    $("btn-save-settings").addEventListener("click", saveSettings);
    $("btn-trip-new").addEventListener("click", async function () {
      var ok = await confirmModal("Nova viagem", "Zerar estatísticas e começar uma nova viagem?");
      if (!ok) return;
      var res = await fetch("/api/trips/start", { method: "POST" });
      var data = await res.json();
      tripId = data.trip_id;
      LancerMap.setTrail([]);
    });
    $("btn-gpx").addEventListener("click", function () {
      if (!tripId) return;
      window.location.href = "/api/trips/" + tripId + "/gpx";
    });
    $("btn-dtc-refresh").addEventListener("click", refreshDtcs);
    $("btn-dtc-clear").addEventListener("click", async function () {
      var ok = await confirmModal("Apagar códigos", "Isso apaga os DTCs da ECU e apaga a luz de injeção se a falha não estiver presente. Confirma?");
      if (!ok) return;
      await fetch("/api/dtcs/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
      refreshDtcs();
    });
    $("btn-shutdown").addEventListener("click", async function () {
      var ok = await confirmModal("Desligar", "Desligar o Raspberry Pi agora? Só faça isso com o suporte de desligamento seguro ativo.");
      if (!ok) return;
      await fetch("/api/shutdown", { method: "POST" });
    });

    clockTick();
    setInterval(clockTick, 1000);

    var status = await loadStatus();
    if (status.vehicle) renderVehicle(status.vehicle);
    window._vehicleInfo = status.vehicle || {};
    initHud();
    if ($("set-accent")) $("set-accent").addEventListener("change", function () {
      var id = $("set-accent").value;
      if (ACCENT_PRESETS[id]) $("set-accent-hex").value = ACCENT_PRESETS[id];
      paintAccentSwatches();
    });
    if ($("set-theme")) $("set-theme").addEventListener("change", function () { saveSettings(); });
    if (status.range) renderRange(status.range);
    try { sunTimes = await (await fetch("/api/companion/sun")).json(); } catch (e) {}
    var mapCfg = await (await fetch("/api/map/config")).json();
    LancerMap.init(mapCfg);
    initRangeUi();
    if (status.trip_id) {
      try {
        var trail = await (await fetch("/api/trips/" + status.trip_id + "/trail")).json();
        LancerMap.setTrail(trail.points || []);
      } catch (e) {}
    }
    var pageParam = params().get("page");
    if (pageParam) {
      document.querySelectorAll(".page").forEach(function (p) { p.classList.add("no-anim"); });
      showPage(pageParam);
      requestAnimationFrame(function () {
        document.querySelectorAll(".page").forEach(function (p) { p.classList.remove("no-anim"); });
      });
    }
    refreshDtcs();
    // intro primeiro, depois WS (para a varredura não brigar com dados ao vivo)
    await playIntro();
    connectWs();
    setInterval(async function () {
      if (lastSnap && Date.now() / 1000 - lastSnap.ts < 2) return;
      try {
        var snap = await (await fetch("/api/snapshot")).json();
        applySnapshot(snap);
      } catch (e) {}
    }, 1000);
  }

  function renderVehicle(v) {
    if (!v) return;
    if ($("vin-code")) $("vin-code").textContent = v.vin || "(não lido)";
    if ($("vin-info")) $("vin-info").textContent = v.label || "";
    if ($("vin-src")) {
      var src = (v.source === "obd" || (v.source || "").indexOf("obd") === 0) ? "lido no OBD (Mode 09)" : (v.source === "vpic" || (v.source || "").indexOf("vpic") >= 0 ? "VIN + vPIC" : "modelo configurado");
      if (v.note) src += " — " + v.note;
      $("vin-src").textContent = src;
    }
    var short = [v.make || v.manufacturer, v.model].filter(Boolean).join(" ");
    if (!short) short = "PAINEL TFT";
    if ($("brand-name")) $("brand-name").textContent = short.toUpperCase();
    if ($("intro-title")) $("intro-title").textContent = short.toUpperCase();
    window._vehicleInfo = v;
    var body = (v.art && v.art.body) || v.body;
    if (window.LancerHUDCar) {
      if (v.hud_hero && v.hud_hero.image) LancerHUDCar.setHero(v.hud_hero);
      else {
        LancerHUDCar.setHero(null);
        if (body) LancerHUDCar.setBody(body);
      }
    }
    if ($("intro-trans") && v.transmission) {
      var tr = String(v.transmission).toLowerCase();
      $("intro-trans").textContent = tr === "cvt" ? "CVT" : (tr === "auto" ? "AUTOMÁTICO" : tr.toUpperCase());
    }
  }
  globalThis.applyVehicleInfo = function (d) {
    if (d && d.identity) renderVehicle(d.identity);
  };

  function initRangeUi() {
    var btn = $("btn-postos");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var panel = $("range-panel");
      var show = panel.hidden;
      panel.hidden = !show;
      if (show) {
        if (window.LancerMap && LancerMap.setFollow) LancerMap.setFollow(false);
        loadRange(true);
      }
    });
    if (params().get("range") === "1") {
      $("range-panel").hidden = false;
      setTimeout(function () { loadRange(true); }, 600);
    }
  }

  async function loadRange(open) {
    try {
      var data = await (await fetch("/api/range")).json();
      renderRange(data);
      if (open && window.LancerMap && LancerMap.showStations) LancerMap.showStations(data);
    } catch (e) {}
  }

  function renderRange(data) {
    if (!data) return;
    if ($("range-km")) $("range-km").textContent = data.range_km != null ? fmt(data.range_km, 0) + " km" : "— km";
    if ($("range-note")) $("range-note").textContent = data.traffic_note || "";
    var now = $("home-now");
    // don't overwrite playing media
    var list = $("range-list");
    if (!list) return;
    var badgePt = { reachable: "ALCANCE", "at-risk": "NO LIMITE", unreachable: "FORA" };
    list.innerHTML = (data.stations || []).map(function (s) {
      return '<button class="st-row" data-id="' + s.id + '"><div class="nm">' + (s.name || "Posto") +
        ' <span class="badge ' + s.badge + '">' + (badgePt[s.badge] || s.badge) + "</span></div>" +
        '<div class="meta">' + fmt(s.distance_km, 1) + " km · " + (s.eta_min != null ? s.eta_min + " min" : "—") +
        " · " + (s.fuel_at_arrival_l != null ? fmt(s.fuel_at_arrival_l, 1) + " L na chegada" : "—") +
        (s.traffic_extra_min ? " · +" + s.traffic_extra_min + " min trânsito" : "") +
        "</div></button>";
    }).join("") || '<div class="meta">Nenhum posto (sem GPS ou cache).</div>';
    list.querySelectorAll(".st-row").forEach(function (b) {
      b.addEventListener("click", function () {
        if (window.LancerMap) LancerMap.selectStation(b.getAttribute("data-id"));
      });
    });
  }

  globalThis.LancerUI = { showPage: showPage, loadRange: loadRange, renderRange: renderRange, get lastSnap() { return lastSnap; } };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

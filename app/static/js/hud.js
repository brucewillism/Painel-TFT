/* HUD wireframe: velocímetro, RPM, marcha, telltales, callouts e linhas. */
(function (global) {
  "use strict";

  var ANCHORS = ["motor", "cvt", "battery", "wheels"];
  var TELLTALES = [
    ["low_beam", "Farol baixo"],
    ["high_beam", "Farol alto"],
    ["parking_lights", "Lanterna"],
    ["turn_left", "Seta esq."],
    ["turn_right", "Seta dir."],
    ["parking_brake", "Freio de mão"],
    ["check_engine", "Check engine"],
    ["door_open", "Porta aberta"],
    ["seatbelt", "Cinto"]
  ];
  var DRIVE_LABEL = { fwd: "DIANTEIRA", rwd: "TRASEIRA", awd: "INTEGRAL", "4wd": "4X4", "4x4": "4X4" };

  function $(id) { return document.getElementById(id); }
  function val(snap, key, def) {
    var s = snap && snap.signals && snap.signals[key];
    return s && s.value != null ? s.value : def;
  }
  function fmt(n, d) {
    if (n == null || Number.isNaN(n)) return "—";
    return Number(n).toFixed(d == null ? 0 : d);
  }
  function fmtInt(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return Math.round(n).toLocaleString("pt-BR");
  }

  function setSegBar(id, frac, segs) {
    var el = $(id);
    if (!el) return;
    segs = segs || 16;
    frac = Math.max(0, Math.min(1, frac || 0));
    var on = Math.round(frac * segs);
    if (el.childNodes.length !== segs) {
      el.innerHTML = "";
      for (var i = 0; i < segs; i++) {
        var s = document.createElement("span");
        el.appendChild(s);
      }
    }
    for (var j = 0; j < segs; j++) el.childNodes[j].className = j < on ? "on" : "";
  }

  function gearSlots(transmission) {
    return transmission === "manual" ? ["R", "N", "1", "2", "3", "4", "5", "6"] : ["P", "R", "N", "D", "L"];
  }

  function renderGear(value, transmission) {
    var big = $("hud-gear-current");
    var strip = $("hud-gear-strip");
    var label = value == null || value === "" ? "—" : String(value).toUpperCase();
    if (label === "0") label = "N";
    if (big) big.textContent = label;
    var slots = gearSlots(transmission);
    if (!strip) return;
    if (strip.dataset.slots !== slots.join("")) {
      strip.dataset.slots = slots.join("");
      strip.innerHTML = slots.map(function (g) {
        return '<span data-g="' + g + '">' + g + "</span>";
      }).join("");
    }
    Array.prototype.forEach.call(strip.querySelectorAll("span"), function (s) {
      s.classList.toggle("on", s.getAttribute("data-g") === label);
    });
  }

  function telltaleState(snap, key) {
    var lights = (snap.meta && snap.meta.lights) || {};
    var values = lights.values || {};
    var configured = lights.configured || [];
    var unused = lights.unused || "dim";
    var on = false;
    if (key === "check_engine") on = !!(snap.meta && snap.meta.mil) || !!values[key];
    else if (values[key] != null) on = !!values[key];
    else on = !!val(snap, key, 0);
    var conf = !configured.length || configured.indexOf(key) !== -1;
    if (key === "check_engine") conf = true;
    return { on: on, configured: conf, unused: unused };
  }

  function renderTelltales(snap) {
    TELLTALES.forEach(function (row) {
      var el = $("tt-" + row[0]);
      if (!el) return;
      var st = telltaleState(snap, row[0]);
      el.classList.toggle("on", !!st.on);
      el.classList.toggle("unconfigured", !st.configured);
      el.classList.toggle("hide-unused", !st.configured && st.unused === "hide");
    });
  }

  function renderCallouts(snap, units) {
    var tempU = (units && units.temperature === "f") ? "°F" : "°C";
    function toTemp(c) {
      if (c == null) return null;
      return tempU === "°F" ? c * 9 / 5 + 32 : c;
    }
    var cool = toTemp(val(snap, "coolant_temp", null));
    var load = val(snap, "engine_load", null);
    setText("hud-coolant", cool == null ? "—" : fmt(cool, 0) + tempU);
    setText("hud-load", load == null ? "—" : fmt(load, 0) + "%");

    var cvtT = toTemp(val(snap, "cvt_temp", null));
    var ratio = val(snap, "cvt_ratio", null);
    var trans = (snap.meta && (snap.meta.transmission || (snap.meta.settings && snap.meta.settings.transmission))) || "";
    var cvtBox = $("hud-co-cvt");
    if (cvtBox) {
      var isCvt = trans ? trans !== "manual" : ratio != null || cvtT != null;
      cvtBox.hidden = trans === "manual" && ratio == null;
      setText("hud-cvt-temp", cvtT == null ? "—" : fmt(cvtT, 0) + tempU);
      setText("hud-cvt-ratio", ratio == null ? "—" : Number(ratio).toFixed(2) + ":1");
    }

    var volt = val(snap, "battery_voltage", null);
    if (volt == null) volt = val(snap, "module_voltage", null);
    setText("hud-volt", volt == null ? "—" : fmt(volt, 1) + " V");

    var tpms = snap.meta && snap.meta.tpms;
    var pressEl = $("hud-tpms");
    var wheels = tpms && (tpms.wheels || tpms);
    var vals = [];
    if (wheels) {
      ["fl", "fr", "rl", "rr"].forEach(function (w) {
        var rec = wheels[w];
        if (rec && rec.kpa != null) vals.push(rec.kpa / 100.0); // bar
      });
    }
    if (pressEl) {
      if (!vals.length) {
        pressEl.hidden = true;
      } else {
        pressEl.hidden = false;
        var mean = vals.reduce(function (a, b) { return a + b; }, 0) / vals.length;
        setText("hud-tpms-val", mean.toFixed(1) + " bar");
      }
    }
    var drive = (snap.meta && (snap.meta.drive || (snap.meta.vehicle && snap.meta.vehicle.drive))) || "fwd";
    setText("hud-drive-co", "TRAÇÃO " + (DRIVE_LABEL[String(drive).toLowerCase()] || "DIANTEIRA"));
  }

  function setText(id, text) {
    var el = $(id);
    if (el) el.textContent = text;
  }

  function renderStatus(snap) {
    var drive = (snap.meta && (snap.meta.drive || (snap.meta.vehicle && snap.meta.vehicle.drive))) || "fwd";
    setText("hud-status-drive", "TRAÇÃO " + (DRIVE_LABEL[String(drive).toLowerCase()] || "DIANTEIRA"));
    var mode = val(snap, "drive_mode", null) || (snap.meta && snap.meta.drive_mode) || "NORMAL";
    setText("hud-status-mode", "MOD. CONDUÇÃO: " + String(mode).toUpperCase());
    var src = (snap.meta && snap.meta.source) || "—";
    var sps = snap.meta && (snap.meta.samples_s || snap.meta.poll_s);
    var link = (snap.meta && snap.meta.vehicle_connected) ? "OK" : "—";
    var bits = ["OBD " + String(src).toUpperCase(), link];
    if (sps) bits.push(fmt(sps, 0) + "/s");
    else if (String(src).toLowerCase() === "simulator") bits.push("20/s");
    setText("hud-status-obd", bits.join(" · "));
  }

  function renderLeaders() {
    var svg = $("hud-leaders");
    var stage = $("hud-stage");
    if (!svg || !stage || !global.LancerHUDCar) return;
    var sr = stage.getBoundingClientRect();
    var d = "";
    ANCHORS.forEach(function (name) {
      var co = $("hud-co-" + (name === "battery" ? "battery" : name === "wheels" ? "wheels" : name));
      // ids: hud-co-motor, hud-co-cvt, hud-co-battery, hud-co-wheels
      if (name === "cvt") co = $("hud-co-cvt");
      if (!co || co.hidden) return;
      var p = LancerHUDCar.projectAnchor(name);
      if (!p || !p.visible) return;
      var cr = co.getBoundingClientRect();
      var x1 = p.x, y1 = p.y;
      var x2 = cr.left - sr.left, y2 = cr.top - sr.top + cr.height * 0.35;
      // linhas só fazem sentido se o callout está à direita do palco
      if (x2 < 8) return;
      var mid = (x1 + x2) / 2;
      d += "M " + x1.toFixed(1) + " " + y1.toFixed(1) +
        " L " + mid.toFixed(1) + " " + y1.toFixed(1) +
        " L " + mid.toFixed(1) + " " + y2.toFixed(1) +
        " L " + x2.toFixed(1) + " " + y2.toFixed(1) + " ";
    });
    var path = $("hud-leaders-path");
    if (path) path.setAttribute("d", d);
  }

  function update(snap, ctx) {
    ctx = ctx || {};
    if (!$("hud-gauges")) return;
    var units = ctx.units || (snap.meta && snap.meta.settings && snap.meta.settings.units) || {};
    var speedU = units.speed === "mph" ? "mph" : "km/h";
    var speed = val(snap, "speed_fused", null);
    if (speed == null) speed = val(snap, "speed", 0) || 0;
    if (units.speed === "mph") speed = speed * 0.621371;
    var rpm = val(snap, "rpm", 0) || 0;
    setText("hud-speed-value", fmt(speed, 0));
    setText("hud-speed-unit", speedU);
    setText("hud-rpm-value", fmtInt(rpm));
    setSegBar("hud-speed-bar", speed / 240, 16);
    var redline = (ctx.redline || 8000);
    setSegBar("hud-rpm-bar", rpm / redline, 16);

    var gearMeta = snap.meta && snap.meta.gear;
    var g = (gearMeta && gearMeta.value != null) ? gearMeta.value : val(snap, "gear_label", null);
    if (g == null) g = val(snap, "gear", null);
    var trans = ctx.transmission || (snap.meta && snap.meta.transmission) || "cvt";
    renderGear(g, trans);
    renderTelltales(snap);
    renderCallouts(snap, units);
    renderStatus(snap);
    renderLeaders();

    var fpsEl = $("hud-fps");
    if (fpsEl && fpsEl.parentElement && !fpsEl.parentElement.hidden) {
      var fps = global.LancerHUDCar ? LancerHUDCar.fps() : 0;
      fpsEl.textContent = fps ? fps.toFixed(0) + " fps" : "— fps";
    }
  }

  function init(opts) {
    opts = opts || {};
    var canvas = $("hud-car-canvas");
    if (canvas && global.LancerHUDCar) {
      LancerHUDCar.mount(canvas, {
        accent: opts.accent || "#00D8FF",
        body: opts.body || "sedan",
        hero: opts.hero || null,
        rotate: opts.rotate !== false,
        perf: !!opts.perf,
        onFrame: renderLeaders
      });
    }
    var btn = $("hud-rotate-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        var on = !btn.classList.contains("paused");
        btn.classList.toggle("paused", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
        btn.title = on ? "Retomar rotação" : "Pausar rotação";
        if (global.LancerHUDCar) LancerHUDCar.setRotate(!on);
        if (opts.onRotateChange) opts.onRotateChange(!on);
      });
    }
    if (new URLSearchParams(location.search).get("fps") === "1" && $("hud-fps-wrap")) {
      $("hud-fps-wrap").hidden = false;
    }
  }

  global.LancerHUD = {
    init: init,
    update: update,
    renderLeaders: renderLeaders,
    fps: function () { return global.LancerHUDCar ? LancerHUDCar.fps() : 0; }
  };
})(window);

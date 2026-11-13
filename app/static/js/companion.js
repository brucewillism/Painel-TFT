(function () {
  "use strict";
  var TOKEN = "lancer_token";
  var ACCENTS = [
    { id: "arc", hex: "#00D8FF", label: "Reator arc" },
    { id: "red", hex: "#E10600", label: "Vermelho" },
    { id: "matrix", hex: "#00FF6A", label: "Verde Matrix" },
    { id: "amber", hex: "#FFB000", label: "Âmbar" },
    { id: "violet", hex: "#B14CFF", label: "Roxo" },
    { id: "white", hex: "#F4FBFF", label: "Branco" },
  ];
  var CARS = [
    { hex: "#b1121a", label: "Vermelho" },
    { hex: "#1a1a1e", label: "Preto" },
    { hex: "#c0c4c8", label: "Prata" },
    { hex: "#f2f2f0", label: "Branco" },
    { hex: "#1c3a70", label: "Azul" },
    { hex: "#4a4e52", label: "Grafite" },
  ];
  var settings = { ui: {}, fuel: {} };
  var timer = null;

  function $(id) { return document.getElementById(id); }
  function token() { return localStorage.getItem(TOKEN) || ""; }
  function headers() {
    var h = { "Content-Type": "application/json" };
    if (token()) h.Authorization = "Bearer " + token();
    return h;
  }

  async function pair() {
    $("pin-err").hidden = true;
    var res = await fetch("/api/companion/auth", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: $("pin").value || "" }),
    });
    if (!res.ok) { $("pin-err").hidden = false; return; }
    var data = await res.json();
    localStorage.setItem(TOKEN, data.token);
    await enter();
  }

  async function enter() {
    if (!token()) { $("gate").hidden = false; $("app").hidden = true; return; }
    var res = await fetch("/api/settings", { headers: headers() });
    if (res.status === 401) { localStorage.removeItem(TOKEN); $("gate").hidden = false; $("app").hidden = true; return; }
    settings = await res.json();
    $("gate").hidden = true;
    $("app").hidden = false;
    fill();
    loadExtras();
  }

  function fill() {
    var ui = settings.ui || {};
    $("accent-hex").value = ui.accent_hex || "#00D8FF";
    $("car-color").value = ui.car_color || "#b1121a";
    if ($("theme")) $("theme").value = ui.theme === "classic" ? "classic" : "hud";
    if ($("hud-rotate")) $("hud-rotate").checked = ui.hud_rotate !== false;
    $("bright").value = ui.brightness || 80;
    $("bright-val").textContent = $("bright").value;
    $("night").value = ui.night_mode || "auto";
    $("perf").checked = !!ui.performance_mode;
    var g = ui.gauges || {};
    ["rpm","temp","volt","cvt","bars"].forEach(function (k) {
      var el = $("g-" + k);
      if (el) el.checked = g[k] == null ? true : !!g[k];
    });
    paintSwatches();
    document.documentElement.style.setProperty("--accent", $("accent-hex").value);
  }

  function paintSwatches() {
    $("presets").innerHTML = ACCENTS.map(function (a) {
      var on = ($("accent-hex").value || "").toLowerCase() === a.hex.toLowerCase() ? " on" : "";
      return '<button type="button" class="swatch' + on + '" data-id="' + a.id + '" data-hex="' + a.hex + '" style="--c:' + a.hex + '" title="' + a.label + '"></button>';
    }).join("");
    $("presets").querySelectorAll(".swatch").forEach(function (b) {
      b.addEventListener("click", function () {
        $("accent-hex").value = b.getAttribute("data-hex");
        settings.ui.accent = b.getAttribute("data-id");
        settings.ui.accent_hex = b.getAttribute("data-hex");
        push();
        paintSwatches();
      });
    });
    $("car-presets").innerHTML = CARS.map(function (a) {
      var on = ($("car-color").value || "").toLowerCase() === a.hex.toLowerCase() ? " on" : "";
      return '<button type="button" class="swatch' + on + '" data-hex="' + a.hex + '" style="--c:' + a.hex + '" title="' + a.label + '"></button>';
    }).join("");
    $("car-presets").querySelectorAll(".swatch").forEach(function (b) {
      b.addEventListener("click", function () {
        $("car-color").value = b.getAttribute("data-hex");
        push();
        paintSwatches();
      });
    });
  }

  function collect() {
    var hex = $("accent-hex").value;
    var known = ACCENTS.filter(function (a) { return a.hex.toLowerCase() === hex.toLowerCase(); })[0];
    return {
      ui: {
        theme: ($("theme") && $("theme").value) || "hud",
        accent: known ? known.id : "custom",
        accent_hex: hex,
        car_color: $("car-color").value,
        brightness: Number($("bright").value),
        night_mode: $("night").value,
        performance_mode: $("perf").checked,
        hud_rotate: $("hud-rotate") ? $("hud-rotate").checked : true,
        gauges: {
          rpm: $("g-rpm").checked,
          temp: $("g-temp").checked,
          volt: $("g-volt").checked,
          cvt: $("g-cvt").checked,
          bars: $("g-bars").checked
        }
      }
    };
  }

  function push() {
    document.documentElement.style.setProperty("--accent", $("accent-hex").value);
    $("bright-val").textContent = $("bright").value;
    clearTimeout(timer);
    timer = setTimeout(async function () {
      var res = await fetch("/api/settings", { method: "PUT", headers: headers(), body: JSON.stringify(collect()) });
      if (res.status === 401) { localStorage.removeItem(TOKEN); enter(); return; }
      if (res.ok) settings = await res.json();
    }, 160);
  }

  async function loadExtras() {
    try {
      var v = await (await fetch("/api/vehicle")).json();
      $("veh-line").textContent = (v.label || "Veículo") + (v.vin ? "  ·  " + v.vin : "");
      if ($("app-brand") && (v.make || v.model)) {
        $("app-brand").textContent = [v.make, v.model].filter(Boolean).join(" ").toUpperCase() || "PAINEL TFT";
      }
    } catch (e) {}
    try {
      var r = await (await fetch("/api/range")).json();
      var line = "Autonomia: " + (r.range_km != null ? Math.round(r.range_km) + " km" : "—");
      if (r.remaining_l != null) line += "  ·  " + r.remaining_l.toFixed(1) + " L";
      $("range-stat").textContent = line;
      $("range-note").textContent = r.traffic_note || "";
      var tank = r.tank_l || 50;
      $("btn-fill").textContent = "Marcar tanque cheio (" + tank + " L)";
    } catch (e) {}
    try {
      var s = await (await fetch("/api/companion/sun")).json();
      $("sun-hint").textContent = "Hoje o sol nasce às " + s.sunrise + " e se põe às " + s.sunset + " (America/Sao_Paulo).";
    } catch (e) {}
    try {
      var led = await (await fetch("/api/leds")).json();
      if ($("led-color") && led.static_color) $("led-color").value = led.static_color;
      if ($("led-bright") && led.brightness != null) {
        $("led-bright").value = Math.round(led.brightness * 100);
        $("led-bright-val").textContent = $("led-bright").value;
      }
      document.querySelectorAll("#led-modes button").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-mode") === led.mode);
      });
    } catch (e) {}
    try {
      var val = await (await fetch("/api/valet")).json();
      if ($("valet-line")) $("valet-line").textContent = val.active ? "TRAVADO — mídia, telefone e ajustes bloqueados no painel" : "destravado";
    } catch (e) {}
    try { await loadVehicle(); } catch (e) {}
  }

  async function loadVehicle() {
    if (!$("veh-profile")) return;
    var info = await (await fetch("/api/vehicle")).json();
    var plist = await (await fetch("/api/vehicle/profiles")).json();
    var sel = $("veh-profile");
    sel.innerHTML = (plist.profiles || []).map(function (p) {
      return '<option value="' + p.id + '">' + (p.name || p.id) + "</option>";
    }).join("");
    if (info.profile && info.profile.id) sel.value = info.profile.id;
    if (info.state && info.state.body) $("veh-body").value = info.state.body;
    if (info.photo && info.photo.attribution) $("photo-attr").textContent = info.photo.attribution;
    document.querySelectorAll("#art-modes button").forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-art") === ((info.state && info.state.art_mode) || "auto"));
    });
    if (info.photo && info.photo.ready) $("overlay-edits").hidden = false;
    if (info.photo && info.photo.zones && info.photo.zones.headlight) {
      var z = info.photo.zones;
      if ($("ov-hl-x")) $("ov-hl-x").value = Math.round((z.headlight.x || 0) * 100);
      if ($("ov-hl-y")) $("ov-hl-y").value = Math.round((z.headlight.y || 0) * 100);
      if ($("ov-tl-x")) $("ov-tl-x").value = Math.round((z.taillight.x || 0) * 100);
      if ($("ov-tl-y")) $("ov-tl-y").value = Math.round((z.taillight.y || 0) * 100);
    }
    window._vehInfo = info;
  }

  function postProfile(extra) {
    var body = Object.assign({
      id: $("veh-profile") ? $("veh-profile").value : "generic",
      body: $("veh-body") ? $("veh-body").value : undefined,
      paint: $("car-color") ? $("car-color").value : undefined,
      setup_completed: true,
    }, extra || {});
    return fetch("/api/vehicle/profile", { method: "POST", headers: Object.assign({"Content-Type":"application/json"}, headers()), body: JSON.stringify(body) });
  }

  function bind() {
    $("btn-pin").addEventListener("click", pair);
    $("pin").addEventListener("keydown", function (e) { if (e.key === "Enter") pair(); });
    ["accent-hex","car-color","bright","night","perf","theme","hud-rotate","g-rpm","g-temp","g-volt","g-cvt","g-bars"].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener("input", push);
      el.addEventListener("change", push);
    });
    function sendLeds(mode) {
      var body = {
        color: $("led-color") ? $("led-color").value : undefined,
        brightness: $("led-bright") ? Number($("led-bright").value) / 100 : undefined,
      };
      if (mode) body.mode = mode;
      fetch("/api/leds", { method: "POST", headers: Object.assign({"Content-Type":"application/json"}, headers()), body: JSON.stringify(body) });
    }
    document.querySelectorAll("#led-modes button").forEach(function (b) {
      b.addEventListener("click", function () { sendLeds(b.getAttribute("data-mode")); loadExtras(); });
    });
    if ($("led-color")) $("led-color").addEventListener("change", function () { sendLeds("static"); });
    if ($("led-bright")) $("led-bright").addEventListener("input", function () {
      $("led-bright-val").textContent = $("led-bright").value;
    });
    if ($("led-bright")) $("led-bright").addEventListener("change", function () { sendLeds(null); });
    if ($("veh-profile")) {
      $("veh-profile").addEventListener("change", function () { postProfile({}).then(loadVehicle); });
      $("veh-body").addEventListener("change", function () { postProfile({ body: $("veh-body").value }).then(loadVehicle); });
      document.querySelectorAll("#art-modes button").forEach(function (b) {
        b.addEventListener("click", function () { postProfile({ art_mode: b.getAttribute("data-art") }).then(loadVehicle); });
      });
      $("btn-detect").addEventListener("click", async function () {
        await fetch("/api/vehicle/detect", { method: "POST", headers: Object.assign({"Content-Type":"application/json"}, headers()), body: JSON.stringify({ online: true }) });
        loadExtras();
      });
      $("btn-photo-search").addEventListener("click", async function () {
        $("photo-cands").textContent = "Buscando…";
        var d = await (await fetch("/api/vehicle/photos/search", { method: "POST", headers: headers() })).json();
        var html = (d.candidates || []).slice(0, 5).map(function (c, i) {
          return '<button class="cand" data-i="' + i + '"><img src="' + c.url + '" alt=""><span>' +
            (c.title || ("foto " + (i + 1))) + "</span><small>" + (c.license || "") + "</small></button>";
        }).join("") || "Nenhuma foto encontrada.";
        $("photo-cands").innerHTML = html;
        $("photo-cands").querySelectorAll(".cand").forEach(function (b) {
          b.addEventListener("click", async function () {
            b.textContent = "Processando…";
            await fetch("/api/vehicle/photos/select", { method: "POST", headers: Object.assign({"Content-Type":"application/json"}, headers()), body: JSON.stringify({ index: Number(b.getAttribute("data-i")) }) });
            loadVehicle();
          });
        });
      });
      if ($("art-file")) $("art-file").addEventListener("change", async function () {
        if (!this.files || !this.files[0]) return;
        var fd = new FormData();
        fd.append("view", $("art-view").value);
        fd.append("file", this.files[0]);
        await fetch("/api/vehicle/art/upload", { method: "POST", headers: headers(), body: fd });
        loadVehicle();
      });
      if ($("btn-ov-save")) $("btn-ov-save").addEventListener("click", async function () {
        var info = window._vehInfo || {};
        var z = (info.photo && info.photo.zones) || { headlight: {w:0.1,h:0.12}, taillight: {w:0.1,h:0.12} };
        z.headlight = Object.assign({}, z.headlight, { x: $("ov-hl-x").value / 100, y: $("ov-hl-y").value / 100 });
        z.taillight = Object.assign({}, z.taillight, { x: $("ov-tl-x").value / 100, y: $("ov-tl-y").value / 100 });
        await fetch("/api/vehicle/overlays", { method: "PUT", headers: Object.assign({"Content-Type":"application/json"}, headers()), body: JSON.stringify({ zones: z }) });
      });
    }
    $("btn-fill").addEventListener("click", async function () {
      var res = await fetch("/api/fuel/fill", { method: "POST", headers: headers(), body: JSON.stringify({ full: true }) });
      if (res.ok) loadExtras();
    });
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).catch(function () {});
    }
  }

  bind();
  enter();
})();

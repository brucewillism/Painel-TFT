/* Telas extras: desempenho, pista, G, telemetria, dash cam, saúde, LEDs, TPMS, valet. */
(function (global) {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function fmtTime(s) {
    if (s == null || isNaN(s)) return "—";
    if (s < 60) return s.toFixed(3) + " s";
    var m = Math.floor(s / 60);
    var r = s - m * 60;
    return m + ":" + (r < 10 ? "0" : "") + r.toFixed(3);
  }
  function when(ts) {
    if (!ts) return "";
    try {
      return new Date(ts * 1000).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
    } catch (e) { return ""; }
  }
  var lastTelemId = null;
  var telemRows = [];
  var telemZoom = 1;
  var telemReview = null;
  var bound = false;

  function bind() {
    if (bound) return;
    bound = true;
    if ($("btn-sprint")) $("btn-sprint").onclick = function () { post("/api/sim/sprint"); };
    if ($("btn-perf-reset")) $("btn-perf-reset").onclick = function () { post("/api/perf/reset"); };
    if ($("btn-shift-save")) $("btn-shift-save").onclick = function () {
      var pts = ($("shift-pts").value || "").split(",").map(function (x) { return parseInt(x, 10); }).filter(Boolean);
      post("/api/shift", { points: pts });
    };
    if ($("btn-gate-here")) $("btn-gate-here").onclick = function () { post("/api/track/gate", { here: true }); };
    if ($("btn-gate-map")) $("btn-gate-map").onclick = function () {
      window._lancerPickGate = function (lat, lon) {
        post("/api/track/gate", { lat: lat, lon: lon });
        if (window.LancerUI) LancerUI.showPage("track");
      };
      if (window.LancerUI) LancerUI.showPage("map");
    };
    if ($("btn-track-start")) $("btn-track-start").onclick = function () { post("/api/track/start", { name: "Sessão" }); };
    if ($("btn-track-stop")) $("btn-track-stop").onclick = function () { post("/api/track/stop"); };
    if ($("track-canvas")) $("track-canvas").addEventListener("click", function (ev) {
      /* o canvas é um traçado, não um mapa geográfico — o portão 'aqui' usa GPS */
    });
    if ($("btn-g-reset")) $("btn-g-reset").onclick = function () { post("/api/gforce/reset"); };
    if ($("btn-g-cal")) $("btn-g-cal").onclick = function () { post("/api/gforce/calibrate"); };
    if ($("btn-telem-start")) $("btn-telem-start").onclick = function () {
      var hz = parseFloat($("telem-hz").value) || 10;
      post("/api/telemetry/start", { hz: hz, name: "Log" });
    };
    if ($("btn-telem-stop")) $("btn-telem-stop").onclick = function () { post("/api/telemetry/stop"); };
    if ($("telem-chart") && !$("telem-chart").dataset.zoom) {
      $("telem-chart").dataset.zoom = "1";
      $("telem-chart").addEventListener("wheel", function (e) {
        e.preventDefault();
        telemZoom = Math.max(0.6, Math.min(8, telemZoom * (e.deltaY > 0 ? 0.85 : 1.18)));
      }, { passive: false });
    }

    if ($("btn-dash-start")) $("btn-dash-start").onclick = function () { post("/api/dashcam/start", {}); };
    if ($("btn-dash-stop")) $("btn-dash-stop").onclick = function () { post("/api/dashcam/stop"); };
    if ($("btn-dash-protect")) $("btn-dash-protect").onclick = function () { post("/api/dashcam/protect"); };
    if ($("btn-odo")) $("btn-odo").onclick = function () {
      var km = parseFloat($("odo-input").value);
      if (!isNaN(km)) post("/api/health/odometer", { km: km });
    };
    if ($("led-modes")) {
      $("led-modes").querySelectorAll("button[data-mode]").forEach(function (b) {
        b.addEventListener("click", function () { sendLeds(b.getAttribute("data-mode")); });
      });
      $("led-color").addEventListener("change", function () { sendLeds("static"); });
      $("led-bright").addEventListener("change", function () { sendLeds(null); });
    }
    if ($("btn-valet-lock")) $("btn-valet-lock").onclick = function () { post("/api/valet/lock", {}); };
    if ($("btn-valet-unlock")) $("btn-valet-unlock").onclick = function () {
      post("/api/valet/unlock", { pin: $("valet-pin").value || "" }).then(function (d) {
        if (d && d.report) renderValetReport(d.report);
        if (d && d.error) alert(d.error);
      });
    };
  }

  function sendLeds(mode) {
    post("/api/leds", {
      mode: mode || undefined,
      color: $("led-color") ? $("led-color").value : undefined,
      brightness: $("led-bright") ? ($("led-bright").value / 100) : undefined,
    });
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : "{}",
    }).then(function (r) { return r.json(); }).catch(function () { return {}; });
  }

  function renderPerf(meta) {
    var p = meta.perf; if (!p || !$("perf-cards")) return;
    var kinds = [
      ["0-100", "0–100"],
      ["80-120", "80–120"],
      ["402m", "402 m"],
      ["100-0", "100–0"],
    ];
    $("perf-src").textContent = (meta.fuse && meta.fuse.source) ? ("vel. " + meta.fuse.source) : "GPS + OBD";
    $("perf-cards").innerHTML = kinds.map(function (row) {
      var r = (p.runs || {})[row[0]] || {};
      var best = (p.best || {})[row[0]];
      var st = r.state || "idle";
      var t = r.time_s != null ? r.time_s : null;
      return '<div class="cardx ' + st + '"><div class="k">' + row[1] +
        ' <span class="st-pill' + (st === "running" || st === "armed" ? " on" : "") + '">' + st + "</span></div>" +
        '<div class="v">' + (t != null ? t.toFixed(2) : "—") + '</div><div class="u">s</div>' +
        '<div class="best">melhor ' + (best && best.time_s != null ? best.time_s.toFixed(2) + " s" : "—") + "</div></div>";
    }).join("");
    if (p.best && $("perf-hist") && !$("perf-hist").dataset.loaded) {
      fetch("/api/perf").then(function (r) { return r.json(); }).then(function (d) {
        var list = d.history || [];
        $("perf-hist").dataset.loaded = "1";
        $("perf-hist").innerHTML = list.slice(0, 8).map(function (h) {
          return "<li><span>" + h.kind + " · " + (h.time_s != null ? Number(h.time_s).toFixed(2) + " s" : "—") +
            "</span><span>" + when(h.started_at) + "</span></li>";
        }).join("") || "<li>Sem histórico ainda.</li>";
      }).catch(function () {});
    }
  }

  function renderShift(meta) {
    var s = meta.shift;
    if (!s || !$("shift-pts-label")) return;
    $("shift-pts-label").textContent = (s.points || []).join(" / ");
  }

  function renderTrack(meta) {
    var t = meta.track; if (!t || !$("track-lap")) return;
    $("track-lap").textContent = t.lap || 0;
    $("track-time").textContent = t.elapsed_s != null ? fmtTime(t.elapsed_s) : "0:00.000";
    $("track-best").textContent = t.best_s != null ? fmtTime(t.best_s) : "—";
    var d = t.delta_s;
    var el = $("track-delta");
    if (d == null) {
      el.textContent = "Δ —";
      el.className = "delta-val";
    } else {
      el.textContent = (d >= 0 ? "+" : "") + d.toFixed(2);
      el.className = "delta-val " + (d <= 0 ? "better" : "worse");
    }
    var needle = $("delta-needle");
    if (needle) {
      var pct = 50 + Math.max(-45, Math.min(45, (d || 0) * 12));
      needle.style.left = pct + "%";
      $("delta-bar").classList.toggle("worse", d != null && d > 0);
    }
    drawTrace(t.trace || []);
  }

  function drawTrace(pts) {
    var c = $("track-canvas"); if (!c) return;
    var ctx = c.getContext("2d");
    var w = c.width, h = c.height;
    ctx.fillStyle = "#0a0404";
    ctx.fillRect(0, 0, w, h);
    if (!pts.length) {
      ctx.fillStyle = "#663";
      ctx.font = "12px Rajdhani, sans-serif";
      ctx.fillText("Toque em “Portão aqui” no ponto de largada/chegada, ou defina no mapa.", 16, h / 2);
      return;
    }
    var lats = pts.map(function (p) { return p.lat; });
    var lons = pts.map(function (p) { return p.lon; });
    var minLat = Math.min.apply(null, lats), maxLat = Math.max.apply(null, lats);
    var minLon = Math.min.apply(null, lons), maxLon = Math.max.apply(null, lons);
    var pad = 16;
    function xy(p) {
      var x = pad + ((p.lon - minLon) / (maxLon - minLon || 1e-6)) * (w - pad * 2);
      var y = pad + (1 - (p.lat - minLat) / (maxLat - minLat || 1e-6)) * (h - pad * 2);
      return [x, y];
    }
    ctx.strokeStyle = "#e10600";
    ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach(function (p, i) {
      var pt = xy(p);
      if (i === 0) ctx.moveTo(pt[0], pt[1]); else ctx.lineTo(pt[0], pt[1]);
    });
    ctx.stroke();
    var last = xy(pts[pts.length - 1]);
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(last[0], last[1], 4, 0, Math.PI * 2); ctx.fill();
  }

  function renderG(meta) {
    var g = meta.gforce; if (!g || !$("gforce-canvas")) return;
    $("gforce-src").textContent = "fonte: " + (g.source || "gps") + (g.chip ? " · " + g.chip : "");
    $("g-ax").textContent = (g.ax || 0).toFixed(2);
    $("g-ay").textContent = (g.ay || 0).toFixed(2);
    $("g-peaks").textContent = "lon " + (g.peak_lon || 0).toFixed(2) + " · lat " + (g.peak_lat || 0).toFixed(2);
    var c = $("gforce-canvas");
    var ctx = c.getContext("2d");
    var w = c.width, h = c.height, cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 16;
    ctx.fillStyle = "#0a0404";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#3a1515";
    ctx.lineWidth = 1;
    [0.25, 0.5, 0.75, 1].forEach(function (f) {
      ctx.beginPath(); ctx.arc(cx, cy, R * f, 0, Math.PI * 2); ctx.stroke();
    });
    ctx.beginPath(); ctx.moveTo(cx - R, cy); ctx.lineTo(cx + R, cy);
    ctx.moveTo(cx, cy - R); ctx.lineTo(cx, cy + R); ctx.stroke();
    ctx.fillStyle = "#664";
    ctx.font = "10px Rajdhani, sans-serif";
    ctx.fillText("FRENAGEM", cx - 28, cy - R + 12);
    ctx.fillText("ACELERA", cx - 24, cy + R - 4);
    ctx.fillText("ESQ", 8, cy + 4);
    ctx.fillText("DIR", w - 24, cy + 4);
    var trail = g.trail || [];
    trail.forEach(function (p, i) {
      var x = cx + (p[0] || 0) * R; // lat
      var y = cy + (p[1] || 0) * R; // lon (frente = baixo da tela? acelera +ay wait: ay lat, ax lon)
      ctx.fillStyle = "rgba(225,6,0," + (0.15 + 0.7 * i / trail.length) + ")";
      ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
    });
    var px = cx + (g.ay || 0) * R;
    var py = cy + (g.ax || 0) * R;
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#e10600"; ctx.lineWidth = 2; ctx.stroke();
  }

  function renderTelem(meta) {
    var t = meta.telemetry; if (!t || !$("telem-stat")) return;
    $("telem-stat").textContent = t.running
      ? ("gravando · " + (t.samples || 0) + " amostras · " + (t.hz || 10) + " Hz")
      : "parado";
    if (t.running && t.session_id && t.session_id !== lastTelemId) {
      lastTelemId = t.session_id;
    }
    // gráfico ao vivo a partir dos sinais do snapshot
  }

  function drawTelemLive(snap) {
    var c = $("telem-chart"); if (!c) return;
    var sig = snap.signals || {};
    function v(k) { return sig[k] && sig[k].value != null ? Number(sig[k].value) : 0; }
    telemRows.push({ spd: v("speed_fused") || v("speed"), rpm: v("rpm"), g: Math.abs(v("g_lon")) + Math.abs(v("g_lat")) });
    if (telemRows.length > 240) telemRows.shift();
    var ctx = c.getContext("2d");
    var w = c.width, h = c.height;
    ctx.fillStyle = "#0a0404"; ctx.fillRect(0, 0, w, h);
    function line(key, color, max) {
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
      telemRows.forEach(function (r, i) {
        var x = (i / Math.max(1, telemRows.length - 1)) * w;
        var y = h - (r[key] / max) * (h - 8) - 4;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
    }
    var maxS = 80, maxR = 2500, maxG = 0.5;
    telemRows.forEach(function (r) {
      if (r.spd > maxS) maxS = r.spd;
      if (r.rpm > maxR) maxR = r.rpm;
      if (r.g > maxG) maxG = r.g;
    });
    var z = telemZoom || 1;
    line("spd", "#e10600", (maxS * 1.15) / z);
    line("rpm", "#ff8a00", (maxR * 1.15) / z);
    line("g", "#6af", (maxG * 1.4) / z);
    // mini traçado GPS à direita, se houver
    if (telemReview && telemReview.length) {
      var pts = telemReview.filter(function (r) { return r.gps_lat && r.gps_lon; });
      if (pts.length > 2) {
        var lats = pts.map(function (r) { return Number(r.gps_lat); });
        var lons = pts.map(function (r) { return Number(r.gps_lon); });
        var mina = Math.min.apply(null, lats), maxa = Math.max.apply(null, lats);
        var mino = Math.min.apply(null, lons), maxo = Math.max.apply(null, lons);
        var x0 = w * 0.72, y0 = 24, ww = w * 0.26, hh = h - 36;
        ctx.strokeStyle = "#3a1515"; ctx.strokeRect(x0, y0, ww, hh);
        ctx.strokeStyle = "#e10600"; ctx.beginPath();
        pts.forEach(function (r, i) {
          var x = x0 + 4 + ((Number(r.gps_lon) - mino) / (maxo - mino || 1e-6)) * (ww - 8);
          var y = y0 + 4 + (1 - (Number(r.gps_lat) - mina) / (maxa - mina || 1e-6)) * (hh - 8);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });
        ctx.stroke();
      }
    }
    ctx.fillStyle = "#866"; ctx.font = "11px Rajdhani, sans-serif";
    ctx.fillText("vermelho vel.  ·  laranja rpm  ·  azul |G|  — pinça/zoom na revisão CSV", 8, 14);
  }

  function loadTelemSessions() {
    var box = $("telem-sess"); if (!box || box.dataset.loaded) return;
    fetch("/api/telemetry").then(function (r) { return r.json(); }).then(function (d) {
      box.dataset.loaded = "1";
      box.innerHTML = (d.sessions || []).map(function (s) {
        return "<li><span>" + (s.name || ("Log " + s.id)) + " · " + (s.samples || 0) + " am. · " + (s.hz || "") + " Hz</span>" +
          (s.path ? '<a class="btn" href="/api/telemetry/' + s.id + '/csv">CSV</a>' : "") + "</li>";
      }).join("") || "<li>Nenhuma sessão ainda.</li>";
    }).catch(function () {});
  }

  function renderDash(meta) {
    var d = meta.dashcam; if (!d || !$("dash-stat")) return;
    $("dash-stat").textContent = (d.running ? "gravando" : "parada") +
      " · " + (d.used_mb || 0) + " MB / " + (d.max_gb || 8) + " GB" +
      (d.ffmpeg ? "" : " · ffmpeg ausente (stub)");
    var sig = (global.LancerUI && global.LancerUI.lastSnap && global.LancerUI.lastSnap.signals) || {};
    function num(k, d) {
      var x = sig[k] && sig[k].value;
      if (x == null || isNaN(Number(x))) return d;
      return Number(x);
    }
    if ($("dash-overlay")) {
      var spd = num("speed_fused", num("speed", 0));
      var lat = num("gps_lat", null), lon = num("gps_lon", null);
      $("dash-overlay").textContent = spd.toFixed(0) + " km/h   " + num("rpm", 0).toFixed(0) +
        " rpm   G " + num("g_lon", 0).toFixed(2) + " / " + num("g_lat", 0).toFixed(2) +
        "   GPS " + (lat != null && lon != null ? lat.toFixed(5) + ", " + lon.toFixed(5) : "—");
    }
  }

  function loadClips() {
    var box = $("dash-clips"); if (!box || box.dataset.tick && Date.now() - box.dataset.tick < 4000) return;
    box.dataset.tick = Date.now();
    fetch("/api/dashcam").then(function (r) { return r.json(); }).then(function (d) {
      box.innerHTML = (d.clips || []).map(function (c) {
        var name = (c.path || "").split("/").pop();
        return "<li><span>" + name + (c.protected ? ' <span class="prot">PROTEGIDO</span>' : "") +
          (c.reason ? " · " + c.reason : "") + "</span>" +
          (c.exists ? '<a class="btn" href="/api/dashcam/' + c.id + '/file">abrir</a>' : "") + "</li>";
      }).join("") || "<li>Nenhum clipe.</li>";
    }).catch(function () {});
  }

  function renderHealth(meta) {
    var h = meta.health; if (!h || !$("odo-km")) return;
    var odo = (h.odometer || {}).total_km;
    $("odo-km").textContent = odo != null ? Number(odo).toFixed(1) : "—";
    var b = h.battery || {};
    $("batt-line").textContent = "partida " + (b.last_crank != null ? Number(b.last_crank).toFixed(1) + " V" : "—") +
      " · repouso " + (b.last_rest != null ? Number(b.last_rest).toFixed(2) + " V" : "—") +
      " · tendência " + (b.trend || "—");
    $("batt-warn").textContent = b.warning || "";
    var list = $("svc-list");
    if (list) {
      list.innerHTML = (h.items || []).map(function (it) {
        return '<li class="' + (it.status || "") + '"><span>' + it.name +
          "</span><span>" + (it.due_km != null ? (it.due_km <= 0 ? "atrasado " + Math.abs(it.due_km).toFixed(0) + " km" : "falta " + it.due_km.toFixed(0) + " km") : "") +
          ' <button class="btn" data-svc="' + it.item_id + '">Feito</button></span></li>';
      }).join("");
      list.querySelectorAll("[data-svc]").forEach(function (b) {
        b.onclick = function () { post("/api/health/service", { item_id: b.getAttribute("data-svc") }); };
      });
    }
    var dh = $("dtc-hist");
    if (dh && (h.open_dtcs || []).length) {
      dh.innerHTML = h.open_dtcs.map(function (d) {
        return "<li><span>" + d.code + (d.description ? " · " + d.description : "") +
          (d.cleared_at ? " (apagado)" : "") + "</span><span>" + when(d.last_seen) + "</span></li>";
      }).join("");
    }
  }

  function renderLeds(meta) {
    var l = meta.leds; if (!l || !$("led-strip")) return;
    $("led-hw").textContent = l.hw ? ("GPIO " + l.pin + " · " + l.count + " LEDs") : "preview (sem rpi_ws281x)";
    var c = $("led-strip"), ctx = c.getContext("2d");
    var w = c.width, h = c.height, n = l.count || 30;
    ctx.fillStyle = "#0a0404"; ctx.fillRect(0, 0, w, h);
    var pix = l.pixels || [];
    var bw = w / n;
    pix.forEach(function (p, i) {
      ctx.fillStyle = "rgb(" + (p[0] || 0) + "," + (p[1] || 0) + "," + (p[2] || 0) + ")";
      ctx.fillRect(i * bw + 1, 4, Math.max(2, bw - 2), h - 8);
    });
    if ($("led-modes")) {
      $("led-modes").querySelectorAll("button[data-mode]").forEach(function (b) {
        b.classList.toggle("active", b.getAttribute("data-mode") === l.mode);
      });
    }
  }

  function renderTpms(meta) {
    var t = meta.tpms; if (!t || !$("tpms-row")) return;
    var names = { fl: "D. esq.", fr: "D. dir.", rl: "T. esq.", rr: "T. dir." };
    $("tpms-row").innerHTML = ["fl", "fr", "rl", "rr"].map(function (w) {
      var rec = (t.wheels || {})[w];
      if (!rec) return '<div class="tpms-cell"><div class="w">' + names[w] + '</div><div class="p">—</div></div>';
      var kpa = rec.kpa != null ? Number(rec.kpa).toFixed(0) : "—";
      var psi = rec.psi != null ? Number(rec.psi).toFixed(1) : "";
      var temp = rec.temp_c != null ? Number(rec.temp_c).toFixed(0) + " °C" : "";
      return '<div class="tpms-cell' + (rec.alert ? " alert" : "") + '"><div class="w">' + names[w] +
        (rec.alert ? " · " + rec.alert : "") + '</div><div class="p">' + kpa + ' kPa</div>' +
        '<div class="t">' + psi + " psi · " + temp + "</div></div>";
    }).join("");
  }

  function renderValet(meta) {
    var v = meta.valet; if (!v || !$("valet-state")) return;
    $("valet-state").textContent = v.active ? "TRAVADO" : "destravado";
    $("valet-vmax").textContent = v.max_speed != null ? Number(v.max_speed).toFixed(0) : "—";
    $("valet-ev").textContent = v.events != null ? v.events : 0;
    document.body.classList.toggle("valet-on", !!v.active);
    if (v.last_report && !v.active) renderValetReport(v.last_report);
  }

  function renderValetReport(r) {
    var el = $("valet-report"); if (!el || !r) return;
    var min = r.duration_s != null ? (r.duration_s / 60).toFixed(1) : "—";
    el.innerHTML = "<strong>Relatório do valet</strong><br>" +
      "Duração: " + min + " min · Distância: " + (r.distance_km != null ? r.distance_km.toFixed(2) : "—") + " km<br>" +
      "Velocidade máxima: " + (r.max_speed != null ? r.max_speed.toFixed(1) : "—") + " km/h<br>" +
      "Eventos bruscos: " + (r.event_count || 0) +
      ((r.events || []).length ? " (" + r.events.map(function (e) { return e.kind; }).join(", ") + ")" : "");
  }

  var sessLoaded = false;
  function maybeLists(page) {
    if (page === "telemetry") loadTelemSessions();
    if (page === "dashcam") loadClips();
    if (page === "track" && !sessLoaded) {
      sessLoaded = true;
      fetch("/api/track").then(function (r) { return r.json(); }).then(function (d) {
        var box = $("track-sess"); if (!box) return;
        box.innerHTML = (d.sessions || []).map(function (s) {
          return "<li><span>" + (s.name || "Sessão") + " · " + (s.laps || 0) + " voltas · melhor " +
            (s.best_lap_s != null ? fmtTime(s.best_lap_s) : "—") + "</span><span>" + when(s.started_at) + "</span></li>";
        }).join("");
      }).catch(function () {});
    }
    if (page === "perf" && $("perf-hist")) $("perf-hist").dataset.loaded = "";
  }

  function update(snap) {
    bind();
    var meta = (snap && snap.meta) || {};
    renderPerf(meta);
    renderShift(meta);
    renderTrack(meta);
    renderG(meta);
    renderTelem(meta);
    drawTelemLive(snap || {});
    renderDash(meta);
    renderHealth(meta);
    renderLeds(meta);
    renderTpms(meta);
    renderValet(meta);
  }

  global.LancerExtras = { update: update, maybeLists: maybeLists, restricted: function (name, snap) {
    var v = snap && snap.meta && snap.meta.valet;
    if (!v || !v.active) return false;
    return (v.restricted || ["media", "phone", "carplay", "radio", "settings"]).indexOf(name) >= 0;
  } };
})(window);

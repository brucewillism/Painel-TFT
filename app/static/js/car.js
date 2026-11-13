/* Arte do carro: ilustração PNG por tipo de carroceria, foto recortada, ou SVG de reserva. */
(function (global) {
  "use strict";

  var sideHost = null;
  var topHost = null;
  var introHost = null;
  var sideSvg = "";
  var topSvg = "";
  var mode = "vector";
  var zones = null;
  var attribution = "";
  var lastArtRev = -1;
  var lastBody = "";

  function $(id) { return document.getElementById(id); }

  function mountSvg(host, svg, extraClass) {
    if (!host) return;
    host.classList.remove("photo-mode");
    host.innerHTML = svg;
    var root = host.querySelector("svg");
    if (root && extraClass) root.classList.add(extraClass);
  }

  function applyTo(host, cls, on) {
    if (!host) return;
    var root = host.querySelector("svg") || host;
    root.classList.toggle(cls, !!on);
    host.classList.toggle(cls, !!on);
  }

  function setSpin(host, speed) {
    if (!host) return;
    var moving = (speed || 0) > 1;
    applyTo(host, "car-moving", moving);
    host.querySelectorAll(".spokes, .photo-wheel").forEach(function (sp) {
      if (!moving) {
        sp.style.animationDuration = "";
        return;
      }
      var sec = Math.max(0.18, Math.min(2.2, 18 / speed));
      sp.style.animationDuration = sec + "s";
    });
  }

  function paintColor() {
    return getComputedStyle(document.body).getPropertyValue("--car-paint").trim() || "#b1121a";
  }

  function mountPhoto(host, url, z, opts) {
    if (!host) return;
    host.classList.add("photo-mode");
    var tint = opts && opts.tint;
    var sideOn = z && z.side_on && z.wheels_confident;
    var wheels = (sideOn && z.wheels && z.wheels.length === 2) ? z.wheels : [];
    var ar = (z && z.image && z.image.w && z.image.h) ? (z.image.w / z.image.h) : (z && z.aspect);
    var html = '<div class="photo-stage"><div class="photo-fit"><div class="photo-stack"' +
      (ar ? ' style="--car-ar:' + ar + '"' : '') + '>';
    html += '<img class="car-photo" alt="' + (tint ? "Ilustração do veículo" : "Foto do veículo") + '" src="' + url + '">';
    if (tint) {
      html += '<div class="photo-paint" style="mask-image:url(\'' + url + '\');-webkit-mask-image:url(\'' + url + '\')"></div>';
    }
    html += '<div class="photo-overlays" style="mask-image:url(\'' + url + '\');-webkit-mask-image:url(\'' + url + '\')">';
    function box(cls, b) {
      if (!b) return "";
      return '<div class="' + cls + '" style="left:' + (b.x * 100) + "%;top:" + (b.y * 100) +
        "%;width:" + (b.w * 100) + "%;height:" + (b.h * 100) + '%"></div>';
    }
    html += box("photo-hl headlight-beam", z && z.headlight);
    html += box("photo-tl brake-light", z && z.taillight);
    html += box("photo-turn turn-fl", z && z.turn_fl);
    html += box("photo-turn turn-rl", z && z.turn_rl);
    wheels.forEach(function (w, i) {
      var size = (w.r ? w.r * 2 : 0.18) * 100;
      var left = (w.x * 100) - size / 2;
      var rh = w.r_h ? w.r_h * 100 : size / 2;
      var top = (w.y * 100) - rh;
      html += '<div class="photo-wheel' + (i === 0 ? " wheel-front" : " wheel-rear") +
        '" style="left:' + left + "%;top:" + top + "%;width:" + size + '%;aspect-ratio:1">' +
        '<span class="spokes"></span></div>';
    });
    html += "</div></div></div></div>";
    host.innerHTML = html;
  }

  function credit(text) {
    var el = $("car-photo-credit");
    if (!el) return;
    if (text) {
      el.hidden = false;
      el.textContent = text;
    } else {
      el.hidden = true;
      el.textContent = "";
    }
  }

  function load() {
    return fetch("/api/vehicle").then(function (r) { return r.json(); }).then(function (info) {
      var body = (info.state && info.state.body) || (info.profile && info.profile.body) || "sedan";
      var artMode = (info.state && info.state.art_mode) || "auto";
      var photoReady = info.photo && info.photo.ready;
      var paint = (info.state && info.state.paint) || paintColor();
      document.body.style.setProperty("--car-paint", paint);
      lastBody = body;
      var usePhoto = (artMode === "photo" || artMode === "auto") && photoReady;
      var illus = info.illustration;
      var useIllus = !usePhoto && illus && illus.ready && artMode !== "custom";
      mode = usePhoto ? "photo" : (useIllus ? "illustration" : "vector");
      zones = usePhoto ? ((info.photo && info.photo.zones) || null)
            : (useIllus ? (illus.zones || null) : null);
      if (usePhoto && info.photo && info.photo.attribution) {
        attribution = "Foto: " + info.photo.attribution;
        credit(attribution);
      } else {
        attribution = "";
        credit("");
      }
      var bust = Date.now();
      var topUrl = "/api/vehicle/art/top?body=" + encodeURIComponent(body) + "&mode=" +
        (artMode === "custom" ? "custom" : "vector") + "&t=" + bust;
      function mountTopSvg() {
        return fetch(topUrl).then(function (r) { return r.text(); }).then(function (svg) {
          topSvg = svg;
          if (topHost) mountSvg(topHost, topSvg);
        });
      }
      if (usePhoto) {
        mountPhoto(sideHost, "/api/vehicle/art/side?t=" + bust, zones);
        if (introHost) mountPhoto(introHost, "/api/vehicle/art/side?t=" + bust, zones);
        return mountTopSvg();
      }
      if (useIllus) {
        var illUrl = "/api/vehicle/art/side?body=" + encodeURIComponent(body) + "&mode=vector&t=" + bust;
        mountPhoto(sideHost, illUrl, zones, {tint: true});
        if (introHost) mountPhoto(introHost, illUrl, zones, {tint: true});
        return mountTopSvg();
      }
      return Promise.all([
        fetch("/api/vehicle/art/side?body=" + encodeURIComponent(body) + "&mode=" + (artMode === "custom" ? "custom" : "vector") + "&t=" + bust).then(function (r) { return r.text(); }),
        fetch(topUrl).then(function (r) { return r.text(); }),
      ]).then(function (parts) {
        sideSvg = parts[0];
        topSvg = parts[1];
        if (sideHost) mountSvg(sideHost, sideSvg);
        if (topHost) mountSvg(topHost, topSvg);
        if (introHost) mountSvg(introHost, sideSvg);
      });
    }).catch(function () {
      // fallback estático: ilustração PNG, depois SVG
      return fetch("/static/img/bodies/sedan.json").then(function (r) {
        return r.ok ? r.json() : null;
      }).then(function (meta) {
        if (meta && meta.zones) {
          mountPhoto(sideHost, "/static/img/bodies/sedan.png", meta.zones, {tint: true});
          if (introHost) mountPhoto(introHost, "/static/img/bodies/sedan.png", meta.zones, {tint: true});
          return fetch("/static/img/bodies/sedan-top.svg").then(function (r) { return r.text(); })
            .then(function (svg) { topSvg = svg; if (topHost) mountSvg(topHost, svg); });
        }
        return Promise.all([
          fetch("/static/img/bodies/sedan.svg").then(function (r) { return r.text(); }),
          fetch("/static/img/bodies/sedan-top.svg").then(function (r) { return r.text(); }),
        ]).then(function (parts) {
          sideSvg = parts[0]; topSvg = parts[1];
          if (sideHost) mountSvg(sideHost, sideSvg);
          if (topHost) mountSvg(topHost, topSvg);
          if (introHost) mountSvg(introHost, sideSvg);
        });
      });
    });
  }

  function mount(sideEl, topEl) {
    sideHost = sideEl;
    topHost = topEl;
    return load();
  }

  function mountIntro(el) {
    introHost = el;
    return load();
  }

  function introOn() {
    [introHost, sideHost].forEach(function (h) {
      applyTo(h, "lights-on", true);
      applyTo(h, "car-moving", true);
      if (h) h.querySelectorAll(".spokes").forEach(function (sp) {
        sp.style.animationDuration = "0.6s";
      });
    });
  }

  function update(snap) {
    if (!snap) return;
    var rev = snap.meta && snap.meta.art_rev;
    var body = snap.meta && snap.meta.body;
    if ((rev != null && rev !== lastArtRev) || (body && body !== lastBody && lastArtRev !== -1)) {
      lastArtRev = rev == null ? lastArtRev : rev;
      load();
    } else if (rev != null) {
      lastArtRev = rev;
    }
    function v(key, def) {
      var s = snap.signals && snap.signals[key];
      return s && s.value != null ? s.value : def;
    }
    var speed = v("speed_fused", null);
    if (speed == null) speed = v("speed", 0) || 0;
    var lights = !!v("headlights", 0);
    var brake = !!v("brake", 0);
    var tl = !!v("turn_left", 0);
    var tr = !!v("turn_right", 0);
    var accel = v("accel_state", 0) || 0;
    var alerts = (snap.meta && snap.meta.alerts) || [];
    var ids = {};
    alerts.forEach(function (a) { ids[a.id] = a; });

    [sideHost, introHost].forEach(function (h) {
      applyTo(h, "lights-on", lights);
      applyTo(h, "brake-on", brake);
      applyTo(h, "turn-left", tl);
      applyTo(h, "turn-right", tr);
      setSpin(h, speed);
    });
    if (topHost) {
      applyTo(topHost, "lights-on", lights);
      applyTo(topHost, "brake-on", brake);
      applyTo(topHost, "turn-left", tl);
      applyTo(topHost, "turn-right", tr);
      var svg = topHost.querySelector("svg");
      if (svg) {
        var eng = svg.querySelector(".zone-engine");
        var bat = svg.querySelector(".zone-battery");
        var cvt = svg.querySelector(".zone-cvt, .zone-trans");
        if (eng) eng.classList.toggle("hot", !!(ids.coolant_high || ids.coolant_temp_high));
        if (bat) bat.classList.toggle("hot", !!(ids.voltage_low || ids.voltage_high));
        if (cvt) cvt.classList.toggle("hot", !!(ids.cvt_temp_high || ids.trans_temp_high));
      }
    }
    if (sideHost) {
      sideHost.classList.toggle("tilt-fwd", accel > 0.15);
      sideHost.classList.toggle("tilt-back", accel < -0.15);
    }
    var box = $("car-alerts");
    if (box) {
      var transHot = !!ids.cvt_temp_high || !!ids.trans_temp_high;
      var tags = [
        { on: lights, t: "FARÓIS" },
        { on: brake, t: "FREIO" },
        { on: tl, t: "SETA ESQ." },
        { on: tr, t: "SETA DIR." },
        { on: speed > 1, t: Math.round(speed) + " km/h" },
        { on: !!ids.coolant_high || !!ids.coolant_temp_high, t: "MOTOR QUENTE" },
        { on: !!ids.voltage_low, t: "BATERIA BAIXA" },
        { on: transHot, t: "CÂMBIO QUENTE" },
      ];
      box.innerHTML = tags.map(function (x) {
        return '<span class="tag' + (x.on ? " on" : "") + '">' + x.t + "</span>";
      }).join("");
    }
  }

  global.LancerCar = { mount: mount, mountIntro: mountIntro, introOn: introOn, update: update, load: load, reload: load };
})(window);

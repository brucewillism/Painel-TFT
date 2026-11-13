/* Assistente de primeiro uso: perfil, cor e arte do carro. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  var step = 0;
  var profiles = [];
  var chosen = null;
  var paint = "#b1121a";
  var detect = null;
  var params = new URLSearchParams(location.search);
  var force = params.get("setup") === "1";

  function show(on) {
    var el = $("setup-wizard");
    if (!el) return;
    el.hidden = !on;
  }

  function render() {
    var titles = ["Bem-vindo", "Identificar", "Perfil", "Aparência"];
    var leads = [
      "Este painel funciona com qualquer carro. O Lancer 2016 é só um dos perfis de exemplo.",
      "Lemos o VIN na ECU (Mode 09) e tentamos casar com um perfil. Você pode escolher à mão.",
      "Escolha o perfil mais próximo — tanque, câmbio, revisões e a silhueta vêm dele. Depois você pode ajustar.",
      "Cor da pintura e arte: silhueta do tipo de carroceria, ou uma foto real do modelo (Commons, licença livre)."
    ];
    $("wiz-step").textContent = "PASSO " + (step + 1) + " DE 4";
    $("wiz-title").textContent = titles[step].toUpperCase();
    $("wiz-lead").textContent = leads[step];
    $("wiz-back").hidden = step === 0;
    $("wiz-skip").hidden = step === 3;
    $("wiz-next").textContent = step === 3 ? "Concluir" : "Continuar";
    var body = $("wiz-body");
    if (step === 0) {
      body.innerHTML = '<p>Na próxima etapa tentamos ler o VIN. Se o clone ELM327 não responder Mode 09, escolha o modelo na lista.</p>';
    } else if (step === 1) {
      body.innerHTML = '<p id="wiz-detect">Lendo VIN…</p>';
      fetch("/api/vehicle/detect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ online: true }) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          detect = d;
          var idn = d.identity || {};
          var sug = d.suggested;
          var html = "<p>VIN: <strong>" + (idn.vin || "não lido") + "</strong><br>" +
            (idn.label || "modelo não identificado") +
            (idn.source ? " <span class='meta'>(" + idn.source + ")</span>" : "") + "</p>";
          if (sug) {
            html += "<p>Perfil sugerido: <strong>" + sug.name + "</strong> (" + (sug.body || "") + ").</p>";
            chosen = sug.id;
          } else {
            html += "<p>Nenhum perfil automático. Escolha na lista a seguir.</p>";
          }
          $("wiz-detect").outerHTML = html;
        })
        .catch(function () { body.innerHTML = "<p>Não foi possível detectar agora. Siga e escolha um perfil.</p>"; });
    } else if (step === 2) {
      var html = '<div class="wiz-grid">';
      profiles.forEach(function (p) {
        var on = (chosen || (detect && detect.suggested && detect.suggested.id)) === p.id;
        html += '<button class="wiz-card-item' + (on ? " active" : "") + '" data-id="' + p.id + '">' +
          '<img src="/static/img/bodies/' + (p.body || "sedan") + '.svg" alt="" style="--car-paint:' + (p.paint || "#c41e3a") + '">' +
          '<div class="nm">' + (p.name || p.id) + "</div>" +
          '<div class="meta">' + [p.body, p.transmission, p.tank_liters ? p.tank_liters + " L" : ""].filter(Boolean).join(" · ") + "</div></button>";
      });
      html += "</div>";
      body.innerHTML = html;
      body.querySelectorAll("[data-id]").forEach(function (b) {
        b.addEventListener("click", function () {
          chosen = b.getAttribute("data-id");
          body.querySelectorAll(".wiz-card-item").forEach(function (x) { x.classList.toggle("active", x === b); });
        });
      });
    } else if (step === 3) {
      var prof = profiles.filter(function (p) { return p.id === chosen; })[0];
      paint = (prof && prof.paint) || paint;
      body.innerHTML = '<label>Pintura <input type="color" id="wiz-paint" value="' + paint + '"></label>' +
        '<div class="xrow" style="margin-top:8px">' +
        '<label class="toggle"><input type="radio" name="wiz-art" value="auto" checked> Foto automática + silhueta de reserva</label>' +
        '<label class="toggle"><input type="radio" name="wiz-art" value="vector"> Só ilustração (sem foto)</label>' +
        "</div>" +
        '<p class="hint">A foto vem do Wikimedia Commons (licença livre) e é guardada neste aparelho, com créditos na página Carro.</p>';
      $("wiz-paint").addEventListener("input", function () { paint = $("wiz-paint").value; });
    }
  }

  function next() {
    if (step < 3) { step += 1; render(); return; }
    var art = (document.querySelector("input[name=wiz-art]:checked") || {}).value || "auto";
    fetch("/api/vehicle/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: chosen || "generic", paint: paint, art_mode: art, setup_completed: true }),
    }).then(function () {
      show(false);
      document.body.style.setProperty("--car-paint", paint);
      if (window.LancerCar && LancerCar.reload) LancerCar.reload();
      fetch("/api/vehicle").then(function (r) { return r.json(); }).then(function (d) {
        if (window.applyVehicleInfo) applyVehicleInfo(d);
      });
    });
  }

  function back() { if (step > 0) { step -= 1; render(); } }

  function boot() {
    if (!$("setup-wizard")) return;
    fetch("/api/vehicle").then(function (r) { return r.json(); }).then(function (d) {
      if (d.suggested_profile) chosen = d.suggested_profile;
      if (d.state && d.state.paint) paint = d.state.paint;
      var need = force || (d.needs_setup && !sessionStorage.getItem("wiz-skip"));
      return fetch("/api/vehicle/profiles").then(function (r) { return r.json(); }).then(function (p) {
        profiles = p.profiles || [];
        if (need) { show(true); render(); }
      });
    }).catch(function () {});
    $("wiz-next").addEventListener("click", next);
    $("wiz-back").addEventListener("click", back);
    $("wiz-skip").addEventListener("click", function () {
      sessionStorage.setItem("wiz-skip", "1");
      // não marca como concluído — volta a perguntar no próximo arranque
      show(false);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();

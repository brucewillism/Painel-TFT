/* Mídia local + rádio online + BT, equalizador, FM, telefone e CarPlay (mocks no simulador). */
(function (global) {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : "{}",
    }).then(function (r) { return r.json(); });
  }

  /* ——— Mídia ——— */
  var mediaState = { source: "local", status: "stopped", volume: 70, library: [], radio: [], eq: [0, 0, 0, 0, 0], eq_labels: [] };

  function renderEq() {
    var box = $("eq-box");
    if (!box) return;
    var labels = mediaState.eq_labels && mediaState.eq_labels.length
      ? mediaState.eq_labels : ["60", "230", "910", "4k", "14k"];
    var bands = mediaState.eq || [0, 0, 0, 0, 0];
    box.innerHTML = labels.map(function (lb, i) {
      return '<label>' + lb + '<input type="range" min="-12" max="12" step="1" data-eq="' + i + '" value="' + (bands[i] || 0) + '"></label>';
    }).join("");
    box.querySelectorAll("input").forEach(function (inp) {
      inp.addEventListener("change", function () {
        var next = (mediaState.eq || [0, 0, 0, 0, 0]).slice();
        next[Number(inp.getAttribute("data-eq"))] = Number(inp.value);
        post("/api/media", { action: "eq", eq: next }).then(applyMedia);
      });
    });
  }

  function applyMedia(data) {
    if (!data) return;
    mediaState = data;
    var tr = data.track;
    var title = "Parado";
    var artist = "—";
    if (data.source === "radio" && tr) {
      title = tr.name || tr.title || "Rádio";
      artist = "Rádio online";
    } else if (data.source === "bluetooth") {
      title = (data.bluetooth && data.bluetooth.title) || (tr && tr.title) || "Bluetooth";
      artist = (data.bluetooth && (data.bluetooth.artist || data.bluetooth.device)) || "A2DP";
    } else if (tr) {
      title = tr.title || "Faixa";
      artist = tr.artist || "—";
    }
    $("media-title").textContent = title;
    $("media-artist").textContent = artist;
    $("btn-play").textContent = data.status === "playing" ? "❚❚" : "▶";
    if ($("media-vol")) $("media-vol").value = data.volume;
    var cover = $("media-cover");
    if (tr && tr.cover && tr.id) {
      cover.innerHTML = '<img alt="" src="/api/media/cover/' + tr.id + '">';
    } else {
      cover.textContent = "♪";
    }
    document.querySelectorAll("#page-media .src-btn").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-src") === data.source);
    });
    var rows = $("media-rows");
    if (rows) {
      if (data.source === "radio") {
        rows.innerHTML = (data.radio || []).map(function (r, i) {
          return '<div class="radio-row" data-radio="' + i + '"><span>' + r.name + '</span></div>';
        }).join("");
        rows.querySelectorAll(".radio-row").forEach(function (el) {
          el.addEventListener("click", function () {
            post("/api/media", { action: "play", radio: Number(el.getAttribute("data-radio")) }).then(applyMedia);
          });
        });
      } else if (data.source === "bluetooth") {
        var bt = data.bluetooth || {};
        rows.innerHTML = '<div class="radio-row"><span>' +
          (bt.connected ? ("Conectado: " + (bt.device || "aparelho")) : "Nenhum aparelho A2DP (mock no simulador)") +
          "</span></div>";
      } else {
        rows.innerHTML = (data.library || []).map(function (t) {
          return '<div class="track-row" data-id="' + t.id + '"><span>' + (t.title || t.id) +
            '</span><span class="sub">' + (t.artist || "") + "</span></div>";
        }).join("") || '<div class="radio-row"><span>Pasta data/music vazia</span></div>';
        rows.querySelectorAll(".track-row").forEach(function (el) {
          el.addEventListener("click", function () {
            post("/api/media", { action: "play", track_id: el.getAttribute("data-id") }).then(applyMedia);
          });
        });
      }
    }
    var now = $("home-now");
    if (now) {
      now.innerHTML = data.status === "playing"
        ? 'Tocando: <strong>' + title + "</strong>"
        : "Toque em um app";
    }
    if (!document.getElementById("eq-box").dataset.ready) {
      renderEq();
      $("eq-box").dataset.ready = "1";
    }
  }

  function initMedia() {
    document.querySelectorAll("#page-media .src-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        post("/api/media", { action: "source", source: b.getAttribute("data-src") }).then(applyMedia);
      });
    });
    $("btn-play").addEventListener("click", function () {
      post("/api/media", { action: mediaState.status === "playing" ? "pause" : "play" }).then(applyMedia);
    });
    $("btn-prev").addEventListener("click", function () { post("/api/media", { action: "prev" }).then(applyMedia); });
    $("btn-next").addEventListener("click", function () { post("/api/media", { action: "next" }).then(applyMedia); });
    $("media-vol").addEventListener("change", function () {
      post("/api/media", { action: "volume", volume: Number($("media-vol").value) }).then(applyMedia);
    });
    fetch("/api/media").then(function (r) { return r.json(); }).then(applyMedia).catch(function () {});
  }

  /* ——— Telefone ——— */
  var dialBuf = "";

  function renderPhone(data) {
    if (!data) return;
    var contacts = $("phone-contacts");
    if (contacts) {
      contacts.innerHTML = (data.contacts || []).map(function (c) {
        return '<div class="contact" data-num="' + c.number + '"><strong>' + c.name +
          '</strong><div class="sub" style="color:var(--muted);font-size:11px">' + c.number + "</div></div>";
      }).join("");
      contacts.querySelectorAll(".contact").forEach(function (el) {
        el.addEventListener("click", function () {
          dialBuf = el.getAttribute("data-num").replace(/\s/g, "");
          $("phone-number").textContent = el.getAttribute("data-num");
        });
      });
    }
    var logEl = $("phone-log");
    if (logEl) {
      var dirLabel = { in: "RECEBIDA", out: "EFETUADA", missed: "PERDIDA" };
      logEl.innerHTML = (data.log || []).map(function (r) {
        return '<div class="clog" data-num="' + r.number + '"><span class="dir">' +
          (dirLabel[r.dir] || r.dir) + "</span> " + (r.name || r.number) + "</div>";
      }).join("");
      logEl.querySelectorAll(".clog").forEach(function (el) {
        el.addEventListener("click", function () {
          $("phone-number").textContent = el.getAttribute("data-num");
          dialBuf = el.getAttribute("data-num");
        });
      });
    }
    var call = data.call;
    var ov = $("call-overlay");
    if (!ov) return;
    if (call && (call.state === "incoming" || call.state === "ringing" || call.state === "active" || call.state === "dialing")) {
      ov.hidden = false;
      $("call-state").textContent = (call.state === "incoming" || call.state === "ringing") ? "CHAMADA RECEBIDA" :
        (call.state === "dialing" ? "DISCANDO" : "EM CHAMADA");
      $("call-who").textContent = call.name || call.number || "—";
      $("call-num").textContent = call.number || "";
      $("btn-call-answer").hidden = (call.state !== "incoming" && call.state !== "ringing");
    } else {
      ov.hidden = true;
    }
  }

  function phoneAction(action, extra) {
    var body = Object.assign({ action: action }, extra || {});
    return post("/api/phone", body).then(renderPhone);
  }

  function initPhone() {
    var pad = $("keypad");
    pad.innerHTML = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].map(function (k) {
      return '<button class="btn key" data-k="' + k + '">' + k + "</button>";
    }).join("");
    pad.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        dialBuf += b.getAttribute("data-k");
        $("phone-number").textContent = dialBuf;
      });
    });
    $("btn-backspace").addEventListener("click", function () {
      dialBuf = dialBuf.slice(0, -1);
      $("phone-number").textContent = dialBuf;
    });
    $("btn-dial").addEventListener("click", function () {
      if (dialBuf) phoneAction("dial", { number: dialBuf });
    });
    $("btn-hang").addEventListener("click", function () { phoneAction("hangup"); });
    $("btn-call-answer").addEventListener("click", function () { phoneAction("answer"); });
    $("btn-call-end").addEventListener("click", function () { phoneAction("hangup"); });
    $("btn-demo-in").addEventListener("click", function () { phoneAction("incoming"); });
    fetch("/api/phone").then(function (r) { return r.json(); }).then(renderPhone).catch(function () {});
    setInterval(function () {
      fetch("/api/phone").then(function (r) { return r.json(); }).then(renderPhone).catch(function () {});
    }, 1500);
  }

  /* ——— FM ——— */
  function applyFm(data) {
    if (!data) return;
    $("fm-mhz").innerHTML = Number(data.mhz).toFixed(1) + " <span>MHz</span>";
    $("fm-slider").value = Math.round(data.mhz * 10);
    var name = "FM";
    (data.presets || []).forEach(function (p) {
      if (Math.abs(p.mhz - data.mhz) < 0.06) name = p.name;
    });
    $("fm-name").textContent = name + (data.playing ? "  ·  NO AR" : "");
    var hint = $("fm-hint");
    if (data.backend === "rtl_fm" && data.device_present) {
      hint.textContent = "Sintonizador RTL-SDR detectado (rtl_fm). Áudio sai pelo DAC/HDMI/aux configurado no PipeWire/ALSA.";
    } else {
      hint.textContent = "FM via dongle RTL-SDR (opcional). Sem o dongle, o sintonizador é só visual — use o rádio online à direita.";
    }
    var box = $("fm-presets");
    if (box && !box.dataset.ready) {
      box.innerHTML = (data.presets || []).map(function (p) {
        return '<div class="radio-row" data-mhz="' + p.mhz + '"><span>' + p.name +
          '</span><span class="sub">' + p.mhz.toFixed(1) + "</span></div>";
      }).join("");
      box.querySelectorAll(".radio-row").forEach(function (el) {
        el.addEventListener("click", function () {
          post("/api/fm", { action: "tune", mhz: Number(el.getAttribute("data-mhz")) }).then(applyFm);
        });
      });
      box.dataset.ready = "1";
    }
  }

  function initFm() {
    $("fm-slider").addEventListener("change", function () {
      post("/api/fm", { action: "tune", mhz: Number($("fm-slider").value) / 10 }).then(applyFm);
    });
    $("btn-fm-play").addEventListener("click", function () { post("/api/fm", { action: "play" }).then(applyFm); });
    $("btn-fm-stop").addEventListener("click", function () { post("/api/fm", { action: "stop" }).then(applyFm); });
    fetch("/api/fm").then(function (r) { return r.json(); }).then(applyFm).catch(function () {});
    fetch("/api/media").then(function (r) { return r.json(); }).then(function (m) {
      var box = $("fm-online");
      if (!box) return;
      box.innerHTML = (m.radio || []).map(function (r, i) {
        return '<div class="radio-row" data-radio="' + i + '"><span>' + r.name + "</span></div>";
      }).join("");
      box.querySelectorAll(".radio-row").forEach(function (el) {
        el.addEventListener("click", function () {
          post("/api/media", { action: "play", radio: Number(el.getAttribute("data-radio")) });
        });
      });
    }).catch(function () {});
  }

  /* ——— CarPlay / Android Auto (dongle + mock) ——— */
  function applyCp(data) {
    if (!data) return;
    var st = "SIMULADOR";
    if (data.running) st = "DONGLE EM EXECUÇÃO";
    else if (data.connected) st = "DONGLE CONECTADO";
    else if (data.driver_installed) st = "DRIVER OK — SEM DONGLE";
    $("cp-status").textContent = st;
    var dongle = data.dongle ? ((data.dongle.name || "USB") + " " + (data.dongle.vid || "") + ":" + (data.dongle.pid || "")) : "nenhum";
    $("cp-banner").innerHTML =
      "Integração com dongle USB estilo Carlinkit (ligado ou wireless). " +
      "O protocolo vem do driver open-source <strong>node-CarPlay / react-carplay</strong> " +
      "(<code>scripts/install-carplay.sh</code>). " +
      "Dongle agora: <strong>" + dongle + "</strong>. " +
      "Sem dongle ou driver, esta tela é um mock da experiência de central. " +
      "Toque em <strong>← Painel</strong> para voltar. " +
      "Microfone: use um USB/headset no Pi e roteie o rec/play no PipeWire para o processo do driver " +
      "(veja o README, seção Áudio e CarPlay). Não usamos logotipos oficiais da Apple ou do Google.";
  }

  function initCarPlay() {
    var apps = [
      ["Mapas", "⌖"], ["Música", "♪"], ["Telefone", "☎"], ["Mensagens", "✉"],
      ["Agora", "◉"], ["Podcasts", "◈"], ["Ajustes", "⚙"], ["Relógio", "◷"],
    ];
    $("cp-grid").innerHTML = apps.map(function (a) {
      return '<div class="cp-app"><span class="ico">' + a[1] + "</span>" + a[0] + "</div>";
    }).join("");
    $("btn-cp-back").addEventListener("click", function () {
      post("/api/carplay/stop").catch(function () {});
      document.body.classList.remove("mode-carplay");
      if (global.LancerUI && LancerUI.showPage) LancerUI.showPage("home", -1);
    });
    $("btn-cp-launch").addEventListener("click", function () {
      post("/api/carplay/launch").then(applyCp);
    });
    fetch("/api/carplay").then(function (r) { return r.json(); }).then(applyCp).catch(function () {});
  }

  function initAll() {
    initMedia();
    initPhone();
    initFm();
    initCarPlay();
  }

  global.LancerMedia = { init: initAll, apply: applyMedia };
  global.LancerPhone = { init: initPhone };
  global.LancerFm = { init: initFm };
  global.LancerCarPlay = { init: initCarPlay };
})(window);

/* Grade / câmera única / 360° e troca automática na ré. */
(function (global) {
  "use strict";

  var cams = [];
  var mode = "grid";
  var active = false;
  var lastReverse = false;

  function $(id) { return document.getElementById(id); }

  function cell(id, label) {
    return '<div class="cam-cell" data-id="' + id + '">' +
      '<img alt="' + label + '" data-src="/api/cameras/' + id + '/stream">' +
      '<span class="lbl">' + label + "</span></div>";
  }

  function bindSrc(on) {
    var grid = $("cam-grid");
    if (!grid) return;
    grid.querySelectorAll("img").forEach(function (img) {
      var src = img.getAttribute("data-src");
      if (on) {
        if (img.getAttribute("src") !== src) img.setAttribute("src", src + "?t=" + Date.now());
      } else {
        img.removeAttribute("src");
      }
    });
  }

  function render() {
    var grid = $("cam-grid");
    if (!grid) return;
    if (mode === "grid") {
      grid.className = "cam-grid grid-4";
      grid.innerHTML = cams.map(function (c) { return cell(c.id, c.label); }).join("");
    } else if (mode === "birdseye") {
      grid.className = "cam-grid grid-1";
      grid.innerHTML = cell("birdseye", "360° (experimental)");
    } else {
      grid.className = "cam-grid grid-1";
      var cam = cams.filter(function (c) { return c.id === mode; })[0];
      var label = cam ? cam.label : mode;
      grid.innerHTML = cell(mode, label);
    }
    document.querySelectorAll(".cam-toolbar .src-btn").forEach(function (b) {
      b.classList.toggle("on", (b.getAttribute("data-cam") || "") === (mode === "grid" ? "grid" : mode));
    });
    bindSrc(active);
  }

  function show(id) {
    mode = id || "grid";
    render();
  }

  function activate() { active = true; bindSrc(true); }
  function deactivate() { active = false; bindSrc(false); }

  function setReverse(on) {
    var el = $("cam-rev");
    if (el) {
      el.classList.toggle("on", !!on);
      el.textContent = on ? "RÉ ON" : "RÉ OFF";
    }
    var entered = on && !lastReverse;
    lastReverse = !!on;
    if (entered) show("rear");
    return entered;
  }

  async function init() {
    document.querySelectorAll(".cam-toolbar .src-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        var id = b.getAttribute("data-cam");
        show(id === "grid" ? "grid" : id);
      });
    });
    try {
      var data = await (await fetch("/api/cameras")).json();
      cams = data.cameras || [];
      setReverse(!!data.reverse);
      render();
    } catch (e) {
      cams = [
        { id: "front", label: "Frente" },
        { id: "rear", label: "Ré" },
        { id: "left", label: "Esquerda" },
        { id: "right", label: "Direita" },
      ];
      render();
    }
  }

  global.LancerCameras = { init: init, show: show, activate: activate, deactivate: deactivate, setReverse: setReverse };
})(window);

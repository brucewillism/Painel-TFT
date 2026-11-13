/* Medidores circulares em canvas, com interpolação, glow barato e varredura de intro. */
(function (global) {
  "use strict";

  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function polar(cx, cy, r, angle) {
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  }
  function perfOn() { return document.body.classList.contains("perf"); }

  function Gauge(canvas, opts) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.opts = Object.assign({
      min: 0, max: 8000, value: 0, display: 0,
      unit: "rpm", label: "RPM", decimals: 0,
      redFrom: 6500, yellowFrom: 5500,
      startAngle: Math.PI * 0.75, endAngle: Math.PI * 2.25,
      major: 8, color: "#ff6a00", follow: 0.18,
    }, opts);
    this._pulse = 0;
  }

  Gauge.prototype.setTarget = function (v) {
    if (v == null || Number.isNaN(v)) return;
    this.opts.value = clamp(v, this.opts.min, this.opts.max);
  };

  Gauge.prototype.setFollow = function (t) { this.opts.follow = t; };

  Gauge.prototype.tick = function (dt) {
    this.opts.display = lerp(this.opts.display, this.opts.value, this.opts.follow);
    if (this.opts.redFrom != null && this.opts.display >= this.opts.redFrom) {
      this._pulse += (dt || 0.016) * 10;
    } else {
      this._pulse = 0;
    }
    this.draw();
  };

  Gauge.prototype.angleOf = function (v) {
    var t = (v - this.opts.min) / (this.opts.max - this.opts.min);
    return this.opts.startAngle + t * (this.opts.endAngle - this.opts.startAngle);
  };

  Gauge.prototype.draw = function () {
    var c = this.ctx;
    var w = this.canvas.width, h = this.canvas.height;
    var cx = w / 2, cy = h / 2 + 4;
    var r = Math.min(w, h) * 0.42;
    var o = this.opts;
    function cssv(name, fallback) {
      var v = getComputedStyle(document.body).getPropertyValue(name).trim();
      return v || fallback;
    }
    var accent = cssv("--accent", o.color || "#e10600");
    var text = cssv("--text", "#fff0f0"), muted = cssv("--muted", "#9a8080"), stroke = cssv("--stroke", "#3a1010");
    var red = cssv("--hot", "#ff1a1a"), yellow = cssv("--accent-hi", "#ff2a2a");
    var perf = perfOn();
    var font = '"Orbitron", sans-serif';

    c.clearRect(0, 0, w, h);

    // arco de fundo + glow barato (traço largo translúcido, sem shadowBlur)
    if (!perf) {
      c.beginPath();
      c.arc(cx, cy, r, o.startAngle, o.endAngle);
      c.strokeStyle = accent;
      c.globalAlpha = 0.22;
      c.lineWidth = 16;
      c.lineCap = "round";
      c.stroke();
      c.globalAlpha = 1;
    }
    c.beginPath();
    c.arc(cx, cy, r, o.startAngle, o.endAngle);
    c.strokeStyle = stroke;
    c.lineWidth = 10;
    c.lineCap = "round";
    c.stroke();

    if (o.yellowFrom != null) {
      c.beginPath();
      c.arc(cx, cy, r, this.angleOf(o.yellowFrom), this.angleOf(o.redFrom != null ? o.redFrom : o.max));
      c.strokeStyle = yellow;
      c.lineWidth = 10;
      c.stroke();
    }
    if (o.redFrom != null) {
      var pulse = (!perf && this._pulse > 0) ? 0.55 + 0.45 * Math.sin(this._pulse) : 1;
      c.beginPath();
      c.arc(cx, cy, r, this.angleOf(o.redFrom), o.endAngle);
      c.strokeStyle = red;
      c.globalAlpha = pulse;
      c.lineWidth = 12;
      c.stroke();
      c.globalAlpha = 1;
    }

    var ticks = o.major;
    for (var i = 0; i <= ticks; i++) {
      var val = o.min + (i / ticks) * (o.max - o.min);
      var ang = this.angleOf(val);
      var a = polar(cx, cy, r - 16, ang);
      var b = polar(cx, cy, r - 4, ang);
      c.beginPath();
      c.moveTo(a[0], a[1]);
      c.lineTo(b[0], b[1]);
      c.strokeStyle = val >= (o.redFrom || Infinity) ? red : text;
      c.lineWidth = 2;
      c.stroke();
      var p = polar(cx, cy, r - 26, ang);
      c.fillStyle = muted;
      c.font = "10px " + font;
      c.textAlign = "center";
      c.textBaseline = "middle";
      var shown = o.max >= 1000 ? (val / 1000).toFixed(val % 1000 === 0 ? 0 : 1) : String(Math.round(val));
      c.fillText(shown, p[0], p[1]);
    }

    var angV = this.angleOf(o.display);
    var tip = polar(cx, cy, r - 20, angV);
    var left = polar(cx, cy, 8, angV + Math.PI / 2);
    var right = polar(cx, cy, 8, angV - Math.PI / 2);
    if (!perf) {
      c.beginPath();
      c.moveTo(left[0], left[1]);
      c.lineTo(tip[0], tip[1]);
      c.lineTo(right[0], right[1]);
      c.closePath();
      c.fillStyle = accent; c.globalAlpha = 0.28;
      c.fill();
      c.globalAlpha = 1;
    }
    c.beginPath();
    c.moveTo(left[0], left[1]);
    c.lineTo(tip[0], tip[1]);
    c.lineTo(right[0], right[1]);
    c.closePath();
    c.fillStyle = accent;
    c.fill();
    c.beginPath();
    c.arc(cx, cy, 6, 0, Math.PI * 2);
    c.fillStyle = text;
    c.fill();

    c.fillStyle = text;
    c.font = "700 22px " + font;
    c.textAlign = "center";
    c.textBaseline = "alphabetic";
    var num = o.decimals > 0 ? o.display.toFixed(o.decimals) : String(Math.round(o.display));
    c.fillText(num, cx, cy + r * 0.42);
    c.fillStyle = muted;
    c.font = "700 10px " + font;
    c.fillText((o.label + " " + o.unit).trim().toUpperCase(), cx, cy + r * 0.42 + 14);
  };

  global.LancerGauges = { Gauge: Gauge, lerp: lerp, clamp: clamp };
})(window);

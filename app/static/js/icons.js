/* Ícones SVG do lançador. Sem depender das fontes Orbitron/Rajdhani (que não cobrem esses símbolos.). */
(function (global) {
  "use strict";
  var S = ' fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
  var icons = {
    gauges:
      '<circle cx="12" cy="13" r="8"' + S + '/>' +
      '<path d="M12 13 L17 9"' + S + '/>' +
      '<path d="M6 13 h2 M16 13 h2 M12 7 v2"' + S + '/>',
    map:
      '<path d="M4 6 L9 4 L15 7 L20 5 V18 L15 20 L9 17 L4 19 Z"' + S + '/>' +
      '<path d="M9 4 V17 M15 7 V20"' + S + '/>' +
      '<circle cx="12" cy="11" r="1.6" fill="currentColor" stroke="none"/>',
    carplay:
      '<rect x="4" y="5" width="16" height="12" rx="1.5"' + S + '/>' +
      '<path d="M8 21 h8 M12 17 v4"' + S + '/>',
    media:
      '<path d="M9 18 a3 3 0 1 0 0-0.1"' + S + '/>' +
      '<path d="M17 16 a3 3 0 1 0 0-0.1"' + S + '/>' +
      '<path d="M12 18 V6 l8 -2 v12"' + S + '/>',
    phone:
      '<path d="M7 3 H10 L11 7 L9 9 C10 12 12 14 15 15 L17 13 L21 14 V17 C21 18 19 21 12 21 C6 21 3 16 3 12 C3 5 6 3 7 3 Z"' + S + '/>',
    cameras:
      '<path d="M4 8 H8 L10 6 H14 L16 8 H20 V18 H4 Z"' + S + '/>' +
      '<circle cx="12" cy="13" r="3.2"' + S + '/>',
    radio:
      '<circle cx="12" cy="14" r="6"' + S + '/>' +
      '<circle cx="12" cy="14" r="1.4" fill="currentColor" stroke="none"/>' +
      '<path d="M8 5 L16 2 M12 8 V9"' + S + '/>',
    settings:
      '<circle cx="12" cy="12" r="3"' + S + '/>' +
      '<path d="M12 3 v2.4 M12 18.6 V21 M3 12 h2.4 M18.6 12 H21 M5.6 5.6 l1.7 1.7 M16.7 16.7 l1.7 1.7 M5.6 18.4 l1.7 -1.7 M16.7 7.3 l1.7 -1.7"' + S + '/>',
    car:
      '<path d="M4 15 L6 10 H10 L13 7 H19 L22 15 H20 C20 16.6 18.6 18 17 18 C15.4 18 14 16.6 14 15 H10 C10 16.6 8.6 18 7 18 C5.4 18 4 16.6 4 15 Z"' + S + '/>' +
      '<circle cx="7" cy="15" r="1.5"' + S + '/>' +
      '<circle cx="17" cy="15" r="1.5"' + S + '/>',
    sensors:
      '<rect x="4" y="4" width="7" height="7" rx="1"' + S + '/>' +
      '<rect x="13" y="4" width="7" height="7" rx="1"' + S + '/>' +
      '<rect x="4" y="13" width="7" height="7" rx="1"' + S + '/>' +
      '<rect x="13" y="13" width="7" height="7" rx="1"' + S + '/>',
    trip:
      '<path d="M4 18 V6 L12 10 L20 6 V18 L12 14 Z"' + S + '/>' +
      '<path d="M12 10 V14"' + S + '/>',
    dtcs:
      '<path d="M12 3 L21 19 H3 Z"' + S + '/>' +
      '<path d="M12 9 V13"' + S + '/>' +
      '<circle cx="12" cy="16" r="0.8" fill="currentColor" stroke="none"/>',
    range:
      '<path d="M7 20 V9 H10 V6 H14 V9 H17 V20 Z"' + S + '/>' +
      '<rect x="11" y="11" width="2" height="5" fill="currentColor" stroke="none"/>' +
      '<path d="M10 20 V22 H14 V20"' + S + '/>',
    perf:
      '<path d="M4 16 L8 8 L12 14 L16 6 L20 16"' + S + '/>' +
      '<path d="M4 18 H20"' + S + '/>',
    track:
      '<path d="M5 8 C8 4 16 4 19 8 C22 12 16 14 12 16 C8 18 3 17 5 12 Z"' + S + '/>' +
      '<circle cx="8" cy="10" r="1.2" fill="currentColor" stroke="none"/>',
    gforce:
      '<circle cx="12" cy="12" r="8"' + S + '/>' +
      '<circle cx="12" cy="12" r="4"' + S + '/>' +
      '<circle cx="16" cy="9" r="1.6" fill="currentColor" stroke="none"/>',
    telemetry:
      '<path d="M3 16 L7 10 L11 14 L15 6 L21 12"' + S + '/>' +
      '<path d="M3 19 H21"' + S + '/>',
    dashcam:
      '<rect x="3" y="7" width="14" height="10" rx="1.5"' + S + '/>' +
      '<path d="M17 10 L21 8 V16 L17 14 Z"' + S + '/>',
    health:
      '<path d="M12 21 C12 21 4 15 4 9 C4 6 6 4 9 4 C10.5 4 12 5 12 6.5 C12 5 13.5 4 15 4 C18 4 20 6 20 9 C20 15 12 21 12 21 Z"' + S + '/>',
    leds:
      '<rect x="3" y="10" width="18" height="4" rx="1"' + S + '/>' +
      '<circle cx="6" cy="12" r="1.2" fill="currentColor" stroke="none"/>' +
      '<circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>' +
      '<circle cx="18" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
    valet:
      '<rect x="8" y="11" width="8" height="8" rx="1"' + S + '/>' +
      '<path d="M9 11 V8 a3 3 0 0 1 6 0 v3"' + S + '/>'
  };

  function svg(name) {
    var inner = icons[name] || icons.gauges;
    return '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">' + inner + "</svg>";
  }

  global.LancerIcons = { svg: svg, names: icons };
})(window);

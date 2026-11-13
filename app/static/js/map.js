/* Mapa Leaflet: tiles offline (local/MBTiles) com fallback online, rastro e posição. */
(function (global) {
  "use strict";

  var map, marker, trailLine, trail = [], follow = true, inited = false, stationLayer, routeLine, stations = [];

  function init(cfg) {
    if (map) return;
    map = L.map("map", {
      zoomControl: false,
      attributionControl: true,
      preferCanvas: true,
    }).setView([cfg.default_lat, cfg.default_lon], cfg.default_zoom);
    L.control.zoom({ position: "topright" }).addTo(map);

    var layers = [];
    if (cfg.offline_ok) {
      layers.push(L.tileLayer(cfg.offline_url, {
        maxZoom: 18,
        minZoom: 5,
        attribution: "Tiles offline (OSM)",
      }));
    }
    if (cfg.online_url) {
      layers.push(L.tileLayer(cfg.online_url, {
        maxZoom: 19,
        attribution: cfg.attribution || "© OpenStreetMap",
      }));
    }
    if (!layers.length) {
      // malha vazia — o mapa ainda mostra o rastro
    } else if (cfg.offline_ok) {
      // tenta offline primeiro; o Leaflet só pede o próximo se o tile falhar
      // (não há fallback automático por tile, então empilhamos online por baixo).
      if (layers.length === 2) {
        layers[1].addTo(map);
        layers[0].addTo(map);
      } else {
        layers[0].addTo(map);
      }
    } else {
      layers[0].addTo(map);
    }

    trailLine = L.polyline([], {
      color: (getComputedStyle(document.body).getPropertyValue("--accent").trim() || "#e10600"),
      weight: 4,
      opacity: 0.9,
    }).addTo(map);

    var icon = L.divIcon({ className: "", html: '<div class="car-marker"></div>', iconSize: [18, 18], iconAnchor: [9, 9] });
    marker = L.marker([cfg.default_lat, cfg.default_lon], { icon: icon }).addTo(map);

    map.on("dragstart", function () { follow = false; });
    map.on("click", function (ev) {
      if (window._lancerPickGate) {
        var fn = window._lancerPickGate;
        window._lancerPickGate = null;
        document.body.classList.remove("pick-gate");
        fn(ev.latlng.lat, ev.latlng.lng);
        return;
      }
      follow = true;
    });
    inited = true;
    setTimeout(function () { map.invalidateSize(); }, 200);
  }

  function invalidate() {
    if (map) setTimeout(function () { map.invalidateSize(); }, 80);
  }

  function update(lat, lon, heading) {
    if (!inited || lat == null || lon == null) return;
    var ll = [lat, lon];
    marker.setLatLng(ll);
    var last = trail[trail.length - 1];
    if (!last || Math.abs(last[0] - lat) > 1e-6 || Math.abs(last[1] - lon) > 1e-6) {
      trail.push(ll);
      if (trail.length > 2000) trail = trail.slice(-2000);
      trailLine.setLatLngs(trail);
    }
    if (follow) {
      map.setView(ll, map.getZoom(), { animate: false });
    }
  }

  function setTrail(points) {
    trail = (points || []).map(function (p) { return [p.lat, p.lon]; });
    if (trailLine) trailLine.setLatLngs(trail);
  }

  var badgeColor = { reachable: "#3ee06a", "at-risk": "#ffb000", unreachable: "#ff3a3a" };

  function setFollow(on) { follow = !!on; }

  function showStations(data) {
    if (!inited || !map) return;
    stations = (data && data.stations) || [];
    if (stationLayer) map.removeLayer(stationLayer);
    stationLayer = L.layerGroup().addTo(map);
    stations.forEach(function (s) {
      var col = badgeColor[s.badge] || "#ff3a3a";
      var icon = L.divIcon({
        className: "",
        html: '<div style="width:14px;height:14px;border-radius:50%;background:' + col +
              ';border:2px solid #fff;box-shadow:0 0 6px ' + col + '"></div>',
        iconSize: [14, 14], iconAnchor: [7, 7],
      });
      var m = L.marker([s.lat, s.lon], { icon: icon }).addTo(stationLayer);
      m.bindTooltip((s.name || "Posto") + " · " + (s.distance_km || s.distance_air_km || "?") + " km", { direction: "top" });
      m.on("click", function () { selectStation(s.id); follow = false; });
    });
  }

  function selectStation(id) {
    var s = stations.filter(function (x) { return x.id === id; })[0];
    if (!s || !map) return;
    follow = false;
    if (routeLine) map.removeLayer(routeLine);
    var latlngs = [];
    if (s.geometry && s.geometry.coordinates && s.geometry.coordinates.length) {
      latlngs = s.geometry.coordinates.map(function (c) { return [c[1], c[0]]; });
    } else {
      var here = marker ? marker.getLatLng() : null;
      if (here) latlngs = [[here.lat, here.lng], [s.lat, s.lon]];
    }
    if (latlngs.length) {
      var col = badgeColor[s.badge] || "#e10600";
      routeLine = L.polyline(latlngs, { color: col, weight: 5, opacity: 0.9 }).addTo(map);
      map.fitBounds(routeLine.getBounds().pad(0.2), { animate: false });
    }
  }

  global.LancerMap = {
    init: init, update: update, invalidate: invalidate, setTrail: setTrail,
    showStations: showStations, selectStation: selectStation, setFollow: setFollow,
  };
})(window);

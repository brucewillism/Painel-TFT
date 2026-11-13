/* Carro 3D HUD: modelos Kenney Car Kit (CC0) em wireframe brilhante. */
(function (global) {
  "use strict";

  var MODEL_BASE = "/static/models/";
  var MODEL_FILE = {
    sedan: "innerscene/sedan.glb",
    hatch: "kenney-car/hatchback-sports.glb",
    suv: "kenney-car/suv.glb",
    pickup: "kenney-car/truck.glb",
    coupe: "kenney-car/sedan-sports.glb",
    wagon: "kenney-car/van.glb"
  };
  var TARGET_LEN = 3.70;
  var EDGE_ANGLE = 16;
  var RING_RADII = [1.72, 2.38, 3.05];
  var HIDE_RE = /spoke|wiper|handle|registration|brake|hub|underbody|grille/i;
  var GLASS_RE = /glass|windscreen|windshield/i;
  var LAMP_RE = /headlamp|headlight|lamp(?!.*tail)/i;
  var TAIL_RE = /tail\s*lamp|taillight|tail lamp/i;
  var WHEEL_RE = /wheel|tire|rim/i;

  var _templates = {};
  var _pending = {};

  function hexToInt(hex) {
    if (typeof hex === "number") return hex;
    var s = String(hex || "#00D8FF").replace("#", "");
    return parseInt(s, 16);
  }

  function roleOf(obj) {
    return (obj.material && obj.material.userData && obj.material.userData.role) || "";
  }

  /* Parser GLB mínimo (TRIANGLES + POSITION/indices, só translação nos nós). */
  function parseGLB(buffer) {
    var dv = new DataView(buffer);
    var magic = dv.getUint32(0, true);
    if (magic !== 0x46546C67) throw new Error("não é glTF/GLB");
    var jsonLen = dv.getUint32(12, true);
    var json = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 20, jsonLen)));
    var binOff = 20 + jsonLen;
    var binLen = dv.getUint32(binOff, true);
    var bin = buffer.slice(binOff + 8, binOff + 8 + binLen);
    var COMP = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
    var ELEMS = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };

    function accessorArray(idx) {
      var acc = json.accessors[idx];
      var bv = json.bufferViews[acc.bufferView];
      var off = (bv.byteOffset || 0) + (acc.byteOffset || 0);
      var elems = ELEMS[acc.type];
      var cb = COMP[acc.componentType];
      var stride = bv.byteStride || elems * cb;
      var count = acc.count;
      var i, j;
      if (acc.componentType === 5126) {
        if (stride === elems * 4 && (off % 4) === 0) {
          return new Float32Array(bin, off, count * elems);
        }
        var f = new Float32Array(count * elems);
        var src = new DataView(bin, off);
        for (i = 0; i < count; i++) {
          for (j = 0; j < elems; j++) f[i * elems + j] = src.getFloat32(i * stride + j * 4, true);
        }
        return f;
      }
      if (acc.componentType === 5123) {
        if (stride === 2 && (off % 2) === 0) return new Uint16Array(bin, off, count);
        var u = new Uint16Array(count);
        var sv = new DataView(bin, off);
        for (i = 0; i < count; i++) u[i] = sv.getUint16(i * stride, true);
        return u;
      }
      if (acc.componentType === 5125) {
        var u32 = new Uint32Array(count);
        var dv32 = new DataView(bin, off);
        for (i = 0; i < count; i++) u32[i] = dv32.getUint32(i * stride, true);
        return u32;
      }
      throw new Error("accessor não suportado " + acc.componentType);
    }

    function makeGeometry(prim) {
      var geo = new THREE.BufferGeometry();
      var pos = accessorArray(prim.attributes.POSITION);
      geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      if (prim.indices != null) {
        var idx = accessorArray(prim.indices);
        geo.setIndex(new THREE.BufferAttribute(idx, 1));
      }
      geo.computeVertexNormals();
      geo.computeBoundingBox();
      return geo;
    }

    function buildNode(i) {
      var n = json.nodes[i];
      var g = new THREE.Group();
      g.name = n.name || "";
      if (n.translation) g.position.fromArray(n.translation);
      if (n.rotation) g.quaternion.fromArray(n.rotation);
      if (n.scale) g.scale.fromArray(n.scale);
      if (n.matrix) {
        var m = new THREE.Matrix4().fromArray(n.matrix);
        m.decompose(g.position, g.quaternion, g.scale);
      }
      if (n.mesh != null) {
        var meshDef = json.meshes[n.mesh];
        var dummy = new THREE.MeshBasicMaterial({ color: 0x000000 });
        (meshDef.primitives || []).forEach(function (prim, pi) {
          var mesh = new THREE.Mesh(makeGeometry(prim), dummy);
          mesh.name = (n.name || meshDef.name || "part") + (pi ? "-" + pi : "");
          if (prim.material != null && json.materials && json.materials[prim.material]) {
            mesh.userData.matName = json.materials[prim.material].name || "";
          }
          g.add(mesh);
        });
      }
      (n.children || []).forEach(function (c) { g.add(buildNode(c)); });
      return g;
    }

    var root = new THREE.Group();
    root.name = (json.scenes[json.scene || 0].name) || "car";
    (json.scenes[json.scene || 0].nodes || []).forEach(function (i) {
      root.add(buildNode(i));
    });
    return root;
  }

  function loadTemplate(body) {
    var key = MODEL_FILE[body] ? body : "sedan";
    if (_templates[key]) return Promise.resolve(_templates[key]);
    if (_pending[key]) return _pending[key];
    var url = MODEL_BASE + MODEL_FILE[key];
    _pending[key] = fetch(url).then(function (r) {
      if (!r.ok) throw new Error("falha ao carregar " + url);
      return r.arrayBuffer();
    }).then(function (buf) {
      var tpl = parseGLB(buf);
      _templates[key] = tpl;
      delete _pending[key];
      return tpl;
    }).catch(function (err) {
      delete _pending[key];
      throw err;
    });
    return _pending[key];
  }

  function partName(obj) {
    var n = obj.name || "";
    if (obj.parent && obj.parent.name) n = obj.parent.name + " " + n;
    return n;
  }

  function stylize(root, accentInt) {
    var col = new THREE.Color(accentInt);
    var fillCol = new THREE.Color(0x03080c);
    fillCol.lerp(col, 0.10);
    var glassCol = new THREE.Color(0x02060a);
    glassCol.lerp(col, 0.16);
    var fillMat = new THREE.MeshBasicMaterial({
      color: fillCol, transparent: true, opacity: 0.64,
      side: THREE.FrontSide, depthWrite: true
    });
    fillMat.userData.role = "fill";
    var glassMat = new THREE.MeshBasicMaterial({
      color: glassCol, transparent: true, opacity: 0.20,
      side: THREE.FrontSide, depthWrite: false
    });
    glassMat.userData.role = "fill";
    var edgeMat = new THREE.LineBasicMaterial({
      color: col, transparent: true, opacity: 0.96
    });
    edgeMat.userData.role = "edge";
    var glowMat = new THREE.LineBasicMaterial({
      color: col, transparent: true, opacity: 0.46,
      blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false
    });
    glowMat.userData.role = "glow";
    var glowSoft = new THREE.LineBasicMaterial({
      color: col, transparent: true, opacity: 0.18,
      blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false
    });
    glowSoft.userData.role = "glow";
    var gridMat = new THREE.LineBasicMaterial({
      color: col, transparent: true, opacity: 0.13,
      blending: THREE.AdditiveBlending, depthWrite: false
    });
    gridMat.userData.role = "grid";
    var softEdge = new THREE.LineBasicMaterial({
      color: col, transparent: true, opacity: 0.62
    });
    softEdge.userData.role = "edge";
    var headMat = new THREE.MeshBasicMaterial({
      color: col.clone().lerp(new THREE.Color(0xffffff), 0.65),
      transparent: true, opacity: 1,
      blending: THREE.AdditiveBlending, depthWrite: false
    });
    headMat.userData.role = "head";
    var tailMat = new THREE.MeshBasicMaterial({
      color: 0xff2244, transparent: true, opacity: 0.92,
      blending: THREE.AdditiveBlending, depthWrite: false
    });
    tailMat.userData.role = "tail";

    root.traverse(function (obj) {
      if (!obj.isMesh || !obj.geometry) return;
      var name = partName(obj);
      if (HIDE_RE.test(name)) {
        obj.visible = false;
        return;
      }
      var isGlass = GLASS_RE.test(name) || (obj.userData.matName || "") === "glass";
      var isTail = TAIL_RE.test(name) || (obj.userData.matName || "") === "tail";
      var isHead = !isTail && (LAMP_RE.test(name) || (obj.userData.matName || "") === "lamp");
      var isWheel = WHEEL_RE.test(name);
      if (isHead) {
        obj.material = headMat;
        obj.renderOrder = 5;
      } else if (isTail) {
        obj.material = tailMat;
        obj.renderOrder = 5;
      } else if (isGlass) {
        obj.material = glassMat;
        obj.renderOrder = 2;
      } else {
        obj.material = fillMat;
        obj.renderOrder = 1;
      }
      if (isHead || isTail) {
        var lampEdge = new THREE.EdgesGeometry(obj.geometry, 30);
        var le = new THREE.LineSegments(lampEdge, isTail ? softEdge : edgeMat);
        le.renderOrder = 6;
        le.userData.hudLine = true;
        obj.add(le);
        return;
      }
      var edges = new THREE.EdgesGeometry(obj.geometry, isWheel ? 28 : EDGE_ANGLE);
      var lines = new THREE.LineSegments(edges, isGlass ? softEdge : edgeMat);
      lines.renderOrder = 3;
      lines.userData.hudLine = true;
      obj.add(lines);
      var major = /body|cab|coachwork|roof|bumper|spoiler/i.test(name);
      if (major) {
        var glow = new THREE.LineSegments(edges, glowMat);
        glow.scale.setScalar(1.012);
        glow.renderOrder = 4;
        glow.userData.hudLine = true;
        obj.add(glow);
        /* grade completa no WireframeGeometry ficou cara no SwiftShader; o EdgesGeometry já marca as arestas. */
      }
    });
  }

  function addLightHints(wrap, accentInt) {
    var hasHead = false, hasTail = false;
    wrap.traverse(function (o) {
      var n = partName(o);
      if (TAIL_RE.test(n) || (o.userData && o.userData.matName === "tail")) hasTail = true;
      else if (LAMP_RE.test(n) || (o.userData && o.userData.matName === "lamp")) hasHead = true;
    });
    if (hasHead && hasTail) return;
    wrap.updateMatrixWorld(true);
    var box = new THREE.Box3().setFromObject(wrap);
    var size = new THREE.Vector3();
    box.getSize(size);
    var y = box.min.y + size.y * 0.30;
    var zF = box.max.z - size.z * 0.015;
    var zR = box.min.z + size.z * 0.02;
    var xOff = size.x * 0.28;
    var headCol = new THREE.Color(accentInt).lerp(new THREE.Color(0xffffff), 0.55);
    var tailCol = new THREE.Color(0xff2244);

    function hint(x, y, z, color, role, w, h, d) {
      var geo = new THREE.BoxGeometry(w, h, d);
      var mat = new THREE.MeshBasicMaterial({
        color: color, transparent: true, opacity: 0.95,
        blending: THREE.AdditiveBlending, depthWrite: false
      });
      mat.userData.role = role;
      var m = new THREE.Mesh(geo, mat);
      m.position.set(x, y, z);
      m.renderOrder = 5;
      var haloMat = new THREE.MeshBasicMaterial({
        color: color, transparent: true, opacity: 0.28,
        blending: THREE.AdditiveBlending, depthWrite: false
      });
      haloMat.userData.role = role;
      var halo = new THREE.Mesh(geo, haloMat);
      halo.scale.set(2.2, 2.0, 2.4);
      m.add(halo);
      wrap.add(m);
    }
    if (!hasHead) {
      hint(xOff, y, zF, headCol, "head", 0.13, 0.055, 0.05);
      hint(-xOff, y, zF, headCol, "head", 0.13, 0.055, 0.05);
    }
    if (!hasTail) {
      hint(xOff, y * 0.98, zR, tailCol, "tail", 0.15, 0.05, 0.045);
      hint(-xOff, y * 0.98, zR, tailCol, "tail", 0.15, 0.05, 0.045);
    }
  }

  function worldToLocal(wrap, obj) {
    var v = new THREE.Vector3();
    obj.updateMatrixWorld(true);
    obj.getWorldPosition(v);
    wrap.worldToLocal(v);
    return v;
  }

  function findNamed(wrap, name) {
    var found = null;
    wrap.traverse(function (o) {
      if (!found && o.name === name) found = o;
    });
    return found;
  }

  function visibleBox(wrap) {
    var box = new THREE.Box3();
    var tmp = new THREE.Box3();
    wrap.updateMatrixWorld(true);
    wrap.traverse(function (o) {
      if (!o.isMesh || !o.visible || !o.geometry || o.userData.hudLine) return;
      if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
      tmp.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld);
      box.union(tmp);
    });
    return box;
  }

  function setAnchors(wrap) {
    wrap.updateMatrixWorld(true);
    var box = visibleBox(wrap);
    if (box.isEmpty()) box = new THREE.Box3().setFromObject(wrap);
    var size = new THREE.Vector3();
    box.getSize(size);
    function loc(x, y, z) {
      return wrap.worldToLocal(new THREE.Vector3(x, y, z));
    }
    var anchors = {
      motor: loc(0.00, box.min.y + size.y * 0.22, box.max.z * 0.96),
      cvt: loc(0.10, box.min.y + size.y * 0.18, (box.min.z + box.max.z) * 0.10),
      battery: loc(-0.42, box.min.y + size.y * 0.26, box.max.z * 0.88),
      wheels: loc(box.min.x * 0.92, box.min.y + size.y * 0.16, box.max.z * 0.62)
    };
    var best = null, bestScore = -1e9;
    wrap.traverse(function (o) {
      if (!o.isMesh || !o.visible || o.userData.hudLine) return;
      var n = ((o.name || "") + " " + (o.parent && o.parent.name || ""));
      if (!/tire|wheel-front/i.test(n)) return;
      var v = worldToLocal(wrap, o);
      if (Math.abs(v.x) < 0.15 || Math.abs(v.z) < 0.2) return;
      /* frente e lado da câmera (−X) */
      var score = v.z * 2 - v.x;
      if (score > bestScore) { bestScore = score; best = v; }
    });
    if (best) anchors.wheels = best;
    wrap.userData.anchors = anchors;
    wrap.userData.box = box;
  }

  function groundAndScale(src) {
    var wrap = new THREE.Group();
    wrap.add(src);
    src.updateMatrixWorld(true);
    var box = new THREE.Box3().setFromObject(src);
    var size = new THREE.Vector3();
    var center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    src.position.x -= center.x;
    src.position.z -= center.z;
    src.position.y -= box.min.y;
    var len = Math.max(size.z, 0.001);
    wrap.scale.setScalar(TARGET_LEN / len);
    return wrap;
  }

  function buildCar(template, accentInt) {
    var src = template.clone(true);
    var wrap = groundAndScale(src);
    stylize(wrap, accentInt);
    addLightHints(wrap, accentInt);
    setAnchors(wrap);
    return wrap;
  }

  function fallbackCar() {
    var g = new THREE.Group();
    g.name = "fallback";
    var body = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.7, 2.6), new THREE.MeshBasicMaterial({ color: 0x000000 }));
    body.position.y = 0.55;
    body.name = "body";
    var cabin = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.45, 1.3), new THREE.MeshBasicMaterial({ color: 0x000000 }));
    cabin.position.set(0, 0.95, -0.15);
    cabin.name = "cabin";
    g.add(body);
    g.add(cabin);
    return g;
  }

  function makeRings(accentInt) {
    var g = new THREE.Group();
    var col = new THREE.Color(accentInt);
    var disc = new THREE.CircleGeometry(1, 32);
    disc.rotateX(-Math.PI / 2);
    var shadowMat = new THREE.MeshBasicMaterial({
      color: 0x00010a, transparent: true, opacity: 0.55, depthWrite: false
    });
    shadowMat.userData.role = "shadow";
    var shadow = new THREE.Mesh(disc, shadowMat);
    shadow.name = "heroGroundShadow";
    shadow.scale.set(1.20, 1, 2.10);
    shadow.position.y = 0.003;
    g.add(shadow);
    var groundMat = new THREE.MeshBasicMaterial({
      color: col, transparent: true, opacity: 0.22,
      blending: THREE.AdditiveBlending, depthWrite: false
    });
    groundMat.userData.role = "ground";
    var glow = new THREE.Mesh(disc, groundMat);
    glow.name = "heroGroundGlow";
    glow.scale.set(1.40, 1, 2.30);
    glow.position.y = 0.006;
    g.add(glow);
    var innerMat = groundMat.clone();
    innerMat.opacity = 0.28;
    innerMat.userData.role = "ground";
    var inner = new THREE.Mesh(disc, innerMat);
    inner.name = "heroGroundInner";
    inner.scale.set(0.88, 1, 1.55);
    inner.position.y = 0.008;
    g.add(inner);
    RING_RADII.forEach(function (r, i) {
      var geo = new THREE.RingGeometry(r - 0.014, r + 0.014, 64);
      var mat = new THREE.MeshBasicMaterial({
        color: col, transparent: true, opacity: 0.70 - i * 0.14,
        side: THREE.DoubleSide, depthWrite: false
      });
      mat.userData.role = "ring";
      var mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.y = 0.012;
      g.add(mesh);
      var tickPts = [];
      var ticks = 20;
      for (var t = 0; t < ticks; t++) {
        var a = (t / ticks) * Math.PI * 2;
        var r0 = r + 0.04, r1 = r + (i === 0 ? 0.10 : 0.13);
        tickPts.push(Math.cos(a) * r0, 0.012, Math.sin(a) * r0, Math.cos(a) * r1, 0.012, Math.sin(a) * r1);
      }
      var tg = new THREE.BufferGeometry();
      tg.setAttribute("position", new THREE.Float32BufferAttribute(tickPts, 3));
      var tmat = new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.38 });
      tmat.userData.role = "ring";
      g.add(new THREE.LineSegments(tg, tmat));
    });
    return g;
  }

  var _state = {
    ready: false,
    loaded: false,
    renderer: null,
    scene: null,
    camera: null,
    car: null,
    rings: null,
    body: "sedan",
    accent: 0x00d8ff,
    rotate: true,
    pausedPage: false,
    perf: false,
    raf: 0,
    last: 0,
    frames: 0,
    fps: 0,
    fpsAccum: 0,
    canvas: null,
    onFrame: null,
    loadToken: 0,
    yawT: 0,
    yawBase: 0.10,
    yawAmp: 0.30,
    hero: null,
    heroEl: null
  };

  function paintAccent(hex) {
    _state.accent = hexToInt(hex);
    if (!_state.scene) return;
    var col = new THREE.Color(_state.accent);
    var fillCol = new THREE.Color(0x03080c);
    fillCol.lerp(col, 0.10);
    var headCol = col.clone().lerp(new THREE.Color(0xffffff), 0.55);
    _state.scene.traverse(function (obj) {
      var mat = obj.material;
      if (!mat || !mat.color) return;
      var role = (mat.userData && mat.userData.role) || "";
      if (role === "tail" || role === "shadow") return;
      if (role === "fill") mat.color.copy(fillCol);
      else if (role === "head") mat.color.copy(headCol);
      else mat.color.copy(col);
    });
  }

  function resize() {
    var c = _state.canvas;
    if (!c || !_state.renderer) return;
    var w = c.clientWidth || 320, h = c.clientHeight || 240;
    var pr = _state.perf ? 1 : Math.min(1.25, window.devicePixelRatio || 1);
    _state.renderer.setPixelRatio(pr);
    _state.renderer.setSize(w, h, false);
    _state.camera.aspect = w / Math.max(1, h);
    _state.camera.updateProjectionMatrix();
    if (_state.hero) layoutHero();
  }

  function loop(now) {
    _state.raf = requestAnimationFrame(loop);
    if (!_state.ready) return;
    var dt = _state.last ? Math.min(0.08, (now - _state.last) / 1000) : 0.016;
    _state.last = now;
    if (_state.rotate && !_state.pausedPage) {
      _state.yawT += dt;
      if (_state.car && !_state.hero) {
        _state.car.rotation.y = _state.yawBase + Math.sin(_state.yawT * 0.45) * _state.yawAmp;
      }
      if (_state.rings && _state.hero) {
        _state.rings.rotation.y += dt * 0.18;
      }
    } else if (_state.car && !_state.hero) {
      _state.car.rotation.y = _state.yawBase;
    }
    _state.renderer.render(_state.scene, _state.camera);
    _state.frames++;
    _state.fpsAccum += dt;
    if (_state.fpsAccum >= 0.5) {
      _state.fps = _state.frames / _state.fpsAccum;
      _state.frames = 0;
      _state.fpsAccum = 0;
    }
    if (_state.onFrame) _state.onFrame();
  }

  function attachCar(tpl) {
    var car = buildCar(tpl, _state.accent);
    if (_state.car && _state.scene) _state.scene.remove(_state.car);
    _state.car = car;
    _state.scene.add(car);
    car.rotation.y = _state.yawBase;
    _state.loaded = true;
  }

  function loadBody(body) {
    var key = MODEL_FILE[body] ? body : "sedan";
    _state.body = key;
    if (_state.hero) {
      _state.loaded = true;
      return;
    }
    var token = ++_state.loadToken;
    _state.loaded = false;
    loadTemplate(key).then(function (tpl) {
      if (token !== _state.loadToken) return;
      attachCar(tpl);
    }).catch(function (err) {
      console.warn("HUD car: falha no modelo Kenney, usando fallback", err);
      if (token !== _state.loadToken) return;
      attachCar(fallbackCar());
    });
    setTimeout(function () {
      Object.keys(MODEL_FILE).forEach(function (b) {
        if (b !== key) loadTemplate(b).catch(function () {});
      });
    }, 2500);
  }

  function mount(canvas, opts) {
    opts = opts || {};
    if (!global.THREE) {
      console.warn("three.js não carregou");
      return null;
    }
    _state.canvas = canvas;
    _state.perf = !!opts.perf;
    _state.rotate = opts.rotate !== false;
    _state.body = opts.body || "sedan";
    _state.accent = hexToInt(opts.accent || "#00D8FF");
    _state.onFrame = opts.onFrame || null;

    var renderer = new THREE.WebGLRenderer({
      canvas: canvas, alpha: true, antialias: false, powerPreference: "high-performance"
    });
    renderer.setClearColor(0x000000, 0);
    renderer.sortObjects = true;
    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(36, 1, 0.1, 48);
    /* 3/4 dianteira, ligeiramente de cima — como o mockup (frente +Z, esquerda −X). */
    camera.position.set(-3.95, 1.68, 4.15);
    camera.lookAt(0, 0.62, 0);

    var rings = makeRings(_state.accent);
    scene.add(rings);

    _state.renderer = renderer;
    _state.scene = scene;
    _state.camera = camera;
    _state.rings = rings;
    _state.car = null;
    _state.ready = true;
    _state.loaded = false;
    resize();
    if (_state.raf) cancelAnimationFrame(_state.raf);
    _state.last = 0;
    loop(performance.now());
    window.addEventListener("resize", resize);
    if (opts.hero && opts.hero.image) setHero(opts.hero);
    else loadBody(_state.body);
    return api;
  }

  function setBody(body) {
    if (!global.THREE || !_state.scene) return;
    if (_state.hero) {
      _state.body = MODEL_FILE[body] ? body : (body || _state.body);
      return;
    }
    var key = MODEL_FILE[body] ? body : "sedan";
    if (key === _state.body && _state.loaded) return;
    loadBody(key);
  }

  function projectWorld(x, y, z) {
    if (!_state.camera || !_state.canvas) return { x: 0, y: 0 };
    var v = new THREE.Vector3(x, y, z);
    v.project(_state.camera);
    var w = _state.canvas.clientWidth, h = _state.canvas.clientHeight;
    return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h };
  }

  function cssUrl(u) { return 'url("' + String(u).replace(/"/g, "\\") + '")'; }

  function ensureHeroEl() {
    if (_state.heroEl) return _state.heroEl;
    var stage = _state.canvas && _state.canvas.parentElement;
    if (!stage) return null;
    var el = document.getElementById("hud-hero");
    if (!el) {
      el = document.createElement("div");
      el.id = "hud-hero";
      el.className = "hud-hero";
      el.setAttribute("aria-hidden", "true");
      el.hidden = true;
      el.innerHTML = '<div class="hud-hero-stack">' +
        '<div class="hud-hero-halo"></div>' +
        '<div class="hud-hero-tint"></div>' +
        '<div class="hud-hero-core"></div>' +
        '<div class="hud-hero-scan"></div></div>';
      var leaders = document.getElementById("hud-leaders");
      stage.insertBefore(el, leaders || null);
    }
    _state.heroEl = el;
    return el;
  }

  function applyHeroMasks(el, hero) {
    var stack = el.querySelector(".hud-hero-stack");
    if (!stack) return;
    var luma = hero.luma || hero.image;
    stack.style.maskImage = cssUrl(luma);
    stack.style.maskMode = "luminance";
    stack.style.maskSize = "100% 100%";
    stack.style.maskRepeat = "no-repeat";
    stack.style.webkitMaskImage = cssUrl(hero.image);
    stack.style.webkitMaskSize = "100% 100%";
    stack.style.webkitMaskRepeat = "no-repeat";
    var core = el.querySelector(".hud-hero-core");
    if (core && hero.core) {
      core.style.maskImage = cssUrl(hero.core);
      core.style.maskMode = "luminance";
      core.style.maskSize = "100% 100%";
      core.style.maskRepeat = "no-repeat";
      core.style.webkitMaskImage = cssUrl(hero.core);
      core.style.webkitMaskSize = "100% 100%";
      core.style.webkitMaskRepeat = "no-repeat";
      core.style.display = "";
    } else if (core) {
      core.style.display = "none";
    }
  }

  function layoutHero() {
    var el = _state.heroEl;
    if (!el || !_state.hero || !_state.canvas || !_state.camera) return;
    var w = _state.canvas.clientWidth, h = _state.canvas.clientHeight;
    if (!w || !h) return;
    var groundY = (typeof _state.hero.ground === "number") ? _state.hero.ground : 0.88;
    var p0 = projectWorld(0, 0.0, 0.15);
    var pL = projectWorld(-1.85, 0.0, 0.55);
    var pR = projectWorld(1.85, 0.0, -1.05);
    var span = Math.abs(pR.x - pL.x);
    var width = Math.max(w * 0.82, Math.min(w * 0.98, span * 1.32));
    var aspect = _state.hero.aspect || (1280 / 720);
    var height = width / aspect;
    if (height > h * 0.98) {
      height = h * 0.98;
      width = height * aspect;
    }
    var left = (w - width) / 2;
    var top = p0.y - groundY * height;
    if (top + height * 0.12 < 0) top = -height * 0.12;
    if (top + height * 0.96 > h) top = h - height * 0.96;
    el.style.width = width + "px";
    el.style.height = height + "px";
    el.style.left = left + "px";
    el.style.top = top + "px";
  }

  function syncHeroAnim() {
    if (!_state.heroEl) return;
    var paused = !_state.rotate || _state.pausedPage;
    _state.heroEl.classList.toggle("is-paused", paused);
    _state.heroEl.classList.toggle("is-perf", !!_state.perf);
  }

  function setHeroGround(heroMode) {
    if (!_state.rings) return;
    var glow = _state.rings.getObjectByName("heroGroundGlow");
    var inner = _state.rings.getObjectByName("heroGroundInner");
    var shadow = _state.rings.getObjectByName("heroGroundShadow");
    if (glow) glow.visible = !heroMode;
    if (inner) inner.visible = !heroMode;
    if (shadow) {
      shadow.visible = true;
      shadow.scale.set(heroMode ? 0.92 : 1.20, 1, heroMode ? 1.50 : 2.10);
      if (shadow.material) shadow.material.opacity = heroMode ? 0.42 : 0.55;
    }
  }

  function setHero(hero) {
    _state.hero = (hero && hero.image) ? hero : null;
    var el = ensureHeroEl();
    if (_state.hero) {
      setHeroGround(true);
      if (el) {
        applyHeroMasks(el, _state.hero);
        el.hidden = false;
        el.setAttribute("aria-hidden", "false");
        layoutHero();
        syncHeroAnim();
      }
      if (_state.car && _state.scene) {
        _state.scene.remove(_state.car);
        _state.car = null;
      }
      _state.loadToken++;
      _state.loaded = true;
    } else if (el) {
      setHeroGround(false);
      el.hidden = true;
      el.setAttribute("aria-hidden", "true");
      if (!_state.car && _state.scene) loadBody(_state.body);
    } else {
      setHeroGround(false);
    }
  }

  function setRotate(on) {
    _state.rotate = !!on;
    syncHeroAnim();
  }

  function projectAnchor(name) {
    if (_state.hero && _state.heroEl && _state.canvas) {
      var a = (_state.hero.anchors || {})[name];
      if (!a || a.x == null || a.y == null) return null;
      var r = _state.heroEl.getBoundingClientRect();
      var cr = _state.canvas.getBoundingClientRect();
      return {
        x: r.left - cr.left + Number(a.x) * r.width,
        y: r.top - cr.top + Number(a.y) * r.height,
        visible: true
      };
    }
    if (!_state.car || !_state.camera || !_state.canvas) return null;
    var local = _state.car.userData.anchors && _state.car.userData.anchors[name];
    if (!local) return null;
    var v = local.clone();
    _state.car.updateMatrixWorld();
    v.applyMatrix4(_state.car.matrixWorld);
    v.project(_state.camera);
    var w = _state.canvas.clientWidth, h = _state.canvas.clientHeight;
    return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h, visible: v.z < 1 };
  }

  var api = {
    mount: mount,
    setAccent: paintAccent,
    setRotate: setRotate,
    setYaw: function (rad) {
      _state.yawBase = rad;
      _state.yawT = 0;
      if (_state.car) _state.car.rotation.y = rad;
    },
    setPerf: function (on) { _state.perf = !!on; syncHeroAnim(); resize(); },
    setBody: setBody,
    setHero: setHero,
    setPageActive: function (on) { _state.pausedPage = !on; syncHeroAnim(); },
    projectAnchor: projectAnchor,
    fps: function () { return _state.fps; },
    resize: resize,
    ready: function () { return _state.ready; },
    loaded: function () { return _state.loaded; },
    debugAnchors: function () {
      var out = {};
      ["motor", "cvt", "battery", "wheels"].forEach(function (n) {
        var a = _state.car && _state.car.userData.anchors && _state.car.userData.anchors[n];
        out[n] = { local: a && [a.x, a.y, a.z], proj: projectAnchor(n) };
      });
      return out;
    }
  };

  global.LancerHUDCar = api;
})(window);

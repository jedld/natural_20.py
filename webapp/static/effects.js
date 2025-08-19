const Effects = {
  // store active effect instances
  _instances: {},

  // Broadcast handler registration
  initSocketHandlers: function (socket) {
    socket.on('effect:set', function (data) {
      // data = { effect: 'fog', action: 'start'|'stop'|'update', config: {...} }
      console.log('effect:set', data);
      if (data.action === 'start') {
        // When starting a new effect, stop any other active effects so switching
        // effects disables the previous ones (fog <-> rain exclusive behavior).
        Object.keys(Effects._instances).forEach(function(k){
          try { if (k !== data.effect && Effects._instances[k]) Effects._instances[k].stop(); } catch(e){}
          try { delete Effects._instances[k]; } catch(e){}
        });
        if (data.effect === 'fog') {
          Effects._instances.fog = Effects.createFogEffect(data.config || {});
        }
        if (data.effect === 'rain') {
          Effects._instances.rain = Effects.createRainEffect(data.config || {});
        }
        if (data.effect === 'snow') {
          Effects._instances.snow = Effects.createSnowEffect(data.config || {});
        }
        if (data.effect === 'water') {
          Effects._instances.water = Effects.createWaterEffect(data.config || {});
        }
      } else if (data.action === 'stop') {
        if (Effects._instances[data.effect]) {
          Effects._instances[data.effect].stop();
          delete Effects._instances[data.effect];
        }
      } else if (data.action === 'update') {
        if (data.effect === 'fog' && Effects._instances.fog) {
          Effects._instances.fog.updateConfig(data.config || {});
        }
        if (data.effect === 'rain' && Effects._instances.rain) {
          Effects._instances.rain.updateConfig(data.config || {});
        }
        if (data.effect === 'snow' && Effects._instances.snow) {
          Effects._instances.snow.updateConfig(data.config || {});
        }
        if (data.effect === 'water' && Effects._instances.water) {
          Effects._instances.water.updateConfig(data.config || {});
        }
      }
    });
  },

  // Apply an effect locally (used for map-default effects)
  applyEffect: function(data) {
    // data = { effect: 'fog'|'rain', action: 'start'|'stop'|'update', config: {...} }
    if (!data || !data.effect || !data.action) return;
    if (data.action === 'start') {
      // stop others
      Object.keys(Effects._instances).forEach(function(k){ try{ if (k !== data.effect && Effects._instances[k]) Effects._instances[k].stop(); }catch(e){} try{ delete Effects._instances[k]; }catch(e){} });
  if (data.effect === 'fog') Effects._instances.fog = Effects.createFogEffect(data.config || {});
  if (data.effect === 'rain') Effects._instances.rain = Effects.createRainEffect(data.config || {});
  if (data.effect === 'snow') Effects._instances.snow = Effects.createSnowEffect(data.config || {});
  if (data.effect === 'water') Effects._instances.water = Effects.createWaterEffect(data.config || {});
    } else if (data.action === 'stop') {
      if (Effects._instances[data.effect]) { Effects._instances[data.effect].stop(); delete Effects._instances[data.effect]; }
    } else if (data.action === 'update') {
      if (data.effect === 'fog' && Effects._instances.fog) Effects._instances.fog.updateConfig(data.config || {});
      if (data.effect === 'rain' && Effects._instances.rain) Effects._instances.rain.updateConfig(data.config || {});
  if (data.effect === 'snow' && Effects._instances.snow) Effects._instances.snow.updateConfig(data.config || {});
  if (data.effect === 'water' && Effects._instances.water) Effects._instances.water.updateConfig(data.config || {});
    }
  },

  // Stop and remove all active effects
  stopAll: function() {
    try {
      Object.keys(Effects._instances).forEach(function(k){
        try { if (Effects._instances[k]) Effects._instances[k].stop(); } catch(e) {}
        try { delete Effects._instances[k]; } catch(e) {}
      });
    } catch (e) { /* no-op */ }
  },

  // Internal helper: build a fog-of-war visibility mask for a given overlay.
  // White (opaque) where tiles are visible, transparent where fog-of-war hides tiles.
  // The mask automatically updates on tile/size changes and window resizes.
  _buildFoWMaskForOverlay: function(overlay, options) {
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    var tilesRoot = document.querySelector('.tiles-container');
    var container = document.querySelector('.image-container') || document.body;
    var mo = null; var ro = null; var dirty = true;
    var _opts = options || {}; // { featherPx?: number }

    function markDirty(){ dirty = true; }

    function rebuild(){
      try {
        // Match overlay pixel buffer size
        var ow = Math.max(1, overlay.width || overlay.clientWidth || 1);
        var oh = Math.max(1, overlay.height || overlay.clientHeight || 1);
        canvas.width = ow; canvas.height = oh;
        ctx.clearRect(0,0,ow,oh);

  // Map DOM pixels to overlay pixels taking DPR and overlay rect into account
  var overlayRect = overlay.getBoundingClientRect();
  var scaleX = ow / Math.max(1, overlayRect.width || 1);
  var scaleY = oh / Math.max(1, overlayRect.height || 1);

        // Draw onto an offscreen canvas to allow feathered edges
        var off = document.createElement('canvas');
        off.width = ow; off.height = oh;
        var octx = off.getContext('2d');
        octx.clearRect(0,0,ow,oh);
        // Fill visible tiles (no .fog-of-war child) as white
        var tiles = document.querySelectorAll('.tile');
        octx.fillStyle = '#ffffff';
        for (var i=0; i<tiles.length; i++){
          var tile = tiles[i];
          if (tile.querySelector('.fog-of-war')) continue; // hidden
          var r = tile.getBoundingClientRect();
          var x = (r.left - overlayRect.left) * scaleX;
          var y = (r.top - overlayRect.top) * scaleY;
          var w = r.width * scaleX;
          var h = r.height * scaleY;
          if (x > ow || y > oh || x + w < 0 || y + h < 0) continue;
          octx.fillRect(Math.round(x), Math.round(y), Math.ceil(w), Math.ceil(h));
        }
        // Composite with optional blur for smoother transition
        var feather = Math.max(0, _opts.featherPx || 0);
        ctx.clearRect(0,0,ow,oh);
        if (feather > 0) ctx.filter = 'blur(' + feather + 'px)';
        ctx.drawImage(off, 0, 0);
        if (feather > 0) ctx.filter = 'none';
        dirty = false;
      } catch(e) {
        // On any failure, keep mask fully opaque rather than breaking effects
        canvas.width = Math.max(1, overlay.width || 1);
        canvas.height = Math.max(1, overlay.height || 1);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0,0,canvas.width, canvas.height);
        dirty = false;
      }
    }

    // Observe tile DOM for changes that may affect FoW
    if (tilesRoot) {
      try { mo = new MutationObserver(markDirty); mo.observe(tilesRoot, { childList:true, attributes:true, subtree:true }); } catch(e) {}
    }
    // Observe overlay/container resizes
    try { ro = new ResizeObserver(markDirty); ro.observe(overlay); if (container) ro.observe(container); } catch(e) {}
    window.addEventListener('resize', markDirty);

    return {
      setOptions: function(newOpts){ _opts = newOpts || {}; dirty = true; },
      update: function(){ if (dirty) rebuild(); return { canvas: canvas, changed: dirty === false }; },
      // Slightly different contract: call force to guarantee rebuild next read
      force: function(){ dirty = true; },
      destroy: function(){ try{ if (mo) mo.disconnect(); }catch(e){} try{ if (ro) ro.disconnect(); }catch(e){} window.removeEventListener('resize', markDirty); }
    };
  },

  // Internal helper: build a manual mask from config.mask_layers (grid-based shapes).
  // Currently supports type: 'rectangle' with position [x,y] and size [w,h] in tile units.
  _buildManualMaskForOverlay: function(overlay, layers, options) {
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    var tilesRoot = document.querySelector('.tiles-container');
    var container = document.querySelector('.image-container') || document.body;
    var _layers = Array.isArray(layers) ? layers.slice() : (layers ? [layers] : []);
    var mo = null; var ro = null; var dirty = true;
    var _opts = options || {}; // { featherPx?: number }

    function setLayers(newLayers){ _layers = Array.isArray(newLayers) ? newLayers.slice() : (newLayers ? [newLayers] : []); dirty = true; }
    function setOptions(newOpts){ _opts = newOpts || {}; dirty = true; }
    function markDirty(){ dirty = true; }

    function fillTileRect(tile, overlayRect, scaleX, scaleY){
      var r = tile.getBoundingClientRect();
      var x = (r.left - overlayRect.left) * scaleX;
      var y = (r.top - overlayRect.top) * scaleY;
      var w = r.width * scaleX;
      var h = r.height * scaleY;
      if (!(x > canvas.width || y > canvas.height || x + w < 0 || y + h < 0))
        ctx.fillRect(Math.round(x), Math.round(y), Math.ceil(w), Math.ceil(h));
    }

    function rebuild(){
      var ow = Math.max(1, overlay.width || overlay.clientWidth || 1);
      var oh = Math.max(1, overlay.height || overlay.clientHeight || 1);
      canvas.width = ow; canvas.height = oh;
      ctx.clearRect(0,0,ow,oh);
      if (!_layers || _layers.length === 0) { // no restriction, full pass-through
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0,0,ow,oh);
        dirty = false; return;
      }
      var overlayRect = overlay.getBoundingClientRect();
      var scaleX = ow / Math.max(1, overlayRect.width || 1);
      var scaleY = oh / Math.max(1, overlayRect.height || 1);
      // draw union of shapes to offscreen for optional feather
      var off = document.createElement('canvas');
      off.width = ow; off.height = oh;
      var octx = off.getContext('2d');
      octx.fillStyle = '#ffffff';
      // draw union of shapes by tile lookup
      try {
        for (var li=0; li<_layers.length; li++){
          var L = _layers[li] || {};
          if ((L.type || L.kind) === 'rectangle'){
            var pos = L.position || L.pos || [0,0];
            var size = L.size || [0,0];
            var x0 = pos[0]||0, y0 = pos[1]||0;
            var w = size[0]||0, h = size[1]||0;
            for (var y=y0; y<y0+h; y++){
              for (var x=x0; x<x0+w; x++){
                var sel = '.tile[data-coords-x="'+x+'"][data-coords-y="'+y+'"]';
                var tile = document.querySelector(sel);
                if (tile) {
                  var r = tile.getBoundingClientRect();
                  var px = (r.left - overlayRect.left) * scaleX;
                  var py = (r.top - overlayRect.top) * scaleY;
                  var pw = r.width * scaleX;
                  var ph = r.height * scaleY;
                  octx.fillRect(Math.round(px), Math.round(py), Math.ceil(pw), Math.ceil(ph));
                }
              }
            }
          } else if ((L.type || L.kind) === 'polygon' || (L.type || L.kind) === 'poly') {
            var pts = L.points || L.vertices || [];
            if (pts.length >= 3) {
              octx.beginPath();
              for (var pi=0; pi<pts.length; pi++){
                var pt = pts[pi] || [0,0];
                var tx = pt[0], ty = pt[1];
                var sel = '.tile[data-coords-x="'+tx+'"][data-coords-y="'+ty+'"]';
                var tile = document.querySelector(sel);
                if (!tile) continue;
                var r = tile.getBoundingClientRect();
                var cx = (r.left - overlayRect.left) * scaleX + (r.width * scaleX) / 2;
                var cy = (r.top - overlayRect.top) * scaleY + (r.height * scaleY) / 2;
                if (pi === 0) octx.moveTo(cx, cy); else octx.lineTo(cx, cy);
              }
              octx.closePath();
              octx.fill();
            }
          }
        }
      } catch(e) {
        // on error, default to full pass-through rather than hide all
        ctx.clearRect(0,0,ow,oh);
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0,0,ow,oh);
      }
      // Composite with optional feather blur
      var feather = Math.max(0, _opts.featherPx || 0);
      if (feather > 0) ctx.filter = 'blur(' + feather + 'px)';
      ctx.drawImage(off, 0, 0);
      if (feather > 0) ctx.filter = 'none';
      dirty = false;
    }

    // watch tiles and overlay/container for changes
    if (tilesRoot) { try { mo = new MutationObserver(markDirty); mo.observe(tilesRoot, { childList:true, attributes:true, subtree:true }); } catch(e) {} }
    try { var ro = new ResizeObserver(markDirty); ro.observe(overlay); if (container) ro.observe(container); } catch(e) {}
    window.addEventListener('resize', markDirty);

    return {
      setLayers: setLayers,
      setOptions: setOptions,
      update: function(){ if (dirty) rebuild(); return { canvas: canvas, changed: dirty === false }; },
      force: function(){ dirty = true; },
      destroy: function(){ try{ mo && mo.disconnect(); }catch(e){} try{ ro && ro.disconnect(); }catch(e){} window.removeEventListener('resize', markDirty); }
    };
  },

  createRainEffect: function (config) {
    config = config || {};
    var intensity = config.intensity != null ? config.intensity : 0.6; // 0..1
    var wind = config.wind != null ? config.wind : 0.0; // -1..1 horizontal drift
    var speed = config.speed != null ? config.speed : 1.0;
    var color = config.color || '#a8c0e6';
  var lightning = config.lightning || false;
    var lightningFreq = config.lightningFreq || 0.01; // chance per second
    var lightningIntensity = config.lightningIntensity || 1.0;
  var useManualMask = !!config.mask;
  var manualMaskLayers = config.mask_layers || config.mask_layer || [];
  var maskFeatherPx = Math.max(0, config.mask_feather || 0);
  var reflection = (config.reflection != null ? config.reflection : 0.6); // 0..1

    // Attach overlay to the battlemap container so effect aligns to the map image
    var container = document.querySelector('.image-container') || document.body;
    var overlay = container.querySelector('#effects-overlay-rain');
    if (!overlay) {
      overlay = document.createElement('canvas');
      overlay.id = 'effects-overlay-rain';
      overlay.style.position = 'absolute';
      overlay.style.left = '0';
      overlay.style.top = '0';
      overlay.style.pointerEvents = 'none';
      overlay.style.zIndex = 2000;
      container.appendChild(overlay);
    }

    function getMapElement(){ return document.querySelector('.image-container img.background-image, .image-container img'); }
    function getMapRect(){
      var img = getMapElement();
      var cRect = container.getBoundingClientRect();
      if (img) {
        var r = img.getBoundingClientRect();
        return { left: Math.round(r.left - cRect.left), top: Math.round(r.top - cRect.top), width: Math.round(r.width), height: Math.round(r.height) };
      }
      return { left: 0, top: 0, width: container.clientWidth, height: container.clientHeight };
    }

    function resize() {
      var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
      var rect = getMapRect();
      overlay.style.left = rect.left + 'px';
      overlay.style.top = rect.top + 'px';
      overlay.style.width = rect.width + 'px';
      overlay.style.height = rect.height + 'px';
      overlay.width = Math.floor(rect.width * dpr);
      overlay.height = Math.floor(rect.height * dpr);
    }
    resize();
    window.addEventListener('resize', resize);
    var ro = new ResizeObserver(resize);
    try { ro.observe(container); } catch (e) {}

  var gl = null;
  try { gl = overlay.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: true }) || overlay.getContext('experimental-webgl', { antialias: true, alpha: true, premultipliedAlpha: true }); } catch (e) { gl = null; }

    // helper to parse color
    function rgbFromHex(hex) {
      var r = parseInt(hex.slice(1,3),16)/255;
      var g = parseInt(hex.slice(3,5),16)/255;
      var b = parseInt(hex.slice(5,7),16)/255;
      return [r,g,b];
    }

    if (gl) {
      // Vertex + fragment shader: render streaked rain via FBM and directional bias.
      var vertexSrc = '\n      attribute vec2 a_position;\n      varying vec2 v_uv;\n      void main() { v_uv = a_position * 0.5 + 0.5; gl_Position = vec4(a_position, 0.0, 1.0); }\n    ';
  var fragSrc = `
      precision mediump float;
      varying vec2 v_uv;
      uniform vec2 u_resolution;
      uniform float u_time;
      uniform float u_intensity;
      uniform float u_wind;
      uniform float u_speed;
      uniform vec3 u_color;
      uniform float u_lightning;
  uniform sampler2D u_map;
  uniform sampler2D u_manual;
  uniform sampler2D u_fow;

      // simple hash / random
      float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }

      // rotate a vector by angle a
      mat2 rot(float a){ float c = cos(a); float s = sin(a); return mat2(c, -s, s, c); }

      void main(){
        vec2 res = u_resolution;
        // scale uv to keep consistent drop density regardless of aspect
        vec2 uv = v_uv * (res / min(res.x, res.y));
        float t = u_time * 0.001 * u_speed;

        // drop direction (points down, tilt by wind)
        vec2 dir = normalize(vec2(u_wind * 0.6, 1.0));
        vec2 perp = vec2(-dir.y, dir.x);

        // density controls tiling of pseudo-random drop grid
        float density = mix(18.0, 60.0, clamp(u_intensity, 0.0, 1.0));
        vec2 p = uv * density;

        vec3 baseCol = u_color;
        float accum = 0.0;
        float highlight = 0.0;

        // iterate nearby cells to render drops
        for(int oy=-1; oy<=1; oy++){
          for(int ox=-1; ox<=1; ox++){
            vec2 cell = floor(p) + vec2(float(ox), float(oy));
            vec2 id = cell;
            // pseudo-random seed per cell
            float seed = hash(id);
            // drop jitter within cell
            vec2 jitter = vec2(hash(id + 1.0), hash(id + 2.0)) - 0.5;
            // position of this drop in cell space
            vec2 dropPos = (cell + 0.5 + jitter) / density;
            // animate vertical offset so drops fall
            float fall = mod((t * (0.5 + seed*1.5) + seed*17.0), 1.0);
            dropPos += dir * (-fall * 1.2);

            // convert to normalized uv space for evaluation
            vec2 d = v_uv - dropPos;
            // project into local coordinates along dir/perp
            float along = dot(d, dir);
            float across = dot(d, perp);

            // drop shape: long in 'along' direction, thin in 'across'
            float length = mix(0.02, 0.12, seed) * (1.2 + u_intensity);
            float thickness = mix(0.002, 0.01, seed) * (0.5 + u_intensity*1.5);

            // taper along length (front is brighter)
            float head = smoothstep(length*0.4, 0.0, abs(along));
            float tail = smoothstep(0.0, -length, along);

            // alpha shaped by perpendicular falloff and along taper
            float a = smoothstep(thickness, 0.0, abs(across)) * smoothstep(0.0, length, -along);
            // make small round head brightness
            float headMask = exp(-pow((across/(thickness*0.8)),2.0)) * smoothstep(length*0.6, 0.0, abs(along));

            accum += a * (0.8 + 0.6*head);
            highlight += headMask * (0.6 + 0.8*seed);
          }
        }

        accum = clamp(accum * u_intensity * 1.6, 0.0, 1.0);
        highlight = clamp(highlight * u_intensity * 1.8, 0.0, 1.0);

        // lightning boost
        float lightningBoost = u_lightning;

  // sample map alpha to mask and FoW to hide hidden tiles
        float mapA = 1.0;
        #ifdef GL_ES
        mapA = texture2D(u_map, v_uv).a;
        #else
        mapA = texture(u_map, v_uv).a;
        #endif
  float fowA = 1.0;
  #ifdef GL_ES
  fowA = texture2D(u_fow, v_uv).a;
  #else
  fowA = texture(u_fow, v_uv).a;
  #endif
  float manualA = 1.0;
  #ifdef GL_ES
  manualA = texture2D(u_manual, v_uv).a;
  #else
  manualA = texture(u_manual, v_uv).a;
  #endif

        // final color: base color plus white highlights
        vec3 col = baseCol * accum + vec3(1.0) * highlight * 0.6 + vec3(lightningBoost);
  float alpha = clamp(accum * mapA * fowA * manualA, 0.0, 0.95);
        gl_FragColor = vec4(col, alpha);
      }
      `;

      function compileShader(src, type) {
        var s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.warn(gl.getShaderInfoLog(s));
        return s;
      }

      var program = gl.createProgram();
      gl.attachShader(program, compileShader(vertexSrc, gl.VERTEX_SHADER));
      gl.attachShader(program, compileShader(fragSrc, gl.FRAGMENT_SHADER));
      gl.linkProgram(program);

      var positionLoc = gl.getAttribLocation(program, 'a_position');
      var resLoc = gl.getUniformLocation(program, 'u_resolution');
      var timeLoc = gl.getUniformLocation(program, 'u_time');
      var intensityLoc = gl.getUniformLocation(program, 'u_intensity');
      var windLoc = gl.getUniformLocation(program, 'u_wind');
      var speedLoc = gl.getUniformLocation(program, 'u_speed');
      var colorLoc = gl.getUniformLocation(program, 'u_color');
      var lightningLoc = gl.getUniformLocation(program, 'u_lightning');
  var mapLoc = gl.getUniformLocation(program, 'u_map');
  var fowLoc = gl.getUniformLocation(program, 'u_fow');
  var manualLoc = gl.getUniformLocation(program, 'u_manual');

      var buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
      gl.useProgram(program);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

      // map texture
  var mapTexture = null;
      var mapImageEl = document.querySelector('.image-container img.background-image, .image-container img');
    function createMapTexture() {
        if (!gl || !mapImageEl || !mapImageEl.complete) return;
        if (!mapTexture) mapTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, mapTexture);
        try {
      var c = document.createElement('canvas');
      c.width = overlay.width; c.height = overlay.height;
      var ctx2 = c.getContext('2d');
      ctx2.drawImage(mapImageEl, 0, 0, c.width, c.height);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        } catch (e) {
      var c2 = document.createElement('canvas');
      c2.width = overlay.width; c2.height = overlay.height;
      var ctx3 = c2.getContext('2d');
      ctx3.drawImage(mapImageEl, 0, 0, c2.width, c2.height);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c2);
        }
        gl.bindTexture(gl.TEXTURE_2D, null);
      }
      if (mapImageEl) {
        if (mapImageEl.complete) createMapTexture();
        else mapImageEl.addEventListener('load', createMapTexture);
        try { new ResizeObserver(function(){ createMapTexture(); }).observe(mapImageEl); } catch(e) {}
      }

  var start = Date.now();
      var running = true;
      var lightningStrength = 0.0;
      var lastLightning = 0;
  var _lastOverlayW = overlay.width, _lastOverlayH = overlay.height;
  var manualHelper = Effects._buildManualMaskForOverlay(overlay, manualMaskLayers, { featherPx: maskFeatherPx });
  var manualTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, manualTexture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1,1,0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);

  // FoW mask resources
  var fowHelper = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPx });
  var fowTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, fowTexture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);

      function frame() {
  if (!running) return;
  gl.viewport(0, 0, overlay.width, overlay.height);
        gl.clearColor(0,0,0,0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.useProgram(program);
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);
        gl.uniform2f(resLoc, overlay.width, overlay.height);
        gl.uniform1f(timeLoc, Date.now() - start);
        gl.uniform1f(intensityLoc, intensity);
        gl.uniform1f(windLoc, wind);
        gl.uniform1f(speedLoc, speed);
        var rgb = rgbFromHex(color);
        gl.uniform3f(colorLoc, rgb[0], rgb[1], rgb[2]);

        // lightning simulation (probabilistic)
        if (lightning) {
          var now = Date.now();
          var secondsSinceLast = (now - lastLightning) / 1000.0;
          if (Math.random() < lightningFreq * secondsSinceLast) {
            lightningStrength = 0.6 + Math.random() * lightningIntensity;
            lastLightning = now;
          }
          // decay
          lightningStrength *= 0.96;
        } else {
          lightningStrength = 0.0;
        }
        gl.uniform1f(lightningLoc, lightningStrength);

        if (mapTexture) {
          // Recreate map texture if overlay size changed
          if (overlay.width !== _lastOverlayW || overlay.height !== _lastOverlayH) {
            _lastOverlayW = overlay.width; _lastOverlayH = overlay.height;
            try { createMapTexture(); } catch(e) {}
          }
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, mapTexture);
          gl.uniform1i(mapLoc, 0);
        }

        // Update and bind FoW texture (unit 1)
        try {
          var upd = fowHelper.update();
          if (upd && upd.canvas) {
            gl.activeTexture(gl.TEXTURE1);
            gl.bindTexture(gl.TEXTURE_2D, fowTexture);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, upd.canvas);
            gl.uniform1i(fowLoc, 1);
          }
        } catch(e) {}
        // Update and bind Manual mask (unit 2)
        try {
          manualHelper.setLayers(manualMaskLayers);
          if (manualHelper.setOptions) manualHelper.setOptions({ featherPx: maskFeatherPx });
          if (fowHelper.setOptions) fowHelper.setOptions({ featherPx: maskFeatherPx });
          var updM = manualHelper.update();
          if (updM && updM.canvas) {
            gl.activeTexture(gl.TEXTURE2);
            gl.bindTexture(gl.TEXTURE_2D, manualTexture);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, updM.canvas);
            gl.uniform1i(manualLoc, 2);
          }
        } catch(e) {}

        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        requestAnimationFrame(frame);
      }

      requestAnimationFrame(frame);

      return {
  stop: function(){ running = false; try{ gl.getExtension('WEBGL_lose_context').loseContext(); }catch(e){} overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} try{ fowHelper && fowHelper.destroy(); }catch(e){} try{ manualHelper && manualHelper.destroy(); }catch(e){} },
  updateConfig: function(c){ intensity = c.intensity != null ? c.intensity : intensity; wind = c.wind != null ? c.wind : wind; speed = c.speed != null ? c.speed : speed; color = c.color || color; lightning = c.lightning != null ? c.lightning : lightning; lightningFreq = c.lightningFreq || lightningFreq; lightningIntensity = c.lightningIntensity || lightningIntensity; useManualMask = c.mask != null ? !!c.mask : useManualMask; manualMaskLayers = c.mask_layers || manualMaskLayers; maskFeatherPx = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPx)); manualHelper.setLayers(manualMaskLayers); if (manualHelper.setOptions) manualHelper.setOptions({ featherPx: maskFeatherPx }); if (fowHelper.setOptions) fowHelper.setOptions({ featherPx: maskFeatherPx }); }
      };
    }

    // Canvas fallback: streaked rain + lightning flashes
  var ctx = overlay.getContext('2d');
    var running = true;
    var drops = [];
  // FoW mask (2D path)
  var fow2D = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPx });
  var manual2D = Effects._buildManualMaskForOverlay(overlay, manualMaskLayers, { featherPx: maskFeatherPx });
    var W = overlay.width, H = overlay.height;
    function makeDrop() {
      // tapered drop: head is brighter and slightly larger
      var baseLen = 12 + Math.random()*30;
      var seed = Math.random();
      return {
        x: Math.random()*W,
        y: Math.random()*H,
        len: baseLen * (0.8 + seed*1.2),
        speed: 2 + Math.random()*8,
        w: 1 + Math.random()*1.2,
        tilt: -0.6 + wind*0.6 + (Math.random()-0.5)*0.2,
        headSize: 1.0 + seed*2.5,
        seed: seed
      };
    }
    for (var i=0;i<Math.floor(220*intensity);i++) drops.push(makeDrop());
    var lightningAlpha = 0.0;

    function draw() {
      if (!running) return;
      ctx.clearRect(0,0,overlay.width, overlay.height);
      ctx.globalCompositeOperation = 'source-over';

      // softly fade previous frame to smooth trails (gives motion blur feel)
      ctx.fillStyle = 'rgba(0,0,0,0)';
      // draw tapered drops
      for (var i=0;i<drops.length;i++){
        var d = drops[i];
        // compute end point based on tilt and length
        var nx = d.x + Math.cos(d.tilt) * d.len;
        var ny = d.y + Math.sin(d.tilt) * d.len + d.len*0.15;

        // draw tail (semi-transparent) with gradient for taper
        var grad = ctx.createLinearGradient(d.x, d.y, nx, ny);
        var c = color;
        grad.addColorStop(0, `rgba(0,0,0,0)`);
        grad.addColorStop(0.6, `rgba(0,0,0,0)`);
        grad.addColorStop(1, c);
        ctx.strokeStyle = c;
        ctx.lineWidth = Math.max(0.6, d.w * 0.6);
        ctx.beginPath();
        ctx.moveTo(d.x, d.y);
        ctx.lineTo(nx, ny);
        ctx.stroke();

        // draw bright head (small ellipse) to simulate water glint
        ctx.beginPath();
        ctx.fillStyle = `rgba(255,255,255,${0.15 + 0.35 * d.seed})`;
        ctx.ellipse(d.x, d.y, d.headSize, d.headSize*0.6, d.tilt, 0, Math.PI*2);
        ctx.fill();

        // subtle motion: move along tilt
        d.x += Math.cos(d.tilt) * d.speed * (0.6 + speed*0.4) + wind * (0.3 + d.seed*0.7);
        d.y += Math.sin(d.tilt) * d.speed * (0.6 + speed*0.4);

        // recycle drops that moved off screen
        if (d.y > H + 50 || d.x < -60 || d.x > W + 60) {
          d.x = Math.random()*W;
          d.y = -10 - Math.random()*80;
          d.len = 12 + Math.random()*40;
          d.speed = 2 + Math.random()*8;
          d.w = 1 + Math.random()*1.2;
          d.tilt = -0.6 + wind*0.6 + (Math.random()-0.5)*0.2;
          d.headSize = 1.0 + Math.random()*2.5;
          d.seed = Math.random();
        }
      }

      // lightning: probabilistic flash
      if (lightning && Math.random() < lightningFreq) {
        lightningAlpha = 0.5 + Math.random()*0.6*lightningIntensity;
      }
      if (lightningAlpha > 0.01) {
        ctx.fillStyle = `rgba(255,255,255,${lightningAlpha})`;
        ctx.fillRect(0,0,overlay.width, overlay.height);
        lightningAlpha *= 0.9;
      }

      // mask by map image using destination-in for alpha preservation
      var mapEl = document.querySelector('.image-container img.background-image, .image-container img');
      if (mapEl && mapEl.complete) {
        try {
          var tx = document.createElement('canvas');
          tx.width = overlay.width; tx.height = overlay.height;
          var tctx = tx.getContext('2d');
          tctx.drawImage(mapEl, 0, 0, overlay.width, overlay.height);
          ctx.globalCompositeOperation = 'destination-in';
          ctx.drawImage(tx, 0, 0);
          ctx.globalCompositeOperation = 'source-over';
        } catch (e) {
          // if drawImage fails, skip masking
        }
      }

      // Apply Manual mask (2D)
      if (useManualMask) {
        try {
          if (manual2D.setLayers) manual2D.setLayers(manualMaskLayers);
          if (manual2D.setOptions) manual2D.setOptions({ featherPx: maskFeatherPx });
          var man = manual2D.update();
          if (man && man.canvas) {
            ctx.globalCompositeOperation = 'destination-in';
            ctx.drawImage(man.canvas, 0, 0);
            ctx.globalCompositeOperation = 'source-over';
          }
        } catch(e) {}
      }

      // Apply FoW mask to hide hidden tiles
      try {
        var upd = fow2D.update();
        if (upd && upd.canvas) {
          ctx.globalCompositeOperation = 'destination-in';
          ctx.drawImage(upd.canvas, 0, 0);
          ctx.globalCompositeOperation = 'source-over';
        }
      } catch(e) {}

      requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);

    return {
  stop: function(){ running = false; overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try { ro.disconnect(); } catch(e) {} try{ fow2D && fow2D.destroy(); }catch(e){} },
      updateConfig: function(c){ intensity = c.intensity != null ? c.intensity : intensity; wind = c.wind != null ? c.wind : wind; speed = c.speed != null ? c.speed : speed; color = c.color || color; lightning = c.lightning != null ? c.lightning : lightning; lightningFreq = c.lightningFreq || lightningFreq; lightningIntensity = c.lightningIntensity || lightningIntensity; }
    };
  },
  
  createSnowEffect: function (config) {
    config = config || {};
    var intensity = config.intensity != null ? config.intensity : 0.6; // 0..1
    var wind = config.wind != null ? config.wind : 0.0; // -1..1
    var speed = config.speed != null ? config.speed : 1.0; // 0..2
    var color = config.color || '#ffffff';
    var flakeSize = config.flakeSize != null ? config.flakeSize : 1.0; // scales size
    var turbulence = config.turbulence != null ? config.turbulence : 0.35; // side sway

  // Optional realism controls
  var gusts = !!config.gusts; // enable stochastic gusts
  var gustFreq = config.gustFreq != null ? config.gustFreq : 0.04; // chance per second
  var gustStrength = config.gustStrength != null ? config.gustStrength : 0.5; // 0..1
  var gustDuration = config.gustDuration != null ? config.gustDuration : 1.8; // seconds
  var dof = config.dof != null ? config.dof : 0.35; // depth-of-field amount for distant layers
  var accumulationEnabled = !!config.accumulationEnabled;
  var accumulationRate = config.accumulationRate != null ? config.accumulationRate : 0.02; // per second
  var accumulationMax = config.accumulationMax != null ? config.accumulationMax : 0.35; // 0..1
  var accumulationColor = config.accumulationColor || '#ffffff';
  var useManualMaskSnow = !!config.mask;
  var manualMaskLayersSnow = config.mask_layers || config.mask_layer || [];
  var maskFeatherPxSnow = Math.max(0, config.mask_feather || 0);

    // Attach overlay to the battlemap container
    var container = document.querySelector('.image-container') || document.body;
    var overlay = container.querySelector('#effects-overlay-snow');
    if (!overlay) {
      overlay = document.createElement('canvas');
      overlay.id = 'effects-overlay-snow';
      overlay.style.position = 'absolute';
      overlay.style.left = '0';
      overlay.style.top = '0';
      overlay.style.pointerEvents = 'none';
      overlay.style.zIndex = 2000;
      container.appendChild(overlay);
    }

    function getMapElement(){ return document.querySelector('.image-container img.background-image, .image-container img'); }
    function getMapRect(){
      var img = getMapElement();
      var cRect = container.getBoundingClientRect();
      if (img) {
        var r = img.getBoundingClientRect();
        return { left: Math.round(r.left - cRect.left), top: Math.round(r.top - cRect.top), width: Math.round(r.width), height: Math.round(r.height) };
      }
      return { left: 0, top: 0, width: container.clientWidth, height: container.clientHeight };
    }

    function resize() {
      var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
      var rect = getMapRect();
      overlay.style.left = rect.left + 'px';
      overlay.style.top = rect.top + 'px';
      overlay.style.width = rect.width + 'px';
      overlay.style.height = rect.height + 'px';
      overlay.width = Math.floor(rect.width * dpr);
      overlay.height = Math.floor(rect.height * dpr);
    }
    resize();
    window.addEventListener('resize', resize);
    var ro = new ResizeObserver(resize);
    try { ro.observe(container); } catch (e) {}

  var gl = null;
  try { gl = overlay.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: true }) || overlay.getContext('experimental-webgl', { antialias: true, alpha: true, premultipliedAlpha: true }); } catch (e) { gl = null; }

    // helper to parse color
    function rgbFromHex(hex) {
      var r = parseInt(hex.slice(1,3),16)/255;
      var g = parseInt(hex.slice(3,5),16)/255;
      var b = parseInt(hex.slice(5,7),16)/255;
      return [r,g,b];
    }

    if (gl) {
      // WebGL snowfall using pseudo-random flake field with depth and sway
      var vertexSrc = 'attribute vec2 a_position; varying vec2 v_uv; void main(){ v_uv = a_position*0.5+0.5; gl_Position = vec4(a_position,0.0,1.0);}';
      var fragSrc = `
        precision highp float;
        varying vec2 v_uv;
        uniform vec2 u_resolution;
        uniform float u_time;
        uniform float u_intensity;
        uniform float u_wind;
        uniform float u_speed;
        uniform float u_size;
        uniform float u_turb;
        uniform float u_gustWind;
        uniform float u_gustTurb;
        uniform float u_dof;
        uniform vec3 u_color;
        uniform sampler2D u_map;
  uniform sampler2D u_fow;
  uniform sampler2D u_manual;
        uniform float u_accumLevel;
        uniform vec3 u_accumColor;

        float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
        float noise(vec2 p){ vec2 i=floor(p); vec2 f=fract(p); float a=hash(i); float b=hash(i+vec2(1.0,0.0)); float c=hash(i+vec2(0.0,1.0)); float d=hash(i+vec2(1.0,1.0)); vec2 u=f*f*(3.0-2.0*f); return mix(a,b,u.x)+ (c-a)*u.y*(1.0-u.x) + (d-b)*u.x*u.y; }

        void main(){
          vec2 res = u_resolution;
          vec2 uv = v_uv * (res / min(res.x,res.y));
          float t = u_time * 0.001 * u_speed;
          
          float density = mix(40.0, 140.0, clamp(u_intensity, 0.0, 1.0));
          vec3 baseCol = u_color;
          
          float accum = 0.0;
          float windAll = u_wind + u_gustWind;
          float turbAll = max(0.0, u_turb + u_gustTurb);
          vec2 dir = normalize(vec2(windAll*0.8, 1.0));
          vec2 perp = vec2(-dir.y, dir.x);

          for (int layer=0; layer<4; layer++){
            float depth = float(layer)/3.0; // 0..1
            float layerDensity = density * mix(0.6, 1.3, 1.0 - depth);
            vec2 p = uv * layerDensity;
            vec2 cell = floor(p);
            for (int oy=-1; oy<=1; oy++){
              for (int ox=-1; ox<=1; ox++){
                vec2 c = cell + vec2(float(ox), float(oy));
                float seed = hash(c + float(layer)*13.17);
                vec2 jitter = vec2(hash(c+1.0), hash(c+2.0)) - 0.5;
                vec2 flakePos = (c + 0.5 + jitter) / layerDensity;
                float fall = mod(t * mix(0.4, 0.9, 1.0-depth) + seed*17.0, 1.0);
                float sway = (noise(vec2(seed*100.0, t*0.1 + seed*5.0)) - 0.5) * turbAll;
                flakePos += dir * (-fall) + perp * (sway + windAll*0.05*(1.0-depth));

                vec2 d = v_uv - flakePos;
                float blur = u_dof * depth;
                float r = mix(0.0015, 0.010, seed) * u_size * mix(1.6, 0.7, depth) * (1.0 + blur*1.2);
                float dist = length(d);
                float core = 1.0 - smoothstep(r, r*1.8 + blur*0.02, dist);
                float halo = 1.0 - smoothstep(r*1.8, r*3.2 + blur*0.04, dist);
                float a = core + halo * (0.18 + 0.12*blur);
                accum += a * mix(1.0, 0.6, depth);
              }
            }
          }

          float mapA = 1.0;
          #ifdef GL_ES
          mapA = texture2D(u_map, v_uv).a;
          #else
          mapA = texture(u_map, v_uv).a;
          #endif
          float fowA = 1.0;
          #ifdef GL_ES
          fowA = texture2D(u_fow, v_uv).a;
          #else
          fowA = texture(u_fow, v_uv).a;
          #endif

          vec3 col = baseCol * clamp(accum, 0.0, 1.2);
          float manualA = 1.0;
          #ifdef GL_ES
          manualA = texture2D(u_manual, v_uv).a;
          #else
          manualA = texture(u_manual, v_uv).a;
          #endif
          float alpha = clamp(accum * 0.8, 0.0, 0.9) * mapA * fowA * manualA;

          // accumulation tint near bottom
          float gy = 1.0 - v_uv.y;
          float accMask = smoothstep(0.0, 0.6, gy) * u_accumLevel;
          float n = noise(v_uv * vec2(200.0, 120.0) + vec2(0.0, t*0.15));
          accMask *= (0.85 + 0.3*(n-0.5));
          col = mix(col, u_accumColor, clamp(accMask, 0.0, 1.0));
          alpha = max(alpha, accMask * 0.25);
          gl_FragColor = vec4(col, alpha);
        }
      `;

      function compileShader(src, type) {
        var s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.warn(gl.getShaderInfoLog(s));
        return s;
      }

      var program = gl.createProgram();
      gl.attachShader(program, compileShader(vertexSrc, gl.VERTEX_SHADER));
      gl.attachShader(program, compileShader(fragSrc, gl.FRAGMENT_SHADER));
      gl.linkProgram(program);

      var positionLoc = gl.getAttribLocation(program, 'a_position');
      var resLoc = gl.getUniformLocation(program, 'u_resolution');
      var timeLoc = gl.getUniformLocation(program, 'u_time');
      var intensityLoc = gl.getUniformLocation(program, 'u_intensity');
      var windLoc = gl.getUniformLocation(program, 'u_wind');
      var speedLoc = gl.getUniformLocation(program, 'u_speed');
      var sizeLoc = gl.getUniformLocation(program, 'u_size');
      var turbLoc = gl.getUniformLocation(program, 'u_turb');
      var colorLoc = gl.getUniformLocation(program, 'u_color');
  var mapLoc = gl.getUniformLocation(program, 'u_map');
  var fowLoc = gl.getUniformLocation(program, 'u_fow');
  var manualLoc = gl.getUniformLocation(program, 'u_manual');
  var gustWindLoc = gl.getUniformLocation(program, 'u_gustWind');
  var gustTurbLoc = gl.getUniformLocation(program, 'u_gustTurb');
  var dofLoc = gl.getUniformLocation(program, 'u_dof');
  var accumLevelLoc = gl.getUniformLocation(program, 'u_accumLevel');
  var accumColorLoc = gl.getUniformLocation(program, 'u_accumColor');

      var buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
      gl.useProgram(program);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    // map texture
  var mapTexture = null;
  var fallbackTex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, fallbackTex);
  var whitePixel = new Uint8Array([255,255,255,255]);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, whitePixel);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
  gl.bindTexture(gl.TEXTURE_2D, null);
  var mapImageEl = getMapElement();
    function createMapTexture() {
        if (!gl || !mapImageEl || !mapImageEl.complete) return;
        if (!mapTexture) mapTexture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, mapTexture);
        try {
      var c = document.createElement('canvas');
      c.width = overlay.width; c.height = overlay.height;
      var ctx2 = c.getContext('2d');
      ctx2.drawImage(mapImageEl, 0, 0, c.width, c.height);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        } catch (e) {
      var c2 = document.createElement('canvas');
      c2.width = overlay.width; c2.height = overlay.height;
      var ctx3 = c2.getContext('2d');
      ctx3.drawImage(mapImageEl, 0, 0, c2.width, c2.height);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c2);
        }
        gl.bindTexture(gl.TEXTURE_2D, null);
      }
      if (mapImageEl) {
        if (mapImageEl.complete) createMapTexture();
        else mapImageEl.addEventListener('load', createMapTexture);
        try { new ResizeObserver(function(){ createMapTexture(); }).observe(mapImageEl); } catch(e) {}
      }

  var start = Date.now();
  var running = true;
  var _lastOverlayW = overlay.width, _lastOverlayH = overlay.height;
  var lastTime = start;
  var curAccum = 0.0;
  var gustActive = false; var gustEnd = 0; var gustWindVal = 0.0; var gustTurbVal = 0.0;

  // FoW mask resources
  var fowHelper = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPxSnow });
  var fowTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, fowTexture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);
  // Manual mask resources
  var manualHelperSnow = Effects._buildManualMaskForOverlay(overlay, manualMaskLayersSnow, { featherPx: maskFeatherPxSnow });
  var manualTextureSnow = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, manualTextureSnow);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);

  function frame(){
        if (!running) return;
        var now = Date.now();
        var dt = Math.max(0, (now - lastTime) / 1000.0);
        lastTime = now;
        // Update accumulation
        if (accumulationEnabled) curAccum = Math.min(accumulationMax, curAccum + accumulationRate * dt); else curAccum = 0.0;
        // Update gusts
        if (gusts) {
          if (!gustActive && Math.random() < Math.min(0.9, gustFreq * dt)) {
            gustActive = true; gustEnd = now + Math.floor(gustDuration*1000);
            var s = Math.random()<0.5?-1:1;
            gustWindVal = s * (0.3 + 0.7*Math.random()) * gustStrength;
            gustTurbVal = (0.3 + 0.7*Math.random()) * gustStrength;
          } else if (gustActive && now >= gustEnd) {
            gustActive = false; gustWindVal = 0.0; gustTurbVal = 0.0;
          } else if (gustActive) {
            var rem = Math.max(0, gustEnd - now) / (gustDuration*1000.0);
            gustWindVal *= (0.95 + 0.05*rem);
            gustTurbVal *= (0.95 + 0.05*rem);
          }
        } else { gustWindVal = 0.0; gustTurbVal = 0.0; }
        gl.viewport(0, 0, overlay.width, overlay.height);
        gl.clearColor(0,0,0,0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.useProgram(program);
        gl.enableVertexAttribArray(positionLoc);
        gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);
        gl.uniform2f(resLoc, overlay.width, overlay.height);
        gl.uniform1f(timeLoc, now - start);
        gl.uniform1f(intensityLoc, intensity);
        gl.uniform1f(windLoc, wind);
        gl.uniform1f(speedLoc, speed);
        gl.uniform1f(sizeLoc, flakeSize);
        gl.uniform1f(turbLoc, turbulence);
        var rgb = rgbFromHex(color);
        gl.uniform3f(colorLoc, rgb[0], rgb[1], rgb[2]);
        gl.uniform1f(gustWindLoc, gustWindVal);
        gl.uniform1f(gustTurbLoc, gustTurbVal);
        gl.uniform1f(dofLoc, dof);
        var accRgb = rgbFromHex(accumulationColor);
        gl.uniform1f(accumLevelLoc, curAccum);
        gl.uniform3f(accumColorLoc, accRgb[0], accRgb[1], accRgb[2]);
  gl.activeTexture(gl.TEXTURE0);
  if (overlay.width !== _lastOverlayW || overlay.height !== _lastOverlayH) {
    _lastOverlayW = overlay.width; _lastOverlayH = overlay.height;
    try { createMapTexture(); } catch(e) {}
  }
  gl.bindTexture(gl.TEXTURE_2D, mapTexture || fallbackTex);
  gl.uniform1i(mapLoc, 0);
        // Update and bind FoW texture (unit 1)
        try {
          var upd = fowHelper.update();
          if (upd && upd.canvas) {
            gl.activeTexture(gl.TEXTURE1);
            gl.bindTexture(gl.TEXTURE_2D, fowTexture);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, upd.canvas);
            gl.uniform1i(fowLoc, 1);
          }
        } catch(e) {}
        // Update and bind Manual mask (unit 2)
        try {
          manualHelperSnow.setLayers(manualMaskLayersSnow);
          var updM2 = manualHelperSnow.update();
          if (updM2 && updM2.canvas) {
            gl.activeTexture(gl.TEXTURE2);
            gl.bindTexture(gl.TEXTURE_2D, manualTextureSnow);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, updM2.canvas);
            gl.uniform1i(manualLoc, 2);
          }
        } catch(e) {}
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);

      return {
  stop: function(){ running = false; try{ gl.getExtension('WEBGL_lose_context').loseContext(); }catch(e){} overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} try{ fowHelper && fowHelper.destroy(); }catch(e){} try{ manualHelperSnow && manualHelperSnow.destroy(); }catch(e){} },
        updateConfig: function(c){
          intensity = c.intensity != null ? c.intensity : intensity;
          wind = c.wind != null ? c.wind : wind;
          speed = c.speed != null ? c.speed : speed;
          color = c.color || color;
          flakeSize = c.flakeSize != null ? c.flakeSize : flakeSize;
          turbulence = c.turbulence != null ? c.turbulence : turbulence;
          gusts = c.gusts != null ? !!c.gusts : gusts;
          gustFreq = c.gustFreq != null ? c.gustFreq : gustFreq;
          gustStrength = c.gustStrength != null ? c.gustStrength : gustStrength;
          gustDuration = c.gustDuration != null ? c.gustDuration : gustDuration;
          dof = c.dof != null ? c.dof : dof;
          accumulationEnabled = c.accumulationEnabled != null ? !!c.accumulationEnabled : accumulationEnabled;
          accumulationRate = c.accumulationRate != null ? c.accumulationRate : accumulationRate;
          accumulationMax = c.accumulationMax != null ? c.accumulationMax : accumulationMax;
          accumulationColor = c.accumulationColor || accumulationColor;
          useManualMaskSnow = c.mask != null ? !!c.mask : useManualMaskSnow;
          manualMaskLayersSnow = c.mask_layers || manualMaskLayersSnow;
          maskFeatherPxSnow = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPxSnow));
          try{ manualHelperSnow.setLayers(manualMaskLayersSnow); }catch(e){}
          try{ if (manualHelperSnow.setOptions) manualHelperSnow.setOptions({ featherPx: maskFeatherPxSnow }); }catch(e){}
          try{ if (fowHelper.setOptions) fowHelper.setOptions({ featherPx: maskFeatherPxSnow }); }catch(e){}
        }
      };
    }

    // 2D canvas fallback with parallax layers and turbulence sway
  var ctx = overlay.getContext('2d');
  ctx.imageSmoothingEnabled = true;
    var running2D = true;
  // FoW mask for 2D path
  var fow2D = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPxSnow });
  var manual2DSnow = Effects._buildManualMaskForOverlay(overlay, manualMaskLayersSnow, { featherPx: maskFeatherPxSnow });
  var W = overlay.clientWidth, H = overlay.clientHeight;
  function updateLogicalSize(){ var rect = getMapRect(); W = rect.width; H = rect.height; }
  function setDPRTransform(){ var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1)); ctx.setTransform(dpr,0,0,dpr,0,0); }

    function makeFlake(depth){
      return {
    x: Math.random()*W,
    y: Math.random()*H,
        z: depth, // 0..1, 0 front
        r: (0.7 + Math.random()*2.2) * (1.6 - depth) * flakeSize,
        vy: (0.3 + Math.random()*1.2) * (1.0 + speed) * (1.0 - depth*0.3),
        vx: wind * (0.2 + 0.4*(1.0-depth)) + (Math.random()-0.5)*0.3,
        seed: Math.random()*1000.0
      };
    }
  var layers = [[],[],[],[]];
    var counts = [60, 90, 110, 130].map(function(c){ return Math.floor(c*intensity); });
    for (var li=0; li<4; li++){
      for (var i=0; i<counts[li]; i++) layers[li].push(makeFlake(li/3));
    }
  var curAccum2D = 0.0;
  var last2D = Date.now();
  var gustActive2D = false; var gustEnd2D = 0; var gustWind2D = 0.0; var gustTurb2D = 0.0;

    function draw2D(){
      if (!running2D) return;
      updateLogicalSize();
      // ensure backing store matches DPR
      var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
      var targetW = Math.floor(W * dpr), targetH = Math.floor(H * dpr);
      if (overlay.width !== targetW || overlay.height !== targetH) { overlay.width = targetW; overlay.height = targetH; overlay.style.width = W + 'px'; overlay.style.height = H + 'px'; }
      setDPRTransform();
      ctx.clearRect(0,0,W,H);
      ctx.globalCompositeOperation = 'source-over';
      var rgb = rgbFromHex(color);
      var now = Date.now();
      var dt = Math.max(0, (now - last2D) / 1000.0); last2D = now;
      if (accumulationEnabled) curAccum2D = Math.min(accumulationMax, curAccum2D + accumulationRate * dt); else curAccum2D = 0.0;
      if (gusts) {
        if (!gustActive2D && Math.random() < Math.min(0.9, gustFreq * dt)) {
          gustActive2D = true; gustEnd2D = now + Math.floor(gustDuration*1000);
          var s2 = Math.random()<0.5?-1:1; gustWind2D = s2 * (0.3 + 0.7*Math.random()) * gustStrength; gustTurb2D = (0.3 + 0.7*Math.random()) * gustStrength;
        } else if (gustActive2D && now >= gustEnd2D) {
          gustActive2D = false; gustWind2D = 0.0; gustTurb2D = 0.0;
        } else if (gustActive2D) {
          var rem2 = Math.max(0, gustEnd2D - now) / (gustDuration*1000.0);
          gustWind2D *= (0.95 + 0.05*rem2);
          gustTurb2D *= (0.95 + 0.05*rem2);
        }
      } else { gustWind2D = 0.0; gustTurb2D = 0.0; }
      for (var li=0; li<4; li++){
        var depth = li/3;
        for (var i=0; i<layers[li].length; i++){
          var f = layers[li][i];
          // sway by turbulence and per-flake phase
          var turbAll2D = Math.max(0, turbulence + gustTurb2D);
          var sway = (Math.sin((now*0.001 + f.seed) * (0.6 + turbAll2D*1.8)))* (turbAll2D*6.0) * (1.0 - depth*0.6);
          var windAll2D = wind + gustWind2D;
          f.x += f.vx + sway*0.02 + windAll2D*0.4*(1.0-depth);
          f.y += f.vy;
          // wrap
          if (f.y > H + 10) { f.y = -10; f.x = Math.random()*W; }
          if (f.x > W + 10) f.x = -10;
          if (f.x < -10) f.x = W + 10;

          // render flake as soft circle with slight halo
          var dofAmt = dof * depth;
          var grd = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.r*(2.6 + 0.8*dofAmt));
          grd.addColorStop(0.0, 'rgba(255,255,255,' + (0.90 - depth*0.55) + ')');
          grd.addColorStop(0.6, 'rgba(255,255,255,' + (0.22 - depth*0.16 + 0.1*dofAmt) + ')');
          grd.addColorStop(1.0, 'rgba(255,255,255,0)');
          ctx.fillStyle = grd;
          ctx.beginPath();
          ctx.arc(f.x, f.y, f.r*(1.2 + 0.25*dofAmt), 0, Math.PI*2);
          ctx.fill();
        }
      }
      // accumulation overlay near bottom
      if (curAccum2D > 0.0) {
        var accRgb = rgbFromHex(accumulationColor);
        var g = ctx.createLinearGradient(0, H, 0, Math.max(0, H - H*0.4));
        var alphaBase = Math.min(0.35, curAccum2D);
        g.addColorStop(0.0, 'rgba(' + Math.floor(accRgb[0]*255) + ',' + Math.floor(accRgb[1]*255) + ',' + Math.floor(accRgb[2]*255) + ',' + (alphaBase) + ')');
        g.addColorStop(1.0, 'rgba(' + Math.floor(accRgb[0]*255) + ',' + Math.floor(accRgb[1]*255) + ',' + Math.floor(accRgb[2]*255) + ',0)');
        ctx.fillStyle = g;
        ctx.fillRect(0, Math.max(0, H - H*0.4), W, H*0.4);
      }
      // Apply Manual mask then FoW mask on 2D (destination-in)
      try {
        var man2 = manual2DSnow.update();
        if (man2 && man2.canvas) {
          ctx.globalCompositeOperation = 'destination-in';
          ctx.drawImage(man2.canvas, 0, 0);
          ctx.globalCompositeOperation = 'source-over';
        }
      } catch(e) {}
      // Apply FoW mask on 2D (destination-in)
      try {
        var upd2 = fow2D.update();
        if (upd2 && upd2.canvas) {
          ctx.globalCompositeOperation = 'destination-in';
          ctx.drawImage(upd2.canvas, 0, 0);
          ctx.globalCompositeOperation = 'source-over';
        }
      } catch(e) {}
      requestAnimationFrame(draw2D);
    }
    requestAnimationFrame(draw2D);

    return {
  stop: function(){ running2D = false; overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} try{ fow2D && fow2D.destroy(); }catch(e){} try{ manual2DSnow && manual2DSnow.destroy(); }catch(e){} },
      updateConfig: function(c){
        intensity = c.intensity != null ? c.intensity : intensity;
        wind = c.wind != null ? c.wind : wind;
        speed = c.speed != null ? c.speed : speed;
        color = c.color || color;
        flakeSize = c.flakeSize != null ? c.flakeSize : flakeSize;
  turbulence = c.turbulence != null ? c.turbulence : turbulence;
  gusts = c.gusts != null ? !!c.gusts : gusts;
  gustFreq = c.gustFreq != null ? c.gustFreq : gustFreq;
  gustStrength = c.gustStrength != null ? c.gustStrength : gustStrength;
  gustDuration = c.gustDuration != null ? c.gustDuration : gustDuration;
  dof = c.dof != null ? c.dof : dof;
  accumulationEnabled = c.accumulationEnabled != null ? !!c.accumulationEnabled : accumulationEnabled;
  accumulationRate = c.accumulationRate != null ? c.accumulationRate : accumulationRate;
  accumulationMax = c.accumulationMax != null ? c.accumulationMax : accumulationMax;
  accumulationColor = c.accumulationColor || accumulationColor;
  useManualMaskSnow = c.mask != null ? !!c.mask : useManualMaskSnow;
  manualMaskLayersSnow = c.mask_layers || manualMaskLayersSnow;
  maskFeatherPxSnow = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPxSnow));
  try{ manual2DSnow.setLayers(manualMaskLayersSnow); }catch(e){}
  try{ if (manual2DSnow.setOptions) manual2DSnow.setOptions({ featherPx: maskFeatherPxSnow }); }catch(e){}
  try{ if (fow2D.setOptions) fow2D.setOptions({ featherPx: maskFeatherPxSnow }); }catch(e){}
      }
    };
  }
}

// Water implementation: animated ripples with subtle specular highlights.
Effects.createWaterEffect = function(config) {
  config = config || {};
  var speed = config.speed != null ? config.speed : 0.8;
  var amplitude = config.amplitude != null ? config.amplitude : 0.8; // visual strength 0..1
  var distortion = config.distortion != null ? config.distortion : 0.015; // UV warp scale
  var brightness = config.brightness != null ? config.brightness : 0.9; // highlight boost
  var color = config.color || '#3aa1c7'; // water tint
  var reflection = (config.reflection != null ? config.reflection : 0.6); // reflection strength 0..1
  var useManualMask = !!config.mask;
  var manualMaskLayers = config.mask_layers || config.mask_layer || [];
  var maskFeatherPx = Math.max(0, config.mask_feather || 0);

  // Align overlay to map image rect
  var container = document.querySelector('.image-container') || document.body;
  var overlay = container.querySelector('#effects-overlay-water');
  if (!overlay) {
    overlay = document.createElement('canvas');
    overlay.id = 'effects-overlay-water';
    overlay.style.position = 'absolute';
    overlay.style.left = '0';
    overlay.style.top = '0';
    overlay.style.pointerEvents = 'none';
    // place just above the background image and below tokens (tiles-container z-index: 1)
    overlay.style.zIndex = 0;
    container.appendChild(overlay);
  }

  function getMapElement(){ return document.querySelector('.image-container img.background-image, .image-container img'); }
  function getMapRect(){
    var img = getMapElement();
    var cRect = container.getBoundingClientRect();
    if (img) {
      var r = img.getBoundingClientRect();
      return { left: Math.round(r.left - cRect.left), top: Math.round(r.top - cRect.top), width: Math.round(r.width), height: Math.round(r.height) };
    }
    return { left: 0, top: 0, width: container.clientWidth, height: container.clientHeight };
  }

  function resize(){
    var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    var rect = getMapRect();
    overlay.style.left = rect.left + 'px';
    overlay.style.top = rect.top + 'px';
    overlay.style.width = rect.width + 'px';
    overlay.style.height = rect.height + 'px';
    overlay.width = Math.floor(rect.width * dpr);
    overlay.height = Math.floor(rect.height * dpr);
  }
  resize();
  window.addEventListener('resize', resize);
  var ro = new ResizeObserver(resize);
  try { ro.observe(container); } catch(e) {}

  function rgbFromHex(hex){ var r=parseInt(hex.slice(1,3),16)/255, g=parseInt(hex.slice(3,5),16)/255, b=parseInt(hex.slice(5,7),16)/255; return [r,g,b]; }

  var gl = null;
  try { gl = overlay.getContext('webgl', { antialias:true, alpha:true, premultipliedAlpha:true }) || overlay.getContext('experimental-webgl', { antialias:true, alpha:true, premultipliedAlpha:true }); } catch(e) { gl = null; }

  if (gl) {
    var vertexSrc = 'attribute vec2 a_position; varying vec2 v_uv; void main(){ v_uv = a_position*0.5+0.5; gl_Position = vec4(a_position,0.0,1.0);}';
    var fragSrc = `
      precision mediump float;
      varying vec2 v_uv;
      uniform vec2 u_resolution;
      uniform float u_time;
      uniform float u_speed;
      uniform float u_amp;
      uniform float u_distort;
      uniform float u_brightness;
      uniform float u_reflect;
      uniform vec3 u_color;
      uniform sampler2D u_map;
      uniform sampler2D u_fow;
      uniform sampler2D u_manual;

      // pseudo-random
      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453123); }
      float noise(vec2 p){ vec2 i=floor(p); vec2 f=fract(p); vec2 u=f*f*(3.0-2.0*f); float a=hash(i); float b=hash(i+vec2(1.0,0.0)); float c=hash(i+vec2(0.0,1.0)); float d=hash(i+vec2(1.0,1.0)); return mix(mix(a,b,u.x), mix(c,d,u.x), u.y); }
      float fbm(vec2 p){ float v=0.0; float a=0.5; mat2 m=mat2(1.6,1.2,-1.2,1.6); for(int i=0;i<4;i++){ v += a*noise(p); p = m*p*1.8; a*=0.5;} return v; }

      float heightField(vec2 uv, float t){
        float h = 0.0;
        h += sin(uv.x*18.0 + t*0.9) * 0.35;
        h += sin(uv.y*22.0 - t*1.1) * 0.35;
        h += sin((uv.x+uv.y)*12.0 + t*0.7) * 0.25;
        h += fbm(uv*3.0 + vec2(t*0.08, -t*0.06)) * 0.6;
        return h;
      }

      void main(){
        vec2 res = u_resolution; 
        vec2 uv = v_uv * (res / min(res.x,res.y));
        float t = u_time * 0.001 * u_speed;
        // warp uv by subtle flow
        vec2 flow = vec2(sin(t*0.4), cos(t*0.33));
        vec2 wuv = v_uv + (flow*0.02 + vec2(fbm(uv*1.2), fbm(uv*1.2+11.0))*0.015) * u_distort * 8.0;

        // compute height and approximate gradient for highlights
        float eps = 1.0 / min(res.x, res.y);
        float h = heightField(uv + flow*0.05, t) * u_amp;
        float hx = heightField(uv + vec2(eps,0.0) + flow*0.05, t) * u_amp;
        float hy = heightField(uv + vec2(0.0,eps) + flow*0.05, t) * u_amp;
        vec3 n = normalize(vec3(h - hx, h - hy, 0.5));
        vec3 L = normalize(vec3(0.3, 0.5, 0.8));
        float spec = pow(max(0.0, dot(n, L)), 18.0) * 1.4;
        float rim = smoothstep(0.2, 0.8, h);

        // base water tint + specular
        vec3 base = u_color * (0.7 + 0.3*rim);
        base += vec3(0.9,0.95,1.0) * spec * u_brightness;

        // Fresnel-based reflection sampling of underlying map
        vec3 V = normalize(vec3(0.0, 0.0, 1.0));
        float NoV = clamp(dot(n, V), 0.0, 1.0);
        float fresnel = pow(1.0 - NoV, 5.0); // Schlick approx without F0
        // use normal to offset reflection lookup to mimic environment reflection
        vec2 reflUV = v_uv + n.xy * 0.04 * u_distort + flow * 0.01;
        // slight scroll to avoid static look
        reflUV += vec2(t*0.01, -t*0.007);
        vec3 mapCol = texture2D(u_map, clamp(reflUV, 0.0, 1.0)).rgb;
        // boost highlights, blend by fresnel and user reflection strength
        vec3 reflectCol = mix(base, mapCol, clamp(u_reflect * (0.3 + 0.7*fresnel), 0.0, 1.0));

        float mapA = 1.0;
        #ifdef GL_ES
          mapA = texture2D(u_map, v_uv).a;
        #else
          mapA = texture(u_map, v_uv).a;
        #endif
        float fowA = 1.0;
        #ifdef GL_ES
          fowA = texture2D(u_fow, v_uv).a;
        #else
          fowA = texture(u_fow, v_uv).a;
        #endif
        float manualA = 1.0;
        #ifdef GL_ES
          manualA = texture2D(u_manual, v_uv).a;
        #else
          manualA = texture(u_manual, v_uv).a;
        #endif
        float alpha = clamp(0.30 + 0.35*rim + 0.25*spec, 0.0, 0.9) * mapA * fowA * manualA;
        gl_FragColor = vec4(reflectCol, alpha);
      }
    `;

    function compileShader(src, type){ var s=gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.warn(gl.getShaderInfoLog(s)); return s; }
    var program = gl.createProgram();
    gl.attachShader(program, compileShader(vertexSrc, gl.VERTEX_SHADER));
    gl.attachShader(program, compileShader(fragSrc, gl.FRAGMENT_SHADER));
    gl.linkProgram(program);

    var positionLoc = gl.getAttribLocation(program, 'a_position');
    var resLoc = gl.getUniformLocation(program, 'u_resolution');
    var timeLoc = gl.getUniformLocation(program, 'u_time');
    var speedLoc = gl.getUniformLocation(program, 'u_speed');
    var ampLoc = gl.getUniformLocation(program, 'u_amp');
    var distLoc = gl.getUniformLocation(program, 'u_distort');
  var brightLoc = gl.getUniformLocation(program, 'u_brightness');
  var reflectLoc = gl.getUniformLocation(program, 'u_reflect');
    var colorLoc = gl.getUniformLocation(program, 'u_color');
    var mapLoc = gl.getUniformLocation(program, 'u_map');
    var fowLoc = gl.getUniformLocation(program, 'u_fow');
    var manualLoc = gl.getUniformLocation(program, 'u_manual');

    var buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    gl.useProgram(program);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    // Map texture handling
    var mapTexture = null;
    var mapImageEl = getMapElement();
    var imgResizeObserver = null;
    function createMapTexture(){
      if (!gl || !mapImageEl || !mapImageEl.complete) return;
      if (!mapTexture) mapTexture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, mapTexture);
      try {
        var c = document.createElement('canvas'); c.width = overlay.width; c.height = overlay.height; var ctx2 = c.getContext('2d'); ctx2.drawImage(mapImageEl, 0, 0, c.width, c.height);
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      } catch(e) {
        // Fallback: still try canvas copy
        var c2 = document.createElement('canvas'); c2.width = overlay.width; c2.height = overlay.height; var ctx3 = c2.getContext('2d'); ctx3.drawImage(mapImageEl, 0, 0, c2.width, c2.height);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c2);
      }
      gl.bindTexture(gl.TEXTURE_2D, null);
    }
    if (mapImageEl) {
      if (mapImageEl.complete) createMapTexture(); else mapImageEl.addEventListener('load', createMapTexture);
      try { imgResizeObserver = new ResizeObserver(function(){ createMapTexture(); }); imgResizeObserver.observe(mapImageEl); } catch(e) {}
    }

    // FoW & Manual masks
    var fowHelper = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPx });
    var fowTexture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, fowTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.bindTexture(gl.TEXTURE_2D, null);

    var manualHelper = Effects._buildManualMaskForOverlay(overlay, manualMaskLayers, { featherPx: maskFeatherPx });
    var manualTexture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, manualTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.bindTexture(gl.TEXTURE_2D, null);

    var start = Date.now();
    var running = true;
    var _lastOverlayW = overlay.width, _lastOverlayH = overlay.height;

    function frame(){
      if (!running) return;
      gl.viewport(0, 0, overlay.width, overlay.height);
      gl.clearColor(0,0,0,0); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.enableVertexAttribArray(positionLoc);
      gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(resLoc, overlay.width, overlay.height);
      gl.uniform1f(timeLoc, Date.now() - start);
      gl.uniform1f(speedLoc, speed);
      gl.uniform1f(ampLoc, amplitude);
      gl.uniform1f(distLoc, distortion);
      gl.uniform1f(brightLoc, brightness);
  var rgb = rgbFromHex(color); gl.uniform3f(colorLoc, rgb[0], rgb[1], rgb[2]);
  gl.uniform1f(reflectLoc, reflection);

      if (mapTexture) {
        if (overlay.width !== _lastOverlayW || overlay.height !== _lastOverlayH) { _lastOverlayW = overlay.width; _lastOverlayH = overlay.height; try{ createMapTexture(); }catch(e){} }
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, mapTexture); gl.uniform1i(mapLoc, 0);
      }
      // FoW
      try { var upd = fowHelper.update(); if (upd && upd.canvas) { gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, fowTexture); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, upd.canvas); gl.uniform1i(fowLoc, 1); } } catch(e) {}
      // Manual
      try { manualHelper.setLayers(manualMaskLayers); var updM = manualHelper.update(); if (updM && updM.canvas) { gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, manualTexture); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, updM.canvas); gl.uniform1i(manualLoc, 2); } } catch(e) {}

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    return {
      stop: function(){
        running = false;
        try{ gl.getExtension('WEBGL_lose_context').loseContext(); }catch(e){}
        if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
        if (ro) try{ ro.disconnect(); }catch(e){}
        if (imgResizeObserver) try{ imgResizeObserver.disconnect(); }catch(e){}
        try{ fowHelper && fowHelper.destroy(); }catch(e){}
        try{ manualHelper && manualHelper.destroy(); }catch(e){}
      },
      updateConfig: function(c){
        speed = c.speed != null ? c.speed : speed;
        amplitude = c.amplitude != null ? c.amplitude : amplitude;
        distortion = c.distortion != null ? c.distortion : distortion;
        brightness = c.brightness != null ? c.brightness : brightness;
  color = c.color || color;
        useManualMask = c.mask != null ? !!c.mask : useManualMask;
        manualMaskLayers = c.mask_layers || manualMaskLayers;
        maskFeatherPx = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPx));
  reflection = (c.reflection != null ? c.reflection : reflection);
        try{ manualHelper.setLayers(manualMaskLayers); }catch(e){}
        try{ if (manualHelper.setOptions) manualHelper.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
        try{ if (fowHelper.setOptions) fowHelper.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
      }
    };
  }

  // Canvas fallback
  var ctx = overlay.getContext('2d');
  var running2D = true;
  var t0 = Date.now();
  var fow2D = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPx });
  var manual2D = Effects._buildManualMaskForOverlay(overlay, manualMaskLayers, { featherPx: maskFeatherPx });

  function draw2D(){
    if (!running2D) return;
    // ensure backing store matches DPR and rect
    var rect = getMapRect();
    var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    var targetW = Math.floor(rect.width * dpr), targetH = Math.floor(rect.height * dpr);
    if (overlay.width !== targetW || overlay.height !== targetH) { overlay.width = targetW; overlay.height = targetH; overlay.style.width = rect.width + 'px'; overlay.style.height = rect.height + 'px'; }
    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.clearRect(0,0,rect.width, rect.height);

    var now = Date.now();
    var t = (now - t0) * 0.001 * speed;
    var rgb = rgbFromHex(color);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 0.6 * amplitude;
    ctx.fillStyle = 'rgba(' + Math.floor(rgb[0]*255) + ',' + Math.floor(rgb[1]*255) + ',' + Math.floor(rgb[2]*255) + ',0.35)';
    // draw horizontal wave bands
    var W = rect.width, H = rect.height;
    var bands = 16;
    for (var i=0; i<bands; i++){
      var y = (i + 0.5) * H / bands;
      var ampPx = 6 + 12*amplitude;
      var freq = 0.012 + 0.02*(i/bands);
      ctx.beginPath();
      for (var x=0; x<=W; x+=4){
        var yy = y + Math.sin(x*freq + t*2.0 + i)*ampPx;
        if (x===0) ctx.moveTo(x, yy); else ctx.lineTo(x, yy);
      }
      ctx.lineWidth = 2.0;
      ctx.strokeStyle = 'rgba(255,255,255,' + (0.08 + 0.08*brightness) + ')';
      ctx.stroke();
    }
    // soft tint overlay
    ctx.globalAlpha = 0.12 * amplitude;
    ctx.fillStyle = 'rgba(' + Math.floor(rgb[0]*255) + ',' + Math.floor(rgb[1]*255) + ',' + Math.floor(rgb[2]*255) + ',1)';
    ctx.fillRect(0,0,W,H);

    // mask by map alpha
    var mapEl = getMapElement();
    if (mapEl && mapEl.complete){
      var tx = document.createElement('canvas'); tx.width = overlay.width; tx.height = overlay.height; var tctx = tx.getContext('2d'); tctx.drawImage(mapEl, 0, 0, overlay.width, overlay.height);
      ctx.globalCompositeOperation = 'destination-in';
      ctx.drawImage(tx, 0, 0);
      ctx.globalCompositeOperation = 'source-over';
    }
    // Manual then FoW masks
    try { var man = manual2D.update(); if (man && man.canvas){ ctx.globalCompositeOperation='destination-in'; ctx.drawImage(man.canvas, 0, 0); ctx.globalCompositeOperation='source-over'; } } catch(e) {}
    try { var upd = fow2D.update(); if (upd && upd.canvas){ ctx.globalCompositeOperation='destination-in'; ctx.drawImage(upd.canvas, 0, 0); ctx.globalCompositeOperation='source-over'; } } catch(e) {}

    requestAnimationFrame(draw2D);
  }
  requestAnimationFrame(draw2D);

  return {
    stop: function(){ running2D = false; if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} try{ fow2D && fow2D.destroy(); }catch(e){} try{ manual2D && manual2D.destroy(); }catch(e){} },
    updateConfig: function(c){
      speed = c.speed != null ? c.speed : speed;
      amplitude = c.amplitude != null ? c.amplitude : amplitude;
      distortion = c.distortion != null ? c.distortion : distortion;
      brightness = c.brightness != null ? c.brightness : brightness;
      color = c.color || color;
      useManualMask = c.mask != null ? !!c.mask : useManualMask;
      manualMaskLayers = c.mask_layers || manualMaskLayers;
      maskFeatherPx = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPx));
      try{ manual2D.setLayers(manualMaskLayers); }catch(e){}
      try{ if (manual2D.setOptions) manual2D.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
      try{ if (fow2D.setOptions) fow2D.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
    }
  };
};

// Fog implementation: WebGL accelerated if available, canvas fallback otherwise.
Effects.createFogEffect = function (config) {
  config = config || {};
  var density = config.density != null ? config.density : 0.45;
  var speed = config.speed != null ? config.speed : 0.7;
  var color = config.color || '#cfcfd6';
  var useManualMask = !!config.mask;
  var manualMaskLayers = config.mask_layers || config.mask_layer || [];
  var maskFeatherPx = Math.max(0, config.mask_feather || 0);

  // Attach overlay aligned to the actual map image rect (to avoid offset issues)
  var container = document.querySelector('.image-container') || document.body;
  var overlay = container.querySelector('#effects-overlay');
  if (!overlay) {
    overlay = document.createElement('canvas');
    overlay.id = 'effects-overlay';
    overlay.style.position = 'absolute';
    overlay.style.left = '0';
    overlay.style.top = '0';
    overlay.style.pointerEvents = 'none';
    overlay.style.zIndex = 2000; // above map tiles but below UI
    container.appendChild(overlay);
  }

  function getMapElement(){ return document.querySelector('.image-container img.background-image, .image-container img'); }
  function getMapRect(){
    var img = getMapElement();
    var cRect = container.getBoundingClientRect();
    if (img) {
      var r = img.getBoundingClientRect();
      return { left: Math.round(r.left - cRect.left), top: Math.round(r.top - cRect.top), width: Math.round(r.width), height: Math.round(r.height) };
    }
    return { left: 0, top: 0, width: container.clientWidth, height: container.clientHeight };
  }

  function resize() {
    var dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
    var rect = getMapRect();
    overlay.style.left = rect.left + 'px';
    overlay.style.top = rect.top + 'px';
    overlay.style.width = rect.width + 'px';
    overlay.style.height = rect.height + 'px';
    overlay.width = Math.floor(rect.width * dpr);
    overlay.height = Math.floor(rect.height * dpr);
  }
  resize();
  // Listen for window resize and also mutation of container size
  window.addEventListener('resize', resize);
  var ro = new ResizeObserver(resize);
  try { ro.observe(container); } catch (e) {}

  var gl = null;
  try {
    gl = overlay.getContext('webgl') || overlay.getContext('experimental-webgl');
  } catch (e) { gl = null; }

  if (gl) {
    // Improved FBM-based fragment shader with resolution and speed
    var vertexSrc = '\n      attribute vec2 a_position;\n      varying vec2 v_uv;\n      void main() { v_uv = a_position * 0.5 + 0.5; gl_Position = vec4(a_position, 0.0, 1.0); }\n    ';
    var fragSrc = `
      precision mediump float;
      varying vec2 v_uv;
      uniform vec2 u_resolution;
      uniform float u_time;
      uniform float u_density;
      uniform float u_speed;
      uniform float u_contrast;
      uniform float u_grain;
      uniform float u_falloff;
      uniform vec3 u_color;
  uniform sampler2D u_map;
  uniform sampler2D u_fow;
  uniform sampler2D u_manual;

      // value noise helpers
      float hash(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123); }
      float noise(vec2 p) {
        vec2 i = floor(p);
        vec2 f = fract(p);
        // Smooth interpolation
        vec2 u = f*f*(3.0-2.0*f);
        float a = hash(i + vec2(0.0,0.0));
        float b = hash(i + vec2(1.0,0.0));
        float c = hash(i + vec2(0.0,1.0));
        float d = hash(i + vec2(1.0,1.0));
        return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);
      }

      float fbm(vec2 p) {
        float v = 0.0;
        float a = 0.5;
        mat2 m = mat2(1.6,1.2,-1.2,1.6);
        for (int i=0; i<5; i++) {
          v += a * noise(p);
          p = m * p * 1.9;
          a *= 0.5;
        }
        return v;
      }

      void main(){
        vec2 uv = v_uv * u_resolution / min(u_resolution.x, u_resolution.y);
        float t = u_time * u_speed * 0.001;

        // base fbm layers
        float n = fbm(uv * 0.8 + vec2(0.0, t*0.2));
        n += 0.5 * fbm(uv * 2.0 + vec2(t*0.4, t*0.2));
        n += 0.25 * fbm(uv * 4.0 + vec2(t*0.8, -t*0.3));

        // depth/height attenuation (more fog near bottom)
        float depth = smoothstep(0.0, 1.0, v_uv.y);
  float fog = smoothstep(0.35 - u_density, 0.65 + u_density, 0.5 + (n - 0.5) * 0.9);
  // vertical falloff control
  fog *= pow(mix(0.6, 1.0, depth), u_falloff);
  // contrast
  fog = pow(fog, max(0.01, 1.0 / max(0.01, u_contrast)));
  // grain - subtle per-pixel noise
  float grain = (hash(v_uv * u_time * 0.001) - 0.5) * u_grain;
  fog = clamp(fog + grain, 0.0, 1.0);

  vec3 col = mix(vec3(0.0), u_color, fog);
  // sample map alpha to mask fog outside map
  float mapAlpha = 1.0;
  #ifdef GL_ES
  mapAlpha = texture2D(u_map, v_uv).a;
  #else
  mapAlpha = texture(u_map, v_uv).a;
  #endif
  float fowA = 1.0;
  #ifdef GL_ES
  fowA = texture2D(u_fow, v_uv).a;
  #else
  fowA = texture(u_fow, v_uv).a;
  #endif
  float manualA = 1.0;
  #ifdef GL_ES
  manualA = texture2D(u_manual, v_uv).a;
  #else
  manualA = texture(u_manual, v_uv).a;
  #endif
  float outAlpha = clamp(fog * 0.85 * mapAlpha * fowA * manualA, 0.0, 0.95);
  gl_FragColor = vec4(col, outAlpha);
      }
    `;

    function compileShader(src, type) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.warn(gl.getShaderInfoLog(s));
      return s;
    }

    var program = gl.createProgram();
    gl.attachShader(program, compileShader(vertexSrc, gl.VERTEX_SHADER));
    gl.attachShader(program, compileShader(fragSrc, gl.FRAGMENT_SHADER));
    gl.linkProgram(program);

    var positionLoc = gl.getAttribLocation(program, 'a_position');
  var resLoc = gl.getUniformLocation(program, 'u_resolution');
  var timeLoc = gl.getUniformLocation(program, 'u_time');
  var densityLoc = gl.getUniformLocation(program, 'u_density');
  var speedLoc = gl.getUniformLocation(program, 'u_speed');
  var contrastLoc = gl.getUniformLocation(program, 'u_contrast');
  var grainLoc = gl.getUniformLocation(program, 'u_grain');
  var falloffLoc = gl.getUniformLocation(program, 'u_falloff');
  var colorLoc = gl.getUniformLocation(program, 'u_color');
  var mapLoc = gl.getUniformLocation(program, 'u_map');
  var fowLoc = gl.getUniformLocation(program, 'u_fow');
  var manualLoc = gl.getUniformLocation(program, 'u_manual');

    var buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);

    gl.useProgram(program);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    function rgbFromHex(hex) {
      var r = parseInt(hex.slice(1,3),16)/255;
      var g = parseInt(hex.slice(3,5),16)/255;
      var b = parseInt(hex.slice(5,7),16)/255;
      return [r,g,b];
    }

    // map texture and image handling for masking
  var mapTexture = null;
    var mapImageEl = document.querySelector('.image-container img.background-image, .image-container img');
    var imgResizeObserver = null;
  function createMapTexture() {
      if (!gl || !mapImageEl || !mapImageEl.complete) return;
      if (!mapTexture) mapTexture = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, mapTexture);
      try {
    // Upload a canvas copy sized to overlay so texture UV matches overlay space
    var c = document.createElement('canvas');
    c.width = overlay.width; c.height = overlay.height;
    var ctx2 = c.getContext('2d');
    // Draw the map image scaled to overlay size
    ctx2.drawImage(mapImageEl, 0, 0, c.width, c.height);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      } catch (e) {
    // If direct draw fails, still try canvas copy
    var c2 = document.createElement('canvas');
    c2.width = overlay.width; c2.height = overlay.height;
    var ctx3 = c2.getContext('2d');
    ctx3.drawImage(mapImageEl, 0, 0, c2.width, c2.height);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c2);
      }
      gl.bindTexture(gl.TEXTURE_2D, null);
    }

    if (mapImageEl) {
      if (mapImageEl.complete) createMapTexture();
      else {
        var onMapLoad = function () { createMapTexture(); mapImageEl.removeEventListener('load', onMapLoad); };
        mapImageEl.addEventListener('load', onMapLoad);
      }
      try {
        imgResizeObserver = new ResizeObserver(function() { createMapTexture(); });
        imgResizeObserver.observe(mapImageEl);
      } catch (e) {}
    }

  var start = Date.now();
    var running = true;
  var _lastOverlayW = overlay.width, _lastOverlayH = overlay.height;

  // FoW mask resources
  var fowHelper = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPx });
  var fowTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, fowTexture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);

  // Manual mask resources
  var manualHelper = Effects._buildManualMaskForOverlay(overlay, manualMaskLayers, { featherPx: maskFeatherPx });
  var manualTexture = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, manualTexture);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255,255,255,255]));
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.bindTexture(gl.TEXTURE_2D, null);

    function frame() {
      if (!running) return;
      gl.viewport(0, 0, overlay.width, overlay.height);
      gl.clearColor(0,0,0,0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.enableVertexAttribArray(positionLoc);
      gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(resLoc, overlay.width, overlay.height);
      gl.uniform1f(timeLoc, Date.now() - start);
      gl.uniform1f(densityLoc, density);
      gl.uniform1f(speedLoc, speed);
      gl.uniform1f(contrastLoc, config.contrast || 1.0);
      gl.uniform1f(grainLoc, config.grain || 0.15);
      gl.uniform1f(falloffLoc, config.falloff || 1.0);
      var rgb = rgbFromHex(color);
      gl.uniform3f(colorLoc, rgb[0], rgb[1], rgb[2]);
      // bind map texture if present
      if (mapTexture) {
        // Recreate map texture if overlay size changed
        if (overlay.width !== _lastOverlayW || overlay.height !== _lastOverlayH) {
          _lastOverlayW = overlay.width; _lastOverlayH = overlay.height;
          try { createMapTexture(); } catch(e) {}
        }
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, mapTexture);
        gl.uniform1i(mapLoc, 0);
      }
      // Update and bind FoW texture (unit 1)
      try {
        var upd = fowHelper.update();
        if (upd && upd.canvas) {
          gl.activeTexture(gl.TEXTURE1);
          gl.bindTexture(gl.TEXTURE_2D, fowTexture);
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, upd.canvas);
          gl.uniform1i(fowLoc, 1);
        }
      } catch(e) {}
      // Update and bind Manual mask (unit 2)
      try {
        manualHelper.setLayers(manualMaskLayers);
        var updM = manualHelper.update();
        if (updM && updM.canvas) {
          gl.activeTexture(gl.TEXTURE2);
          gl.bindTexture(gl.TEXTURE_2D, manualTexture);
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, updM.canvas);
          gl.uniform1i(manualLoc, 2);
        }
      } catch(e) {}
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);

    return {
      stop: function () {
        running = false;
        try { gl.getExtension('WEBGL_lose_context').loseContext(); } catch (e) {}
        if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
        if (ro) try { ro.disconnect(); } catch (e) {}
        if (imgResizeObserver) try { imgResizeObserver.disconnect(); } catch (e) {}
        try{ fowHelper && fowHelper.destroy(); }catch(e){}
        try{ manualHelper && manualHelper.destroy(); }catch(e){}
      },
      updateConfig: function (c) {
        density = c.density != null ? c.density : density;
        speed = c.speed != null ? c.speed : speed;
        color = c.color || color;
        useManualMask = c.mask != null ? !!c.mask : useManualMask;
        manualMaskLayers = c.mask_layers || manualMaskLayers;
        maskFeatherPx = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPx));
        try{ manualHelper.setLayers(manualMaskLayers);}catch(e){}
        try{ if (manualHelper.setOptions) manualHelper.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
        try{ if (fowHelper.setOptions) fowHelper.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
      }
    };
  }

  // Canvas fallback (2D layered noise) - draw only inside container size
  var ctx = overlay.getContext('2d');
  var running = true;
  var t = 0;
  // FoW mask for 2D path
  var fow2D = Effects._buildFoWMaskForOverlay(overlay, { featherPx: maskFeatherPx });
  var manual2D = Effects._buildManualMaskForOverlay(overlay, manualMaskLayers, { featherPx: maskFeatherPx });

  function draw() {
    if (!running) return;
    ctx.clearRect(0,0,overlay.width, overlay.height);
    // multiple layers for richer fog
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = color;
    var w = overlay.width, h = overlay.height;
    for (var layer=0; layer<4; layer++) {
      var step = 6 - layer;
      var alpha = (0.06 + layer*0.04) * density;
      ctx.globalAlpha = alpha;
      for (var y=0; y<h; y+=step) {
        for (var x=0; x<w; x+=step) {
          var nx = x / w * (1 + layer*0.8);
          var ny = y / h * (1 + layer*0.8);
          var v = Math.abs(Math.sin((nx + t*0.002*(layer+1))*3.1415) * Math.cos((ny + t*0.001*(layer+1))*3.1415));
          if (Math.random() > 0.995) v += 0.2; // grain
          if (v > 0.45) ctx.fillRect(x, y, step, step);
        }
      }
    }
    // mask by map image if available
    var mapEl = document.querySelector('.image-container img.background-image, .image-container img');
    if (mapEl && mapEl.complete) {
      var tx = document.createElement('canvas');
      tx.width = overlay.width;
      tx.height = overlay.height;
      var tctx = tx.getContext('2d');
      tctx.drawImage(mapEl, 0, 0, overlay.width, overlay.height);
      // apply mask: keep fog only where map is opaque
      ctx.globalCompositeOperation = 'destination-in';
      ctx.drawImage(tx, 0, 0);
      ctx.globalCompositeOperation = 'source-over';
    }
    // Apply Manual mask (2D)
    try {
      var man = manual2D.update();
      if (man && man.canvas) {
        ctx.globalCompositeOperation = 'destination-in';
        ctx.drawImage(man.canvas, 0, 0);
        ctx.globalCompositeOperation = 'source-over';
      }
    } catch(e) {}
    // Apply FoW mask (2D)
    try {
      var upd = fow2D.update();
      if (upd && upd.canvas) {
        ctx.globalCompositeOperation = 'destination-in';
        ctx.drawImage(upd.canvas, 0, 0);
        ctx.globalCompositeOperation = 'source-over';
      }
    } catch(e) {}
    t += speed * 5;
    requestAnimationFrame(draw);
  }

  requestAnimationFrame(draw);

  return {
  stop: function () { running = false; overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} try{ fow2D && fow2D.destroy(); }catch(e){} try{ manual2D && manual2D.destroy(); }catch(e){} },
    updateConfig: function (c) {
      density = c.density != null ? c.density : density;
      speed = c.speed != null ? c.speed : speed;
      color = c.color || color;
      useManualMask = c.mask != null ? !!c.mask : useManualMask;
      manualMaskLayers = c.mask_layers || manualMaskLayers;
      maskFeatherPx = Math.max(0, (c.mask_feather != null ? c.mask_feather : maskFeatherPx));
      try{ manual2D.setLayers(manualMaskLayers);}catch(e){}
      try{ if (manual2D.setOptions) manual2D.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
      try{ if (fow2D.setOptions) fow2D.setOptions({ featherPx: maskFeatherPx }); }catch(e){}
    }
  };
};

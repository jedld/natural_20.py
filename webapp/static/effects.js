const Effects = {
  // store active effect instances
  _instances: {},

  // Broadcast handler registration
  initSocketHandlers: function (socket) {
    socket.on('effect:set', function (data) {
      // data = { effect: 'fog', action: 'start'|'stop'|'update', config: {...} }
      console.log('effect:set', data);
      if (data.action === 'start') {
        if (data.effect === 'fog') {
          if (Effects._instances.fog) Effects._instances.fog.stop();
          Effects._instances.fog = Effects.createFogEffect(data.config || {});
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
      }
    });
  },

  createRainEffect: function () {
    // Set up variables
    var canvas = document.querySelector('canvas');
    var ctx = canvas.getContext('2d');
    var w = canvas.width;
    var h = canvas.height;
    var drops = [];

    // Create drop object
    function Drop() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.r = Math.random() * 1 + 0.5; // thinner lines
      this.speed = 10 + Math.random() * 10 + 1;
      this.angle = Math.random() * 5;
    }

    // Create drops
    for (var i = 0; i < 100; i++) {
      drops.push(new Drop());
    }

    // Draw drops
    function draw() {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      for (var i = 0; i < drops.length; i++) {
        var drop = drops[i];
        ctx.moveTo(drop.x, drop.y);
        ctx.lineTo(drop.x + drop.angle, drop.y + drop.speed + 3);
        ctx.lineWidth = drop.r;
        ctx.strokeStyle = '#fff';
        ctx.stroke();
      }
      move();
    }

    // Move drops
    function move() {
      for (var i = 0; i < drops.length; i++) {
        var drop = drops[i];
        drop.y += drop.speed;
        drop.x += drop.angle / 10;
        if (drop.y > h) {
          drop.y = -25;
        }
        if (drop.x > w) {
          drop.x = 0;
        }
      }
    }

    // Start animation loop
    var interval = setInterval(draw, 33);

    // Stop rain effect
    function stopRainEffect() {
      clearInterval(interval);
      ctx.clearRect(0, 0, w, h);
    }

    return {
      stopRainEffect: stopRainEffect
    };
  },
  
  createSnowEffect: function () {
    // Set up variables
    var canvas = document.querySelector('canvas');
    var ctx = canvas.getContext('2d');
    var w = canvas.width;
    var h = canvas.height;
    var flakes = [];

    // Create flake object
    function Flake() {
      this.x = Math.random() * w;
      this.y = Math.random() * h;
      this.r = Math.random() * 4 + 1; // thicker lines
      this.speed = Math.random() * 3 + 1;
      this.angle = Math.random() * 360;
    }

    // Create flakes
    for (var i = 0; i < 100; i++) {
      flakes.push(new Flake());
    }

    // Draw flakes
    function draw() {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#fff';
      ctx.beginPath();
      for (var i = 0; i < flakes.length; i++) {
        var flake = flakes[i];
        ctx.moveTo(flake.x, flake.y);
        ctx.arc(flake.x, flake.y, flake.r, 0, Math.PI * 2, true);
      }
      ctx.fill();
      move();
    }

    // Move flakes
    function move() {
      for (var i = 0; i < flakes.length; i++) {
        var flake = flakes[i];
        flake.y += flake.speed;
        flake.x += Math.cos(flake.angle) * 2;
        if (flake.y > h) {
          flake.y = -25;
        }
        if (flake.x > w) {
          flake.x = 0;
        }
        if (flake.x < 0) {
          flake.x = w;
        }
      }
    }

    // Start animation loop
    var interval = setInterval(draw, 33);

    // Stop snow effect
    function stopSnowEffect() {
      clearInterval(interval);
      ctx.clearRect(0, 0, w, h);
    }

    return {
      stopSnowEffect: stopSnowEffect
    };
  }
}

// Fog implementation: WebGL accelerated if available, canvas fallback otherwise.
Effects.createFogEffect = function (config) {
  config = config || {};
  var density = config.density != null ? config.density : 0.45;
  var speed = config.speed != null ? config.speed : 0.7;
  var color = config.color || '#cfcfd6';

  // Attach overlay to the battlemap container so effect is masked to the map
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

  function resize() {
    // size to container's inner dimensions
    overlay.width = container.clientWidth;
    overlay.height = container.clientHeight;
    overlay.style.width = container.clientWidth + 'px';
    overlay.style.height = container.clientHeight + 'px';
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
  float outAlpha = clamp(fog * 0.85 * mapAlpha, 0.0, 0.95);
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
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, mapImageEl);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      } catch (e) {
        // fallback: draw to canvas then upload
        var c = document.createElement('canvas');
        c.width = mapImageEl.naturalWidth || mapImageEl.width;
        c.height = mapImageEl.naturalHeight || mapImageEl.height;
        var ctx2 = c.getContext('2d');
        ctx2.drawImage(mapImageEl, 0, 0, c.width, c.height);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, c);
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
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, mapTexture);
        gl.uniform1i(mapLoc, 0);
      }
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
      },
      updateConfig: function (c) { density = c.density != null ? c.density : density; speed = c.speed != null ? c.speed : speed; color = c.color || color; }
    };
  }

  // Canvas fallback (2D layered noise) - draw only inside container size
  var ctx = overlay.getContext('2d');
  var running = true;
  var t = 0;

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
    t += speed * 5;
    requestAnimationFrame(draw);
  }

  requestAnimationFrame(draw);

  return {
    stop: function () { running = false; overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} },
    updateConfig: function (c) { density = c.density != null ? c.density : density; speed = c.speed != null ? c.speed : speed; color = c.color || color; }
  };
};

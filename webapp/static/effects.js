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
      }
    });
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

    // Attach overlay to the battlemap container so effect is masked to the map
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

    function resize() {
      overlay.width = container.clientWidth;
      overlay.height = container.clientHeight;
      overlay.style.width = container.clientWidth + 'px';
      overlay.style.height = container.clientHeight + 'px';
    }
    resize();
    window.addEventListener('resize', resize);
    var ro = new ResizeObserver(resize);
    try { ro.observe(container); } catch (e) {}

    var gl = null;
    try { gl = overlay.getContext('webgl') || overlay.getContext('experimental-webgl'); } catch (e) { gl = null; }

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

        // sample map alpha to mask
        float mapA = 1.0;
        #ifdef GL_ES
        mapA = texture2D(u_map, v_uv).a;
        #else
        mapA = texture(u_map, v_uv).a;
        #endif

        // final color: base color plus white highlights
        vec3 col = baseCol * accum + vec3(1.0) * highlight * 0.6 + vec3(lightningBoost);
        float alpha = clamp(accum * mapA, 0.0, 0.95);
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
          gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, mapImageEl);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        } catch (e) {
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
        else mapImageEl.addEventListener('load', createMapTexture);
        try { new ResizeObserver(function(){ createMapTexture(); }).observe(mapImageEl); } catch(e) {}
      }

      var start = Date.now();
      var running = true;
      var lightningStrength = 0.0;
      var lastLightning = 0;

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
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, mapTexture);
          gl.uniform1i(mapLoc, 0);
        }

        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        requestAnimationFrame(frame);
      }

      requestAnimationFrame(frame);

      return {
    stop: function(){ running = false; try{ gl.getExtension('WEBGL_lose_context').loseContext(); }catch(e){} overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try{ ro.disconnect(); }catch(e){} },
        updateConfig: function(c){ intensity = c.intensity != null ? c.intensity : intensity; wind = c.wind != null ? c.wind : wind; speed = c.speed != null ? c.speed : speed; color = c.color || color; lightning = c.lightning != null ? c.lightning : lightning; lightningFreq = c.lightningFreq || lightningFreq; lightningIntensity = c.lightningIntensity || lightningIntensity; }
      };
    }

    // Canvas fallback: streaked rain + lightning flashes
    var ctx = overlay.getContext('2d');
    var running = true;
    var drops = [];
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

      requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);

    return {
      stop: function(){ running = false; overlay.parentNode && overlay.parentNode.removeChild(overlay); if (ro) try { ro.disconnect(); } catch(e) {} },
      updateConfig: function(c){ intensity = c.intensity != null ? c.intensity : intensity; wind = c.wind != null ? c.wind : wind; speed = c.speed != null ? c.speed : speed; color = c.color || color; lightning = c.lightning != null ? c.lightning : lightning; lightningFreq = c.lightningFreq || lightningFreq; lightningIntensity = c.lightningIntensity || lightningIntensity; }
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

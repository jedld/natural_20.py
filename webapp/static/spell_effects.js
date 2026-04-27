// Lightweight, modular spell effects renderer.
// Usage: SpellEffects.play(spellKey, payload) -> Promise resolves after animation.
// payload: { source: 'entityId', target: 'id' | ['id',...], label?: string, spell?: string }
(function(global){
  const REGISTRY = {};

  function register(name, renderer) {
    if (!name || typeof renderer !== 'function') return;
    REGISTRY[String(name).toLowerCase()] = renderer;
  }

  function getTileCenterFromEngine($tile) {
    try {
      if (typeof getTileCenter === 'function') return getTileCenter($tile);
    } catch (e) {}
    return null;
  }

  // Get pixel center of tile by map coordinates (data-coords-x/y)
  function tileCenterByCoords(tx, ty){
    try {
      const el = document.querySelector(`.tile[data-coords-x="${tx}"][data-coords-y="${ty}"]`);
      if (!el) return null;
      const $tile = typeof $ === 'function' ? $(el) : null;
      if ($tile && $tile.length){
        const p = getTileCenterFromEngine($tile);
        if (p) return p;
      }
      const rect = el.getBoundingClientRect();
      const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      return { x: rect.left + scrollLeft + rect.width/2, y: rect.top + scrollTop + rect.height/2 };
    } catch(e){ return null; }
  }

  // Get tile coordinates [x,y] for an entity id
  function entityTileCoords(entityId){
    try {
      let el = document.querySelector(`[data-entity-id="${entityId}"]`);
      if (!el) el = document.querySelector(`[data-id="${entityId}"]`) || document.getElementById(String(entityId));
      if (!el) return null;
      const tile = el.closest ? (el.closest('.tile, .map-tile, .grid-cell, .cell') || el) : el;
      const x = tile.getAttribute('data-coords-x');
      const y = tile.getAttribute('data-coords-y');
      if (x == null || y == null) return null;
      return [Number(x), Number(y)];
    } catch(e){ return null; }
  }
  
  // Utility: normalize a value to an array
  function ensureArray(x){
    if (x == null) return [];
    return Array.isArray(x) ? x : [x];
  }

  // Compute the on-screen center of an entity by id, with fallbacks
  function centerOfEntity(entityId){
    try {
      // Prefer elements tagged with data-entity-id
      let el = document.querySelector(`[data-entity-id="${entityId}"]`);
      if (!el) {
        // Common alternates
        el = document.querySelector(`[data-id="${entityId}"]`) || document.getElementById(String(entityId));
      }
      if (el) {
        // Try to locate the containing tile cell if present
        const tile = el.closest ? (el.closest('.tile, .map-tile, .grid-cell, .cell') || el) : el;
        const $tile = typeof $ === 'function' ? $(tile) : null;
        if ($tile && $tile.length){
          const p = getTileCenterFromEngine($tile);
          if (p) return p;
        }
        const rect = tile.getBoundingClientRect();
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        return { x: rect.left + scrollLeft + rect.width/2, y: rect.top + scrollTop + rect.height/2 };
      }
    } catch(e) {}
    return null;
  }

  // Create a full-screen canvas overlay at a given z-index
  function createOverlay(z){
    const overlay = document.createElement('canvas');
    overlay.width = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    overlay.height = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
    overlay.style.position = 'absolute';
    overlay.style.left = '0';
    overlay.style.top = '0';
    overlay.style.zIndex = String(z || 1100);
    overlay.style.pointerEvents = 'none';
    document.body.appendChild(overlay);
    const ctx = overlay.getContext('2d');
    return { overlay, ctx, destroy: () => { try { document.body.removeChild(overlay); } catch(e) {} } };
  }

  // Public API to play a registered effect (safe no-op on errors)
  function play(name, payload){
    return new Promise((resolve) => {
      try {
        if (!name) return resolve();
        const key = String(name).toLowerCase();
        const renderer = REGISTRY[key] || REGISTRY[(payload && payload.spell) ? String(payload.spell).toLowerCase() : ''];
        if (!renderer) return resolve();
        const ret = renderer(payload);
        if (ret && typeof ret.then === 'function') ret.then(resolve).catch(()=>resolve()); else resolve();
      } catch(e){ resolve(); }
    });
  }

  // Magic Missile: sequential darts with curved paths and small impact bursts
  register('magic_missile', function(payload){
    return new Promise((resolve) => {
      const targets = ensureArray(payload && payload.target);
      if (!targets.length) return resolve();
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!src || !centers.length) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1102);
      const color = [180, 130, 255]; // arcane purple
      let i = 0;
      function launchNext(){
        if (i >= centers.length) { destroy(); resolve(); return; }
        const target = centers[i++];
        const start = performance.now();
        const duration = 450;
        const ctrl = { x: (src.x + target.x)/2 + (Math.random() < 0.5 ? -1 : 1) * 60, y: (Math.min(src.y, target.y)) - 80 };
        const dart = (now) => {
          const t = Math.min(1, (now - start)/duration);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          // Quadratic bezier position
          const x = (1-t)*(1-t)*src.x + 2*(1-t)*t*ctrl.x + t*t*target.x;
          const y = (1-t)*(1-t)*src.y + 2*(1-t)*t*ctrl.y + t*t*target.y;
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          // trail
          ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.35)`; ctx.lineWidth = 4;
          ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.quadraticCurveTo(ctrl.x, ctrl.y, x, y); ctx.stroke();
          // head
          ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.9)`; ctx.shadowColor = `rgba(${color[0]},${color[1]},${color[2]},0.7)`; ctx.shadowBlur = 12;
          ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2); ctx.fill();
          ctx.restore();
          if (t < 1) requestAnimationFrame(dart); else impact();
        };
        const impactStart = { time: 0 };
        function impact(){
          const t0 = performance.now(); impactStart.time = t0;
          const burst = (now) => {
            const t = Math.min(1, (now - t0)/250);
            ctx.clearRect(0,0,overlay.width, overlay.height);
            const alpha = 1 - t;
            const r = 24 + 22*t;
            ctx.save(); ctx.globalCompositeOperation = 'screen';
            ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha.toFixed(2)})`; ctx.lineWidth = 3;
            ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2); ctx.stroke(); ctx.restore();
            if (t < 1) requestAnimationFrame(burst); else launchNext();
          };
          requestAnimationFrame(burst);
        }
        requestAnimationFrame(dart);
      }
      launchNext();
    });
  });

  // Firebolt: fast straight bolt and fiery impact ring
  register('firebolt', function(payload){
    return new Promise((resolve) => {
      const targets = ensureArray(payload && payload.target);
      if (!targets.length) return resolve();
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!src || !centers.length) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1102);
      const color = [255, 140, 0]; // orange
      const target = centers[0]; // first target only
      const start = performance.now();
      const duration = 250;
      const frame = (now) => {
        const t = Math.min(1, (now - start)/duration);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        const x = src.x + (target.x - src.x)*t;
        const y = src.y + (target.y - src.y)*t;
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},0.6)`; ctx.lineWidth = 5;
        ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
        ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},0.95)`; ctx.shadowColor = `rgba(${color[0]},${color[1]},${color[2]},0.8)`; ctx.shadowBlur = 10;
        ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI*2); ctx.fill(); ctx.restore();
        if (t < 1) requestAnimationFrame(frame); else impact();
      };
      function impact(){
        const t0 = performance.now();
        const burst = (now) => {
          const t = Math.min(1, (now - t0)/280);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          const alpha = 1 - t;
          const r = 20 + 28*t;
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha.toFixed(2)})`; ctx.lineWidth = 4 - 2*t;
          ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2); ctx.stroke(); ctx.restore();
          if (t < 1) requestAnimationFrame(burst); else { destroy(); resolve(); }
        };
        requestAnimationFrame(burst);
      }
      requestAnimationFrame(frame);
    });
  });

  // Eldritch Blast: arcane beams with void ripple impacts, supports multiple beams/targets
  register('eldritch_blast', function(payload){
    return new Promise((resolve) => {
      const beamTargets = ensureArray(payload && payload.target);
      if (!beamTargets.length) return resolve();
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const centers = beamTargets.map(centerOfEntity).filter(Boolean);
      if (!src || !centers.length) return resolve();

      const { overlay, ctx, destroy } = createOverlay(1102);
      const coreColor = [150, 70, 255]; // vibrant violet core
      const auraColor = [70, 0, 140];   // shadowy edge for contrast
      let index = 0;

      const fireBeam = () => {
        if (index >= centers.length) {
          destroy();
          resolve();
          return;
        }

        const target = centers[index++];
        const pathDuration = 260;
        const wobblePhase = Math.random() * Math.PI * 2;

        const drawBeam = (start) => {
          const step = (now) => {
            const t = Math.min(1, (now - start) / pathDuration);
            ctx.clearRect(0, 0, overlay.width, overlay.height);
            ctx.save();
            ctx.globalCompositeOperation = 'screen';

            // Source pulse
            const pulse = 6 + 4 * Math.sin((now - start) * 0.018);
            ctx.fillStyle = `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},0.35)`;
            ctx.beginPath();
            ctx.arc(src.x, src.y, pulse, 0, Math.PI * 2);
            ctx.fill();

            // Beam trajectory with a subtle wobble
            const wobbleStrength = 14 * (1 - t);
            const wobbleX = Math.sin(wobblePhase + now * 0.02) * wobbleStrength;
            const wobbleY = Math.cos(wobblePhase + now * 0.017) * wobbleStrength;
            const x = src.x + (target.x - src.x) * t + wobbleX;
            const y = src.y + (target.y - src.y) * t + wobbleY;

            ctx.strokeStyle = `rgba(${auraColor[0]},${auraColor[1]},${auraColor[2]},0.45)`;
            ctx.lineWidth = 7;
            ctx.beginPath();
            ctx.moveTo(src.x, src.y);
            ctx.lineTo(x, y);
            ctx.stroke();

            ctx.strokeStyle = `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},0.85)`;
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(src.x, src.y);
            ctx.lineTo(x, y);
            ctx.stroke();

            ctx.fillStyle = `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},0.95)`;
            ctx.shadowColor = `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},0.9)`;
            ctx.shadowBlur = 14;
            ctx.beginPath();
            ctx.arc(x, y, 6.5 - 2.5 * t, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();

            if (t < 1) {
              requestAnimationFrame(step);
            } else {
              impact(performance.now());
            }
          };
          requestAnimationFrame(step);
        };

        const impact = (startTime) => {
          const impactDuration = 240;
          const shockRings = 3;

          const burst = (now) => {
            const t = Math.min(1, (now - startTime) / impactDuration);
            ctx.clearRect(0, 0, overlay.width, overlay.height);
            ctx.save();
            ctx.globalCompositeOperation = 'screen';

            const maxRadius = 45;
            const radius = 12 + maxRadius * t;
            const alpha = 0.85 * (1 - t);
            const gradient = ctx.createRadialGradient(target.x, target.y, 0, target.x, target.y, radius);
            gradient.addColorStop(0, `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},${alpha})`);
            gradient.addColorStop(0.35, `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},${alpha * 0.6})`);
            gradient.addColorStop(1, `rgba(${auraColor[0]},${auraColor[1]},${auraColor[2]},0)`);
            ctx.fillStyle = gradient;
            ctx.beginPath();
            ctx.arc(target.x, target.y, radius, 0, Math.PI * 2);
            ctx.fill();

            // Void ripples
            for (let i = 0; i < shockRings; i++) {
              const ringT = Math.max(0, t - i * 0.18);
              if (ringT <= 0) continue;
              const ringAlpha = Math.max(0, 0.35 - ringT * 0.35);
              const ringRadius = radius * (0.6 + 0.35 * i) * ringT;
              ctx.strokeStyle = `rgba(${coreColor[0]},${coreColor[1]},${coreColor[2]},${ringAlpha.toFixed(2)})`;
              ctx.lineWidth = Math.max(1.5, 4 - ringT * 3);
              ctx.beginPath();
              ctx.arc(target.x, target.y, ringRadius, 0, Math.PI * 2);
              ctx.stroke();
            }

            ctx.restore();

            if (t < 1) {
              requestAnimationFrame(burst);
            } else {
              setTimeout(fireBeam, 90);
            }
          };
          requestAnimationFrame(burst);
        };

        drawBeam(performance.now());
      };

      fireBeam();
    });
  });

  // Misty Step: silvery vanish and reappear between coordinates
  register('misty_step', function(payload){
    return new Promise((resolve) => {
      const fromCoords = Array.isArray(payload && payload.from) ? payload.from : null;
      const hasCoordinateTarget = Array.isArray(payload && payload.target) && payload.target.length === 2 && typeof payload.target[0] === 'number' && typeof payload.target[1] === 'number';
      const targets = hasCoordinateTarget ? [payload.target] : ensureArray(payload && payload.target);
      const rawTarget = targets.length ? targets[0] : null;

      const originCenter = (() => {
        if (fromCoords && fromCoords.length === 2) {
          const center = tileCenterByCoords(fromCoords[0], fromCoords[1]);
          if (center) return center;
        }
        if (payload && payload.source) {
          // Fallback to current entity location if the origin tile is no longer present
          const coords = entityTileCoords(payload.source);
          if (coords && coords.length === 2) {
            const center = tileCenterByCoords(coords[0], coords[1]);
            if (center) return center;
          }
          return centerOfEntity(payload.source);
        }
        return null;
      })();

      const destinationCenter = (() => {
        const candidate = (arr) => {
          if (Array.isArray(arr) && arr.length === 2 && typeof arr[0] === 'number' && typeof arr[1] === 'number') {
            const center = tileCenterByCoords(arr[0], arr[1]);
            if (center) return center;
          }
          return null;
        };

        if (hasCoordinateTarget) {
          const direct = candidate(payload.target);
          if (direct) return direct;
        }

        const arrayTarget = candidate(rawTarget);
        if (arrayTarget) return arrayTarget;

        if (rawTarget != null) {
          const entityCenter = centerOfEntity(rawTarget);
          if (entityCenter) return entityCenter;
        }

        if (payload && payload.source) {
          const coords = entityTileCoords(payload.source);
          if (coords) {
            const fallback = candidate(coords);
            if (fallback) return fallback;
          }
          return centerOfEntity(payload.source);
        }

        return null;
      })();

      if (!originCenter || !destinationCenter) return resolve();

      const { overlay, ctx, destroy } = createOverlay(1102);
      const aura = [185, 215, 255];
      const core = [120, 170, 255];

      function drawRing(center, radius, strength) {
        ctx.save();
        ctx.globalCompositeOperation = 'screen';
        const grad = ctx.createRadialGradient(center.x, center.y, Math.max(1, radius * 0.35), center.x, center.y, radius);
        grad.addColorStop(0, `rgba(${aura[0]},${aura[1]},${aura[2]},${(0.6 * strength).toFixed(2)})`);
        grad.addColorStop(1, `rgba(${core[0]},${core[1]},${core[2]},0)`);
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(center.x, center.y, radius, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }

      const vanishDuration = 260;
      const appearDuration = 300;

      function stageVanish(startTime) {
        const step = (now) => {
          const t = Math.min(1, (now - startTime) / vanishDuration);
          ctx.clearRect(0, 0, overlay.width, overlay.height);
          const radius = 60 * (1 - t);
          drawRing(originCenter, Math.max(10, radius), 1 - t * 0.6);
          ctx.save();
          ctx.globalCompositeOperation = 'screen';
          ctx.fillStyle = `rgba(${core[0]},${core[1]},${core[2]},${(0.75 * (1 - t)).toFixed(2)})`;
          ctx.beginPath(); ctx.arc(originCenter.x, originCenter.y, 10 * (1 - t), 0, Math.PI * 2); ctx.fill();
          ctx.restore();
          if (t < 1) {
            requestAnimationFrame(step);
          } else {
            stageAppear(performance.now());
          }
        };
        requestAnimationFrame(step);
      }

      function stageAppear(startTime) {
        const sparkleCount = 20;
        const sparkSeeds = Array.from({ length: sparkleCount }, (_, i) => ({
          angle: (i / sparkleCount) * Math.PI * 2,
          radius: 12 + Math.random() * 14
        }));

        const step = (now) => {
          const t = Math.min(1, (now - startTime) / appearDuration);
          ctx.clearRect(0, 0, overlay.width, overlay.height);
          drawRing(destinationCenter, 20 + 45 * t, 0.8 - t * 0.5);
          ctx.save();
          ctx.globalCompositeOperation = 'screen';
          ctx.fillStyle = `rgba(${core[0]},${core[1]},${core[2]},${(0.8 * t).toFixed(2)})`;
          ctx.beginPath(); ctx.arc(destinationCenter.x, destinationCenter.y, 8 + 10 * t, 0, Math.PI * 2); ctx.fill();
          sparkSeeds.forEach((seed) => {
            const pulse = Math.sin(now * 0.02 + seed.angle) * 2;
            const r = seed.radius + 20 * (1 - t) + pulse;
            const sx = destinationCenter.x + Math.cos(seed.angle) * r;
            const sy = destinationCenter.y + Math.sin(seed.angle) * r;
            ctx.fillStyle = `rgba(${aura[0]},${aura[1]},${aura[2]},${(0.35 * (1 - t)).toFixed(2)})`;
            ctx.beginPath(); ctx.arc(sx, sy, 2 + 2 * (1 - t), 0, Math.PI * 2); ctx.fill();
          });
          ctx.restore();
          if (t < 1) {
            requestAnimationFrame(step);
          } else {
            destroy();
            resolve();
          }
        };
        requestAnimationFrame(step);
      }

      stageVanish(performance.now());
    });
  });

  // Guiding Bolt: radiant beam, starburst impact, lingering motes
  register('guiding_bolt', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const target = centers[0];
      if (!src || !target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1103);
      const color = [255, 250, 210]; // warm radiant
      const accent = [255, 215, 100];

      // Stage 1: brief charge at source
      const chargeStart = performance.now();
      const chargeDur = 180;
      const doCharge = (now) => {
        const t = Math.min(1, (now - chargeStart)/chargeDur);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        const r = 4 + 10*t;
        const a = 0.7 + 0.3*Math.sin(now*0.02);
        ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${a.toFixed(2)})`;
        ctx.shadowColor = `rgba(${accent[0]},${accent[1]},${accent[2]},0.9)`;
        ctx.shadowBlur = 16;
        ctx.beginPath(); ctx.arc(src.x, src.y, r, 0, Math.PI*2); ctx.fill();
        ctx.restore();
        if (t < 1) requestAnimationFrame(doCharge); else shoot();
      };

      // Stage 2: beam
      function shoot(){
        const start = performance.now();
        const dur = 260;
        const beam = (now) => {
          const t = Math.min(1, (now - start)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const thickness = 10 - 6*Math.abs(0.5 - t)*2;
          const alpha = 0.8;
          // main beam
          ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha})`;
          ctx.lineWidth = thickness;
          ctx.beginPath(); ctx.moveTo(src.x, src.y);
          const x = src.x + (target.x - src.x)*t, y = src.y + (target.y - src.y)*t;
          ctx.lineTo(x, y); ctx.stroke();
          // inner core
          ctx.strokeStyle = `rgba(255,255,255,0.9)`; ctx.lineWidth = Math.max(2, thickness*0.45);
          ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
          // shimmer dots along path
          for (let i=0;i<6;i++){
            const pt = i/5 * t;
            const sx = src.x + (target.x - src.x)*pt;
            const sy = src.y + (target.y - src.y)*pt;
            const rr = 2 + 2*Math.sin((now*0.02 + i)*1.3);
            ctx.beginPath(); ctx.arc(sx, sy, rr, 0, Math.PI*2);
            ctx.fillStyle = `rgba(255,255,255,0.85)`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(beam); else impact();
        };
        requestAnimationFrame(beam);
      }

      // Stage 3: starburst + lingering motes
      function impact(){
        const t0 = performance.now();
        const total = 800;
        const motes = Array.from({length: 18}, (_,i)=>({
          ang: (i/18)*Math.PI*2,
          r: 4 + Math.random()*8,
          speed: 30 + Math.random()*40
        }));
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/total);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          // starburst cross
          const fade = 1 - t;
          const len = 34 + 26*(1 - t);
          ctx.strokeStyle = `rgba(255,255,255,${(0.9*fade).toFixed(2)})`;
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.moveTo(target.x - len, target.y); ctx.lineTo(target.x + len, target.y);
          ctx.moveTo(target.x, target.y - len); ctx.lineTo(target.x, target.y + len);
          ctx.moveTo(target.x - len*0.707, target.y - len*0.707); ctx.lineTo(target.x + len*0.707, target.y + len*0.707);
          ctx.moveTo(target.x + len*0.707, target.y - len*0.707); ctx.lineTo(target.x - len*0.707, target.y + len*0.707);
          ctx.stroke();
          // radiant ring
          ctx.beginPath();
          ctx.arc(target.x, target.y, 18 + 22*t, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${accent[0]},${accent[1]},${accent[2]},${(0.7*fade).toFixed(2)})`;
          ctx.lineWidth = 3; ctx.stroke();
          // motes swirling
          motes.forEach((m, idx)=>{
            const ang = m.ang + now*0.003 + idx*0.1;
            const r = 14 + m.r + m.speed*t;
            const x = target.x + Math.cos(ang)*r;
            const y = target.y + Math.sin(ang)*r*0.65; // slight ellipse
            ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI*2);
            ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${(0.85*fade).toFixed(2)})`;
            ctx.fill();
          });
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
        };
        requestAnimationFrame(loop);
      }

      requestAnimationFrame(doCharge);
    });
  });

  // Sacred Flame: descending radiant flame from above onto targets
  register('sacred_flame', function(payload){
    return new Promise((resolve) => {
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!centers.length) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1103);
      const start = performance.now();
      const total = 900;
      const col = [255, 245, 200];
      const accent = [255, 230, 140];
      const draw = (now) => {
        const t = Math.min(1, (now - start)/total);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        centers.forEach((p, idx)=>{
          const phase = t;
          // Column parameters
          const y0 = p.y - 240; const y1 = p.y + 8;
          const w = 18 + 18*(0.6 + 0.4*Math.sin((now*0.02 + idx)*1.7));
          const alpha = 0.85 * (phase < 0.6 ? phase/0.6 : 1 - (phase-0.6)/0.4);
          // Vertical gradient column
          const grad = ctx.createLinearGradient(p.x, y0, p.x, y1);
          grad.addColorStop(0, `rgba(255,255,255,${(0.6*alpha).toFixed(2)})`);
          grad.addColorStop(0.5, `rgba(${col[0]},${col[1]},${col[2]},${alpha.toFixed(2)})`);
          grad.addColorStop(1, `rgba(${accent[0]},${accent[1]},${accent[2]},${(0.7*alpha).toFixed(2)})`);
          ctx.fillStyle = grad;
          ctx.beginPath(); ctx.moveTo(p.x - w, y0); ctx.lineTo(p.x + w, y0); ctx.lineTo(p.x + w*0.7, y1); ctx.lineTo(p.x - w*0.7, y1); ctx.closePath(); ctx.fill();
          // Flicker tongues (triangles)
          for (let k=0;k<4;k++){
            const fw = w*0.4*(0.7 + 0.3*Math.random());
            const fx = p.x + (Math.random()*2-1)*w*0.5;
            const fy = y0 + Math.random()*(y1 - y0);
            ctx.beginPath();
            ctx.moveTo(fx, fy);
            ctx.lineTo(fx + fw*(Math.random()*2-1), fy + 20 + Math.random()*40);
            ctx.lineTo(fx - fw*(Math.random()*2-1), fy + 10 + Math.random()*40);
            ctx.closePath();
            ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${(0.18*alpha).toFixed(2)})`;
            ctx.fill();
          }
          // Impact bloom near end
          if (phase > 0.4){
            const tt = (phase - 0.4)/0.6;
            const r = 18 + 30*tt;
            const a2 = 0.9*(1-tt);
            ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2);
            ctx.strokeStyle = `rgba(${accent[0]},${accent[1]},${accent[2]},${a2.toFixed(2)})`;
            ctx.lineWidth = 3 - 1.5*tt; ctx.stroke();
            // rays
            const rays = 8;
            for (let m=0;m<rays;m++){
              const ang = (m/rays)*Math.PI*2;
              const len = 26 + 14*tt;
              ctx.beginPath();
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(p.x + Math.cos(ang)*len, p.y + Math.sin(ang)*len);
              ctx.strokeStyle = `rgba(255,255,255,${(0.6*a2).toFixed(2)})`;
              ctx.lineWidth = 1.5; ctx.stroke();
            }
          }
          // falling embers
          for (let e=0;e<6;e++){
            const ex = p.x + (Math.random()*2-1)*w;
            const ey = y0 + (t + Math.random()*0.3)*(y1 - y0);
            ctx.beginPath(); ctx.arc(ex, ey, 1.6, 0, Math.PI*2);
            ctx.fillStyle = `rgba(255,255,255,${(0.6*alpha).toFixed(2)})`; ctx.fill();
          }
        });
        ctx.restore();
        if (t < 1) requestAnimationFrame(draw); else { destroy(); resolve(); }
      };
      requestAnimationFrame(draw);
    });
  });

  // Attack: enhanced visuals parsed from label/type (sword slash, bow arrow, bite/claw, etc.)
  register('attack', function(payload){
    return new Promise((resolve) => {
      const srcId = payload && payload.source;
      const tgtId = payload && payload.target;
      const label = (payload && payload.label) ? String(payload.label) : '';
      const lower = label.toLowerCase();
      const src = srcId ? centerOfEntity(srcId) : null;
      const tgt = tgtId ? centerOfEntity(tgtId) : null;
      if (!tgt) return resolve();

      // Parse weapon/type from label "attack with X ..."
      let weapon = '';
      const m = /attack with\s+([^\->\n]+)/i.exec(label);
      if (m && m[1]) weapon = m[1].trim().toLowerCase();
      if (!weapon) weapon = lower;

      // Choose style
      const isRangedFlag = !!(payload && payload.ranged);
      const isBow = /\b(shortbow|longbow|bow)\b/.test(weapon);
      const isXbow = /\b(crossbow)\b/.test(weapon);
      const isSling = /\b(sling)\b/.test(weapon);
      const isThrown = /\b(javelin|dart|handaxe|throw|thrown)\b/.test(weapon);
      const isBite = /\b(bite|beak)\b/.test(weapon);
      const isClaw = /\b(claw|talon)\b/.test(weapon);
      const isPunch = /\b(unarmed|punch|fist|kick)\b/.test(weapon);
      const isAxe = /\b(axe|greataxe|battleaxe)\b/.test(weapon);
      const isBlunt = /\b(mace|club|hammer|maul|staff)\b/.test(weapon);
      const isThrust = /\b(rapier|spear|pike|lance|trident|dagger)\b/.test(weapon);
      const isSword = /\b(sword|scimitar|sabre|saber|katana|greatsword|longsword|shortsword)\b/.test(weapon);

      // default to generic by range, then specialize when known
      let style = isRangedFlag ? 'ranged_generic' : 'melee_generic';
      if (isBow || isXbow || isSling || isThrown) {
        style = isBow ? 'ranged_arrow' : isXbow ? 'ranged_bolt' : isThrown ? 'ranged_thrown' : 'ranged_generic';
      } else if (isBite) style = 'natural_bite';
      else if (isClaw) style = 'natural_claw';
      else if (isPunch) style = 'melee_blunt'; // treat unarmed as blunt-ish
      else if (isAxe) style = 'melee_chop';
      else if (isBlunt) style = 'melee_blunt';
      else if (isThrust) style = 'melee_thrust';
      else if (isSword) style = 'melee_slash';

      const { overlay, ctx, destroy } = createOverlay(1102);

      // Fire SFX per style with generic fallback
      try { if (window.SFX && SFX.play) {
        let cue;
        if (style === 'ranged_arrow') cue = 'attack_arrow';
        else if (style === 'ranged_bolt') cue = 'attack_bolt';
        else if (style === 'ranged_thrown') cue = 'attack_thrown';
        else if (style === 'melee_chop' || style === 'melee_slash') cue = 'attack_slash';
        else if (style === 'melee_blunt') cue = 'attack_blunt';
        else if (style === 'melee_thrust') cue = 'attack_thrust';
        else if (style === 'natural_bite') cue = 'attack_bite';
        else if (style === 'natural_claw') cue = 'attack_claw';
        else cue = isRangedFlag ? 'attack_generic_ranged' : 'attack_generic_melee';
        SFX.play(cue);
      } }
      catch(e){}

      const start = performance.now();
      const total = (/ranged_/.test(style) ? 420 : 260);

      function drawArrow(t){
        if (!src) return;
        const ctrl = { x: (src.x + tgt.x)/2, y: Math.min(src.y, tgt.y) - 40 };
        const x = (1-t)*(1-t)*src.x + 2*(1-t)*t*ctrl.x + t*t*tgt.x;
        const y = (1-t)*(1-t)*src.y + 2*(1-t)*t*ctrl.y + t*t*tgt.y;
        ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.quadraticCurveTo(ctrl.x, ctrl.y, x, y); ctx.stroke();
        // arrow head
        ctx.save(); ctx.translate(x, y);
        const ang = Math.atan2(y - ctrl.y, x - ctrl.x);
        ctx.rotate(ang);
        ctx.fillStyle = 'rgba(255,255,255,0.95)';
        ctx.beginPath(); ctx.moveTo(0,0); ctx.lineTo(-8, 3); ctx.lineTo(-8, -3); ctx.closePath(); ctx.fill();
        ctx.restore();
        // faint contrail
        ctx.strokeStyle = 'rgba(200,220,255,0.35)'; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.quadraticCurveTo(ctrl.x, ctrl.y, x, y); ctx.stroke();
      }

      function drawBolt(t){
        if (!src) return;
        const x = src.x + (tgt.x - src.x)*t;
        const y = src.y + (tgt.y - src.y)*t;
        ctx.strokeStyle = 'rgba(230,240,255,0.9)'; ctx.lineWidth = 3.5;
        ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI*2); ctx.fillStyle='rgba(255,255,255,0.9)'; ctx.fill();
      }

      function drawThrown(t){
        if (!src) return;
        const ctrl = { x: (src.x + tgt.x)/2, y: Math.min(src.y, tgt.y) - 60 };
        const x = (1-t)*(1-t)*src.x + 2*(1-t)*t*ctrl.x + t*t*tgt.x;
        const y = (1-t)*(1-t)*src.y + 2*(1-t)*t*ctrl.y + t*t*tgt.y;
        ctx.save(); ctx.translate(x, y);
        ctx.rotate(t*10);
        ctx.fillStyle = 'rgba(255,255,255,0.9)';
        ctx.beginPath(); ctx.moveTo(0,-3); ctx.lineTo(6,0); ctx.lineTo(0,3); ctx.lineTo(-6,0); ctx.closePath(); ctx.fill();
        ctx.restore();
        ctx.strokeStyle = 'rgba(220,230,255,0.35)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.quadraticCurveTo(ctrl.x, ctrl.y, x, y); ctx.stroke();
      }

      function drawSlash(t){
        const radius = 24 + 8*Math.sin((start+t*1000)*0.002);
        const ang = start*0.0015 + t*3.0;
        ctx.strokeStyle = 'rgba(255,100,100,0.9)'; ctx.lineWidth = 4;
        ctx.beginPath(); ctx.arc(tgt.x, tgt.y, radius, ang, ang + Math.PI*0.95);
        ctx.stroke();
        ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(tgt.x, tgt.y, radius-2, ang+0.05, ang + Math.PI*0.9); ctx.stroke();
      }

      function drawGenericMelee(t){
        // neutral flash cross
        const len = 18 + 10*t;
        const alpha = 0.8 * (1 - Math.abs(0.5 - t) * 2);
        ctx.strokeStyle = `rgba(230,240,255,${alpha.toFixed(2)})`;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(tgt.x - len, tgt.y); ctx.lineTo(tgt.x + len, tgt.y);
        ctx.moveTo(tgt.x, tgt.y - len); ctx.lineTo(tgt.x, tgt.y + len);
        ctx.stroke();
      }

      function drawChop(t){
        const ang = start*0.002 + t*4.0;
        const len = 30;
        const x0 = tgt.x + Math.cos(ang)*(-len), y0 = tgt.y + Math.sin(ang)*(-len);
        const x1 = tgt.x + Math.cos(ang)*(len), y1 = tgt.y + Math.sin(ang)*(len);
        ctx.strokeStyle = 'rgba(255,140,100,0.9)'; ctx.lineWidth = 5;
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      }

      function drawBlunt(t){
        const r = 16 + 14*t;
        ctx.beginPath(); ctx.arc(tgt.x, tgt.y, r, 0, Math.PI*2);
        ctx.strokeStyle = 'rgba(255,200,120,0.8)';
        ctx.lineWidth = 6 - 3*t;
        ctx.stroke();
      }

      function drawGenericRanged(t){
        if (!src) return;
        const x = src.x + (tgt.x - src.x)*t;
        const y = src.y + (tgt.y - src.y)*t;
        ctx.strokeStyle = 'rgba(220,230,255,0.8)'; ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI*2); ctx.fillStyle='rgba(255,255,255,0.9)'; ctx.fill();
      }

      function drawThrust(t){
        if (!src) return;
        const x = src.x + (tgt.x - src.x)*Math.min(1,t*1.2);
        const y = src.y + (tgt.y - src.y)*Math.min(1,t*1.2);
        ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
        // tip
        ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI*2); ctx.fillStyle='rgba(255,255,255,0.95)'; ctx.fill();
      }

      function drawClaw(t){
        const off = 10; const sep = 6;
        for (let i=-1;i<=1;i++){
          const dx = i*sep;
          ctx.strokeStyle = 'rgba(255,120,120,0.9)'; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(tgt.x - off + dx, tgt.y - off);
          ctx.lineTo(tgt.x + off + dx, tgt.y + off);
          ctx.stroke();
          ctx.strokeStyle = 'rgba(255,255,255,0.9)'; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(tgt.x - off + dx, tgt.y - off);
          ctx.lineTo(tgt.x + off + dx, tgt.y + off);
          ctx.stroke();
        }
      }

      function drawBite(t){
        const r = 14 + 6*Math.sin(start*0.005);
        // upper arc teeth
        ctx.strokeStyle='rgba(255,255,255,0.9)'; ctx.lineWidth=2;
        ctx.beginPath(); ctx.arc(tgt.x, tgt.y, r, Math.PI*0.1, Math.PI*0.9); ctx.stroke();
        // lower arc
        ctx.beginPath(); ctx.arc(tgt.x, tgt.y, r, -Math.PI*0.9, -Math.PI*0.1); ctx.stroke();
      }

      const draw = (now) => {
        const t = Math.min(1, (now - start)/total);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
  if (style === 'ranged_arrow') drawArrow(t);
        else if (style === 'ranged_bolt') drawBolt(t);
        else if (style === 'ranged_thrown') drawThrown(t);
  else if (style === 'ranged_generic') drawGenericRanged(t);
        else if (style === 'melee_slash') drawSlash(t);
        else if (style === 'melee_chop') drawChop(t);
        else if (style === 'melee_blunt') drawBlunt(t);
        else if (style === 'melee_thrust') drawThrust(t);
        else if (style === 'natural_claw') drawClaw(t);
        else if (style === 'natural_bite') drawBite(t);
  else drawGenericMelee(t);
        ctx.restore();
        if (t < 1) requestAnimationFrame(draw); else impact();
      };

      function impact(){
        try { if (window.SFX && SFX.play) {
          let cue;
          if (style.startsWith('ranged_')) cue = 'attack_impact_ranged';
          else if (style === 'melee_blunt') cue = 'attack_blunt';
          else if (style === 'melee_thrust') cue = 'attack_thrust';
          else if (style === 'natural_bite') cue = 'attack_bite';
          else if (style === 'natural_claw') cue = 'attack_claw';
          else cue = 'attack_impact_melee';
          SFX.play(cue);
        } }
        catch(e){}
        const t0 = performance.now();
        const dur = 260;
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const a = 1 - t; const r = 16 + 22*t;
          ctx.beginPath(); ctx.arc(tgt.x, tgt.y, r, 0, Math.PI*2);
          const col = style.startsWith('ranged_') ? '200,220,255' : (style==='melee_blunt'?'255,200,120':'255,120,120');
          ctx.strokeStyle = `rgba(${col},${a.toFixed(2)})`; ctx.lineWidth = 3 - 1.5*t; ctx.stroke();
          // sparks/cracks for blunt
          if (style === 'melee_blunt'){
            for (let i=0;i<8;i++){
              const ang = (i/8)*Math.PI*2;
              const len = 8 + 10*t;
              ctx.beginPath(); ctx.moveTo(tgt.x, tgt.y);
              ctx.lineTo(tgt.x + Math.cos(ang)*len, tgt.y + Math.sin(ang)*len);
              ctx.strokeStyle = 'rgba(255,255,255,0.7)'; ctx.lineWidth = 1.4; ctx.stroke();
            }
          } else {
            for (let i=0;i<6;i++){
              const ang = (i/6)*Math.PI*2 + now*0.004;
              const len = 12 + 10*t;
              ctx.beginPath();
              ctx.moveTo(tgt.x, tgt.y);
              ctx.lineTo(tgt.x + Math.cos(ang)*len, tgt.y + Math.sin(ang)*len);
              ctx.strokeStyle = 'rgba(255,255,255,0.65)'; ctx.lineWidth = 1.2; ctx.stroke();
            }
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
        };
        requestAnimationFrame(loop);
      }
      requestAnimationFrame(draw);
    });
  });

  // Ray of Frost: icy jagged ray, snow drift, crystalline impact
  register('ray_of_frost', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const target = centers[0];
      if (!src || !target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1102);
      const color = [140, 200, 255];
      const start = performance.now();
      const travel = 260;
      function drawJaggedLine(ax, ay, bx, by, alpha){
        const dx = bx - ax, dy = by - ay; const dist = Math.hypot(dx, dy);
        const steps = Math.max(6, Math.floor(dist/40));
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha})`;
        ctx.lineWidth = 3; ctx.beginPath();
        for (let i=0;i<=steps;i++){
          const t = i/steps;
          const x = ax + dx*t; const y = ay + dy*t;
          const nx = -dy/dist, ny = dx/dist;
          const off = (Math.sin((i*1.7)+start*0.02) * 6) * (1 - Math.abs(0.5 - t)*2);
          const jx = x + nx*off, jy = y + ny*off;
          if (i===0) ctx.moveTo(jx, jy); else ctx.lineTo(jx, jy);
        }
        ctx.stroke();
        // inner core
        ctx.strokeStyle = `rgba(255,255,255,${alpha})`; ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
      }
      const fly = (now) => {
        const t = Math.min(1, (now - start)/travel);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        const x = src.x + (target.x - src.x)*t;
        const y = src.y + (target.y - src.y)*t;
        drawJaggedLine(src.x, src.y, x, y, 0.85);
        // cold motes drifting
        for (let i=0;i<8;i++){
          const pt = Math.random()*t;
          const px = src.x + (x - src.x)*pt + (Math.random()*2-1)*8;
          const py = src.y + (y - src.y)*pt + (Math.random()*2-1)*8;
          ctx.beginPath(); ctx.arc(px, py, 1.5, 0, Math.PI*2);
          ctx.fillStyle = 'rgba(220,240,255,0.6)'; ctx.fill();
        }
        if (t < 1) requestAnimationFrame(fly); else impact();
      };
      function impact(){
        const t0 = performance.now();
        const dur = 520;
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const fade = 1 - t;
          // crystal ring
          ctx.beginPath(); ctx.arc(target.x, target.y, 22 + 24*t, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${(0.8*fade).toFixed(2)})`;
          ctx.lineWidth = 3 - 1.5*t; ctx.stroke();
          // snowflake cross
          const len = 24 + 12*(1 - t);
          ctx.strokeStyle = `rgba(255,255,255,${(0.9*fade).toFixed(2)})`; ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(target.x - len, target.y); ctx.lineTo(target.x + len, target.y);
          ctx.moveTo(target.x, target.y - len); ctx.lineTo(target.x, target.y + len);
          ctx.moveTo(target.x - len*0.577, target.y - len*0.577); ctx.lineTo(target.x + len*0.577, target.y + len*0.577);
          ctx.moveTo(target.x + len*0.577, target.y - len*0.577); ctx.lineTo(target.x - len*0.577, target.y + len*0.577);
          ctx.stroke();
          // lingering frost mist
          for (let i=0;i<12;i++){
            const ang = (i/12)*Math.PI*2 + now*0.0015;
            const r = 10 + 22*t + Math.sin(ang*3)*2;
            const px = target.x + Math.cos(ang)*r, py = target.y + Math.sin(ang)*r;
            ctx.beginPath(); ctx.arc(px, py, 2, 0, Math.PI*2);
            ctx.fillStyle = `rgba(210,235,255,${(0.5*fade).toFixed(2)})`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
        };
        requestAnimationFrame(loop);
      }
      requestAnimationFrame(fly);
    });
  });

  // Armor of Agathys: jagged frost shell forming around target with swirling shards
  register('armor_of_agathys', function(payload){
    return new Promise((resolve) => {
      const targetKey = (() => {
        if (payload && payload.target != null) {
          const arr = ensureArray(payload.target);
          if (arr.length && arr[0] != null) return arr[0];
        }
        return payload && payload.source ? payload.source : null;
      })();
      const target = (() => {
        if (Array.isArray(targetKey) && targetKey.length === 2 && typeof targetKey[0] === 'number') {
          return tileCenterByCoords(targetKey[0], targetKey[1]);
        }
        return targetKey ? centerOfEntity(targetKey) : null;
      })();
      if (!target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1102);
      const shardCount = 22;
      const shards = Array.from({ length: shardCount }, (_, idx) => ({
        angle: (idx / shardCount) * Math.PI * 2 + (Math.random() - 0.5) * 0.35,
        jitter: 0.7 + Math.random() * 0.6,
        length: 24 + Math.random() * 28
      }));
      const start = performance.now();
      const total = 1180;
      const frost = [170, 225, 255];
      const deep = [55, 110, 165];
      const draw = (now) => {
        const t = Math.min(1, (now - start) / total);
        ctx.clearRect(0, 0, overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        const grow = Math.min(1, t / 0.55);
        const linger = Math.max(0, (t - 0.45) / 0.55);
        const glowRadius = 24 + 40 * grow;
        const glow = ctx.createRadialGradient(target.x, target.y, 0, target.x, target.y, glowRadius + 24);
        glow.addColorStop(0, `rgba(230,250,255,${(0.55 - 0.2 * grow).toFixed(2)})`);
        glow.addColorStop(0.5, `rgba(${frost[0]},${frost[1]},${frost[2]},${(0.32 - linger * 0.12).toFixed(2)})`);
        glow.addColorStop(1, `rgba(${deep[0]},${deep[1]},${deep[2]},0)`);
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(target.x, target.y, glowRadius + 12, 0, Math.PI * 2); ctx.fill();
        shards.forEach((shard, idx) => {
          const phase = Math.max(0, Math.min(1, grow * 1.2 - idx * 0.012));
          if (phase <= 0) return;
          const eased = 1 - Math.pow(1 - phase, 3);
          const inner = 14 + shard.jitter * 6;
          const span = shard.length * (0.45 + 0.55 * eased);
          const ang = shard.angle + Math.sin(now * 0.0025 + idx) * 0.08 * (1 - linger);
          const baseX = target.x + Math.cos(ang) * inner;
          const baseY = target.y + Math.sin(ang) * inner;
          const tipX = target.x + Math.cos(ang) * (inner + span);
          const tipY = target.y + Math.sin(ang) * (inner + span);
          ctx.strokeStyle = `rgba(${frost[0]},${frost[1]},${frost[2]},${(0.82 - linger * 0.28).toFixed(2)})`;
          ctx.lineWidth = 3.2 - 1.6 * eased;
          ctx.beginPath(); ctx.moveTo(baseX, baseY); ctx.lineTo(tipX, tipY); ctx.stroke();
        });
        const moteCount = 26;
        for (let i = 0; i < moteCount; i++) {
          const prog = (t * 0.85 + i / moteCount) % 1;
          const radius = 12 + 28 * prog;
          const ang = now * 0.003 + i * (Math.PI * 2 / moteCount);
          const px = target.x + Math.cos(ang) * radius;
          const py = target.y + Math.sin(ang) * radius;
          ctx.beginPath(); ctx.arc(px, py, 2 - prog * 0.9, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(235,250,255,${(0.6 - prog * 0.45).toFixed(2)})`; ctx.fill();
        }
        if (linger > 0) {
          const shell = Math.min(1, linger * 1.3);
          ctx.beginPath(); ctx.arc(target.x, target.y, 28 + 26 * shell, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(${frost[0]},${frost[1]},${frost[2]},${(0.42 * (1 - linger * 0.6)).toFixed(2)})`;
          ctx.lineWidth = 2 - 1.1 * shell; ctx.stroke();
        }
        ctx.restore();
        if (t < 1) requestAnimationFrame(draw); else { destroy(); resolve(); }
      };
      requestAnimationFrame(draw);
    });
  });

  // Shield of Faith: protective golden rotating sigils around target
  register('shield_of_faith', function(payload){
    return new Promise((resolve) => {
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!centers.length) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1101);
      const start = performance.now();
      const total = 1200;
      const gold = [255, 215, 120];
      const draw = (now) => {
        const t = Math.min(1, (now - start)/total);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        centers.forEach((p, idx)=>{
          const base = 1 - Math.pow(1 - t, 3);
          const alpha = 0.9 * (1 - Math.max(0, t - 0.7)/0.3);
          const r1 = 26 + 8*Math.sin(now*0.01 + idx);
          const r2 = 38 + 6*Math.cos(now*0.012 + idx*0.7);
          // soft halo
          ctx.beginPath(); ctx.arc(p.x, p.y, r2, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${gold[0]},${gold[1]},${gold[2]},${(0.35*alpha).toFixed(2)})`;
          ctx.lineWidth = 8; ctx.stroke();
          // rotating sigil arcs
          const ang = now*0.004 + idx;
          for (let k=0;k<3;k++){
            const a0 = ang + (k/3)*Math.PI*2;
            ctx.beginPath();
            ctx.arc(p.x, p.y, r1, a0, a0 + Math.PI/3);
            ctx.strokeStyle = `rgba(${gold[0]},${gold[1]},${gold[2]},${(0.9*alpha).toFixed(2)})`;
            ctx.lineWidth = 2.5; ctx.stroke();
          }
          // vertical oval (shield hint)
          ctx.beginPath();
          ctx.ellipse(p.x, p.y, r1*0.7, r2*0.9, 0, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(255,255,255,${(0.6*alpha).toFixed(2)})`; ctx.lineWidth = 1.5; ctx.stroke();
        });
        ctx.restore();
        if (t < 1) requestAnimationFrame(draw); else { destroy(); resolve(); }
      };
      requestAnimationFrame(draw);
    });
  });

  // Healing Word: gentle verdant ribbon to target, soothing bloom and rising motes
  register('healing_word', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const target = centers[0];
      if (!target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1101);
      const green = [140, 255, 180];
      function ribbon(done){
        if (!src) return done();
        const start = performance.now();
        const dur = 420;
        const ctrl = { x: (src.x + target.x)/2, y: Math.min(src.y, target.y) - 80 };
        const dash = 12;
        const step = (now) => {
          const t = Math.min(1, (now - start)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          ctx.lineWidth = 4; ctx.strokeStyle = `rgba(${green[0]},${green[1]},${green[2]},0.9)`;
          ctx.setLineDash([dash, dash]); ctx.lineDashOffset = (1-t)*dash*3;
          const x = (1-t)*(1-t)*src.x + 2*(1-t)*t*ctrl.x + t*t*target.x;
          const y = (1-t)*(1-t)*src.y + 2*(1-t)*t*ctrl.y + t*t*target.y;
          ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.quadraticCurveTo(ctrl.x, ctrl.y, x, y); ctx.stroke();
          // small glow head
          ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI*2);
          ctx.fillStyle = `rgba(255,255,255,0.85)`; ctx.fill();
          ctx.restore();
          if (t < 1) requestAnimationFrame(step); else done();
        };
        requestAnimationFrame(step);
      }
      function bloom(){
        const t0 = performance.now();
        const total = 700;
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/total);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const r = 16 + 24*t; const a = 0.9*(1 - t);
          ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${green[0]},${green[1]},${green[2]},${a.toFixed(2)})`;
          ctx.lineWidth = 3 - 1.5*t; ctx.stroke();
          // rising motes
          for (let i=0;i<10;i++){
            const px = target.x + (Math.random()*2-1)*18;
            const py = target.y - 6 - 40*t + Math.random()*8;
            ctx.beginPath(); ctx.arc(px, py, 1.6, 0, Math.PI*2);
            ctx.fillStyle = `rgba(255,255,255,${(0.6*a).toFixed(2)})`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
        };
        requestAnimationFrame(loop);
      }
      ribbon(bloom);
    });
  });

  // Cure Wounds: warm ribbon from caster's touch to target, radiant healing bloom and uplifting motes
  register('cure_wounds', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!centers.length) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1101);
      const green = [120, 255, 180];
      const gold = [255, 220, 140];

      function ribbonTo(target, done){
        try { if (window.SFX && SFX.play) SFX.play('cure_wounds_cast'); } catch(e){}
        if (!src) return done();
        const start = performance.now();
        const dur = 420;
        const ctrl = { x: (src.x + target.x)/2, y: Math.min(src.y, target.y) - 60 };
        const dash = 10;
        const draw = (now) => {
          const t = Math.min(1, (now - start)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          // gradient ribbon
          const grad = ctx.createLinearGradient(src.x, src.y, target.x, target.y);
          grad.addColorStop(0, `rgba(${green[0]},${green[1]},${green[2]},0.95)`);
          grad.addColorStop(1, `rgba(${gold[0]},${gold[1]},${gold[2]},0.9)`);
          ctx.lineWidth = 5; ctx.strokeStyle = grad;
          ctx.setLineDash([dash, dash]); ctx.lineDashOffset = (1-t)*dash*4;
          const x = (1-t)*(1-t)*src.x + 2*(1-t)*t*ctrl.x + t*t*target.x;
          const y = (1-t)*(1-t)*src.y + 2*(1-t)*t*ctrl.y + t*t*target.y;
          ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.quadraticCurveTo(ctrl.x, ctrl.y, x, y); ctx.stroke();
          // head glow
          ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI*2);
          ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.fill();
          // gentle leaf motes along the path
          for (let i=0;i<6;i++){
            const pt = Math.random()*t; const px = src.x + (x - src.x)*pt; const py = src.y + (y - src.y)*pt - 6*(1-pt);
            ctx.save(); ctx.translate(px, py); ctx.rotate(now*0.002 + i);
            ctx.fillStyle = `rgba(${green[0]},${green[1]},${green[2]},0.6)`;
            ctx.beginPath(); ctx.ellipse(0, 0, 2.4, 1.2, 0, 0, Math.PI*2); ctx.fill();
            ctx.restore();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(draw); else done();
        };
        requestAnimationFrame(draw);
      }

      function bloomAt(target, done){
        try { if (window.SFX && SFX.play) SFX.play('cure_wounds_bloom'); } catch(e){}
        const t0 = performance.now();
        const total = 800;
        const draw = (now) => {
          const t = Math.min(1, (now - t0)/total);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const r = 14 + 26*t; const a = 0.9*(1 - t);
          // dual-color halo
          ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${gold[0]},${gold[1]},${gold[2]},${(0.55*a).toFixed(2)})`; ctx.lineWidth = 4 - 2*t; ctx.stroke();
          ctx.beginPath(); ctx.arc(target.x, target.y, r-3, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${green[0]},${green[1]},${green[2]},${(0.65*a).toFixed(2)})`; ctx.lineWidth = 2.5 - 1.2*t; ctx.stroke();
          // petal cross (four ovals)
          const petals = 4; const pr = 10 + 14*t;
          for (let i=0;i<petals;i++){
            const ang = (i/petals)*Math.PI*0.5 + now*0.001;
            ctx.beginPath();
            ctx.ellipse(target.x, target.y, pr, pr*0.55, ang, 0, Math.PI*2);
            ctx.strokeStyle = `rgba(255,255,255,${(0.4*a).toFixed(2)})`;
            ctx.lineWidth = 1.2; ctx.stroke();
          }
          // uplifting motes
          for (let i=0;i<12;i++){
            const px = target.x + (Math.random()*2-1)*(8 + 10*t);
            const py = target.y - 6 - 36*t + Math.random()*10;
            ctx.beginPath(); ctx.arc(px, py, 1.6, 0, Math.PI*2);
            ctx.fillStyle = `rgba(255,255,255,${(0.55*a).toFixed(2)})`; ctx.fill();
          }
          // subtle heartbeat flash
          const beat = Math.max(0, Math.sin((now - t0)*0.01));
          if (beat > 0.9) {
            ctx.beginPath(); ctx.arc(target.x, target.y, 10 + 20*t, 0, Math.PI*2);
            ctx.strokeStyle = `rgba(${gold[0]},${gold[1]},${gold[2]},0.25)`; ctx.lineWidth = 2; ctx.stroke();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(draw); else done();
        };
        requestAnimationFrame(draw);
      }

      // Support multiple targets by animating sequentially to keep the scene readable.
      let i = 0;
      function next(){
        if (i >= centers.length) { destroy(); resolve(); return; }
        const tgt = centers[i++];
        const goBloom = () => bloomAt(tgt, next);
        if (src) ribbonTo(tgt, goBloom); else goBloom();
      }
      next();
    });
  });

  // Inflict Wounds: ominous necrotic tendrils from caster to target with implosive pulse
  register('inflict_wounds', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const target = centers[0];
      if (!target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1103);
      const nec = [90, 0, 120]; // deep violet
      const sick = [30, 180, 120]; // sickly green accent
      const start = performance.now();
      const total = 900;
      try { if (window.SFX && SFX.play) SFX.play('inflict_wounds_cast'); } catch(e){}
      function drawTendril(ax, ay, bx, by, seed, t){
        const midx = (ax + bx)/2, midy = (ay + by)/2;
        const nx = by - ay, ny = -(bx - ax);
        const len = Math.hypot(bx-ax, by-ay);
        const mag = Math.min(60, 18 + len*0.12);
        const wob = Math.sin((seed*1.7 + start*0.005) + t*6.0) * mag;
        const cx = midx + (nx/Math.max(1,len)) * wob;
        const cy = midy + (ny/Math.max(1,len)) * wob;
        // progressive draw
        const px = (1-t)*(1-t)*ax + 2*(1-t)*t*cx + t*t*bx;
        const py = (1-t)*(1-t)*ay + 2*(1-t)*t*cy + t*t*by;
        ctx.strokeStyle = `rgba(${nec[0]},${nec[1]},${nec[2]},0.85)`; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.quadraticCurveTo(cx, cy, px, py); ctx.stroke();
        ctx.strokeStyle = `rgba(${sick[0]},${sick[1]},${sick[2]},0.4)`; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.quadraticCurveTo(cx, cy, px, py); ctx.stroke();
      }
      const loop = (now) => {
        const t = Math.min(1, (now - start)/total);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        if (src) {
          for (let i=0;i<3;i++) drawTendril(src.x, src.y, target.x, target.y, i, t);
        }
        // target aura pulsing inward (implosive)
        const a = 0.9*(1 - Math.abs(0.5 - t)*2);
        const r = 22 + 10*(1-t);
        ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2);
        ctx.strokeStyle = `rgba(${nec[0]},${nec[1]},${nec[2]},${a.toFixed(2)})`;
        ctx.lineWidth = 3; ctx.stroke();
        // vein-like spokes
        for (let k=0;k<8;k++){
          const ang = (k/8)*Math.PI*2 + now*0.002;
          const len = 10 + 16*(1-t);
          ctx.beginPath(); ctx.moveTo(target.x, target.y);
          ctx.lineTo(target.x + Math.cos(ang)*len, target.y + Math.sin(ang)*len);
          ctx.strokeStyle = `rgba(${sick[0]},${sick[1]},${sick[2]},${(0.5*a).toFixed(2)})`;
          ctx.lineWidth = 1.5; ctx.stroke();
        }
        ctx.restore();
        if (t < 1) requestAnimationFrame(loop); else impact();
      };
      function impact(){
        try { if (window.SFX && SFX.play) SFX.play('inflict_wounds_impact'); } catch(e){}
        const t0 = performance.now();
        const dur = 420;
        const run = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const fade = 1 - t;
          // inward ring (reverse aura)
          const rr = 26 - 16*t;
          ctx.beginPath(); ctx.arc(target.x, target.y, rr, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${nec[0]},${nec[1]},${nec[2]},${(0.9*fade).toFixed(2)})`;
          ctx.lineWidth = 3; ctx.stroke();
          // crackle dots
          for (let i=0;i<14;i++){
            const ang = (i/14)*Math.PI*2 + now*0.005;
            const d = rr * (0.5 + Math.random()*0.5);
            const x = target.x + Math.cos(ang)*d, y = target.y + Math.sin(ang)*d;
            ctx.beginPath(); ctx.arc(x, y, 1.8, 0, Math.PI*2);
            ctx.fillStyle = `rgba(${sick[0]},${sick[1]},${sick[2]},${(0.7*fade).toFixed(2)})`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(run); else { destroy(); resolve(); }
        };
        requestAnimationFrame(run);
      }
      requestAnimationFrame(loop);
    });
  });

  // Toll the Dead: spectral bell manifests above the target, twin toll pulses, necrotic aura
  (function(){
    function tollEffect(payload){
      return new Promise((resolve) => {
        const targets = ensureArray(payload && payload.target);
        const centers = targets.map(centerOfEntity).filter(Boolean);
        if (!centers.length) return resolve();
        const { overlay, ctx, destroy } = createOverlay(1104);
        const nec = [110, 40, 160]; // deep violet
        const steel = [210, 210, 230]; // pale bell metal
        const tileSize = ($('.tiles-container').data('tile-size') || 64);
        const baseR = Math.max(18, tileSize * 0.5);
        try { if (window.SFX && SFX.play) SFX.play('toll_the_dead_cast'); } catch(e){}
        const t0 = performance.now();
        const total = 1000;
        let bong1 = false, bong2 = false;
        function drawBell(x, y, scale, alpha){
          const w = 16*scale, h = 18*scale;
          const top = y - h;
          ctx.save(); ctx.globalAlpha = alpha; ctx.translate(x, top);
          // dome
          ctx.beginPath();
          ctx.moveTo(-w*0.6, h*0.4);
          ctx.quadraticCurveTo(0, -h*0.2, w*0.6, h*0.4);
          ctx.lineTo(w*0.55, h*0.9);
          ctx.quadraticCurveTo(0, h*1.05, -w*0.55, h*0.9);
          ctx.closePath();
          ctx.strokeStyle = `rgba(${steel[0]},${steel[1]},${steel[2]},0.9)`; ctx.lineWidth = 2; ctx.stroke();
          ctx.strokeStyle = `rgba(255,255,255,0.8)`; ctx.lineWidth = 1; ctx.stroke();
          // clapper
          ctx.beginPath(); ctx.arc(0, h*0.95, 2.2*scale, 0, Math.PI*2);
          ctx.fillStyle = `rgba(${steel[0]},${steel[1]},${steel[2]},0.9)`; ctx.fill();
          ctx.restore();
        }
        function loop(now){
          const t = Math.min(1, (now - t0)/total);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          centers.forEach((c, idx)=>{
            // Bell manifests above target
            const appear = Math.min(1, t/0.25);
            const scale = 1.0 + 0.1*Math.sin(now*0.008 + idx);
            drawBell(c.x, c.y - baseR*0.9, scale, appear);
            // Twin toll pulses
            const p1 = (t - 0.25)/0.28; // first pulse window
            const p2 = (t - 0.6)/0.28;  // second pulse window
            if (p1 >= 0 && !bong1){ try { SFX && SFX.play && SFX.play('toll_the_dead_bong'); } catch(e){} bong1 = true; }
            if (p2 >= 0 && !bong2){ try { SFX && SFX.play && SFX.play('toll_the_dead_bong'); } catch(e){} bong2 = true; }
            const drawPulse = (pp) => {
              const u = Math.max(0, Math.min(1, pp));
              const fade = 1 - u;
              const r = baseR * (0.8 + 1.1*u);
              // outer ring
              ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2);
              ctx.strokeStyle = `rgba(${nec[0]},${nec[1]},${nec[2]},${(0.75*fade).toFixed(2)})`;
              ctx.lineWidth = 3 - 1.6*u; ctx.stroke();
              // inner bright edge
              ctx.beginPath(); ctx.arc(c.x, c.y, r-4, 0, Math.PI*2);
              ctx.strokeStyle = `rgba(255,255,255,${(0.6*fade).toFixed(2)})`; ctx.lineWidth = 1.4; ctx.stroke();
              // faint radial spokes
              for (let i=0;i<10;i++){
                const ang = (i/10)*Math.PI*2 + now*0.0015;
                const len = 10 + 14*u;
                ctx.beginPath(); ctx.moveTo(c.x, c.y);
                ctx.lineTo(c.x + Math.cos(ang)*len, c.y + Math.sin(ang)*len);
                ctx.strokeStyle = `rgba(${nec[0]},${nec[1]},${nec[2]},${(0.35*fade).toFixed(2)})`;
                ctx.lineWidth = 1.2; ctx.stroke();
              }
            };
            if (p1 < 1) drawPulse(p1);
            if (p2 < 1) drawPulse(p2);
            // Necrotic aura focusing on target
            const auraT = Math.max(0, Math.min(1, (t - 0.15)/0.7));
            const gf = ctx.createRadialGradient(c.x, c.y, baseR*0.1, c.x, c.y, baseR*0.9);
            gf.addColorStop(0, `rgba(255,255,255, ${(0.12*auraT).toFixed(2)})`);
            gf.addColorStop(1, `rgba(${nec[0]},${nec[1]},${nec[2]}, ${(0.16*auraT).toFixed(2)})`);
            ctx.fillStyle = gf; ctx.beginPath(); ctx.arc(c.x, c.y, baseR*0.9, 0, Math.PI*2); ctx.fill();
            // drifting motes downward (mourning chimes)
            for (let i=0;i<8;i++){
              const ang = Math.random()*Math.PI*2;
              const rr = baseR * (0.2 + 0.7*Math.random());
              const x = c.x + Math.cos(ang)*rr;
              const y = c.y + Math.sin(ang)*rr + 10*t;
              ctx.beginPath(); ctx.arc(x, y, 1.8, 0, Math.PI*2);
              ctx.fillStyle = `rgba(230,220,255, ${(0.28*(1-t)).toFixed(2)})`; ctx.fill();
            }
          });
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
        }
        requestAnimationFrame(loop);
      });
    }
    register('toll_the_dead', tollEffect);
    register('toll the dead', tollEffect); // alias to match label-based spell keys
  })();


  // Ice Knife: crystalline shard to target, then cold shatter ring with fragments
  register('ice_knife', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const target = centers[0];
      if (!src || !target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1102);
      const icy = [160, 220, 255];
      const start = performance.now();
      const flyDur = 300;
      try { if (window.SFX && SFX.play) SFX.play('ice_knife_throw'); } catch(e){}
      const fly = (now) => {
        const t = Math.min(1, (now - start)/flyDur);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        const x = src.x + (target.x - src.x)*t;
        const y = src.y + (target.y - src.y)*t;
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        // shard body
        ctx.translate(x, y); ctx.rotate(t*8);
        ctx.fillStyle = `rgba(${icy[0]},${icy[1]},${icy[2]},0.95)`;
        ctx.beginPath(); ctx.moveTo(0, -5); ctx.lineTo(10, 0); ctx.lineTo(0, 5); ctx.lineTo(-6, 0); ctx.closePath(); ctx.fill();
        ctx.restore();
        // contrail
        ctx.strokeStyle = `rgba(${icy[0]},${icy[1]},${icy[2]},0.5)`; ctx.lineWidth = 2.5;
        ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
        if (t < 1) requestAnimationFrame(fly); else shatter();
      };
      function shatter(){
        try { if (window.SFX && SFX.play) SFX.play('ice_knife_shatter'); } catch(e){}
        const t0 = performance.now();
        const dur = 650;
        const shards = Array.from({length: 18}, (_,i)=>({ a:(i/18)*Math.PI*2, sp: 60 + Math.random()*80 }));
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const fade = 1 - t;
          // cold ring
          ctx.beginPath(); ctx.arc(target.x, target.y, 18 + 28*t, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${icy[0]},${icy[1]},${icy[2]},${(0.8*fade).toFixed(2)})`;
          ctx.lineWidth = 3 - 1.5*t; ctx.stroke();
          // shards
          shards.forEach(s=>{
            const r = 6 + s.sp*t;
            const x = target.x + Math.cos(s.a)*r;
            const y = target.y + Math.sin(s.a)*r;
            ctx.beginPath(); ctx.moveTo(x, y);
            ctx.lineTo(x + Math.cos(s.a)*8, y + Math.sin(s.a)*8);
            ctx.strokeStyle = `rgba(255,255,255,${(0.9*fade).toFixed(2)})`;
            ctx.lineWidth = 1.5; ctx.stroke();
          });
          // mist motes
          for (let i=0;i<12;i++){
            const ang = (i/12)*Math.PI*2 + now*0.0015;
            const r = 8 + 20*t + Math.sin(ang*3)*2;
            const px = target.x + Math.cos(ang)*r, py = target.y + Math.sin(ang)*r;
            ctx.beginPath(); ctx.arc(px, py, 2, 0, Math.PI*2);
            ctx.fillStyle = `rgba(210,235,255,${(0.5*fade).toFixed(2)})`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
        };
        requestAnimationFrame(loop);
      }
      requestAnimationFrame(fly);
    });
  });

  // Burning Hands: 15-ft cone of flame in the direction specified by target vector
  // payload.target is a [dx, dy] direction relative to the caster (tiles or any vector)
  register('burning_hands', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      if (!src) return resolve();
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      // Determine facing angle: prefer absolute tile target -> vector from source tile to target tile
      let angle;
      if (payload && Array.isArray(payload.target) && payload.target.length === 2 &&
          typeof payload.target[0] === 'number' && typeof payload.target[1] === 'number') {
        // Prefer grid-space facing using tile coordinates to match backend exactly
        const srcTile = entityTileCoords(payload.source);
        if (srcTile) {
          const dxg = payload.target[0] - srcTile[0];
          const dyg = payload.target[1] - srcTile[1];
          angle = Math.atan2(dyg, dxg); // grid y grows down, same as canvas
        } else {
          // Fallback to pixel centers if we can't get tile coords for source
          const tgtCenter = tileCenterByCoords(payload.target[0], payload.target[1]);
          if (tgtCenter) {
            const dxp = tgtCenter.x - src.x;
            const dyp = tgtCenter.y - src.y;
            angle = Math.atan2(dyp, dxp);
          } else {
            // Final fallback: treat target as direction vector
            const len = Math.hypot(payload.target[0], payload.target[1]) || 1;
            const nx = payload.target[0] / len, ny = payload.target[1] / len;
            angle = Math.atan2(ny, nx);
          }
        }
      } else {
        // Default facing to the right if no target
        angle = 0;
      }
  // Match backend cone half-aperture: atan(0.5) ≈ 26.565° (distance equals width)
  const halfAngle = Math.atan(0.5);
  // Use range in squares if provided; default 3 (15 ft). Add sqrt(2)/2 buffer like backend.
  const squaresRange = (payload && (payload.range_squares || payload.range || payload.range_cone)) || 3;
  const pxRange = squaresRange * tileSize;
  const pxBufferR = tileSize * Math.SQRT2 / 2; // partial-overlap buffer
  const baseMaxR = pxRange + pxBufferR;
  const maskHalfAngle = halfAngle + 0.02; // tiny epsilon to better cover boundary squares

      const { overlay, ctx, destroy } = createOverlay(1103);
      try { if (window.SFX && SFX.play) { SFX.play('burning_hands_cast'); } } catch(e){}

      // Lightweight noise for jittering boundaries and flow
      const seed = Math.random()*1000;
      function vnoise(u, t){
        return (
          Math.sin(u*3.31 + t*2.07 + seed*0.71) +
          Math.sin(u*5.13 + t*1.37 + seed*1.19) +
          Math.sin(u*7.77 + t*0.81 + seed*2.23)
        ) / 3;
      }

      // Build a softly jittered cone-like mask
      function jitteredPath(now, baseR){
        const a0 = angle - maskHalfAngle;
        const a1 = angle + maskHalfAngle;
        const steps = 34;
        const ampPx = Math.max(2, tileSize * 0.12); // keep jitter small to not undercut coverage
        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        for (let i=0; i<=steps; i++){
          const f = i/steps;
          const aa = a0 + (a1 - a0)*f;
          const n = vnoise(aa*0.9, now*0.002);
          const r = baseR + n * ampPx;
          const x = src.x + Math.cos(aa)*r;
          const y = src.y + Math.sin(aa)*r;
          ctx.lineTo(x, y);
        }
        ctx.closePath();
      }

      // Simple embers system
      let particles = [];
      function initParticles(maxR){
        const count = 60;
        particles = Array.from({length: count}, () => {
          const f = Math.random()*0.35 + 0.05;
          const d = maxR * f;
          const spread = (Math.random()*2-1) * halfAngle*0.9;
          const a = angle + spread;
          return {
            x: src.x + Math.cos(a)*d,
            y: src.y + Math.sin(a)*d,
            a,
            v: tileSize*(1.6 + Math.random()*1.4),
            life: 0,
            maxLife: 280 + Math.random()*260,
            size: 1.4 + Math.random()*2.3
          };
        });
      }

      const start = performance.now();
      const total = 800;
      const colCore = [255, 240, 200];
      const colBody = [255, 160, 60];
      const colEdge = [255, 90, 40];
      const draw = (now) => {
        const t = Math.min(1, (now - start)/total);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        const ease = 1 - Math.pow(1 - t, 3);
  const r = baseMaxR * (0.85 + 0.15*ease);
        if (!particles.length) initParticles(r);

        // Masked plasma body
        jitteredPath(now, r);
        ctx.save();
        ctx.clip();

        // Layered glowing blobs along axis
        const blobs = 5;
        for (let i=0;i<blobs;i++){
          const frac = (i+1)/(blobs+1);
          const wob = vnoise(frac*8.0, now*0.002);
          const cx = src.x + Math.cos(angle) * r * frac * (0.92 + 0.06*wob);
          const cy = src.y + Math.sin(angle) * r * frac * (0.92 + 0.06*wob);
          const rr = 14 + 32*frac*(0.7 + 0.3*Math.sin(now*0.01 + i));
          const g = ctx.createRadialGradient(cx, cy, 2, cx, cy, rr);
          g.addColorStop(0, `rgba(255,255,255,${(0.6*(1-frac)).toFixed(2)})`);
          g.addColorStop(0.45, `rgba(${colCore[0]},${colCore[1]},${colCore[2]},${(0.5*(1-frac)).toFixed(2)})`);
          g.addColorStop(1, `rgba(${colBody[0]},${colBody[1]},${colBody[2]},${(0.25*(1-frac)).toFixed(2)})`);
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(cx, cy, rr, 0, Math.PI*2); ctx.fill();
        }

        // Flowing veins
  const veins = 9;
        for (let i=0;i<veins;i++){
          const frac = (i+1)/(veins+1);
          const base = r * frac;
          const perpX = -Math.sin(angle), perpY = Math.cos(angle);
          const wob = vnoise(i*3.7, now*0.004) * 18 * (1 - frac);
          const c1x = src.x + Math.cos(angle)*base*0.45 + perpX*wob;
          const c1y = src.y + Math.sin(angle)*base*0.45 + perpY*wob;
          const endx = src.x + Math.cos(angle)*base + perpX*wob*0.5;
          const endy = src.y + Math.sin(angle)*base + perpY*wob*0.5;
          ctx.beginPath(); ctx.moveTo(src.x, src.y);
          ctx.quadraticCurveTo(c1x, c1y, endx, endy);
          ctx.strokeStyle = `rgba(${colCore[0]},${colCore[1]},${colCore[2]},${(0.14*(1-frac)).toFixed(2)})`;
          ctx.lineWidth = 2.2 - 1.6*frac; ctx.stroke();
        }

        // Embers
        const dt = 16;
        particles.forEach(p => {
          const drift = vnoise(p.a*2.0, now*0.003) * 0.12;
          p.a += drift*0.04;
          p.x += Math.cos(p.a) * p.v * (dt/1000);
          p.y += Math.sin(p.a) * p.v * (dt/1000);
          p.v *= 0.985;
          p.life += dt;
          const lifeT = Math.min(1, p.life/p.maxLife);
          const size = p.size * (1.2 - 0.8*lifeT);
          const a = 0.7 * (1 - lifeT) * (0.5 + 0.5*ease);
          ctx.beginPath(); ctx.arc(p.x, p.y, size, 0, Math.PI*2);
          ctx.fillStyle = `rgba(${colBody[0]},${colBody[1]},${colBody[2]},${a.toFixed(2)})`; ctx.fill();
        });

        ctx.restore(); // end clip

        // Edge glow hint (not a hard wedge)
        jitteredPath(now, r);
  ctx.strokeStyle = `rgba(${colEdge[0]},${colEdge[1]},${colEdge[2]},${(0.45*ease).toFixed(2)})`;
        ctx.lineWidth = 1.8;
        ctx.stroke();

        ctx.restore();
        if (t < 1) requestAnimationFrame(draw); else {
          // Lingering afterglow
          const t0 = performance.now();
          const linger = (now2) => {
            const tt = Math.min(1, (now2 - t0)/280);
            ctx.clearRect(0,0,overlay.width, overlay.height);
            ctx.save(); ctx.globalCompositeOperation = 'screen';
            jitteredPath(now2, baseMaxR*0.7);
            ctx.clip();
            const g = ctx.createRadialGradient(src.x, src.y, 6, src.x, src.y, baseMaxR*0.7);
            g.addColorStop(0, `rgba(${colCore[0]},${colCore[1]},${colCore[2]},${(0.14*(1-tt)).toFixed(2)})`);
            g.addColorStop(1, `rgba(${colBody[0]},${colBody[1]},${colBody[2]},${(0.08*(1-tt)).toFixed(2)})`);
            ctx.fillStyle = g; ctx.fillRect(0,0,overlay.width, overlay.height);
            ctx.restore();
            if (tt < 1) requestAnimationFrame(linger); else { destroy(); resolve(); }
          };
          requestAnimationFrame(linger);
        }
      };
      requestAnimationFrame(draw);
    });
  });

  // Chill Touch: spectral skeletal hand rushes to target and grasps with necrotic chill
  register('chill_touch', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const target = centers[0];
      if (!target) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1103);
      const cold = [160, 230, 255]; // ghostly cyan
      const nec = [120, 60, 180];   // necrotic violet
      try { if (window.SFX && SFX.play) SFX.play('chill_touch_cast'); } catch(e){}

      // Draw a simple skeletal hand composed of a palm and 5 finger segments.
      function drawHand(x, y, scale, rot, open){
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(rot || 0);
        ctx.scale(scale, scale);
        ctx.globalCompositeOperation = 'screen';
        // Palm glow
        ctx.beginPath(); ctx.arc(0, 0, 8, 0, Math.PI*2);
        ctx.strokeStyle = `rgba(${cold[0]},${cold[1]},${cold[2]},0.85)`; ctx.lineWidth = 2; ctx.stroke();
        ctx.beginPath(); ctx.arc(0, 0, 6, 0, Math.PI*2);
        ctx.strokeStyle = 'rgba(255,255,255,0.8)'; ctx.lineWidth = 1; ctx.stroke();
        // Fingers: 4 upwards, one thumb angled
        function finger(baseX, baseY, baseAng, lengths){
          let bx = baseX, by = baseY, ang = baseAng;
          lengths.forEach((len, idx)=>{
            const curl = (1 - open) * (0.35 + idx*0.18);
            const segAng = ang + curl;
            const nx = bx + Math.cos(segAng)*len;
            const ny = by + Math.sin(segAng)*len;
            ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(nx, ny);
            ctx.strokeStyle = `rgba(${cold[0]},${cold[1]},${cold[2]},0.9)`; ctx.lineWidth = Math.max(1, 2 - idx*0.3); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(nx, ny);
            ctx.strokeStyle = 'rgba(255,255,255,0.7)'; ctx.lineWidth = Math.max(0.8, 1.5 - idx*0.3); ctx.stroke();
            bx = nx; by = ny; ang = segAng + 0.12*(1 - open);
          });
        }
        // four fingers
        const fingerXs = [-6, -2, 2, 6];
        fingerXs.forEach((fx, i)=> finger(fx, -4, -Math.PI/2 + (i-1.5)*0.08, [6,5,4]));
        // thumb
        finger(-7, 2, -2.2, [6,5]);
        ctx.restore();
      }

      // Stage 1: brief spectral charge at caster (if available)
      function charge(next){
        if (!src) return next();
        const t0 = performance.now();
        const dur = 240;
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          const a = 0.8 * (1 - Math.abs(0.5 - t)*2);
          // swirl at source
          for (let i=0;i<8;i++){
            const ang = (i/8)*Math.PI*2 + now*0.004;
            const r = 8 + 10*t;
            const x = src.x + Math.cos(ang)*r, y = src.y + Math.sin(ang)*r;
            ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI*2);
            ctx.fillStyle = `rgba(${cold[0]},${cold[1]},${cold[2]},${(0.7*a).toFixed(2)})`; ctx.fill();
          }
          drawHand(src.x, src.y, 1.0 + 0.2*t, now*0.005, 1);
          if (t < 1) requestAnimationFrame(loop); else next();
        };
        requestAnimationFrame(loop);
      }

      // Stage 2: hand flies to target along a bezier with wispy trail
      function fly(next){
        const t0 = performance.now();
        const dur = 380;
        const from = src || { x: target.x - 140, y: target.y - 120 };
        const ctrl = { x: (from.x + target.x)/2 + (Math.random()<0.5?-1:1)*40, y: (from.y + target.y)/2 - 60 };
        const trail = [];
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          const x = (1-t)*(1-t)*from.x + 2*(1-t)*t*ctrl.x + t*t*target.x;
          const y = (1-t)*(1-t)*from.y + 2*(1-t)*t*ctrl.y + t*t*target.y;
          const rot = Math.atan2(y - ctrl.y, x - ctrl.x);
          // keep short trail of positions
          trail.push({x,y,ts: now});
          while (trail.length > 12) trail.shift();
          trail.forEach((p, idx)=>{
            const age = Math.min(1, (now - p.ts)/300);
            const r = 6 + 10*(1 - age);
            ctx.beginPath(); ctx.arc(p.x, p.y, r*0.35, 0, Math.PI*2);
            ctx.fillStyle = `rgba(${cold[0]},${cold[1]},${cold[2]},${(0.25*(1-age)).toFixed(2)})`; ctx.fill();
          });
          drawHand(x, y, 1.0, rot + Math.PI/2, 0.95);
          if (t < 1) requestAnimationFrame(loop); else next();
        };
        requestAnimationFrame(loop);
      }

      // Stage 3: grasp and necrotic chill pulse
      function grasp(next){
        try { if (window.SFX && SFX.play) SFX.play('chill_touch_grab'); } catch(e){}
        const t0 = performance.now();
        const dur = 560;
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          // hand closes from open->closed on the target
          const open = 1 - Math.min(1, t*1.2);
          drawHand(target.x, target.y, 1.15, 0, open);
          // necrotic ring with icy edge
          const fade = 1 - Math.abs(0.5 - t)*2; // peaks mid
          const rr = 18 + 20*t;
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          ctx.beginPath(); ctx.arc(target.x, target.y, rr, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${nec[0]},${nec[1]},${nec[2]},${(0.55*fade).toFixed(2)})`; ctx.lineWidth = 3 - 1.2*t; ctx.stroke();
          ctx.beginPath(); ctx.arc(target.x, target.y, rr+2, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${cold[0]},${cold[1]},${cold[2]},${(0.45*fade).toFixed(2)})`; ctx.lineWidth = 1.5; ctx.stroke();
          // frost cracks
          for (let i=0;i<10;i++){
            const ang = (i/10)*Math.PI*2 + now*0.003;
            const len = 10 + 16*(1 - t);
            ctx.beginPath(); ctx.moveTo(target.x, target.y);
            ctx.lineTo(target.x + Math.cos(ang)*len, target.y + Math.sin(ang)*len);
            ctx.strokeStyle = `rgba(${cold[0]},${cold[1]},${cold[2]},${(0.5*fade).toFixed(2)})`; ctx.lineWidth = 1.2; ctx.stroke();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else next();
        };
        requestAnimationFrame(loop);
      }

      // Stage 4: lingering ghostly imprint that fades
      function linger(done){
        const t0 = performance.now();
        const dur = 350;
        const loop = (now) => {
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          const a = 1 - t;
          ctx.save(); ctx.globalAlpha = 0.8*a;
          drawHand(target.x, target.y, 1.0, 0, 0.2);
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else done();
        };
        requestAnimationFrame(loop);
      }

      charge(()=> fly(()=> grasp(()=> linger(()=> { destroy(); resolve(); }))));
    });
  });

  // Poison Spray: short-range toxic jet and lingering cloud on target
  register('poison_spray', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const tgtId = payload && payload.target;
      const tgt = tgtId ? centerOfEntity(tgtId) : null;
      if (!src || !tgt) return resolve();

      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const dx = tgt.x - src.x, dy = tgt.y - src.y;
      const ang = Math.atan2(dy, dx);
      const maxLen = tileSize * 2.0; // ~10ft range
      const dist = Math.min(Math.hypot(dx, dy), maxLen);

      const { overlay, ctx, destroy } = createOverlay(1103);
      try { if (window.SFX && SFX.play) { SFX.play('poison_spray_cast'); } } catch(e){}

      // Local helpers (scoped)
      const seed = Math.random()*1000;
      function vnoise(u, t){
        return (
          Math.sin(u*2.11 + t*1.73 + seed*0.51) +
          Math.sin(u*3.97 + t*1.11 + seed*1.27) +
          Math.sin(u*5.63 + t*0.69 + seed*2.03)
        ) / 3;
      }

      // Particles along the jet
      const particles = [];
      const jetCount = 120;
      for (let i=0;i<jetCount;i++){
        const f = Math.random()*0.25; // start offset along jet
        const speed = (0.5 + Math.random()*0.7) * (tileSize*3.2);
        const spread = (Math.PI/18) * (Math.random()*2 - 1); // ~10° spread total
        particles.push({
          t: 0,
          ofs: f*dist,
          speed,
          a: ang + spread,
          r: 1 + Math.random()*2,
          alpha: 0.8,
        });
      }

      const start = performance.now();
      const jetDur = 520; // ms
      const cloudDur = 520; // ms

      function drawJet(now){
        const t = Math.min(1, (now - start)/jetDur);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'lighter';

        // Soft guide beam (very faint)
        ctx.save();
        ctx.translate(src.x, src.y);
        ctx.rotate(ang);
        const grad = ctx.createLinearGradient(0,0, dist,0);
        grad.addColorStop(0, 'rgba(120, 255, 120, 0.15)');
        grad.addColorStop(1, 'rgba(80, 200, 80, 0.0)');
        ctx.fillStyle = grad;
        const beamW = 6;
        ctx.fillRect(0, -beamW/2, dist, beamW);
        ctx.restore();

        // Particles
        const dt = 16;
        particles.forEach(p => {
          // small flow wobble
          const wob = vnoise(p.t*0.01 + p.ofs*0.02, now*0.002) * 0.4;
          const a = p.a + wob;
          p.ofs += p.speed * (dt/1000) * (0.4 + 0.6*(1 - 0.5*t));
          p.t += dt;
          // clamp to jet length
          const L = Math.min(p.ofs, dist);
          const x = src.x + Math.cos(a)*L;
          const y = src.y + Math.sin(a)*L;
          const life = Math.min(1, p.t/jetDur);
          const size = p.r * (1 + 1.2*life);
          const alpha = p.alpha * (0.9 - 0.7*t) * (0.6 + 0.4*Math.random());
          // greenish droplet
          const col = `rgba(${(90+40*Math.random())|0}, ${(200+30*Math.random())|0}, ${(90+20*Math.random())|0}, ${alpha.toFixed(2)})`;
          ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI*2);
          ctx.fillStyle = col; ctx.fill();
        });

        // Misty overlay plume
        ctx.save();
        ctx.translate(src.x, src.y); ctx.rotate(ang);
        const plumeLen = dist * (0.7 + 0.3*t);
        const plumeW = Math.max(18, tileSize*0.35) * (0.7 + 0.6*t);
        ctx.globalAlpha = 0.08;
        for (let i=0;i<6;i++){
          const yofs = (i-3) * (plumeW/6);
          ctx.beginPath();
          ctx.ellipse(plumeLen*0.5, yofs, plumeLen*0.5, plumeW*0.8, 0, 0, Math.PI*2);
          ctx.fillStyle = 'rgb(90,200,90)'; ctx.fill();
        }
        ctx.restore();

        ctx.restore();
        if (t < 1) requestAnimationFrame(drawJet); else {
          try { if (window.SFX && SFX.play) { SFX.play('poison_spray_hit'); } } catch(e){}
          const t0 = performance.now();
          requestAnimationFrame(function cloudLoop(now2){
            const tt = Math.min(1, (now2 - t0)/cloudDur);
            ctx.clearRect(0,0,overlay.width, overlay.height);
            ctx.save(); ctx.globalCompositeOperation = 'lighter';

            // Lingering cloud at target
            const cx = src.x + Math.cos(ang)*dist;
            const cy = src.y + Math.sin(ang)*dist;
            const baseR = Math.max(tileSize*0.4, 16) * (0.9 + 0.6*tt);
            for (let i=0;i<10;i++){
              const rr = baseR * (0.7 + 0.6*Math.random());
              const a = Math.random()*Math.PI*2;
              const rad = baseR * (0.2 + 0.6*Math.random());
              const px = cx + Math.cos(a)*rad;
              const py = cy + Math.sin(a)*rad;
              const g = ctx.createRadialGradient(px, py, 2, px, py, rr);
              g.addColorStop(0, `rgba(190,255,190, ${(0.16*(1-tt)).toFixed(2)})`);
              g.addColorStop(1, `rgba(60,160,60, ${(0.08*(1-tt)).toFixed(2)})`);
              ctx.fillStyle = g;
              ctx.beginPath(); ctx.arc(px, py, rr, 0, Math.PI*2); ctx.fill();
            }
            ctx.restore();
            if (tt < 1) requestAnimationFrame(cloudLoop); else { destroy(); resolve(); }
          });
        }
      }
      requestAnimationFrame(drawJet);
    });
  });

  // Thunderwave: directional 15-ft cube (3x3 tiles) originating from caster's space, with concussive burst and push hints
  register('thunderwave', function(payload){
    return new Promise((resolve) => {
      const srcId = payload && payload.source;
      const src = srcId ? centerOfEntity(srcId) : null;
      if (!src) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1105);
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      const srcTile = entityTileCoords(srcId);

      // Optional facing support: if payload.target is [tx,ty] tile coords or a vector, use it for directional accents
      let facingAngle = null;
      let facingCardinal = null; // 'N'|'E'|'S'|'W'
      (function computeFacing(){
        try {
          if (Array.isArray(payload?.target) && payload.target.length === 2 && typeof payload.target[0] === 'number' && typeof payload.target[1] === 'number'){
            if (srcTile) {
              const dxg = payload.target[0] - srcTile[0];
              const dyg = payload.target[1] - srcTile[1];
              if (dxg !== 0 || dyg !== 0) facingAngle = Math.atan2(dyg, dxg);
            } else {
              const tgtCenter = tileCenterByCoords(payload.target[0], payload.target[1]);
              if (tgtCenter) facingAngle = Math.atan2(tgtCenter.y - src.y, tgtCenter.x - src.x);
            }
          }
          // Derive cardinal from facingAngle if present; default East
          if (facingAngle == null) facingAngle = 0;
          const ang = ((facingAngle % (Math.PI*2)) + Math.PI*2) % (Math.PI*2);
          const dirs = [ {c:'E', a:0}, {c:'S', a:Math.PI/2}, {c:'W', a:Math.PI}, {c:'N', a:3*Math.PI/2} ];
          let best = {c:'E', d: 1e9};
          dirs.forEach(d => { const dd = Math.abs(((ang - d.a + Math.PI) % (2*Math.PI)) - Math.PI); if (dd < best.d) best = {c:d.c, d:dd}; });
          facingCardinal = best.c;
        } catch(e){}
      })();

      try { if (window.SFX && SFX.play) SFX.play('thunderwave_cast'); } catch(e){}

      // Helper: get tile rect by grid coords
      function tileRectByCoords(tx, ty){
        try {
          const el = document.querySelector(`.tile[data-coords-x="${tx}"][data-coords-y="${ty}"]`);
          if (!el) return null;
          const rect = el.getBoundingClientRect();
          const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
          const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          return { x: rect.left + scrollLeft, y: rect.top + scrollTop, w: rect.width, h: rect.height };
        } catch(e){ return null; }
      }

      // Build list of affected cube tiles (3x3) based on facing cardinal
      let cubeTiles = [];
      (function computeCubeTiles(){
        if (!srcTile) return;
        const [gx, gy] = srcTile;
        const half = 1; // 3x3
        let xMin, xMax, yMin, yMax;
        switch (facingCardinal) {
          case 'N': xMin = gx - half; xMax = gx + half; yMin = gy - 3; yMax = gy - 1; break;
          case 'S': xMin = gx - half; xMax = gx + half; yMin = gy + 1; yMax = gy + 3; break;
          case 'W': xMin = gx - 3; xMax = gx - 1; yMin = gy - half; yMax = gy + half; break;
          case 'E':
          default:  xMin = gx + 1; xMax = gx + 3; yMin = gy - half; yMax = gy + half; break;
        }
        for (let x = xMin; x <= xMax; x++){
          for (let y = yMin; y <= yMax; y++){
            // skip source tile if included by accident
            if (x === gx && y === gy) continue;
            const r = tileRectByCoords(x, y);
            if (r) cubeTiles.push({gx:x, gy:y, rect:r});
          }
        }
      })();

      // Helper: jagged lightning segment
      function drawLightning(ax, ay, bx, by, jitter, alpha, width){
        const dx = bx - ax, dy = by - ay; const dist = Math.max(1, Math.hypot(dx, dy));
        const nx = -dy/dist, ny = dx/dist; // normal
        const steps = Math.max(6, Math.floor(dist/28));
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        ctx.lineWidth = width || 2.5;
        ctx.strokeStyle = `rgba(200,230,255,${alpha.toFixed(2)})`;
        ctx.beginPath();
        for (let i=0;i<=steps;i++){
          const t = i/steps;
          const x = ax + dx*t, y = ay + dy*t;
          const amp = jitter * (1 - Math.abs(0.5 - t)*2);
          const off = (Math.random()*2 - 1) * amp;
          const jx = x + nx*off, jy = y + ny*off;
          if (i===0) ctx.moveTo(jx, jy); else ctx.lineTo(jx, jy);
        }
        ctx.stroke();
        // inner bright core
        ctx.lineWidth = Math.max(1, (width||2.5)*0.5);
        ctx.strokeStyle = `rgba(255,255,255,${(alpha*0.95).toFixed(2)})`;
        ctx.stroke();
        ctx.restore();
      }

      // Stage 1: brief charge swirl at caster
      const tCharge0 = performance.now();
      const chargeDur = 200;
      function charge(now){
        const t = Math.min(1, (now - tCharge0)/chargeDur);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        const a = 0.9 * (1 - Math.abs(0.5 - t)*2);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        // tight glowing core
        const r0 = 8 + 10*t;
        const g = ctx.createRadialGradient(src.x, src.y, 2, src.x, src.y, r0);
        g.addColorStop(0, `rgba(255,255,255, ${(0.7*a).toFixed(2)})`);
        g.addColorStop(1, `rgba(150,200,255, ${(0.5*a).toFixed(2)})`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(src.x, src.y, r0, 0, Math.PI*2); ctx.fill();
        // small sparks
        for (let i=0;i<8;i++){
          const ang = (i/8)*Math.PI*2 + now*0.01;
          const rr = 16 + 8*Math.sin(now*0.02 + i);
          const x = src.x + Math.cos(ang)*rr, y = src.y + Math.sin(ang)*rr;
          ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI*2);
          ctx.fillStyle = `rgba(220,240,255, ${(0.5*a).toFixed(2)})`; ctx.fill();
        }
        ctx.restore();
        if (t < 1) requestAnimationFrame(charge); else boom();
      }

      // Stage 2: concussive boom with directional cube highlight + halo and lightning cracks; subtle camera shake
      function boom(){
        try { if (window.SFX && SFX.play) SFX.play('thunderwave_boom'); } catch(e){}
        const t0 = performance.now();
        const dur = 720;
        const rMax = tileSize * 3.2; // ~15ft + a bit
        requestAnimationFrame(function loop(now){
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          const ease = 1 - Math.pow(1 - t, 2);
          // screen shake that decays quickly
          const shake = (1 - t) * 6;
          ctx.save(); ctx.translate((Math.random()-0.5)*shake, (Math.random()-0.5)*shake);
          ctx.globalCompositeOperation = 'screen';

          // Directional cube highlight: softly light up the affected 3x3 area
          if (cubeTiles.length){
            const fillA = 0.28 * (1 - t*0.7);
            const strokeA = 0.55 * (1 - t);
            cubeTiles.forEach(({rect}) => {
              const pad = Math.max(1, Math.min(3, tileSize*0.05));
              const x = rect.x + pad, y = rect.y + pad, w = rect.w - pad*2, h = rect.h - pad*2;
              // inner glow
              const g = ctx.createLinearGradient(x, y, x+w, y+h);
              g.addColorStop(0, `rgba(190,220,255, ${fillA.toFixed(2)})`);
              g.addColorStop(1, `rgba(130,170,255, ${Math.max(0,fillA-0.1).toFixed(2)})`);
              ctx.fillStyle = g;
              ctx.fillRect(x, y, w, h);
              // border
              ctx.strokeStyle = `rgba(255,255,255, ${strokeA.toFixed(2)})`;
              ctx.lineWidth = 2;
              ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
            });
          }

          // Soft circular halo blending the harsh edges around the caster
          const r = rMax * ease;
          const a1 = 0.9 * (1 - t);
          ctx.beginPath(); ctx.arc(src.x, src.y, Math.max(1, r*0.85), 0, Math.PI*2);
          ctx.strokeStyle = `rgba(160,200,255, ${(0.45*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 2.2 - 1.2*t; ctx.stroke();

          // Directional emphasis: draw a brighter arc in facing direction if known
          if (facingAngle != null){
            ctx.beginPath(); ctx.arc(src.x, src.y, Math.max(8, r*0.9), facingAngle - Math.PI/6, facingAngle + Math.PI/6);
            ctx.strokeStyle = `rgba(255,255,255, ${(0.9*(1-t)).toFixed(2)})`; ctx.lineWidth = 3; ctx.stroke();
          }

          // Lightning cracks radiating outward
          const bolts = 8;
          for (let i=0;i<bolts;i++){
            const ang = (i/bolts)*Math.PI*2 + (facingAngle!=null ? (i%2===0?0.08:-0.08) : 0);
            const bx = src.x + Math.cos(ang)*r;
            const by = src.y + Math.sin(ang)*r;
            drawLightning(src.x, src.y, bx, by, 16, 0.65*(1 - t*0.6), 2.5);
          }

          // Push hints on provided targets (short streaks from center through targets)
          centers.forEach((c, idx)=>{
            const dir = Math.atan2(c.y - src.y, c.x - src.x);
            const len = Math.min(r*0.8, Math.hypot(c.x - src.x, c.y - src.y));
            const ex = src.x + Math.cos(dir)*len;
            const ey = src.y + Math.sin(dir)*len;
            ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(ex, ey);
            ctx.strokeStyle = `rgba(255,255,255, ${(0.45*(1-t)).toFixed(2)})`;
            ctx.lineWidth = 2; ctx.stroke();
            // small ring bursting at the target tip
            ctx.beginPath(); ctx.arc(ex, ey, 10 + 14*(1 - (1-ease)*(1-ease)), 0, Math.PI*2);
            ctx.strokeStyle = `rgba(180,210,255, ${(0.35*(1-t)).toFixed(2)})`; ctx.lineWidth = 1.6; ctx.stroke();
          });

          ctx.restore(); // shake
          if (t < 1) requestAnimationFrame(loop); else linger();
        });
      }

      // Stage 3: brief lingering resonance that fades
      function linger(){
        const t0 = performance.now();
        const dur = 320;
        requestAnimationFrame(function f(now){
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const r = tileSize * 2.0;
          const g = ctx.createRadialGradient(src.x, src.y, 6, src.x, src.y, r);
          g.addColorStop(0, `rgba(255,255,255, ${(0.12*(1-t)).toFixed(2)})`);
          g.addColorStop(1, `rgba(150,200,255, ${(0.06*(1-t)).toFixed(2)})`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(src.x, src.y, r, 0, Math.PI*2); ctx.fill();
          ctx.restore();
          if (t < 1) requestAnimationFrame(f); else { destroy(); resolve(); }
        });
      }

      requestAnimationFrame(charge);
    });
  });

  // Spare the Dying: gentle stabilizing aura and soft pulse on the target
  register('spare_the_dying', function(payload){
    return new Promise((resolve) => {
      const tgtId = payload && payload.target;
      const srcId = payload && payload.source;
      const source = srcId ? centerOfEntity(srcId) : null;
      const target = tgtId ? centerOfEntity(tgtId) : null;
      if (!target) return resolve();

      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const baseR = Math.max(18, tileSize * 0.35);

      const { overlay, ctx, destroy } = createOverlay(1102);
      try { if (window.SFX && SFX.play) { SFX.play('spare_the_dying_cast'); } } catch(e){}

      const t0 = performance.now();
      const pulseDur = 520; // ms
      const fadeDur = 420;  // ms

      function drawCross(cx, cy, size, alpha){
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.lineCap = 'round';
        ctx.strokeStyle = 'rgba(255, 240, 200, 0.9)';
        ctx.lineWidth = Math.max(2, size * 0.12);
        // simple upright cross
        ctx.beginPath();
        ctx.moveTo(cx - size*0.6, cy);
        ctx.lineTo(cx + size*0.6, cy);
        ctx.moveTo(cx, cy - size*0.9);
        ctx.lineTo(cx, cy + size*0.9);
        ctx.stroke();
        ctx.restore();
      }

      function pulse(now){
        const t = Math.min(1, (now - t0)/pulseDur);
        ctx.clearRect(0,0,overlay.width, overlay.height);

        // optional faint link from caster to target
        if (source) {
          ctx.save();
          ctx.globalAlpha = 0.15 * (1 - t*0.7);
          const grad = ctx.createLinearGradient(source.x, source.y, target.x, target.y);
          grad.addColorStop(0, 'rgba(220,255,220,0.0)');
          grad.addColorStop(0.3, 'rgba(230,255,230,0.25)');
          grad.addColorStop(0.7, 'rgba(230,255,230,0.15)');
          grad.addColorStop(1, 'rgba(220,255,220,0.0)');
          ctx.strokeStyle = grad;
          ctx.lineWidth = Math.max(2, tileSize * 0.03);
          ctx.beginPath(); ctx.moveTo(source.x, source.y); ctx.lineTo(target.x, target.y); ctx.stroke();
          ctx.restore();
        }

        // expanding soft ring
        const r = baseR * (0.7 + 0.9 * t);
        const g = ctx.createRadialGradient(target.x, target.y, r*0.1, target.x, target.y, Math.max(r, 1));
        g.addColorStop(0, `rgba(255, 235, 190, ${(0.35*(1-t)).toFixed(2)})`);
        g.addColorStop(1, `rgba(120, 220, 160, ${(0.15*(1-t)).toFixed(2)})`);
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(target.x, target.y, r, 0, Math.PI*2); ctx.fill();

        // inner bloom
        const g2 = ctx.createRadialGradient(target.x, target.y, 0, target.x, target.y, r*0.7);
        g2.addColorStop(0, `rgba(255, 255, 230, ${(0.45*(1-t)).toFixed(2)})`);
        g2.addColorStop(1, `rgba(200, 255, 220, 0)`);
        ctx.fillStyle = g2;
        ctx.beginPath(); ctx.arc(target.x, target.y, r*0.7, 0, Math.PI*2); ctx.fill();

        // subtle cross glyph
        drawCross(target.x, target.y, r*0.7, 0.6 * (1 - t*0.8));

        // sparkles rising
        ctx.save(); ctx.globalCompositeOperation = 'lighter';
        for (let i=0;i<6;i++){
          const ang = Math.random()*Math.PI*2;
          const rr = r * (0.2 + 0.7*Math.random());
          const x = target.x + Math.cos(ang)*rr;
          const y = target.y + Math.sin(ang)*rr - t*12;
          const s = 1 + Math.random()*1.5;
          ctx.fillStyle = `rgba(255, 255, 210, ${(0.25*(1-t)).toFixed(2)})`;
          ctx.beginPath(); ctx.arc(x, y, s, 0, Math.PI*2); ctx.fill();
        }
        ctx.restore();

        if (t < 1) requestAnimationFrame(pulse); else {
          try { if (window.SFX && SFX.play) { SFX.play('spare_the_dying_bloom'); } } catch(e){}
          const t1 = performance.now();
          requestAnimationFrame(function fade(now2){
            const tt = Math.min(1, (now2 - t1)/fadeDur);
            ctx.clearRect(0,0,overlay.width, overlay.height);
            // lingering halo
            const r2 = baseR * (1.1);
            const gf = ctx.createRadialGradient(target.x, target.y, r2*0.05, target.x, target.y, r2);
            gf.addColorStop(0, `rgba(255, 250, 220, ${(0.22*(1-tt)).toFixed(2)})`);
            gf.addColorStop(1, `rgba(140, 230, 180, ${(0.10*(1-tt)).toFixed(2)})`);
            ctx.fillStyle = gf;
            ctx.beginPath(); ctx.arc(target.x, target.y, r2, 0, Math.PI*2); ctx.fill();

            // faint cross persists
            drawCross(target.x, target.y, r2*0.6, 0.25 * (1-tt));
            if (tt < 1) requestAnimationFrame(fade); else { destroy(); resolve(); }
          });
        }
      }

      requestAnimationFrame(pulse);
    });
  });

  // Bane: ominous red pulse, clear hex glyph, pulsing ring, and stronger caster->target tethers with impact throb
  register('bane', function(payload){
    return new Promise((resolve)=>{
      const targets = Array.isArray(payload?.target) ? payload.target : [payload?.target].filter(Boolean);
      if (!targets.length) return resolve();
      const src = payload?.source ? centerOfEntity(payload.source) : null;
      const { overlay, ctx, destroy } = createOverlay(1105);
      try { SFX && SFX.play && SFX.play('bane_cast'); } catch(e){}
      const t0 = performance.now(); const dur = 850;
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const centers = targets.map(id => centerOfEntity(id)).filter(Boolean);
      function loop(now){
        const t = Math.min(1, (now - t0)/dur);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save();
        centers.forEach(c => {
          const base = Math.max(18, tileSize*0.46);
          const puls = 0.5 + 0.5*Math.sin(now*0.012);
          const r = base * (0.95 + 0.25*Math.sin(t*Math.PI));
          // darker ominous halo
          const g = ctx.createRadialGradient(c.x, c.y, r*0.05, c.x, c.y, r);
          g.addColorStop(0, `rgba(220,50,50, ${(0.42*(1-t)).toFixed(2)})`);
          g.addColorStop(1, `rgba(90,10,10, 0)`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2); ctx.fill();
          // pulsing dashed ring
          ctx.setLineDash([6, 6]);
          ctx.lineDashOffset = -now*0.04;
          ctx.strokeStyle = `rgba(240,90,90, ${(0.7*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 2.2;
          ctx.beginPath(); ctx.arc(c.x, c.y, r*0.9 + puls*2, 0, Math.PI*2); ctx.stroke();
          ctx.setLineDash([]);
          // prominent hex glyph
          ctx.strokeStyle = `rgba(255,110,110, ${(0.8*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 2.6;
          const sides = 6; const rr = r*0.68; ctx.beginPath();
          for (let i=0;i<sides;i++){ const a = (Math.PI*2)*i/sides + 0.1; const x = c.x + Math.cos(a)*rr; const y = c.y + Math.sin(a)*rr; if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);} ctx.closePath(); ctx.stroke();
        });
        if (src) {
          centers.forEach(c => {
            ctx.save();
            // stronger tether that fades
            const a = 0.35*(1-t);
            const grd = ctx.createLinearGradient(src.x, src.y, c.x, c.y);
            grd.addColorStop(0, `rgba(255,120,120, ${a.toFixed(2)})`);
            grd.addColorStop(1, `rgba(160,40,40, 0)`);
            ctx.strokeStyle = grd; ctx.lineWidth = 3;
            ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(c.x, c.y); ctx.stroke();
            ctx.restore();
          });
        }
        ctx.restore();
        if (t < 1) requestAnimationFrame(loop); else {
          // brief impact throb to signal application
          const t1 = performance.now();
          const impact = (now2)=>{
            const tt = Math.min(1, (now2 - t1)/220);
            ctx.clearRect(0,0,overlay.width, overlay.height);
            ctx.save();
            centers.forEach(c => {
              const r = Math.max(18, tileSize*0.46) * (1 + 0.25*tt);
              ctx.strokeStyle = `rgba(255,120,120, ${(0.7*(1-tt)).toFixed(2)})`;
              ctx.lineWidth = 3 - 1.5*tt;
              ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2); ctx.stroke();
            });
            ctx.restore();
            if (tt < 1) requestAnimationFrame(impact); else { try { SFX && SFX.play && SFX.play('bane_apply'); } catch(e){} destroy(); resolve(); }
          };
          requestAnimationFrame(impact);
        }
      }
      requestAnimationFrame(loop);
    });
  });

  // Bless: radiant boon from caster to allies with golden tethers and clear target glyphs
  register('bless', function(payload){
    return new Promise((resolve)=>{
      const srcId = payload && payload.source;
      const src = srcId ? centerOfEntity(srcId) : null;
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!src && !centers.length) return resolve();
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const { overlay, ctx, destroy } = createOverlay(1104);
      try { if (window.SFX && SFX.play) SFX.play('bless_cast'); } catch(e){}

      // Stage 1: brief radiant charge at caster
      function charge(next){
        if (!src) return next();
        const t0 = performance.now();
        const dur = 260;
        requestAnimationFrame(function loop(now){
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const baseR = Math.max(20, tileSize*0.5);
          const r = baseR * (0.8 + 0.4*t);
          // soft halo
          const g = ctx.createRadialGradient(src.x, src.y, 2, src.x, src.y, r);
          g.addColorStop(0, `rgba(255,255,220, ${(0.5*(1-t)).toFixed(2)})`);
          g.addColorStop(1, `rgba(255,215,120, ${(0.18*(1-t)).toFixed(2)})`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(src.x, src.y, r, 0, Math.PI*2); ctx.fill();
          // rotating sigil arcs
          const ang = now*0.004;
          ctx.strokeStyle = `rgba(255,220,140, ${(0.85*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 2.4;
          for (let k=0;k<3;k++){
            const a0 = ang + (k/3)*Math.PI*2;
            ctx.beginPath(); ctx.arc(src.x, src.y, r*0.75, a0, a0 + Math.PI/3); ctx.stroke();
          }
          // sparkle motes
          for (let i=0;i<8;i++){
            const aa = (i/8)*Math.PI*2 + now*0.006;
            const rr = r*0.5 + Math.sin(aa*4 + now*0.01)*4;
            const x = src.x + Math.cos(aa)*rr, y = src.y + Math.sin(aa)*rr;
            ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI*2);
            ctx.fillStyle = `rgba(255,255,240, ${(0.5*(1-t)).toFixed(2)})`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else next();
        });
      }

      // Stage 2: golden tethers to each target
      function tethers(next){
        if (!src || !centers.length) return next();
        const t0 = performance.now();
        const dur = 320;
        requestAnimationFrame(function loop(now){
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          centers.forEach((c, idx)=>{
            const grad = ctx.createLinearGradient(src.x, src.y, c.x, c.y);
            grad.addColorStop(0, `rgba(255,240,180, ${(0.9*(1-t)).toFixed(2)})`);
            grad.addColorStop(1, `rgba(255,200,120, ${(0.2*(1-t)).toFixed(2)})`);
            ctx.strokeStyle = grad; ctx.lineWidth = 3;
            // Draw progressive line
            const x = src.x + (c.x - src.x) * (0.6 + 0.4*t);
            const y = src.y + (c.y - src.y) * (0.6 + 0.4*t);
            ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(x, y); ctx.stroke();
          });
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else next();
        });
      }

      // Stage 3: target glyphs (ring + star + small rotating d4 diamond)
      function applyGlyphs(done){
        const t0 = performance.now();
        const dur = 820;
        requestAnimationFrame(function loop(now){
          const t = Math.min(1, (now - t0)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          centers.forEach((c, idx)=>{
            const r = Math.max(16, tileSize*0.45) * (0.9 + 0.2*Math.sin(now*0.01 + idx));
            // soft halo fill
            const gf = ctx.createRadialGradient(c.x, c.y, 2, c.x, c.y, r);
            gf.addColorStop(0, `rgba(255,255,220, ${(0.22*(1-t)).toFixed(2)})`);
            gf.addColorStop(1, `rgba(255,215,120, 0)`);
            ctx.fillStyle = gf; ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2); ctx.fill();
            // bright ring
            ctx.beginPath(); ctx.arc(c.x, c.y, r*0.85, 0, Math.PI*2);
            ctx.strokeStyle = `rgba(255,235,180, ${(0.85*(1-t)).toFixed(2)})`; ctx.lineWidth = 2.6; ctx.stroke();
            // tiny 4-point star
            const len = 10;
            ctx.strokeStyle = `rgba(255,255,255, ${(0.9*(1-t)).toFixed(2)})`; ctx.lineWidth = 1.6;
            ctx.beginPath();
            ctx.moveTo(c.x - len, c.y); ctx.lineTo(c.x + len, c.y);
            ctx.moveTo(c.x, c.y - len); ctx.lineTo(c.x, c.y + len);
            ctx.stroke();
            // rotating diamond (d4 hint)
            const rot = now*0.004 + idx*0.6;
            const d = 7;
            ctx.save(); ctx.translate(c.x, c.y - r*0.65); ctx.rotate(rot);
            ctx.beginPath(); ctx.moveTo(0, -d); ctx.lineTo(d, 0); ctx.lineTo(0, d); ctx.lineTo(-d, 0); ctx.closePath();
            ctx.strokeStyle = `rgba(255,255,255, ${(0.8*(1-t)).toFixed(2)})`; ctx.lineWidth = 1.4; ctx.stroke();
            ctx.restore();
          });
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else { try { if (window.SFX && SFX.play) SFX.play('bless_apply'); } catch(e){} done(); }
        });
      }

      charge(()=> tethers(()=> applyGlyphs(()=> { destroy(); resolve(); })));
    });
  });

  // Guidance: focused glow from caster to single ally with hovering d4 motes
  register('guidance', function(payload){
    return new Promise((resolve)=>{
      const targets = ensureArray(payload && payload.target).filter(Boolean);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!centers.length) return resolve();
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const { overlay, ctx, destroy } = createOverlay(1104);
      try { if (window.SFX && SFX.play) SFX.play('guidance_cast'); } catch(e){}

      const motes = centers.map(()=>{
        return Array.from({length: 10}, (_, idx)=>({ angle: (idx/10)*Math.PI*2, radius: 0.4 + 0.12*Math.random(), seed: Math.random()*Math.PI*2 }));
      });

      function stageBeam(next){
        if (!src) return next();
        const start = performance.now();
        const dur = 280;
        requestAnimationFrame(function beam(now){
          const t = Math.min(1, (now - start)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          centers.forEach((c, idx)=>{
            const grad = ctx.createLinearGradient(src.x, src.y, c.x, c.y);
            grad.addColorStop(0, `rgba(230, 200, 120, ${(0.7*(1-t)).toFixed(2)})`);
            grad.addColorStop(1, `rgba(170, 140, 80, ${(0.15*(1-t)).toFixed(2)})`);
            ctx.strokeStyle = grad; ctx.lineWidth = 3 - 1.4*t;
            ctx.beginPath(); ctx.moveTo(src.x, src.y);
            const px = src.x + (c.x - src.x) * (0.5 + 0.5*t);
            const py = src.y + (c.y - src.y) * (0.5 + 0.5*t);
            ctx.lineTo(px, py);
            ctx.stroke();
          });
          ctx.restore();
          if (t < 1) requestAnimationFrame(beam); else next();
        });
      }

      function stageHalo(done){
        const start = performance.now();
        const dur = 780;
        requestAnimationFrame(function halo(now){
          const t = Math.min(1, (now - start)/dur);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          centers.forEach((c, idx)=>{
            const base = Math.max(18, tileSize*0.48);
            const pulse = 0.85 + 0.18*Math.sin((now*0.007) + idx);
            const radius = base * pulse;
            const glow = ctx.createRadialGradient(c.x, c.y, 2, c.x, c.y, radius);
            glow.addColorStop(0, `rgba(245, 230, 170, ${(0.38*(1-t)).toFixed(2)})`);
            glow.addColorStop(1, `rgba(210, 180, 120, 0)`);
            ctx.fillStyle = glow;
            ctx.beginPath(); ctx.arc(c.x, c.y, radius, 0, Math.PI*2); ctx.fill();

            ctx.strokeStyle = `rgba(255, 240, 190, ${(0.75*(1-t)).toFixed(2)})`;
            ctx.lineWidth = 2.3;
            ctx.beginPath(); ctx.arc(c.x, c.y, radius*0.85, 0, Math.PI*2); ctx.stroke();

            const moteSet = motes[idx];
            moteSet.forEach((m, mIdx)=>{
              const ang = m.angle + (now*0.004) + m.seed;
              const rr = radius * (m.radius);
              const x = c.x + Math.cos(ang)*rr;
              const y = c.y + Math.sin(ang)*rr;
              const size = 2 + 1.5*Math.sin((now*0.009) + mIdx);
              ctx.beginPath(); ctx.arc(x, y, size, 0, Math.PI*2);
              ctx.fillStyle = `rgba(255, 255, 220, ${(0.55*(1-t)).toFixed(2)})`;
              ctx.fill();
            });

            const spin = now*0.003 + idx;
            const d = 8;
            ctx.save();
            ctx.translate(c.x, c.y - radius*0.55);
            ctx.rotate(spin);
            ctx.beginPath();
            ctx.moveTo(0, -d);
            ctx.lineTo(d, 0);
            ctx.lineTo(0, d);
            ctx.lineTo(-d, 0);
            ctx.closePath();
            ctx.strokeStyle = `rgba(255, 255, 210, ${(0.65*(1-t)).toFixed(2)})`;
            ctx.lineWidth = 1.4;
            ctx.stroke();
            ctx.restore();
          });
          ctx.restore();
          if (t < 1) requestAnimationFrame(halo); else { try { if (window.SFX && SFX.play) SFX.play('guidance_apply'); } catch(e){} done(); }
        });
      }

      stageBeam(()=> stageHalo(()=> { destroy(); resolve(); }));
    });
  });

  // Resistance: brief protective shimmer on target with teal ring and a soft tether from caster
  register('resistance', function(payload){
    return new Promise((resolve)=>{
      const targets = Array.isArray(payload?.target) ? payload.target : [payload?.target].filter(Boolean);
      if (!targets.length) return resolve();
      const src = payload?.source ? centerOfEntity(payload.source) : null;
      const { overlay, ctx, destroy } = createOverlay(1104);
  try { SFX && SFX.play && SFX.play('resistance_cast'); } catch(e){}
      const t0 = performance.now(); const dur = 700;
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const centers = targets.map(id => centerOfEntity(id)).filter(Boolean);
      function loop(now){
        const t = Math.min(1, (now - t0)/dur);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        centers.forEach(c => {
          const base = Math.max(18, tileSize*0.5);
          const r = base * (0.9 + 0.2*Math.sin(t*Math.PI));
          const g = ctx.createRadialGradient(c.x, c.y, r*0.05, c.x, c.y, r);
          g.addColorStop(0, `rgba(120, 200, 255, ${(0.42*(1-t)).toFixed(2)})`);
          g.addColorStop(1, `rgba(60, 140, 220, 0)`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2); ctx.fill();
          ctx.strokeStyle = `rgba(140, 220, 255, ${(0.85*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 2.4; ctx.beginPath(); ctx.arc(c.x, c.y, r*0.9, 0, Math.PI*2); ctx.stroke();
        });
        if (src) {
          centers.forEach(c => {
            const a = 0.28*(1-t);
            ctx.strokeStyle = `rgba(140, 220, 255, ${a.toFixed(2)})`;
            ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(c.x, c.y); ctx.stroke();
          });
        }
        ctx.restore();
  if (t < 1) requestAnimationFrame(loop); else { try { SFX && SFX.play && SFX.play('resistance_apply'); } catch(e){} destroy(); resolve(); }
      }
      requestAnimationFrame(loop);
    });
  });

  // Second Wind: invigorating inward swirl, heartbeat bloom, and uplifting motes
  register('second_wind', function(payload){
    return new Promise((resolve)=>{
      const srcId = payload && payload.source;
      const c = srcId ? centerOfEntity(srcId) : null;
      if (!c) return resolve();
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const baseR = Math.max(26, tileSize * 0.85);
      const { overlay, ctx, destroy } = createOverlay(1105);
      try { if (window.SFX && SFX.play) SFX.play('second_wind_cast'); } catch(e){}

      // Stage 1: inward swirl (gives a sense of drawing breath/strength)
      const t0 = performance.now();
      const dur1 = 260;
      function stage1(now){
        const t = Math.min(1, (now - t0)/dur1);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        const a = 0.95 * (1 - t);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        const rings = 4;
        for (let i=0;i<rings;i++){
          const f = i/(rings-1);
          const r = baseR * (1.2 - 0.3*t) * (0.55 + 0.55*f);
          ctx.setLineDash([6,6]);
          ctx.lineDashOffset = (1-t) * 28 * (i%2?1:-1);
          ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(140,220,255, ${(0.75*a).toFixed(2)})`;
          ctx.lineWidth = 3.0; ctx.stroke();
        }
        ctx.setLineDash([]);
        // stronger core glow
        const g = ctx.createRadialGradient(c.x, c.y, 2, c.x, c.y, baseR*0.7);
        g.addColorStop(0, `rgba(255,255,255, ${(0.6*a).toFixed(2)})`);
        g.addColorStop(1, `rgba(100,200,180, ${(0.3*a).toFixed(2)})`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c.x, c.y, baseR*0.7, 0, Math.PI*2); ctx.fill();
        ctx.restore();
        if (t < 1) requestAnimationFrame(stage1); else stage2();
      }

      // Stage 2: heartbeat healing bloom with uplifting motes
      function stage2(){
        const t1 = performance.now();
        const dur2 = 850;
        requestAnimationFrame(function loop(now){
          const t = Math.min(1, (now - t1)/dur2);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const beat = Math.max(0, Math.sin((now - t1)*0.012));
          const r = baseR * (0.9 + 0.6*t + 0.1*beat);
          // soft fill glow
          const gf = ctx.createRadialGradient(c.x, c.y, 4, c.x, c.y, r*0.95);
          gf.addColorStop(0, `rgba(255,255,255, ${(0.22*(1-t)).toFixed(2)})`);
          gf.addColorStop(1, `rgba(140,220,200, ${(0.10*(1-t)).toFixed(2)})`);
          ctx.fillStyle = gf; ctx.beginPath(); ctx.arc(c.x, c.y, r*0.95, 0, Math.PI*2); ctx.fill();
          // dual halo
          ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(140,220,255, ${(0.85*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 3.4 - 1.4*t; ctx.stroke();
          ctx.beginPath(); ctx.arc(c.x, c.y, Math.max(6, r-6), 0, Math.PI*2);
          ctx.strokeStyle = `rgba(255,255,255, ${(0.7*(1-t)).toFixed(2)})`; ctx.lineWidth = 2.0; ctx.stroke();
          // uplifting motes
          for (let i=0;i<16;i++){
            const ang = Math.random()*Math.PI*2;
            const rr = r * (0.2 + 0.6*Math.random());
            const x = c.x + Math.cos(ang)*rr;
            const y = c.y + Math.sin(ang)*rr - 14*t;
            const s = 1.2 + Math.random()*1.6;
            ctx.beginPath(); ctx.arc(x, y, s, 0, Math.PI*2);
            ctx.fillStyle = `rgba(220,255,240, ${(0.5*(1-t)).toFixed(2)})`; ctx.fill();
          }
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else stage3();
        });
      }

      // Stage 3: quick, gentle fade
      function stage3(){
        const t2 = performance.now();
        const dur3 = 420;
        requestAnimationFrame(function fade(now){
          const t = Math.min(1, (now - t2)/dur3);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const g = ctx.createRadialGradient(c.x, c.y, 4, c.x, c.y, baseR*1.1);
          g.addColorStop(0, `rgba(255,255,255, ${(0.2*(1-t)).toFixed(2)})`);
          g.addColorStop(1, `rgba(120,220,200, ${(0.1*(1-t)).toFixed(2)})`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c.x, c.y, baseR*1.1, 0, Math.PI*2); ctx.fill();
          ctx.restore();
          if (t < 1) requestAnimationFrame(fade); else { destroy(); resolve(); }
        });
      }

      requestAnimationFrame(stage1);
    });
  });

  // Action Surge: time-slice ripple, speed streaks, and rotating tick marks
  register('action_surge', function(payload){
    return new Promise((resolve)=>{
      const srcId = payload && payload.source;
      const c = srcId ? centerOfEntity(srcId) : null;
      if (!c) return resolve();
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const baseR = Math.max(22, tileSize * 0.7);
      const { overlay, ctx, destroy } = createOverlay(1105);
      try { if (window.SFX && SFX.play) SFX.play('action_surge_cast'); } catch(e){}

      // Stage 1: snap preflash
      const t0 = performance.now();
      const dur1 = 180;
      function stage1(now){
        const t = Math.min(1, (now - t0)/dur1);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        ctx.save(); ctx.globalCompositeOperation = 'screen';
        const a = 1 - t;
        // core flash
        ctx.beginPath(); ctx.arc(c.x, c.y, 8 + 6*t, 0, Math.PI*2);
        ctx.fillStyle = `rgba(255,255,255, ${(0.8*a).toFixed(2)})`; ctx.fill();
        // tick marks (like a speed dial)
        const ticks = 12; const r = baseR*0.8;
        ctx.strokeStyle = `rgba(160,200,255, ${(0.9*a).toFixed(2)})`; ctx.lineWidth = 2;
        for (let i=0;i<ticks;i++){
          const ang = (i/ticks)*Math.PI*2 + now*0.01;
          const x0 = c.x + Math.cos(ang)*(r-6);
          const y0 = c.y + Math.sin(ang)*(r-6);
          const x1 = c.x + Math.cos(ang)*r;
          const y1 = c.y + Math.sin(ang)*r;
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
        }
        ctx.restore();
        if (t < 1) requestAnimationFrame(stage1); else stage2();
      }

      // Stage 2: main ripple with speed streaks and rotating ticks
      function stage2(){
        try { if (window.SFX && SFX.play) SFX.play('action_surge_surge'); } catch(e){}
        const t1 = performance.now();
        const dur2 = 640;
        const streaks = Array.from({length: 22}, (_,i)=>({
          a: (i/22)*Math.PI*2,
          len: baseR * (0.8 + Math.random()*0.6),
          w: 2 + Math.random()*2,
          phase: Math.random()*Math.PI*2
        }));
        requestAnimationFrame(function loop(now){
          const t = Math.min(1, (now - t1)/dur2);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          const ease = 1 - Math.pow(1 - t, 2);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          // expanding ripple ring
          const r = baseR * (0.8 + 1.0*ease);
          ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(200,230,255, ${(0.75*(1-t)).toFixed(2)})`;
          ctx.lineWidth = 3 - 1.5*t; ctx.stroke();
          // inner bright edge
          ctx.beginPath(); ctx.arc(c.x, c.y, r-4, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(255,255,255, ${(0.65*(1-t)).toFixed(2)})`; ctx.lineWidth = 1.4; ctx.stroke();
          // rotating ticks
          const ticks = 16; const rr = r*0.8;
          ctx.strokeStyle = `rgba(160,200,255, ${(0.8*(1-t)).toFixed(2)})`; ctx.lineWidth = 2;
          for (let i=0;i<ticks;i++){
            const ang = (i/ticks)*Math.PI*2 + now*0.008;
            const x0 = c.x + Math.cos(ang)*(rr-6);
            const y0 = c.y + Math.sin(ang)*(rr-6);
            const x1 = c.x + Math.cos(ang)*rr;
            const y1 = c.y + Math.sin(ang)*rr;
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          }
          // speed streaks
          streaks.forEach(s => {
            const wob = Math.sin(now*0.01 + s.phase) * 0.15;
            const ang = s.a + wob;
            const len = s.len * (0.6 + 0.6*ease);
            const fade = 1 - t;
            const x0 = c.x + Math.cos(ang)*(r*0.4);
            const y0 = c.y + Math.sin(ang)*(r*0.4);
            const x1 = c.x + Math.cos(ang)*(r*0.4 + len);
            const y1 = c.y + Math.sin(ang)*(r*0.4 + len);
            const grd = ctx.createLinearGradient(x0, y0, x1, y1);
            grd.addColorStop(0, `rgba(255,255,255, ${(0.55*fade).toFixed(2)})`);
            grd.addColorStop(1, `rgba(140,200,255, ${(0.05*fade).toFixed(2)})`);
            ctx.strokeStyle = grd; ctx.lineWidth = s.w;
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          });
          // subtle opposing arcs (afterimage sweep)
          ctx.beginPath(); ctx.arc(c.x, c.y, Math.max(8, rr*0.9), Math.PI*0.15 + now*0.002, Math.PI*0.3 + now*0.002);
          ctx.strokeStyle = `rgba(255,255,255, ${(0.4*(1-t)).toFixed(2)})`; ctx.lineWidth = 2; ctx.stroke();
          ctx.beginPath(); ctx.arc(c.x, c.y, Math.max(8, rr*0.9), -Math.PI*0.3 - now*0.002, -Math.PI*0.15 - now*0.002);
          ctx.strokeStyle = `rgba(200,230,255, ${(0.3*(1-t)).toFixed(2)})`; ctx.lineWidth = 2; ctx.stroke();
          ctx.restore();
          if (t < 1) requestAnimationFrame(loop); else stage3();
        });
      }

      // Stage 3: quick fade-out
      function stage3(){
        const t2 = performance.now();
        const dur3 = 260;
        requestAnimationFrame(function fade(now){
          const t = Math.min(1, (now - t2)/dur3);
          ctx.clearRect(0,0,overlay.width, overlay.height);
          ctx.save(); ctx.globalCompositeOperation = 'screen';
          const g = ctx.createRadialGradient(c.x, c.y, 4, c.x, c.y, baseR*1.2);
          g.addColorStop(0, `rgba(255,255,255, ${(0.16*(1-t)).toFixed(2)})`);
          g.addColorStop(1, `rgba(160,200,255, ${(0.07*(1-t)).toFixed(2)})`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(c.x, c.y, baseR*1.2, 0, Math.PI*2); ctx.fill();
          ctx.restore();
          if (t < 1) requestAnimationFrame(fade); else { destroy(); resolve(); }
        });
      }

      requestAnimationFrame(stage1);
    });
  });

  // Rage (Barbarian): explosive fiery aura around the source with embers,
  // a spinning runic ring, a "RAGE!" battle cry, and a brief map shake.
  register('rage', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      if (!src) return resolve();

      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const baseR = Math.max(36, tileSize * 0.85);

      // Roar SFX
      try { if (window.SFX && SFX.play) SFX.play('rage_roar'); } catch(e){}

      // Brief map shake
      const $shake = $('.tiles-container').first();
      let shakeOrig = null;
      if ($shake && $shake.length) {
        try {
          shakeOrig = $shake.css('transform') || '';
          const shakeStart = performance.now();
          const shakeDur = 520;
          const shake = (now) => {
            const t = (now - shakeStart) / shakeDur;
            if (t >= 1) { try { $shake.css('transform', shakeOrig || ''); } catch(e){} return; }
            const amp = 6 * (1 - t);
            const dx = (Math.random()*2 - 1) * amp;
            const dy = (Math.random()*2 - 1) * amp;
            try { $shake.css('transform', `translate(${dx.toFixed(2)}px, ${dy.toFixed(2)}px)`); } catch(e){}
            requestAnimationFrame(shake);
          };
          requestAnimationFrame(shake);
        } catch(e){ shakeOrig = null; }
      }

      const { overlay, ctx, destroy } = createOverlay(1103);
      const start = performance.now();
      const total = 1500;

      // Pre-seed embers (sparks)
      const embers = [];
      const emberCount = 60;
      for (let i = 0; i < emberCount; i++) {
        const ang = Math.random() * Math.PI * 2;
        const spd = 90 + Math.random() * 220;
        embers.push({
          ang,
          spd,
          life: 0.3 + Math.random() * 0.7,
          birth: Math.random() * 0.35,
          size: 1 + Math.random() * 2.4,
          hue: 14 + Math.random() * 28, // 14..42 (red-orange-yellow)
        });
      }

      // Floating "RAGE!" text
      const cry = 'RAGE!';

      const draw = (now) => {
        const tt = Math.min(1, (now - start) / total);
        ctx.clearRect(0, 0, overlay.width, overlay.height);

        ctx.save();
        ctx.globalCompositeOperation = 'lighter';

        // 1) Pulsing fiery aura (radial gradient) around the source
        const pulse = 0.5 + 0.5 * Math.sin(now * 0.018);
        const auraR = baseR * (1.0 + 0.18 * pulse) * (0.7 + 0.3 * Math.min(1, tt * 2));
        const auraAlpha = (0.85) * (1 - Math.pow(tt, 1.6));
        const grad = ctx.createRadialGradient(src.x, src.y, baseR * 0.18, src.x, src.y, auraR);
        grad.addColorStop(0.0, `rgba(255,240,180,${(0.85 * auraAlpha).toFixed(3)})`);
        grad.addColorStop(0.25, `rgba(255,140,40,${(0.75 * auraAlpha).toFixed(3)})`);
        grad.addColorStop(0.6, `rgba(220,40,20,${(0.55 * auraAlpha).toFixed(3)})`);
        grad.addColorStop(1.0, `rgba(120,10,0,0)`);
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(src.x, src.y, auraR, 0, Math.PI * 2); ctx.fill();

        // 2) Initial shockwave ring (first 380 ms)
        if (tt < 0.27) {
          const wt = tt / 0.27;
          const ringR = baseR * (0.3 + 1.6 * wt);
          ctx.beginPath(); ctx.arc(src.x, src.y, ringR, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(255,180,80,${(0.85 * (1 - wt)).toFixed(3)})`;
          ctx.lineWidth = 4 + 4 * (1 - wt);
          ctx.stroke();
        }

        // 3) Two counter-rotating runic rings
        const ringAlpha = 0.8 * (1 - Math.pow(Math.max(0, tt - 0.15) / 0.85, 2));
        const ringR1 = baseR * 0.95;
        const ringR2 = baseR * 1.18;
        const angA = now * 0.006;
        const angB = -now * 0.0045;
        for (let k = 0; k < 6; k++) {
          const a0 = angA + (k / 6) * Math.PI * 2;
          ctx.beginPath();
          ctx.arc(src.x, src.y, ringR1, a0, a0 + Math.PI / 7);
          ctx.strokeStyle = `rgba(255,210,120,${(0.95 * ringAlpha).toFixed(3)})`;
          ctx.lineWidth = 3.0; ctx.stroke();
        }
        for (let k = 0; k < 8; k++) {
          const a0 = angB + (k / 8) * Math.PI * 2;
          ctx.beginPath();
          ctx.arc(src.x, src.y, ringR2, a0, a0 + Math.PI / 10);
          ctx.strokeStyle = `rgba(255,90,30,${(0.85 * ringAlpha).toFixed(3)})`;
          ctx.lineWidth = 2.0; ctx.stroke();
        }

        // 4) Embers radiating outward
        const dt = tt; // 0..1 normalized lifetime of effect
        for (let i = 0; i < embers.length; i++) {
          const em = embers[i];
          if (dt < em.birth) continue;
          const elapsed = (dt - em.birth) / em.life;
          if (elapsed >= 1) continue;
          const dist = baseR * 0.25 + em.spd * elapsed * (total / 1000);
          const x = src.x + Math.cos(em.ang) * dist;
          const y = src.y + Math.sin(em.ang) * dist - elapsed * 24; // slight rise
          const a = (1 - elapsed) * (1 - tt * 0.4);
          const r = em.size * (1 - elapsed * 0.4);
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
          ctx.fillStyle = `hsla(${em.hue.toFixed(0)}, 95%, ${(55 + 10 * (1 - elapsed)).toFixed(0)}%, ${a.toFixed(3)})`;
          ctx.fill();
        }

        ctx.restore();

        // 5) "RAGE!" text rising and fading (drawn in source-over for legibility)
        if (tt < 0.9) {
          const ct = tt / 0.9;
          const ease = ct < 0.4 ? (ct / 0.4) : 1;
          const fade = ct < 0.55 ? 1 : (1 - (ct - 0.55) / 0.45);
          const ty = src.y - baseR * 1.1 - ease * 28;
          const scale = 1 + 0.6 * (1 - Math.pow(1 - ease, 3));
          ctx.save();
          ctx.translate(src.x, ty);
          ctx.scale(scale, scale);
          ctx.font = 'bold 28px "Trebuchet MS", system-ui, sans-serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.lineWidth = 5;
          ctx.strokeStyle = `rgba(40,0,0,${(0.85 * fade).toFixed(3)})`;
          ctx.strokeText(cry, 0, 0);
          ctx.shadowColor = `rgba(255,120,40,${(0.9 * fade).toFixed(3)})`;
          ctx.shadowBlur = 18;
          const tg = ctx.createLinearGradient(0, -16, 0, 16);
          tg.addColorStop(0, `rgba(255,240,160,${fade.toFixed(3)})`);
          tg.addColorStop(0.5, `rgba(255,140,40,${fade.toFixed(3)})`);
          tg.addColorStop(1, `rgba(200,30,10,${fade.toFixed(3)})`);
          ctx.fillStyle = tg;
          ctx.fillText(cry, 0, 0);
          ctx.restore();
        }

        if (tt < 1) {
          requestAnimationFrame(draw);
        } else {
          try { if ($shake && shakeOrig !== null) $shake.css('transform', shakeOrig || ''); } catch(e){}
          destroy();
          resolve();
        }
      };
      requestAnimationFrame(draw);
    });
  });

  // End Rage: brief calming exhale of red smoke wisps fading away.
  register('end_rage', function(payload){
    return new Promise((resolve) => {
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      if (!src) return resolve();
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const baseR = Math.max(28, tileSize * 0.7);
      const { overlay, ctx, destroy } = createOverlay(1103);
      const start = performance.now();
      const total = 700;
      const wisps = [];
      for (let i = 0; i < 14; i++) {
        wisps.push({
          ang: -Math.PI/2 + (Math.random() - 0.5) * Math.PI * 0.7,
          spd: 30 + Math.random() * 50,
          birth: Math.random() * 0.25,
          life: 0.6 + Math.random() * 0.4,
          size: 6 + Math.random() * 10,
        });
      }
      const draw = (now) => {
        const tt = Math.min(1, (now - start) / total);
        ctx.clearRect(0, 0, overlay.width, overlay.height);
        ctx.save();
        ctx.globalCompositeOperation = 'source-over';
        // Faint dimming aura
        const a = 0.45 * (1 - tt);
        const grad = ctx.createRadialGradient(src.x, src.y, baseR*0.15, src.x, src.y, baseR);
        grad.addColorStop(0, `rgba(160,30,30,${(0.5*a).toFixed(3)})`);
        grad.addColorStop(1, `rgba(60,10,10,0)`);
        ctx.fillStyle = grad;
        ctx.beginPath(); ctx.arc(src.x, src.y, baseR, 0, Math.PI*2); ctx.fill();
        for (let i = 0; i < wisps.length; i++) {
          const w = wisps[i];
          if (tt < w.birth) continue;
          const e = (tt - w.birth) / w.life;
          if (e >= 1) continue;
          const dist = w.spd * e * (total / 1000);
          const x = src.x + Math.cos(w.ang) * dist + (Math.sin(now*0.01 + i) * 4);
          const y = src.y + Math.sin(w.ang) * dist;
          const r = w.size * (0.6 + 0.8 * e);
          const alpha = (1 - e) * 0.45;
          const wg = ctx.createRadialGradient(x, y, 0, x, y, r);
          wg.addColorStop(0, `rgba(180,90,80,${alpha.toFixed(3)})`);
          wg.addColorStop(1, `rgba(60,30,30,0)`);
          ctx.fillStyle = wg;
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI*2); ctx.fill();
        }
        ctx.restore();
        if (tt < 1) requestAnimationFrame(draw); else { destroy(); resolve(); }
      };
      try { if (window.SFX && SFX.play) SFX.play('rage_calm'); } catch(e){}
      requestAnimationFrame(draw);
    });
  });

  // Expose API
  global.SpellEffects = { register, play };
})(window);


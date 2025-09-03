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

  function getTileCenterFallback($tile) {
    if (!$tile || !$tile.length || !$tile[0] || !$tile[0].getBoundingClientRect) return null;
    const rect = $tile[0].getBoundingClientRect();
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const tileSize = ($('.tiles-container').data('tile-size') || 64);
    return { x: rect.left + scrollLeft + tileSize/2, y: rect.top + scrollTop + tileSize/2 };
  }

  function centerOfEntity(entityId) {
    const $tile = $(`.tile[data-coords-id="${entityId}"]`);
    let pt = getTileCenterFromEngine($tile);
    if (!pt) pt = getTileCenterFallback($tile);
    return pt;
  }

  function ensureArray(val){ return Array.isArray(val) ? val : (val != null ? [val] : []); }

  function createOverlay(z = 1101) {
    const overlay = document.createElement('canvas');
    overlay.width = window.innerWidth;
    overlay.height = window.innerHeight;
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.zIndex = String(z);
    overlay.style.pointerEvents = 'none';
    document.body.appendChild(overlay);
    const ctx = overlay.getContext('2d');
    return {
      overlay,
      ctx,
      destroy: () => { try { document.body.removeChild(overlay); } catch (e) {} }
    };
  }

  function play(spellKey, payload) {
    const raw = (spellKey || (payload && (payload.spell || payload.label)) || '').toString().toLowerCase();
    const key = raw.replace(/[\s-]+/g, '_');
    const fn = REGISTRY[key] || REGISTRY['__default__'];
    try {
      return fn(payload);
    } catch (e) {
      console.warn('SpellEffects.play failed', key, e);
      return Promise.resolve();
    }
  }

  // ---------- Implementations ----------
  // Default: soft buff halo on targets
  register('__default__', function(payload){
    return new Promise((resolve) => {
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!centers.length) return resolve();
      const { overlay, ctx, destroy } = createOverlay(1101);
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const start = performance.now();
      const duration = 900;
      const color = [180, 220, 255];
      const loop = (now) => {
        const t = Math.min(1, (now - start)/duration);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        centers.forEach((p) => {
          const ease = 1 - Math.pow(1 - t, 3);
          const radius = (tileSize*0.35) + ease*(tileSize*1.0);
          const alpha = (1 - ease) * 0.85;
          ctx.save();
          ctx.globalCompositeOperation = 'screen';
          ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI*2);
          ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha.toFixed(3)})`;
          ctx.lineWidth = Math.max(1, 6 - 4*ease);
          ctx.shadowColor = `rgba(${color[0]},${color[1]},${color[2]},${(0.6*alpha).toFixed(3)})`;
          ctx.shadowBlur = 12 * (1 - ease) + 4;
          ctx.stroke();
          ctx.restore();
        });
        if (t < 1) requestAnimationFrame(loop); else { destroy(); resolve(); }
      };
      requestAnimationFrame(loop);
    });
  });

  // Bless: golden beam + two pulsing halos + sparkles
  register('bless', function(payload){
    return new Promise((resolve) => {
      const targets = ensureArray(payload && payload.target);
      const centers = targets.map(centerOfEntity).filter(Boolean);
      if (!centers.length) return resolve();
      const src = payload && payload.source ? centerOfEntity(payload.source) : null;
      const { overlay, ctx, destroy } = createOverlay(1101);
      const tileSize = ($('.tiles-container').data('tile-size') || 64);
      const start = performance.now();
      const duration = 1200;
      const color = [255, 215, 0];
      const frame = (now) => {
        const t = Math.min(1, (now - start)/duration);
        ctx.clearRect(0,0,overlay.width, overlay.height);
        if (src) {
          const beamPhase = Math.max(0, 1 - (now - start)/300);
          if (beamPhase > 0) {
            ctx.save();
            ctx.globalCompositeOperation = 'screen';
            ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${(0.35+0.45*beamPhase).toFixed(3)})`;
            ctx.lineWidth = 6*beamPhase + 2;
            centers.forEach((p)=>{ ctx.beginPath(); ctx.moveTo(src.x, src.y); ctx.lineTo(p.x, p.y); ctx.stroke(); });
            ctx.restore();
          }
        }
        centers.forEach((p, idx) => {
          for (let k=0;k<2;k++){
            const localT = Math.min(1, Math.max(0, (now - start - k*160)/duration));
            if (localT <= 0 || localT > 1) continue;
            const ease = 1 - Math.pow(1 - localT, 3);
            const radius = (tileSize*0.35) + ease*(tileSize*1.4);
            const alpha = (1 - ease) * 0.85;
            ctx.save();
            ctx.globalCompositeOperation = 'screen';
            ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI*2);
            ctx.strokeStyle = `rgba(${color[0]},${color[1]},${color[2]},${alpha.toFixed(3)})`;
            ctx.lineWidth = Math.max(1, 6 - 4*ease);
            ctx.shadowColor = `rgba(${color[0]},${color[1]},${color[2]},${(0.6*alpha).toFixed(3)})`;
            ctx.shadowBlur = 18*(1-ease) + 6; ctx.stroke(); ctx.restore();
            const sparkCount = 4;
            for (let s=0;s<sparkCount;s++){
              const ang = (idx*1.7 + k*0.9 + s) * 1.9 + now*0.002;
              const r = radius * (0.7 + 0.25*Math.sin(now*0.006 + s));
              const sx = p.x + Math.cos(ang)*r, sy = p.y + Math.sin(ang)*r;
              const spAlpha = alpha*0.9;
              ctx.save(); ctx.globalCompositeOperation = 'screen';
              ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${spAlpha.toFixed(3)})`;
              ctx.beginPath(); ctx.arc(sx, sy, 2 + 1.5*(1-ease), 0, Math.PI*2); ctx.fill(); ctx.restore();
            }
          }
        });
        if (t < 1) requestAnimationFrame(frame); else { destroy(); resolve(); }
      };
      requestAnimationFrame(frame);
    });
  });

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
        const ctrl = { x: (src.x + target.x)/2 + (Math.random() < 0.5 ? -1 : 1) * 60, y: (src.y + target.y)/2 - 80 };
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

  // Expose API
  global.SpellEffects = { register, play };
})(window);

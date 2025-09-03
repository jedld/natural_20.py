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
    const key = (spellKey || payload && (payload.spell || payload.label) || '').toString().toLowerCase();
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

  // Expose API
  global.SpellEffects = { register, play };
})(window);

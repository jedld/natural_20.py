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

  // Expose API
  global.SpellEffects = { register, play };
})(window);


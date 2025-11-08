(function(){
  // Persistent per-entity status effects (Bless, Shield, Mage Armor)
  // Applies lightweight CSS-based overlays to entity tiles based on DOM-declared effects
  // Effects appear while the status icon exists on the tile and are removed when it disappears.

  function injectStylesOnce(){
    if (document.getElementById('persistent-effects-style')) return;
    const css = `
    @keyframes pe-pulse {
      0% { transform: scale(0.95); opacity: 0.35; }
      100% { transform: scale(1.05); opacity: 0.15; }
    }
    @keyframes pe-rotate {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    @keyframes pe-breathe {
      0% { transform: scale(0.98); opacity: 0.18; }
      100% { transform: scale(1.02); opacity: 0.10; }
    }
    @keyframes pe-ominous {
      0% { transform: scale(0.96); opacity: 0.40; }
      100% { transform: scale(1.04); opacity: 0.18; }
    }
    @keyframes pe-shimmer {
      0% { box-shadow: 0 0 8px rgba(120,190,255,0.25), inset 0 0 6px rgba(120,190,255,0.2); opacity: 0.25; }
      50% { box-shadow: 0 0 14px rgba(140,210,255,0.40), inset 0 0 10px rgba(140,210,255,0.30); opacity: 0.40; }
      100% { box-shadow: 0 0 8px rgba(120,190,255,0.25), inset 0 0 6px rgba(120,190,255,0.2); opacity: 0.25; }
    }
    @keyframes pe-frost-pulse {
      0% { transform: scale(0.95); opacity: 0.48; }
      100% { transform: scale(1.05); opacity: 0.26; }
    }
    @keyframes pe-frost-rotate {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(-360deg); }
    }
    @keyframes pe-frost-shards {
      0% { transform: rotate(0deg) scale(0.96); opacity: 0.52; }
      100% { transform: rotate(360deg) scale(1.04); opacity: 0.34; }
    }
    .pe-container {
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
      pointer-events: none;
  z-index: 1001; /* above brightness (999) and entity (2), below popovers (10001) */
    }
    .pe-overlay {
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
      pointer-events: none;
  z-index: 1002; /* above brightness (999) and icons (1000), below popovers (10001) */
      mix-blend-mode: screen;
    }
    .pe-bless {
  border-radius: 50%;
  /* Stronger, brighter halo */
  background: radial-gradient(circle, rgba(255, 235, 150, 0.70) 0%, rgba(255, 220, 90, 0.38) 58%, rgba(255, 215, 0, 0.18) 70%, rgba(255, 215, 0, 0.0) 78%);
  /* Subtle outline */
  border: 2px solid rgba(255, 215, 0, 0.35);
  /* Outer + inner glow */
  box-shadow: 0 0 18px rgba(255, 215, 0, 0.55), 0 0 8px rgba(255, 235, 180, 0.45), inset 0 0 14px rgba(255, 215, 0, 0.35);
  animation: pe-pulse 1.6s ease-in-out infinite alternate;
    }
    .pe-shield {
      border-radius: 50% / 65%;
      border: 2px solid rgba(64, 156, 255, 0.45);
      box-shadow: 0 0 14px rgba(64,156,255,0.35), inset 0 0 10px rgba(64,156,255,0.25);
      backdrop-filter: blur(0.2px);
      animation: pe-rotate 3s linear infinite;
    }
    .pe-mage-armor {
      border-radius: 50%;
      background: radial-gradient(circle at 50% 50%, rgba(120, 190, 255, 0.30) 0%, rgba(120, 190, 255, 0.14) 55%, rgba(120, 190, 255, 0.0) 72%);
      box-shadow: 0 0 14px rgba(120,190,255,0.35), inset 0 0 10px rgba(120,190,255,0.28);
      animation: pe-breathe 1.8s ease-in-out infinite alternate;
    }
    .pe-mage-armor-ring {
      border-radius: 50%;
      border: 2px solid rgba(140, 210, 255, 0.45);
      mix-blend-mode: screen;
      animation: pe-shimmer 1.4s ease-in-out infinite;
    }
    .pe-bane {
      border-radius: 50%;
      background: radial-gradient(circle, rgba(220, 50, 50, 0.55) 0%, rgba(160, 30, 30, 0.34) 55%, rgba(120, 20, 20, 0.0) 78%);
      box-shadow: 0 0 18px rgba(160, 30, 30, 0.55), inset 0 0 12px rgba(170, 30, 30, 0.38);
      animation: pe-ominous 1.6s ease-in-out infinite alternate;
    }
    .pe-bane-ring {
      border-radius: 50%;
      border: 2px dashed rgba(220, 70, 70, 0.55);
      box-shadow: 0 0 12px rgba(200, 60, 60, 0.45), inset 0 0 6px rgba(200, 60, 60, 0.30);
      mix-blend-mode: screen;
      animation: pe-rotate 3.8s linear infinite;
    }
    .pe-armor-agathys {
      border-radius: 50%;
      background: radial-gradient(circle, rgba(220, 245, 255, 0.62) 0%, rgba(170, 220, 250, 0.36) 42%, rgba(90, 140, 200, 0.14) 70%, rgba(40, 80, 120, 0.0) 84%);
      box-shadow: 0 0 24px rgba(170, 220, 255, 0.48), inset 0 0 18px rgba(210, 245, 255, 0.36);
      animation: pe-frost-pulse 1.8s ease-in-out infinite alternate;
    }
    .pe-armor-agathys-ring {
      border-radius: 50%;
      border: 2px solid rgba(170, 225, 255, 0.55);
      box-shadow: 0 0 16px rgba(150, 210, 255, 0.36), inset 0 0 8px rgba(210, 245, 255, 0.26);
      mix-blend-mode: screen;
      animation: pe-frost-rotate 6s linear infinite;
    }
    .pe-armor-agathys-shards {
      border-radius: 50%;
      background: repeating-conic-gradient(rgba(220, 250, 255, 0.66) 0deg 12deg, rgba(120, 180, 220, 0.1) 12deg 24deg);
      opacity: 0.42;
      mix-blend-mode: screen;
      animation: pe-frost-shards 8s linear infinite;
    }
    `;
    const style = document.createElement('style');
    style.id = 'persistent-effects-style';
    style.type = 'text/css';
    style.appendChild(document.createTextNode(css));
    document.head.appendChild(style);
  }

  // Normalize text to effect key
  function keyOf(name){
    if (!name) return '';
  let k = String(name).toLowerCase().trim();
  // Remove surrounding brackets or ids like "3" or "#3"
  k = k.replace(/^[#\[]?([a-z0-9_\-\s]+)[]]?$/, '$1');
  // Common synonyms and formatting
  k = k.replace(/\s+/g, '_');
  if (k === 'blessed') k = 'bless';
  if (k === 'shield_of_faith' || k === 'shield-of-faith' || k === 'shield faith') k = 'shield';
  if (k === 'mage_armor' || k === 'mage-armour') k = 'mage_armor';
  return k;
  }

  // Which effect names we render persistently and their CSS class
  const EFFECT_CLASS = {
    bless: 'pe-bless',
    shield: 'pe-shield',
    mage_armor: 'pe-mage-armor',
    armor_of_agathys: 'pe-armor-agathys',
    bane: 'pe-bane',
    resistance: 'pe-bless',
  };

  function createOverlayFor($tile, effKey){
    const cls = EFFECT_CLASS[effKey];
    if (!cls) return null;

    // Determine base size from tile size, adjust if the entity image is larger
    const tileSize = $('.tiles-container').data('tile-size') || 64;
    const $img = $tile.find('.entity img.npc, .entity img.flying-entity').first();
    let w = tileSize, h = tileSize, offsetTop = 0, offsetLeft = 0;
    if ($img && $img.length) {
      const iw = parseInt($img.css('width'), 10) || $img.width() || tileSize;
      const ih = parseInt($img.css('height'), 10) || $img.height() || tileSize;
      w = Math.max(tileSize, iw);
      h = Math.max(tileSize, ih);
    }

    // Ensure a container inside tile to position overlay relative to tile origin
    let $container = $tile.find('.pe-container');
    if (!$container.length) {
      $container = $('<div class="pe-container">').css({ position: 'absolute', top: 0, left: 0, width: w, height: h, pointerEvents: 'none', zIndex: 40 });
      $tile.append($container);
    } else {
      $container.css({ width: w, height: h });
    }

    // Base layer
    const $overlay = $('<div class="pe-overlay">').addClass(cls).attr('data-pe', effKey).css({ width: w, height: h, top: 0, left: 0 });
    $container.append($overlay);

    // Optional extra layer(s) for certain effects to increase visibility
    if (effKey === 'mage_armor') {
      const $ring = $('<div class="pe-overlay pe-mage-armor-ring">').attr('data-pe', effKey).css({ width: w, height: h, top: 0, left: 0 });
      $container.append($ring);
    }
    if (effKey === 'armor_of_agathys') {
      const $ring = $('<div class="pe-overlay pe-armor-agathys-ring">').attr('data-pe', effKey).css({ width: w, height: h, top: 0, left: 0 });
      const $shards = $('<div class="pe-overlay pe-armor-agathys-shards">').attr('data-pe', effKey).css({ width: w, height: h, top: 0, left: 0 });
      $container.append($ring);
      $container.append($shards);
    }
    if (effKey === 'bane') {
      const $ring = $('<div class="pe-overlay pe-bane-ring">').attr('data-pe', effKey).css({ width: w, height: h, top: 0, left: 0 });
      $container.append($ring);
    }

    return $overlay;
  }

  function removeOverlay($tile, effKey){
    $tile.find('.pe-overlay[data-pe="'+effKey+'"]').remove();
    // Clean empty container
    const $c = $tile.find('.pe-container');
    if ($c.length && $c.children('.pe-overlay').length === 0) $c.remove();
  }

  function desiredEffectsForTile($tile){
    // Collect effect names from effect icons
    const list = [];
    $tile.find('.effect img').each(function(){
      const alt = $(this).attr('alt') || $(this).data('tooltip');
      const key = keyOf(alt);
      if (EFFECT_CLASS[key]) list.push(key);
    });
    return Array.from(new Set(list));
  }

  function presentEffectsOnTile($tile){
    return $tile.find('.pe-overlay').map(function(){ return $(this).attr('data-pe'); }).get();
  }

  function syncTile($tile){
    // If tile is under fog, remove any overlays and skip
    if ($tile.find('.fog-of-war').length) {
      $tile.find('.pe-overlay').remove();
      $tile.find('.pe-container').remove();
      return;
    }
    const want = desiredEffectsForTile($tile);
    const have = presentEffectsOnTile($tile);

    // Add missing
    for (let i=0;i<want.length;i++) {
      if (have.indexOf(want[i]) === -1) createOverlayFor($tile, want[i]);
    }
    // Remove extras
    for (let j=0;j<have.length;j++) {
      if (want.indexOf(have[j]) === -1) removeOverlay($tile, have[j]);
    }
  }

  const PersistentEffects = {
    applyAll: function(){
      try { injectStylesOnce(); } catch(e){}
      $('.tile[data-coords-id]').each(function(){ syncTile($(this)); });
    },
    // Optionally expose a per-entity update
    updateForEntity: function(entityId){
      try { injectStylesOnce(); } catch(e){}
      const $tile = $('.tile[data-coords-id="'+entityId+'"]');
      if ($tile.length) syncTile($tile);
    },
    startObserver: function(){
      try { injectStylesOnce(); } catch(e){}
      if (window.__peObserver) return;
      const queue = new Set();
      let scheduled = false;
      const flush = () => {
        scheduled = false;
        queue.forEach(id => {
          const $tile = $('.tile[data-coords-id="'+id+'"]');
          if ($tile.length) syncTile($tile);
        });
        queue.clear();
      };
      const obs = new MutationObserver(muts => {
        for (const m of muts) {
          // If any .effect or its children mutate, resync that tile
          let el = m.target;
          while (el && el !== document) {
            if (el.classList && el.classList.contains('tile')) {
              const id = el.getAttribute('data-coords-id');
              if (id) queue.add(id);
              break;
            }
            el = el.parentNode;
          }
        }
        if (!scheduled) {
          scheduled = true;
          requestAnimationFrame(flush);
        }
      });
      obs.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['src','alt','data-tooltip'], characterData: false });
      window.__peObserver = obs;
    }
  };

  window.PersistentEffects = PersistentEffects;

  // Observe changes in tiles/effects to auto-apply overlays without full refresh
  (function setupObserverOnce(){
    if (window.__peObserverInstalled) return;
    window.__peObserverInstalled = true;
    try { injectStylesOnce(); } catch(e){}

    const container = document.querySelector('.tiles-container') || document.body;
    if (!container || !window.MutationObserver) return;

    const pending = new Map();
    function scheduleSync(tileEl){
      if (!tileEl) return;
      const id = tileEl.getAttribute('data-coords-id') || Math.random().toString(36);
      if (pending.has(id)) return;
      pending.set(id, setTimeout(function(){
        pending.delete(id);
        try { syncTile($(tileEl)); } catch(e){}
      }, 50));
    }

    const observer = new MutationObserver(function(mutations){
      for (let i=0;i<mutations.length;i++){
        const m = mutations[i];
        // Attribute changes on effect icons or fog-of-war visibility
        if (m.type === 'attributes'){
          if (m.target && (m.attributeName === 'alt' || m.attributeName === 'data-tooltip' || m.attributeName === 'class')){
            const tileEl = m.target.closest && m.target.closest('.tile');
            if (tileEl) scheduleSync(tileEl);
          }
          continue;
        }
        // Child list changes under tiles (icons added/removed, fog toggled)
        if (m.type === 'childList'){
          const added = Array.from(m.addedNodes || []);
          const removed = Array.from(m.removedNodes || []);
          const candidates = added.concat(removed);
          for (let n=0;n<candidates.length;n++){
            const node = candidates[n];
            if (!node || !node.closest) continue;
            const tileEl = node.closest('.tile');
            if (tileEl) scheduleSync(tileEl);
          }
        }
      }
    });

    observer.observe(container, { subtree: true, childList: true, attributes: true, attributeFilter: ['alt', 'data-tooltip', 'class'] });
  })();

  // Initial apply on DOM ready
  if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function(){ try { PersistentEffects.applyAll(); PersistentEffects.startObserver(); } catch(e){} });
  } else {
  try { PersistentEffects.applyAll(); PersistentEffects.startObserver(); } catch(e){}
  }
})();

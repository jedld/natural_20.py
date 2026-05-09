/* Character builder: image source picker (prebuilt / upload) and Token Stamp tool.
 *
 * - Profile image: choose from prebuilt gallery, upload, or none. The chosen
 *   source is reflected in either the file input (#profile_image) or the
 *   hidden #profile_prebuilt field; one of them gets cleared so the server
 *   only sees the active source.
 * - Token image: "Auto from portrait" (default), Token Stamp tool, or upload.
 *   The Token Stamp tool produces a 256x256 circular PNG data URL placed in
 *   #token_image_data and matches the style of the existing token_*.png files.
 */
(function(){
  const PROFILE_TABS = document.querySelector('.img-source-tabs[data-target="profile"]');
  const TOKEN_TABS   = document.querySelector('.img-source-tabs[data-target="token"]');
  const PROFILE_PANELS = document.querySelectorAll('.img-source-panel'); // shared selector, filtered by parent

  function panelsFor(target){
    const tabs = document.querySelector(`.img-source-tabs[data-target="${target}"]`);
    if(!tabs) return [];
    const group = tabs.parentElement;
    return group ? Array.from(group.querySelectorAll('.img-source-panel')) : [];
  }

  function activateTab(target, mode){
    const tabs = document.querySelector(`.img-source-tabs[data-target="${target}"]`);
    if(!tabs) return;
    tabs.querySelectorAll('.source-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === mode);
    });
    panelsFor(target).forEach(p => {
      p.style.display = (p.dataset.mode === mode) ? '' : 'none';
    });
  }

  function bindTabs(target, onChange){
    const tabs = document.querySelector(`.img-source-tabs[data-target="${target}"]`);
    if(!tabs) return;
    tabs.addEventListener('click', function(e){
      const btn = e.target.closest('.source-btn');
      if(!btn) return;
      const mode = btn.dataset.mode;
      activateTab(target, mode);
      if(onChange) onChange(mode);
    });
  }

  // ---------------- Profile portrait ----------------
  const profilePreview = document.getElementById('profile-preview-box');
  const profileFile    = document.getElementById('profile_image');
  const profilePrebuilt= document.getElementById('profile_prebuilt');
  const tokenPreview   = document.getElementById('token-preview-box');
  let currentPortraitUrl = null; // for the token stamper "use current portrait"

  function setPreview(box, url, emptyLabel){
    if(!box) return;
    if(url){
      box.innerHTML = `<img src="${url}" alt="">`;
    } else {
      box.innerHTML = `<div class="preview-empty">${emptyLabel || 'None'}</div>`;
    }
  }

  function clearProfile(){
    if(profileFile) profileFile.value = '';
    if(profilePrebuilt) profilePrebuilt.value = '';
    currentPortraitUrl = null;
    setPreview(profilePreview, null, 'No portrait selected');
    refreshAutoTokenPreview();
  }

  bindTabs('profile', function(mode){
    if(mode === 'none'){
      clearProfile();
    } else if(mode === 'prebuilt'){
      if(profileFile) profileFile.value = '';
    } else if(mode === 'upload'){
      if(profilePrebuilt) profilePrebuilt.value = '';
    }
  });

  // Load prebuilt gallery
  function loadPrebuiltGallery(){
    const grid = document.getElementById('profile-prebuilt-grid');
    if(!grid) return;
    fetch('/character_builder/prebuilt_images', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        const images = (data && data.images) || [];
        if(!images.length){
          grid.innerHTML = '<div class="helper">No prebuilt images available.</div>';
          return;
        }
        grid.innerHTML = '';
        images.forEach(img => {
          const tile = document.createElement('div');
          tile.className = 'prebuilt-tile';
          tile.dataset.name = img.name;
          tile.dataset.url = img.url;
          tile.title = img.name;
          tile.innerHTML = `<img src="${img.url}" alt="${img.name}">`;
          tile.addEventListener('click', function(){
            grid.querySelectorAll('.prebuilt-tile').forEach(t => t.classList.remove('selected'));
            tile.classList.add('selected');
            if(profilePrebuilt) profilePrebuilt.value = img.name;
            if(profileFile) profileFile.value = '';
            currentPortraitUrl = img.url;
            setPreview(profilePreview, img.url);
            refreshAutoTokenPreview();
          });
          grid.appendChild(tile);
        });
      })
      .catch(err => {
        grid.innerHTML = '<div class="helper">Failed to load prebuilt images.</div>';
        console.error('prebuilt images:', err);
      });
  }

  if(profileFile){
    profileFile.addEventListener('change', function(){
      const f = profileFile.files && profileFile.files[0];
      if(!f){ setPreview(profilePreview, null, 'No portrait selected'); currentPortraitUrl = null; refreshAutoTokenPreview(); return; }
      if(profilePrebuilt) profilePrebuilt.value = '';
      const url = URL.createObjectURL(f);
      currentPortraitUrl = url;
      setPreview(profilePreview, url);
      refreshAutoTokenPreview();
    });
  }

  // ---------------- Token image ----------------
  const tokenFile     = document.getElementById('token_image');
  const tokenDataUrl  = document.getElementById('token_image_data');

  function activeTokenMode(){
    const btn = TOKEN_TABS && TOKEN_TABS.querySelector('.source-btn.active');
    return btn ? btn.dataset.mode : 'auto';
  }

  function refreshAutoTokenPreview(){
    if(activeTokenMode() !== 'auto') return;
    if(!currentPortraitUrl){ setPreview(tokenPreview, null, 'Auto'); return; }
    // Render a quick circular preview client-side. Server still re-generates
    // the canonical token at save time using the same algorithm.
    renderCircularPreview(currentPortraitUrl, 96).then(dataUrl => {
      setPreview(tokenPreview, dataUrl);
    }).catch(()=> setPreview(tokenPreview, null, 'Auto'));
  }

  bindTabs('token', function(mode){
    if(mode === 'auto'){
      if(tokenFile) tokenFile.value = '';
      if(tokenDataUrl) tokenDataUrl.value = '';
      refreshAutoTokenPreview();
    } else if(mode === 'upload'){
      if(tokenDataUrl) tokenDataUrl.value = '';
      // Preview cleared until user picks a file
      const f = tokenFile && tokenFile.files && tokenFile.files[0];
      if(f){ setPreview(tokenPreview, URL.createObjectURL(f)); }
      else { setPreview(tokenPreview, null, 'Choose a file'); }
    } else if(mode === 'stamp'){
      if(tokenFile) tokenFile.value = '';
      if(tokenDataUrl && tokenDataUrl.value){
        setPreview(tokenPreview, tokenDataUrl.value);
      } else {
        setPreview(tokenPreview, null, 'Open the stamp tool');
      }
    }
  });

  if(tokenFile){
    tokenFile.addEventListener('change', function(){
      const f = tokenFile.files && tokenFile.files[0];
      if(!f){ setPreview(tokenPreview, null, 'Choose a file'); return; }
      setPreview(tokenPreview, URL.createObjectURL(f));
    });
  }

  function renderCircularPreview(url, size){
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = function(){
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.beginPath();
        ctx.arc(size/2, size/2, size/2, 0, Math.PI*2);
        ctx.closePath();
        ctx.clip();
        // center-crop square
        const side = Math.min(img.width, img.height);
        const sx = (img.width - side)/2;
        const sy = (img.height - side)/2;
        ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
        ctx.restore();
        try { resolve(canvas.toDataURL('image/png')); } catch(e){ reject(e); }
      };
      img.onerror = reject;
      img.src = url;
    });
  }

  // ---------------- Token Stamp tool ----------------
  const stampCanvas = document.getElementById('stamp-canvas');
  const stampZoom   = document.getElementById('stamp-zoom');
  const stampBorder = document.getElementById('stamp-border');
  const stampBorderColor = document.getElementById('stamp-border-color');
  const stampFile   = document.getElementById('stamp-file');
  const stampUsePortraitBtn = document.getElementById('stamp-use-portrait');
  const stampSave   = document.getElementById('stamp-save');
  const openStamp   = document.getElementById('open-token-stamp');
  const STAMP_SIZE  = 320;       // displayed canvas size (also storage size)
  const OUTPUT_SIZE = 256;       // exported token size
  const stampState = {
    img: null,
    scale: 1,
    minScale: 0.1,
    offsetX: STAMP_SIZE/2,
    offsetY: STAMP_SIZE/2,
    dragging: false,
    lastX: 0, lastY: 0
  };

  function drawStamp(){
    if(!stampCanvas) return;
    const ctx = stampCanvas.getContext('2d');
    ctx.clearRect(0, 0, STAMP_SIZE, STAMP_SIZE);
    // background checker hint
    ctx.fillStyle = '#111';
    ctx.fillRect(0, 0, STAMP_SIZE, STAMP_SIZE);

    if(stampState.img){
      const w = stampState.img.width * stampState.scale;
      const h = stampState.img.height * stampState.scale;
      ctx.drawImage(stampState.img, stampState.offsetX - w/2, stampState.offsetY - h/2, w, h);
    }

    // dim outside circle
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.beginPath();
    ctx.rect(0, 0, STAMP_SIZE, STAMP_SIZE);
    ctx.arc(STAMP_SIZE/2, STAMP_SIZE/2, STAMP_SIZE/2, 0, Math.PI*2, true);
    ctx.closePath();
    ctx.fill('evenodd');
    ctx.restore();

    // border ring preview
    const borderPx = parseInt(stampBorder.value || '0', 10);
    if(borderPx > 0){
      ctx.save();
      ctx.lineWidth = borderPx;
      ctx.strokeStyle = stampBorderColor.value || '#4a2f19';
      ctx.beginPath();
      ctx.arc(STAMP_SIZE/2, STAMP_SIZE/2, STAMP_SIZE/2 - borderPx/2, 0, Math.PI*2);
      ctx.stroke();
      ctx.restore();
    } else {
      ctx.save();
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(212,175,55,0.6)';
      ctx.beginPath();
      ctx.arc(STAMP_SIZE/2, STAMP_SIZE/2, STAMP_SIZE/2 - 0.5, 0, Math.PI*2);
      ctx.stroke();
      ctx.restore();
    }
  }

  function fitImageToCanvas(img){
    const fillScale = Math.max(STAMP_SIZE / img.width, STAMP_SIZE / img.height);
    stampState.minScale = fillScale * 0.5;
    stampState.scale = fillScale;
    stampState.offsetX = STAMP_SIZE/2;
    stampState.offsetY = STAMP_SIZE/2;
    if(stampZoom){
      stampZoom.min = String(stampState.minScale.toFixed(3));
      stampZoom.max = String((fillScale * 4).toFixed(3));
      stampZoom.step = '0.01';
      stampZoom.value = String(stampState.scale);
    }
    drawStamp();
  }

  function loadStampImage(url){
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function(){
      stampState.img = img;
      fitImageToCanvas(img);
    };
    img.onerror = function(){ alert('Could not load image for token stamp'); };
    img.src = url;
  }

  if(stampZoom){
    stampZoom.addEventListener('input', function(){
      stampState.scale = parseFloat(stampZoom.value) || 1;
      drawStamp();
    });
  }
  if(stampBorder){ stampBorder.addEventListener('input', drawStamp); }
  if(stampBorderColor){ stampBorderColor.addEventListener('input', drawStamp); }

  if(stampCanvas){
    const onPointerDown = function(e){
      stampState.dragging = true;
      stampCanvas.classList.add('dragging');
      const p = pointerPos(e);
      stampState.lastX = p.x; stampState.lastY = p.y;
      e.preventDefault();
    };
    const onPointerMove = function(e){
      if(!stampState.dragging) return;
      const p = pointerPos(e);
      stampState.offsetX += (p.x - stampState.lastX);
      stampState.offsetY += (p.y - stampState.lastY);
      stampState.lastX = p.x; stampState.lastY = p.y;
      drawStamp();
      e.preventDefault();
    };
    const onPointerUp = function(){
      stampState.dragging = false;
      stampCanvas.classList.remove('dragging');
    };
    function pointerPos(e){
      const rect = stampCanvas.getBoundingClientRect();
      const t = (e.touches && e.touches[0]) || e;
      return { x: t.clientX - rect.left, y: t.clientY - rect.top };
    }
    stampCanvas.addEventListener('mousedown', onPointerDown);
    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('mouseup', onPointerUp);
    stampCanvas.addEventListener('touchstart', onPointerDown, { passive:false });
    stampCanvas.addEventListener('touchmove', onPointerMove, { passive:false });
    stampCanvas.addEventListener('touchend', onPointerUp);
    // wheel-zoom
    stampCanvas.addEventListener('wheel', function(e){
      if(!stampState.img) return;
      const factor = (e.deltaY < 0) ? 1.08 : (1/1.08);
      const next = Math.max(stampState.minScale, Math.min(stampState.scale * factor, stampState.minScale * 20));
      stampState.scale = next;
      if(stampZoom) stampZoom.value = String(next);
      drawStamp();
      e.preventDefault();
    }, { passive:false });
  }

  if(stampFile){
    stampFile.addEventListener('change', function(){
      const f = stampFile.files && stampFile.files[0];
      if(!f) return;
      loadStampImage(URL.createObjectURL(f));
    });
  }
  if(stampUsePortraitBtn){
    stampUsePortraitBtn.addEventListener('click', function(){
      if(!currentPortraitUrl){
        alert('Pick a portrait first (prebuilt or upload).');
        return;
      }
      loadStampImage(currentPortraitUrl);
    });
  }
  if(openStamp){
    openStamp.addEventListener('click', function(){
      $('#tokenStampModal').modal('show');
      // If nothing loaded yet but we have a portrait, prefill
      if(!stampState.img && currentPortraitUrl){
        loadStampImage(currentPortraitUrl);
      } else {
        // redraw to show empty circle frame
        setTimeout(drawStamp, 50);
      }
    });
  }

  if(stampSave){
    stampSave.addEventListener('click', function(){
      if(!stampState.img){ alert('Load an image first.'); return; }
      // Build the export canvas at OUTPUT_SIZE with circular alpha + ring.
      const out = document.createElement('canvas');
      out.width = OUTPUT_SIZE; out.height = OUTPUT_SIZE;
      const octx = out.getContext('2d');
      octx.save();
      octx.beginPath();
      octx.arc(OUTPUT_SIZE/2, OUTPUT_SIZE/2, OUTPUT_SIZE/2, 0, Math.PI*2);
      octx.closePath();
      octx.clip();
      const ratio = OUTPUT_SIZE / STAMP_SIZE;
      const w = stampState.img.width * stampState.scale * ratio;
      const h = stampState.img.height * stampState.scale * ratio;
      const cx = stampState.offsetX * ratio;
      const cy = stampState.offsetY * ratio;
      octx.drawImage(stampState.img, cx - w/2, cy - h/2, w, h);
      octx.restore();

      const borderPx = parseInt(stampBorder.value || '0', 10);
      if(borderPx > 0){
        octx.save();
        const scaledBorder = Math.max(1, Math.round(borderPx * ratio));
        octx.lineWidth = scaledBorder;
        octx.strokeStyle = stampBorderColor.value || '#4a2f19';
        octx.beginPath();
        octx.arc(OUTPUT_SIZE/2, OUTPUT_SIZE/2, OUTPUT_SIZE/2 - scaledBorder/2, 0, Math.PI*2);
        octx.stroke();
        octx.restore();
      }

      const dataUrl = out.toDataURL('image/png');
      if(tokenDataUrl) tokenDataUrl.value = dataUrl;
      setPreview(tokenPreview, dataUrl);
      $('#tokenStampModal').modal('hide');
    });
  }

  // Bootstrap: load gallery if logged-in / endpoint accessible.
  loadPrebuiltGallery();
})();

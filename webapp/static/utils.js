const Utils = {
  // function definitions go here
  manhattanDistance: function (sourceX, sourceY, destX, destY) {
    return Math.abs(sourceX - destX) + Math.abs(sourceY - destY);
  },
  euclideanDistance: function (sourceX, sourceY, destX, destY) {
    return Math.sqrt(Math.pow(sourceX - destX, 2) + Math.pow(sourceY - destY, 2));
  },
  toggleNoteOverlay: function (btn) {
    const overlay = btn.nextElementSibling;
    overlay.style.display = (overlay.style.display === "none" || overlay.style.display === "") ? "block" : "none";
  },
  refreshPortraits: function () {
    Utils.ajaxGet('/refresh-portraits', {}, (data) => {
      $('#floating-entity-portraits').html(data);
    });
  },
  switchMap: function (mapId, canvas, first_callback = null) {
    ajaxPost('/switch_map', { map: mapId }, (data) => {
      console.log('Map selection successful:', data);
      $('#mapModal').modal('hide');
      // The new map will have a different .tiles-container bounding rect and
      // possibly a different tile size, so any cached pathfinding origin or
      // memoized /path responses from the previous map are stale.
      try { if (typeof clearMovePathCache === 'function') clearMovePathCache(); } catch (e) { }
      Utils.invalidateMovementGridCache();
      Utils.refreshTileSet(callback = () => {
        Utils.updateMapDisplay(data, canvas);
        // Re-invalidate after DOM swap so the next draw recomputes from the
        // freshly mounted tiles container.
        Utils.invalidateMovementGridCache();
        // Refresh portraits when map is switched
        Utils.refreshPortraits();
        // Show narration if present
        Utils.checkNarration(data);
        // Apply map-default effects if provided and DM has no active override
        try {
          if (!data.dm_active && typeof Effects !== 'undefined') {
            var arr = Array.isArray(data.map_default_effects) ? data.map_default_effects.slice() : [];
            if (!arr.length && data.map_default_effect) arr = [data.map_default_effect];
            if (arr.length && Effects.applyEffect) {
              // Ensure stacking by default
              arr = arr.map(function (p) { try { if (p && typeof p === 'object' && p.exclusive === undefined) p.exclusive = false; } catch (e) { } return p; });
              Effects.applyEffect(arr);
            } else if (Effects.stopAll) {
              // No default and no DM override: ensure any prior effect is removed
              Effects.stopAll();
            }
          }
        } catch (e) { console.warn('Failed to apply map default effect', e); }
        // Ask server to (re)send effects after map switch in case client missed anything
        try { if (typeof socket !== 'undefined' && socket && socket.emit) socket.emit('request_effects'); } catch (e) { }
        if (first_callback) first_callback();
      })
    });
  },


  refreshTileSet: function (is_setup = false, pov = false, x = 0, y = 0, entity_uid = null, callback = null) {
    if (!window.tileUpdateSequence) {
      window.tileUpdateSequence = 0;
    }


    const currentSequence = ++window.tileUpdateSequence;
    // Capture any active map toasts so we can restore them after refresh
    const _activeToasts = Utils.collectAllToasts ? Utils.collectAllToasts() : [];

    // Check if optimization is disabled (for debugging)
    if (window.disableTileOptimization || is_setup) {
      Utils.ajaxGet('/update', { is_setup, pov, x, y, entity_uid }, (data) => {
        // Only apply if this is still the most recent request
        if (currentSequence >= (window.lastAppliedSequence || 0)) {
          lastMovedEntityBeforeRefresh = null;
          $('.tiles-container').html(data);
          window.lastAppliedSequence = currentSequence;
          // Refresh portraits when tiles are refreshed
          Utils.refreshPortraits();
          // Re-apply persistent status overlays (bless/shield/mage armor)
          try { if (window.PersistentEffects && window.PersistentEffects.applyAll) window.PersistentEffects.applyAll(); } catch (e) { }
          // Ensure popover menus stay on top after full refresh
          Utils.ensurePopoverMenusOnTop();
          // Restore map toasts after full refresh
          try { if (Utils.restoreAllToasts) Utils.restoreAllToasts(_activeToasts); } catch (e) { console.warn('Failed to restore map toasts after full refresh', e); }
        } else {
          console.log('Ignoring out-of-order tile update (full): ' + currentSequence + ' < ' + window.lastAppliedSequence);
        }
        if (callback) callback();
        try { if (window.PersistentEffects && PersistentEffects.applyAll) PersistentEffects.applyAll(); } catch (e) { }
      });
      return;
    }

    // For regular updates, use optimized approach
    Utils.ajaxGet('/update', { is_setup, pov, x, y, entity_uid }, (data) => {
      lastMovedEntityBeforeRefresh = null;

      // Get current map from body attribute
      const currentMap = $('body').attr('data-current-map');

      // Parse the HTML to extract individual tiles and check for map info
      const $newContent = $('<div>').html(data);
      const $newTiles = $newContent.find('.tile');

      // Check if this update is for the current map
      if ($newTiles.length > 0) {
        // Look for the map metadata div
        const $mapMetadata = $newContent.find('.map-metadata[data-map-name]').first();

        if ($mapMetadata.length > 0) {
          const updateMapName = $mapMetadata.data('map-name');

          if (updateMapName && currentMap && updateMapName !== currentMap) {
            console.warn('Ignoring tile update - for map "' + updateMapName + '" but current map is "' + currentMap + '"');
            if (callback) callback();
            return;
          }
        }

        // Additional coordinate-based validation
        const existingTilesCount = $('.tiles-container .tile').length;

        if (existingTilesCount > 0) {
          // Sample a few tiles to check if they belong to the current map context
          let mapMismatch = false;
          $newTiles.slice(0, 3).each(function () {
            const $newTile = $(this);
            const x = $newTile.data('coords-x');
            const y = $newTile.data('coords-y');

            if (x !== undefined && y !== undefined) {
              const $existingTile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
              // If this coordinate should exist but doesn't, we might have a map mismatch
              if ($existingTile.length === 0) {
                const tilesContainer = $('.tiles-container');
                const containerWidth = tilesContainer.data('width') || 0;
                const containerHeight = tilesContainer.data('height') || 0;
                // Check if coordinates are way outside expected bounds
                if (x < -10 || y < -10 || x > containerWidth + 10 || y > containerHeight + 10) {
                  mapMismatch = true;
                  return false; // Break out of each loop
                }
              }
            }
          });

          if (mapMismatch) {
            console.warn('Ignoring tile update - coordinates appear to be for a different map');
            if (callback) callback();
            return;
          }
        }
      }

      // Update only changed tiles
      if (currentSequence >= (window.lastAppliedSequence || 0)) {
        Utils.updateChangedTilesOptimized($newTiles);
        window.lastAppliedSequence = currentSequence;

        // Refresh portraits when tiles are refreshed
        Utils.refreshPortraits();
        // Re-apply persistent status overlays (bless/shield/mage armor)
        try { if (window.PersistentEffects && window.PersistentEffects.applyAll) window.PersistentEffects.applyAll(); } catch (e) { }

        // Ensure popover menus stay on top after optimized updates
        Utils.ensurePopoverMenusOnTop();

        // Re-apply persistent effects overlays after partial updates
        try { if (window.PersistentEffects && PersistentEffects.applyAll) PersistentEffects.applyAll(); } catch (e) { }

        // Add entity delete buttons for DMs (if function exists)
        if (typeof window.addEntityDeleteButtons === 'function') {
          setTimeout(window.addEntityDeleteButtons, 100);
        }
        // For safety, if optimized path caused a full container update elsewhere, attempt toast restore too
        try { if (Utils.restoreAllToasts) Utils.restoreAllToasts(_activeToasts, true /*skipExisting*/); } catch (e) { }
      } else {
        console.log('Ignoring out-of-order tile update (optimized): ' + currentSequence + ' < ' + window.lastAppliedSequence);
      }

      if (callback) callback();
    });
  },

  // Optimized tile update that preserves interactive elements
  updateChangedTilesOptimized: function ($newTiles) {
    let tilesUpdated = 0;
    let tilesPreserved = 0;

    $newTiles.each(function () {
      const $newTile = $(this);
      const x = $newTile.data('coords-x');
      const y = $newTile.data('coords-y');

      if (x === undefined || y === undefined) return;

      const $existingTile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');

      if ($existingTile.length === 0) {
        // New tile - just add it
        $('.tiles-container').append($newTile);
        tilesUpdated++;
        return;
      }

      // Check if tile has actually changed by comparing key attributes
      if (Utils.tilesAreEqual($existingTile, $newTile)) {
        tilesPreserved++;
        return; // No change needed - preserve interactive elements
      }

      // Capture any active map toasts on this tile so we can restore them after replacement
      const toastsOnTile = Utils.collectToastsFromTile ? Utils.collectToastsFromTile($existingTile) : [];

      // Debug logging for fog of war changes
      const oldFog = $existingTile.find('.fog-of-war').length;
      const newFog = $newTile.find('.fog-of-war').length;
      if (oldFog !== newFog && console && console.log) {
        console.log('Fog of war change detected at (' + x + ',' + y + '): ' + oldFog + ' -> ' + newFog);
      }

      // Preserve any active interactive elements
      const preservedElements = Utils.preserveInteractiveElements($existingTile);

      // Replace the tile
      $existingTile.replaceWith($newTile);
      tilesUpdated++;

      // Restore preserved elements
      Utils.restoreInteractiveElements($('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]'), preservedElements);

      // Restore any map toasts captured for this tile with their remaining time
      if (toastsOnTile && toastsOnTile.length) {
        try {
          const $tileAfter = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
          Utils.mountToastsOnTile($tileAfter, toastsOnTile);
        } catch (e) { console.warn('Failed to restore map toasts on tile', x, y, e); }
      }
    });

    // Debug logging to show optimization effectiveness
    if (console && console.log) {
      console.log('Tile update optimization: ' + tilesUpdated + ' updated, ' + tilesPreserved + ' preserved');
    }

    // Re-initialize die roll components on updated tiles
    if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
    if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }

    // Ensure popover menus stay on top after tile updates
    Utils.ensurePopoverMenusOnTop();
    $('.tile .entity, .tile .npc').css('visibility', ''); // Ensure entities are visible
  },

  // Compare tiles to see if they need updating
  tilesAreEqual: function ($tile1, $tile2) {
    // Compare key attributes that would indicate a meaningful change
    const attrs = ['data-coords-id', 'data-light', 'data-difficult', 'data-darkvision'];

    for (let attr of attrs) {
      if ($tile1.attr(attr) !== $tile2.attr(attr)) {
        return false;
      }
    }

    // Compare entity/NPC presence and identity robustly
    const $ents1 = $tile1.find('.entity, .npc');
    const $ents2 = $tile2.find('.entity, .npc');
    if ($ents1.length !== $ents2.length) {
      return false;
    }
    // When counts match, compare IDs (support multiple attribute variants)
    for (let i = 0; i < $ents1.length; i++) {
      const $e1 = $($ents1[i]);
      const $e2 = $($ents2[i]);
      const id1 = $e1.attr('data-entity-id') || $e1.attr('data-entity-uid') || $e1.attr('data-entityId') || $e1.attr('data-id') || '';
      const id2 = $e2.attr('data-entity-id') || $e2.attr('data-entity-uid') || $e2.attr('data-entityId') || $e2.attr('data-id') || '';
      if (id1 !== id2) {
        return false;
      }
      // Fallback: if no IDs available, compare basic HTML signature
      if (!id1 && !id2) {
        const sig1 = ($e1.prop('outerHTML') || '').replace(/\s+/g, ' ');
        const sig2 = ($e2.prop('outerHTML') || '').replace(/\s+/g, ' ');
        if (sig1 !== sig2) return false;
      }
    }

    // Compare health bar if present
    const health1 = $tile1.find('.health-bar').attr('style');
    const health2 = $tile2.find('.health-bar').attr('style');
    if (health1 !== health2) {
      return false;
    }

    // Compare nameplate
    const name1 = $tile1.find('.nameplate').text();
    const name2 = $tile2.find('.nameplate').text();
    if (name1 !== name2) {
      return false;
    }

    // Compare effects
    const effects1 = $tile1.find('.effect img').length;
    const effects2 = $tile2.find('.effect img').length;
    if (effects1 !== effects2) {
      return false;
    }

    // Compare conversation bubbles (but not the preserved interactive ones)
    const bubble1 = $tile1.find('.conversation-bubble .bubble-content').text();
    const bubble2 = $tile2.find('.conversation-bubble .bubble-content').text();
    if (bubble1 !== bubble2) {
      return false;
    }

    // Compare fog of war - this is critical for line of sight changes!
    const fog1 = $tile1.find('.fog-of-war').length;
    const fog2 = $tile2.find('.fog-of-war').length;
    if (fog1 !== fog2) {
      return false;
    }

    // Also compare fog of war styling if present (opacity, visibility changes)
    if (fog1 > 0 && fog2 > 0) {
      const fog1Style = $tile1.find('.fog-of-war').attr('style') || '';
      const fog2Style = $tile2.find('.fog-of-war').attr('style') || '';
      if (fog1Style !== fog2Style) {
        return false;
      }
    }

    // Compare brightness overlay for lighting changes
    const brightness1 = $tile1.find('.brightness-overlay').attr('style') || '';
    const brightness2 = $tile2.find('.brightness-overlay').attr('style') || '';
    if (brightness1 !== brightness2) {
      return false;
    }

    // Compare objects on the tile
    const objects1 = $tile1.find('.object-container').length;
    const objects2 = $tile2.find('.object-container').length;
    if (objects1 !== objects2) {
      return false;
    }

    // Compare ground items
    const items1 = $tile1.find('.item-container').length;
    const items2 = $tile2.find('.item-container').length;
    if (items1 !== items2) {
      return false;
    }

    // compare notes
    const notes1 = $tile1.find('.show-note-btn').length;
    const notes2 = $tile2.find('.show-note-btn').length;
    if (notes1 !== notes2) {
      return false;
    }

    // compare unread note state
    const unread1 = $tile1.find('.show-note-btn.unread').length;
    const unread2 = $tile2.find('.show-note-btn.unread').length;
    if (unread1 !== unread2) {
      return false;
    }

    // check if the dialog bubbles are the same
    const dialog1 = $tile1.find('.dialog-bubble').length;
    const dialog2 = $tile2.find('.dialog-bubble').length;
    if (dialog1 !== dialog2) {
      return false;
    }

    return true; // Tiles are effectively the same
  },

  // Preserve interactive elements that shouldn't be removed
  preserveInteractiveElements: function ($tile) {
    const preserved = {};

    // Preserve visible action menus
    const $actionMenus = $tile.find('.popover-menu:visible, .popover-menu-2:visible');
    if ($actionMenus.length > 0) {
      preserved.actionMenus = $actionMenus.clone(true);
    }

    // Preserve visible die roll components
    const $dieRolls = $tile.find('.die-roll-component:visible');
    if ($dieRolls.length > 0) {
      preserved.dieRolls = $dieRolls.clone(true);
    }

    // Preserve any other active interactive elements
    const $interactive = $tile.find('.target-selection:visible, .active-selection:visible');
    if ($interactive.length > 0) {
      preserved.interactive = $interactive.clone(true);
    }

    return preserved;
  },

  // Restore preserved interactive elements
  restoreInteractiveElements: function ($tile, preserved) {
    if (preserved.actionMenus) {
      // Remove any new action menus and replace with preserved ones
      $tile.find('.popover-menu, .popover-menu-2').remove();
      $tile.append(preserved.actionMenus);
    }

    if (preserved.dieRolls) {
      $tile.append(preserved.dieRolls);
    }

    if (preserved.interactive) {
      $tile.append(preserved.interactive);
    }

    // Ensure restored popover menus have correct z-index
    if (preserved.actionMenus && Utils.ensurePopoverMenusOnTop) {
      // Small delay to ensure DOM is updated
      setTimeout(function () {
        Utils.ensurePopoverMenusOnTop();
      }, 10);
    }
  },

  // --- Map Toast Preservation Helpers ---
  // Collect toasts for a single tile as array of { text, remainingMs }
  collectToastsFromTile: function ($tile) {
    const res = [];
    try {
      const now = Date.now();
      $tile.find('.map-toast').each(function () {
        const $t = $(this);
        const exp = parseInt($t.attr('data-toast-expiry')) || (now + 5000);
        const remaining = Math.max(0, exp - now);
        const text = $t.text();
        if (remaining > 50 && text) {
          res.push({ text: text, remainingMs: remaining });
        }
      });
    } catch (e) { }
    return res;
  },
  // Mount a list of toast data back onto a given tile
  mountToastsOnTile: function ($tile, toasts) {
    if (!$tile || !$tile.length || !Array.isArray(toasts)) return;
    const now = Date.now();
    toasts.forEach(function (t) {
      const dur = Math.max(0, parseInt(t.remainingMs) || 0);
      if (dur <= 50) return;
      try {
        const $toast = $('<div class="map-toast"></div>').text(t.text);
        $toast.css({ position: 'absolute', left: '50%', top: '-6px', transform: 'translate(-50%, -100%)' });
        $toast.attr('data-toast-expiry', now + dur);
        $tile.append($toast);
        setTimeout(function () { try { $toast.fadeOut(400, function () { $toast.remove(); }); } catch (_) { } }, dur);
      } catch (e) { /* noop */ }
    });
  },
  // Collect all active toasts across the map with their tile coords
  collectAllToasts: function () {
    const res = [];
    const now = Date.now();
    $('.map-toast').each(function () {
      const $t = $(this);
      const $tile = $t.closest('.tile');
      if (!$tile.length) return;
      const x = $tile.data('coords-x');
      const y = $tile.data('coords-y');
      const exp = parseInt($t.attr('data-toast-expiry')) || (now + 5000);
      const remaining = Math.max(0, exp - now);
      const text = $t.text();
      if (x !== undefined && y !== undefined && text && remaining > 50) {
        res.push({ x: x, y: y, text: text, remainingMs: remaining });
      }
    });
    return res;
  },
  // Restore captured toasts after a full or partial refresh
  restoreAllToasts: function (toasts, skipExisting) {
    if (!Array.isArray(toasts) || toasts.length === 0) return;
    toasts.forEach(function (t) {
      const selector = '.tile[data-coords-x="' + t.x + '"][data-coords-y="' + t.y + '"]';
      const $tile = $(selector);
      if (!$tile.length) return;
      if (skipExisting) {
        // Avoid duplicating if a toast with same text is already present
        const exists = $tile.find('.map-toast').filter(function () { return $(this).text() === t.text; }).length > 0;
        if (exists) return;
      }
      Utils.mountToastsOnTile($tile, [{ text: t.text, remainingMs: t.remainingMs }]);
    });
  },

  ajaxGet: function (url, data, onSuccess) {
    $.ajax({
      url,
      type: 'GET',
      data,
      success: onSuccess,
      error: (jqXHR, textStatus, errorThrown) => {
        console.error('Error with GET ' + url + ':', textStatus, errorThrown);
      }
    });
  },
  rollable: function (entity_id, roll_str, advantage, disadvantage, description) {
    json_data = JSON.stringify({
      id: entity_id,
      roll: roll_str,
      description: description,
      advantage: advantage,
      disadvantage: disadvantage
    });

    $.ajax({
      type: 'POST',
      url: '/manual_roll',
      contentType: 'application/json',
      data: json_data,
      success: function (data) {
        var result = data.roll_result;
        var breakdown = data.roll_explaination;
        console.log(data);
        const $toast = $('<div>')
          .addClass('toast-message')
          .text('Roll completed: ' + description + ' ' + breakdown + "= " + result);
        // Append to toast container, create one if it doesn't exist
        if (!$('.toast-container').length) {
          $('body').append('<div class="toast-container"></div>');
        }
        $('.toast-container').append($toast);
        setTimeout(() => $toast.fadeOut(() => $toast.remove()), 10000);
      }
    }
    );
  },
  draggable: function (container_selector) {
    $(function () {
      var isDragging = false;
      var lastX, lastY;

      $(container_selector + ' .header').mousedown(function (e) {
        isDragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
      });

      $(document).mousemove(function (e) {
        if (isDragging) {
          var deltaX = e.clientX - lastX;
          var deltaY = e.clientY - lastY;
          var offset = $(container_selector).offset();
          $(container_selector).offset({
            top: offset.top + deltaY,
            left: offset.left + deltaX
          });
          lastX = e.clientX;
          lastY = e.clientY;
        }
      }).mouseup(function () {
        isDragging = false;
      });
    });
  },
  autoInsertDieRoll: function () {
    $('.auto-die-roll').each(function () {
      var $container = $(this);
      // Only insert if not already present
      if ($container.find('.die-roll-component').length === 0) {
        // Read entity id from the container's data attribute (data-entity)
        var entityId = $container.data('entity');
        var compact = $container.data('compact');
        var description = $container.data('description');
        var rollStr = $container.data('roll');
        if (!rollStr) {
          rollStr = $container.text();
        }
        var safeDescription = $('<div>').text(description).html();

        if (compact) {
          $container.append('<button class="die-roll-toggle">Roll</button><div class="die-roll-component" style="display: none;"><span class="rollable-die" data-roll="' + rollStr + '" data-entity="' + entityId + '" data-description="' + safeDescription + '">Roll!</span><div class="roll-switch"><button type="button" class="roll-mode" data-mode="normal" label="Normal">&nbsp;</button><button type="button" class="roll-mode" data-mode="advantage" label="Advantage">+</button><button type="button" class="roll-mode" data-mode="disadvantage" label="Disadvantage">-</button></div></div>');
          $container.find('.die-roll-toggle').click(function () {
            $container.find('.die-roll-component').toggle();
          });
        } else {
          $container.append('<div class="die-roll-component"><span class="rollable-die" data-roll="' + rollStr + '" data-entity="' + entityId + '" data-description="' + safeDescription + '">Roll!</span><div class="roll-switch"><button type="button" class="roll-mode" data-mode="normal">&nbsp;</button><button type="button" class="roll-mode" data-mode="advantage">+</button><button type="button" class="roll-mode" data-mode="disadvantage">-</button></div></div>');
        }
      }
    });
  },
  initDieRollComponent: function () {
    $('.die-roll-component').each(function () {
      var $component = $(this);
      // set the first button as active by default
      $component.find('.roll-mode[data-mode="normal"]').addClass('active');

      // toggle selected mode
      $component.find('.roll-mode').click(function () {
        $component.find('.roll-mode').removeClass('active');
        $(this).addClass('active');
      });

      // bind click event on the die roll text
      $component.find('.rollable-die').click(function () {
        var rollStr = $(this).attr('data-roll');
        var entityId = $(this).attr('data-entity');
        var description = $(this).data('description');
        var mode = $component.find('.roll-mode.active').attr('data-mode');
        var advantage = (mode === "advantage");
        var disadvantage = (mode === "disadvantage");
        Utils.rollable(entityId, rollStr, advantage, disadvantage, description);
      });
    });
  },
  drawMovementPath: function (ctx, movePath, available_cost, placeable, terrainInfo, options) {
    // Coalesce all redraws onto a single requestAnimationFrame; the latest
    // pending args win. This avoids forced layouts and synchronous canvas
    // work on every mousemove across browsers.
    Utils._movementPendingArgs = [ctx, movePath, available_cost, placeable, terrainInfo, options];
    if (Utils._movementRafId) return;
    if (typeof requestAnimationFrame !== 'function') {
      const args = Utils._movementPendingArgs;
      Utils._movementPendingArgs = null;
      Utils._doDrawMovementPath.apply(Utils, args);
      return;
    }
    Utils._movementRafId = requestAnimationFrame(function () {
      const args = Utils._movementPendingArgs;
      Utils._movementPendingArgs = null;
      Utils._movementRafId = null;
      if (args) Utils._doDrawMovementPath.apply(Utils, args);
    });
  },

  // Invalidate the cached tile-grid origin (call on resize/scroll/map switch).
  invalidateMovementGridCache: function () {
    Utils._movementGridOrigin = null;
    Utils._movementLastSignature = null;
  },

  // Compute and cache the tile grid origin in viewport coords. Tiles are laid
  // out at (x+1)*tile_size, (y+1)*tile_size relative to .tiles-container
  // (see templates/map.html), so we only need ONE getBoundingClientRect on
  // the container per draw burst.
  _getMovementGridOrigin: function () {
    if (Utils._movementGridOrigin) return Utils._movementGridOrigin;
    const container = document.querySelector('.tiles-container');
    if (!container) return null;
    const tileSize =
      Number(container.getAttribute('data-tile-size')) ||
      ($('.tile').height() || 50);
    const rect = container.getBoundingClientRect();
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft || 0;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
    Utils._movementGridOrigin = {
      // Origin is the top-left of tile (0,0) in document coords.
      // Tile (x,y) sits at (x+1)*tileSize, (y+1)*tileSize within container.
      ox: rect.left + scrollLeft + tileSize,
      oy: rect.top + scrollTop + tileSize,
      tile: tileSize,
    };
    return Utils._movementGridOrigin;
  },

  // Internal implementation of movement path drawing (no throttling)
  _doDrawMovementPath: function (ctx, movePath, available_cost, placeable, terrainInfo, options) {
    const suppressArrow = options && options.suppressArrow === true;
    const grid = Utils._getMovementGridOrigin();
    if (!grid) return;
    const tile_size = grid.tile;
    const half = tile_size / 2;

    // Skip work when the request is identical to the previously rendered one.
    // This is hot — same-tile mouseover events fire constantly.
    let signature = '';
    try {
      const lastIdx = movePath.length - 1;
      const last = lastIdx >= 0 ? movePath[lastIdx] : null;
      const first = movePath[0] || null;
      signature = (movePath.length) + '|' +
        (first ? first[0] + ',' + first[1] : '') + '|' +
        (last ? last[0] + ',' + last[1] : '') + '|' +
        available_cost + '|' + (placeable ? 1 : 0) + '|' + (suppressArrow ? 1 : 0);
    } catch (e) { signature = ''; }
    if (signature && Utils._movementLastSignature === signature) {
      return;
    }
    Utils._movementLastSignature = signature;

    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    if (!movePath || movePath.length === 0) return;

    // Build terrain lookup once.
    const terrainLookup = {};
    if (terrainInfo) {
      for (let i = 0; i < terrainInfo.length; i++) {
        const info = terrainInfo[i];
        terrainLookup[info.x + ',' + info.y] = !!info.difficult;
      }
    }

    // Compute all centers in O(n) with no DOM reads.
    const centers = new Array(movePath.length);
    for (let i = 0; i < movePath.length; i++) {
      const c = movePath[i];
      centers[i] = { x: grid.ox + c[0] * tile_size + half, y: grid.oy + c[1] * tile_size + half };
    }

    // Group segments by dashed/solid and stroke each group with ONE path.
    // Far fewer ctx state changes than per-segment beginPath/stroke.
    ctx.strokeStyle = 'green';
    ctx.lineWidth = 5;

    const flush = (dashed, segments) => {
      if (segments.length === 0) return;
      ctx.setLineDash(dashed ? [10, 10] : []);
      ctx.beginPath();
      for (let i = 0; i < segments.length; i++) {
        const s = segments[i];
        ctx.moveTo(s.fx, s.fy);
        ctx.lineTo(s.tx, s.ty);
      }
      ctx.stroke();
    };

    const solidSegs = [];
    const dashedSegs = [];
    for (let i = 1; i < movePath.length; i++) {
      const a = centers[i - 1];
      const b = centers[i];
      const x = movePath[i][0], y = movePath[i][1];
      const seg = { fx: a.x, fy: a.y, tx: b.x, ty: b.y };
      if (terrainLookup[x + ',' + y]) dashedSegs.push(seg);
      else solidSegs.push(seg);
    }
    flush(false, solidSegs);
    flush(true, dashedSegs);

    // Arrow + cost at the end.
    if (!suppressArrow) {
      const lastIdx = movePath.length - 1;
      const end = centers[lastIdx];
      const prev = lastIdx > 0 ? centers[lastIdx - 1] : end;
      const angle = (lastIdx > 0) ? Math.atan2(end.y - prev.y, end.x - prev.x) : 0;
      const arrowSize = 10;

      ctx.setLineDash([]);
      ctx.beginPath();
      if (placeable) {
        ctx.moveTo(end.x - arrowSize * Math.cos(angle - Math.PI / 6), end.y - arrowSize * Math.sin(angle - Math.PI / 6));
        ctx.lineTo(end.x, end.y);
        ctx.lineTo(end.x - arrowSize * Math.cos(angle + Math.PI / 6), end.y - arrowSize * Math.sin(angle + Math.PI / 6));
      } else {
        ctx.moveTo(end.x - arrowSize, end.y - arrowSize);
        ctx.lineTo(end.x + arrowSize, end.y + arrowSize);
        ctx.moveTo(end.x + arrowSize, end.y - arrowSize);
        ctx.lineTo(end.x - arrowSize, end.y + arrowSize);
      }
      ctx.stroke();

      ctx.font = '20px Arial';
      ctx.fillStyle = 'green';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(available_cost) + 'ft', end.x, end.y + half);
    }

    ctx.setLineDash([]);
  },
  toggleBubble: function (bubble) {
    bubble.classList.toggle('minimized');
  },
  dismissBubble: function (bubble) {
    bubble.style.display = 'none';
  },
  showNoteModal: function (btn) {
    const noteContent = btn.nextElementSibling.innerHTML;
    const name = btn.getAttribute('data-name');
    const label = btn.getAttribute('data-label');
    const noteId = btn.getAttribute('data-note-id');
    const title = label || name || 'Notes';

    $('#noteModalTitle').text(title);
    $('#noteModalContent').html(noteContent);
    $('#noteModal').show();

    // Mark as read
    if (noteId && btn.classList.contains('unread')) {
      btn.classList.remove('unread');
      fetch('/mark_note_read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note_id: noteId })
      }).catch(function () {});
    }
  },
  closeNoteModal: function () {
    $('#noteModal').hide();
  },

  // Ensure popover menus always stay on top of other elements
  ensurePopoverMenusOnTop: function () {
    $('.popover-menu:visible, .popover-menu-2:visible').each(function () {
      const $menu = $(this);
      // Force the z-index to be very high to stay above tiles, fog of war, etc.
      $menu.css('z-index', '10001');

      // Also ensure the parent tile doesn't interfere
      const $parentTile = $menu.closest('.tile');
      if ($parentTile.length > 0) {
        // Save original z-index if it exists
        if (!$parentTile.data('original-z-index')) {
          $parentTile.data('original-z-index', $parentTile.css('z-index') || 'auto');
        }
        // Set tile z-index to be just below the menu
        $parentTile.css('z-index', '10000');
      }
    });

    // Debug log when fixing z-index issues
    const visibleMenus = $('.popover-menu:visible, .popover-menu-2:visible').length;
    if (visibleMenus > 0 && console && console.log) {
      console.log('Ensured ' + visibleMenus + ' popover menus stay on top');
    }
  },

  // Utility function to close all interactive UI elements when switching characters
  closeAllInteractiveElements: function () {
    // Close any open action bars/menus
    $(".popover-menu, .popover-menu-2").hide();
    if (typeof window.closeCenterActionBar === 'function') {
      window.closeCenterActionBar();
    } else {
      $('#centerActionBar').hide();
    }

    // Close target selection modal if open
    $('#targetSelectionModal').modal('hide');

    // Hide any other floating UI elements
    $(".add-to-target").hide();
    $('#multi-target-confirm-bar').hide();

    // Clear any highlighted tiles or selections
    $(".highlighted").removeClass("highlighted");
    $(".target-selection, .active-selection").hide();

    // Hide any visible die roll components that might be open
    $(".die-roll-component:visible").hide();

    // Clear any canvas drawings (movement paths, targeting lines, etc.)
    if (typeof globalCanvas !== 'undefined' && globalCanvas && typeof globalCtx !== 'undefined' && globalCtx) {
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
    }

    // Reset all interactive modes if variables are defined
    if (typeof targetMode !== 'undefined') targetMode = false;
    if (typeof multiTargetMode !== 'undefined') multiTargetMode = false;
    if (typeof moveMode !== 'undefined') moveMode = false;
    if (typeof coneMode !== 'undefined') coneMode = false;

    console.log('Closed all interactive elements for character switch');
  },

  updateMapDisplay: function (data, canvas) {
    const tile_size = $('.tiles-container').data('tile-size');
    const $imageContainer = $("#main-map-area .image-container");

    // Update image container size
    $imageContainer.css({
      height: data.height + 'px',
    });

    // Update image container position with consistent offset handling
    const imageOffset = data.image_offset_px || [0, 0];

    // Update tiles container (align with processMapEvent math)
    // Also update data attributes used elsewhere for bounds/validation
    const $tilesContainer = $("#main-map-area .tiles-container");
    $tilesContainer
      .css({
        position: 'absolute',
        top: '-' + tile_size + 'px',
        left: '-' + tile_size + 'px',
        width: data.width + 'px',
        height: data.height + 'px',
      })
      .data({ width: data.width, height: data.height });

    // Keep the same sign convention used when initially loading the map
    $("#tiles-area").css({
      top: (-tile_size + imageOffset[1]) + 'px',
      left: (-tile_size + imageOffset[0]) + 'px',
    });
    $('.image-container').css({
      height: data.height + 'px',
      top: (imageOffset[1] + tile_size) + 'px',
      left: (imageOffset[0] + tile_size) + 'px'
    });

    // Do NOT resize or reposition the global overlay canvas here.
    // It's created as a full-viewport fixed canvas in createGlobalCanvas().
    // Changing its size/position during POV switches caused visual artifacts.
    if (canvas && canvas.getContext) {
      try {
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      } catch (e) { /* noop */ }
    }

    // Update background - handle both img and video elements
    const bgSrc = data.background;
    const isVideo = bgSrc && (bgSrc.endsWith('.mp4') || bgSrc.endsWith('.webm'));
    const $existingImg = $imageContainer.find('img.background-image, img').first();
    const $existingVideo = $imageContainer.find('video').first();

    if (isVideo) {
      // New background is video - remove existing img if present, add/update video
      if ($existingImg.length) {
        $existingImg.remove();
      }
      if ($existingVideo.length) {
        // Update existing video source
        $existingVideo.find('source').attr('src', bgSrc);
        $existingVideo[0].load();
        $existingVideo[0].play().catch(() => {});
      } else {
        // Create new video element (insert before tiles-container)
        const $video = $('<video autoplay loop muted playsinline></video>')
          .css({ width: data.width + 'px', height: 'inherit', objectFit: 'cover', objectPosition: 'top' })
          .append($('<source>').attr('src', bgSrc).attr('type', 'video/mp4'));
        $imageContainer.find('.tiles-container').before($video);
        $video[0].play().catch(() => {});
      }
    } else {
      // New background is image - remove existing video if present, add/update img
      if ($existingVideo.length) {
        $existingVideo.remove();
      }
      if ($existingImg.length) {
        // Update existing image
        $existingImg.attr('src', bgSrc).css({
          width: data.width + 'px',
          objectFit: 'cover',
          objectPosition: 'top',
        });
      } else {
        // Create new img element (insert before tiles-container)
        const $img = $('<img class="background-image">')
          .attr('src', bgSrc)
          .css({ width: data.width + 'px', objectFit: 'cover', objectPosition: 'top' });
        $imageContainer.find('.tiles-container').before($img);
      }
    }

    // Update map name in body data
    $('body').attr('data-current-map', data.name);
  },

  /**
   * Show the DM narration overlay.
   * @param {object} narration  – narration config (on_enter.title, on_enter.text, on_enter.once)
   * @param {string} mapName    – current map name (used as localStorage key when once=true)
   */
  showNarration: function (narration, mapName) {
    if (!narration || !narration.on_enter) return;
    var entry = narration.on_enter;
    if (!entry.text) return;

    // "once" — skip if already shown for this map+title
    if (entry.once) {
      var key = 'narration_shown_' + (mapName || 'default') + '_' + (entry.title || '');
      try {
        if (localStorage.getItem(key)) return;
        localStorage.setItem(key, '1');
      } catch (e) { /* private browsing / quota — show anyway */ }
    }

    var $overlay = $('#narration-overlay');
    if (entry.title) {
      $('#narration-title').text(entry.title).show();
      $overlay.find('.narration-divider').show();
    } else {
      $('#narration-title').hide();
      $overlay.find('.narration-divider').hide();
    }
    $('#narration-text').text(entry.text);
    $overlay.css({ display: 'flex', animation: 'narration-fade-in 0.8s ease-out' });

    // Dismiss on click
    $overlay.off('click.narration').on('click.narration', function () {
      $overlay.css('animation', 'narration-fade-out 0.4s ease-in forwards');
      setTimeout(function () { $overlay.hide(); }, 400);
    });
  },

  /**
   * Check narration data from a /switch_map response and show if present.
   */
  checkNarration: function (data) {
    if (data && data.narration) {
      Utils.showNarration(data.narration, data.name);
    }
  }
};

$(document).ready(function () {
  // ...existing code...
  if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
  if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }

  // Show initial narration if the server provided one
  if (window._initialNarration) {
    var mapName = $('body').attr('data-current-map') || '';
    Utils.showNarration(window._initialNarration, mapName);
  }

  // Ensure popover menus stay on top when page loads
  if (Utils.ensurePopoverMenusOnTop) {
    Utils.ensurePopoverMenusOnTop();

    // Also set up a periodic check to maintain z-index (every 2 seconds)
    setInterval(function () {
      if ($('.popover-menu:visible, .popover-menu-2:visible').length > 0) {
        Utils.ensurePopoverMenusOnTop();
      }
    }, 2000);
  }
});

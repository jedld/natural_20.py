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
  refreshPortraits: function() {
    Utils.ajaxGet('/refresh-portraits', {}, (data) => {
      $('#floating-entity-portraits').html(data);
    });
  },
  switchMap: function (mapId, canvas, first_callback = null) {
    ajaxPost('/switch_map', { map: mapId }, (data) => {
      console.log('Map selection successful:', data);
      $('#mapModal').modal('hide');
      Utils.refreshTileSet(callback = () => {
        Utils.updateMapDisplay(data, canvas);
        // Refresh portraits when map is switched
        Utils.refreshPortraits();
        // Apply map-default effects if provided and DM has no active override
        try {
          if (!data.dm_active && typeof Effects !== 'undefined') {
            var arr = Array.isArray(data.map_default_effects) ? data.map_default_effects.slice() : [];
            if (!arr.length && data.map_default_effect) arr = [data.map_default_effect];
            if (arr.length && Effects.applyEffect) {
              arr = arr.map(function(p){ try{ if (p && typeof p === 'object' && p.exclusive === undefined) p.exclusive = false; }catch(e){} return p; });
              Effects.applyEffect(arr);
            } else if (Effects.stopAll) {
              Effects.stopAll();
            }
          }
        } catch (e) { console.warn('Failed to apply map default effect', e); }
  // Ask server to (re)send effects after map switch in case client missed anything
  try { if (typeof socket !== 'undefined' && socket && socket.emit) socket.emit('request_effects'); } catch (e) {}
        if (first_callback) first_callback();
      })
    });
  },
  
  // OPTIMIZED VERSION: Only update tiles that have changed
  refreshTileSet: function(is_setup = false, pov = false, x = 0, y = 0, entity_uid= null, callback = null)  {
    // For initial setup, use the full update to avoid complexity
    if (is_setup) {
      Utils.ajaxGet('/update', { is_setup, pov, x, y, entity_uid }, (data) => {
        lastMovedEntityBeforeRefresh = null;
        $('.tiles-container').html(data);
        // Refresh portraits when tiles are refreshed
        Utils.refreshPortraits();
        // Ensure popover menus stay on top after full refresh
        Utils.ensurePopoverMenusOnTop();
        if (callback) callback();
      });
      return;
    }
    
    // For regular updates, use optimized approach
    Utils.ajaxGet('/update', { is_setup, pov, x, y, entity_uid }, (data) => {
      lastMovedEntityBeforeRefresh = null;
      
      // Parse the HTML to extract individual tiles
      const $newContent = $('<div>').html(data);
      const $newTiles = $newContent.find('.tile');
      
      // Update only changed tiles
      Utils.updateChangedTilesOptimized($newTiles);
      
      // Refresh portraits when tiles are refreshed
      Utils.refreshPortraits();
      
      // Ensure popover menus stay on top after optimized updates
      Utils.ensurePopoverMenusOnTop();
      if (callback) callback();
    });
  },
  
  // Optimized tile update that preserves interactive elements
  updateChangedTilesOptimized: function($newTiles) {
    $newTiles.each(function() {
      const $newTile = $(this);
      const x = $newTile.data('coords-x');
      const y = $newTile.data('coords-y');
      
      if (x === undefined || y === undefined) return;
      
      const $existingTile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
      
      if ($existingTile.length === 0) {
        // New tile - just add it
        $('.tiles-container').append($newTile);
        return;
      }
      
      // Check if tile has actually changed by comparing key attributes
      if (Utils.tilesAreEqual($existingTile, $newTile)) {
        return; // No change needed
      }
      
      // Preserve any active interactive elements
      const preservedElements = Utils.preserveInteractiveElements($existingTile);
      
      // Replace the tile
      $existingTile.replaceWith($newTile);
      
      // Restore preserved elements
      Utils.restoreInteractiveElements($('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]'), preservedElements);
    });
    
    // Re-initialize die roll components on updated tiles
    if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
    if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }
    
    // Ensure popover menus stay on top after tile updates
    Utils.ensurePopoverMenusOnTop();
  },
  
  // Compare tiles to see if they need updating
  tilesAreEqual: function($tile1, $tile2) {
    // Compare key attributes that would indicate a meaningful change
    const attrs = ['data-coords-id', 'data-light', 'data-difficult'];
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
    for (let i = 0; i < $ents1.length; i++) {
      const $e1 = $($ents1[i]);
      const $e2 = $($ents2[i]);
      const id1 = $e1.attr('data-entity-id') || $e1.attr('data-entity-uid') || $e1.attr('data-entityId') || $e1.attr('data-id') || '';
      const id2 = $e2.attr('data-entity-id') || $e2.attr('data-entity-uid') || $e2.attr('data-entityId') || $e2.attr('data-id') || '';
      if (id1 !== id2) {
        return false;
      }
      if (!id1 && !id2) {
        const sig1 = ($e1.prop('outerHTML') || '').replace(/\s+/g, ' ');
        const sig2 = ($e2.prop('outerHTML') || '').replace(/\s+/g, ' ');
        if (sig1 !== sig2) return false;
      }
    }

    // Compare conversation bubbles quickly
    const bubble1 = $tile1.find('.conversation-bubble').text();
    const bubble2 = $tile2.find('.conversation-bubble').text();
    if (bubble1 !== bubble2) {
      return false;
    }
    return true; // Tiles are effectively the same
  },
  
  // Preserve interactive elements that shouldn't be removed
  preserveInteractiveElements: function($tile) {
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
  restoreInteractiveElements: function($tile, preserved) {
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
      setTimeout(function() {
        Utils.ensurePopoverMenusOnTop();
      }, 10);
    }
  },
  
  // Ensure popover menus always stay on top of other elements  
  ensurePopoverMenusOnTop: function() {
    $('.popover-menu:visible, .popover-menu-2:visible').each(function() {
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
      var breakdown =  data.roll_explaination;
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
  autoInsertDieRoll: function() {
    $('.auto-die-roll').each(function(){
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
          $container.find('.die-roll-toggle').click(function() {
            $container.find('.die-roll-component').toggle();
          });
        } else {
          $container.append('<div class="die-roll-component"><span class="rollable-die" data-roll="' + rollStr + '" data-entity="' + entityId + '" data-description="' + safeDescription + '">Roll!</span><div class="roll-switch"><button type="button" class="roll-mode" data-mode="normal">&nbsp;</button><button type="button" class="roll-mode" data-mode="advantage">+</button><button type="button" class="roll-mode" data-mode="disadvantage">-</button></div></div>');
        }
      }
    });
  },
  initDieRollComponent: function() {
    $('.die-roll-component').each(function() {
      var $component = $(this);
      // set the first button as active by default
      $component.find('.roll-mode[data-mode="normal"]').addClass('active');

      // toggle selected mode
      $component.find('.roll-mode').click(function() {
        $component.find('.roll-mode').removeClass('active');
        $(this).addClass('active');
      });

      // bind click event on the die roll text
      $component.find('.rollable-die').click(function() {
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
  drawMovementPath: function(ctx, movePath, available_cost, placeable, terrainInfo) {
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    
    // Create a lookup map for terrain information for faster access
    const terrainLookup = {};
    if (terrainInfo) {
      terrainInfo.forEach(info => {
        terrainLookup[info.x + ',' + info.y] = info.difficult;
      });
    }
    
    ctx.strokeStyle = "green";
    ctx.lineWidth = 5;
    let prevX, prevY;
    
    movePath.forEach((coords, index) => {
      const [x, y] = coords;
      const rect = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]')[0].getBoundingClientRect();
      const centerX = rect.left + rect.width / 2 + scrollLeft;
      const centerY = rect.top + rect.height / 2 + scrollTop;
      
      if (index === 0) {
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        prevX = centerX;
        prevY = centerY;
      } else {
        // Check if this segment goes through difficult terrain
        const isDifficult = terrainLookup[x + ',' + y] || false;
        
        // Start a new path segment with appropriate line style
        ctx.beginPath();
        ctx.moveTo(prevX, prevY);
        ctx.lineTo(centerX, centerY);
        
        // Set line dash for difficult terrain
        if (isDifficult) {
          ctx.setLineDash([10, 10]); // Dotted line: 10px dash, 10px gap
        } else {
          ctx.setLineDash([]); // Solid line
        }
        
        ctx.stroke();
        
        prevX = centerX;
        prevY = centerY;
      }
      
      // Draw arrow at the end
      if (index === movePath.length - 1) {
        ctx.beginPath();
        ctx.setLineDash([]); // Reset to solid line for arrow
        const arrowSize = 10;
        // Calculate angle from previous position to current position
        let angle;
        if (index > 0) {
          // Use the direction from the previous segment
          const prevCoords = movePath[index - 1];
          const [prevTileX, prevTileY] = prevCoords;
          const prevRect = $('.tile[data-coords-x="' + prevTileX + '"][data-coords-y="' + prevTileY + '"]')[0].getBoundingClientRect();
          const prevCenterX = prevRect.left + prevRect.width / 2 + scrollLeft;
          const prevCenterY = prevRect.top + prevRect.height / 2 + scrollTop;
          angle = Math.atan2(centerY - prevCenterY, centerX - prevCenterX);
        } else {
          // Fallback for single tile path (shouldn't happen in normal movement)
          angle = 0;
        }
        
        if (placeable) {
          ctx.moveTo(
            centerX - arrowSize * Math.cos(angle - Math.PI / 6),
            centerY - arrowSize * Math.sin(angle - Math.PI / 6),
          );
          ctx.lineTo(centerX, centerY);
          ctx.lineTo(
            centerX - arrowSize * Math.cos(angle + Math.PI / 6),
            centerY - arrowSize * Math.sin(angle + Math.PI / 6),
          );
        } else {
          ctx.moveTo(centerX - arrowSize, centerY - arrowSize);
          ctx.lineTo(centerX + arrowSize, centerY + arrowSize);
          ctx.moveTo(centerX + arrowSize, centerY - arrowSize);
          ctx.lineTo(centerX - arrowSize, centerY + arrowSize);
        }
        
        ctx.stroke();
        
        // Draw movement cost text
        ctx.font = "20px Arial";
        ctx.fillStyle = "green";
        ctx.fillText(
          available_cost + 'ft',
          centerX,
          centerY + $(".tile").height() / 2,
        );
      }
    });
    
    // Reset line dash to solid for future drawing operations
    ctx.setLineDash([]);
  },
  toggleBubble: function(bubble) {
    bubble.classList.toggle('minimized');
  },
  dismissBubble: function(bubble) {
    bubble.style.display = 'none';
  },
  showNoteModal: function(btn) {
    const noteContent = btn.nextElementSibling.innerHTML;
    const name = btn.getAttribute('data-name');
    const label = btn.getAttribute('data-label');
    const title = label || name || 'Notes';
    
    $('#noteModalTitle').text(title);
    $('#noteModalContent').html(noteContent);
    $('#noteModal').show();
  },
  closeNoteModal: function() {
    $('#noteModal').hide();
  },
  updateMapDisplay: function(data, canvas) {
    const tile_size = $('.tiles-container').data('tile-size');
    
    // Update image container and image
    $("#main-map-area .image-container img").css({
      width: data.width + 'px',
      objectFit: 'cover',
      objectPosition: 'top',
    });
    $("#main-map-area .image-container").css({
      height: data.height + 'px',
    });
    
    // Update image container position with consistent offset handling
    const imageOffset = data.image_offset_px || [0, 0];
    
    // Update tiles container and data attributes
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

    // Align offsets with initial map load behavior
    $("#tiles-area").css({
      top: (-tile_size + imageOffset[1]) + 'px',
      left: (-tile_size + imageOffset[0]) + 'px',
    });
    $('.image-container').css({
      height: data.height + 'px',
      top: (imageOffset[1] + tile_size) + 'px',
      left: (imageOffset[0] + tile_size) + 'px'
    });

    // Update image
    $(".image-container img").css({ width: data.width + 'px' });

    // Do not resize/position the global fixed overlay canvas here; just clear it if available
    if (canvas && canvas.getContext) {
      try {
        const ctx = canvas.getContext('2d');
        if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
      } catch (e) { /* noop */ }
    }

    // Update background and map name
    $("#main-map-area .image-container img").attr("src", data.background);
    $('body').attr('data-current-map', data.name);
  }
};

$(document).ready(function() {
  // ...existing code...
  if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
  if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }
  
  // Ensure popover menus stay on top when page loads
  if (Utils.ensurePopoverMenusOnTop) { 
    Utils.ensurePopoverMenusOnTop(); 
    
    // Also set up a periodic check to maintain z-index (every 2 seconds)
    setInterval(function() {
      if ($('.popover-menu:visible, .popover-menu-2:visible').length > 0) {
        Utils.ensurePopoverMenusOnTop();
      }
    }, 2000);
  }
});

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
    
    // Compare entity content
    const entity1 = $tile1.find('.entity').html();
    const entity2 = $tile2.find('.entity').html();
    
    if (entity1 !== entity2) {
      return false;
    }
    
    // Compare conversation bubbles
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
    
    // Update tiles container
    $("#main-map-area .tiles-container").css({
      position: 'absolute',
      top: '-' + tile_size + 'px',
      left: '-' + tile_size + 'px',
      width: data.width,
      height: data.height,
    });
    $("#tiles-area").css({
      top: -(tile_size + imageOffset[1]),
      left: -(tile_size + imageOffset[0]),
    });
    $('.image-container').css({
      height: data.height,
      top: imageOffset[1] + tile_size,
      left: imageOffset[0] + tile_size
    });

    // Update image
    $(".image-container img").css({ width: data.width });

    // Update canvas
    canvas.width = data.width + tile_size;
    canvas.height = data.height + tile_size;
    canvas.style.top = '-' + tile_size + 'px';
    canvas.style.left = '-' + tile_size + 'px';

    // Update background and map name
    $("#main-map-area .image-container img").attr("src", data.background);
    $('body').attr('data-current-map', data.name);
  }
};

$(document).ready(function() {
  // ...existing code...
  if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
  if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }
});

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
        $('#main-map-area .image-container img').attr('src', data.background);
        $('#main-map-area .image-container img').css({ width: `${data.width}px`, height: `${data.height}px` });
        $('#main-map-area .image-container').css({ width: `${data.width}px`, height: `${data.height}px` });
        $('#main-map-area .tiles-container').data({ width: data.width, height: data.height });
        $('.image-container').css({height: data.height});
        $('.image-container img').css({width: data.width});
        canvas.width = data.width + $('.tiles-container').data('tile-size');
        canvas.height = data.height + $('.tiles-container').data('tile-size');
        // Update the map name in the body data
        $('body').attr('data-current-map', mapId);
        // Refresh portraits when map is switched
        Utils.refreshPortraits();
        if (first_callback) first_callback();
      })
    });
  },
  refreshTileSet: function(is_setup = false, pov = false, x = 0, y = 0, entity_uid= null, callback = null)  {
    Utils.ajaxGet('/update', { is_setup, pov, x, y, entity_uid }, (data) => {
      lastMovedEntityBeforeRefresh = null;
      $('.tiles-container').html(data);
      // Refresh portraits when tiles are refreshed
      Utils.refreshPortraits();
      if (callback) callback();
    });
  },
  ajaxGet: function (url, data, onSuccess) {
    $.ajax({
      url,
      type: 'GET',
      data,
      success: onSuccess,
      error: (jqXHR, textStatus, errorThrown) => {
        console.error(`Error with GET ${url}:`, textStatus, errorThrown);
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
          $container.append(`
            <button class="die-roll-toggle">Roll</button>
            <div class="die-roll-component" style="display: none;">
              <span class="rollable-die" data-roll="${rollStr}" data-entity="${entityId}" data-description="${safeDescription}">Roll!</span>
              <div class="roll-switch">
                <button type="button" class="roll-mode" data-mode="normal" label="Normal">&nbsp;</button>
                <button type="button" class="roll-mode" data-mode="advantage" label="Advantage">+</button>
                <button type="button" class="roll-mode" data-mode="disadvantage" label="Disadvantage">-</button>
              </div>
            </div>
          `);
          $container.find('.die-roll-toggle').click(function() {
            $container.find('.die-roll-component').toggle();
          });
        } else {
          $container.append(`
            <div class="die-roll-component">
              <span class="rollable-die" data-roll="${rollStr}" data-entity="${entityId}" data-description="${safeDescription}">Roll!</span>
              <div class="roll-switch">
                <button type="button" class="roll-mode" data-mode="normal">&nbsp;</button>
                <button type="button" class="roll-mode" data-mode="advantage">+</button>
                <button type="button" class="roll-mode" data-mode="disadvantage">-</button>
              </div>
            </div>
          `);
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
  drawMovementPath: function(ctx, movePath, available_cost, placeable) {
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.beginPath();
    ctx.strokeStyle = "green";
    ctx.lineWidth = 5;
    let prevX, prevY;
    movePath.forEach((coords, index) => {
      const [x, y] = coords;
      const rect = $(`.tile[data-coords-x="${x}"][data-coords-y="${y}"]`)[0].getBoundingClientRect();
      const centerX = rect.left + rect.width / 2 + scrollLeft;
      const centerY = rect.top + rect.height / 2 + scrollTop;
      if (index === 0) {
        ctx.moveTo(centerX, centerY);
      } else {
        ctx.lineTo(centerX, centerY);
      }
      if (index === movePath.length - 1) {
        const arrowSize = 10;
        const angle = Math.atan2(centerY - prevY, centerX - prevX);
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
        ctx.font = "20px Arial";
        ctx.fillStyle = "green";
        ctx.fillText(
          `${available_cost}ft`,
          centerX,
          centerY + $(".tile").height() / 2,
        );
      }
      prevX = centerX;
      prevY = centerY;
    });
    ctx.stroke();
  }
};

$(document).ready(function() {
  // ...existing code...
  if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
  if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }
});

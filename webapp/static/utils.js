const Utils = {
  // function definitions go here
  manhattanDistance: function (sourceX, sourceY, destX, destY) {
    return Math.abs(sourceX - destX) + Math.abs(sourceY - destY);
  },
  euclideanDistance: function (sourceX, sourceY, destX, destY) {
    return Math.sqrt(Math.pow(sourceX - destX, 2) + Math.pow(sourceY - destY, 2));
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
    }, function (data) {
      result = data.roll_result
      breakdown =  data.roll_explaination
      console.log(data);
    const $toast = $('<div>')
      .addClass('toast-message')
      .text('Roll completed: ' + data.roll_result)
      .appendTo('body');
    setTimeout(() => $toast.fadeOut(() => $toast.remove()), 3000);
    });
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
        var description = $container.data('description');
        var rollStr = $container.text();
        var safeDescription = $('<div>').text(description).html();
        $container.append(
          '<div class="die-roll-component">' +
            '<span class="rollable-die" data-roll="'+rollStr+'" data-entity="' + entityId + '" data-description="' + safeDescription + '">Roll!</span>' +
            '<div class="roll-switch">' +
              '<button type="button" class="roll-mode" data-mode="normal">Normal</button>' +
              '<button type="button" class="roll-mode" data-mode="advantage">Adv</button>' +
              '<button type="button" class="roll-mode" data-mode="disadvantage">Dis</button>' +
            '</div>' +
          '</div>'
        );
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
  }
};

$(document).ready(function() {
  // ...existing code...
  if (Utils.autoInsertDieRoll) { Utils.autoInsertDieRoll(); }
  if (Utils.initDieRollComponent) { Utils.initDieRollComponent(); }
});

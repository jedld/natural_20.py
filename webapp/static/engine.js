let scale = 1;


function addToInitiative(btn, id, battle_entity_list) {
  const index = battle_entity_list.findIndex(entity => entity.id === id);
  var $this = $(btn);
    if (index === -1) {
      battle_entity_list.push({ id, group: 'a', name });
      $.ajax({
        url: '/add',
        type: 'GET',
        data: { id: id },
        success: function (data) {
          $('#turn-order').append(data);
          $this.find('i.glyphicon').removeClass('glyphicon-plus').addClass('glyphicon-minus');
          $this.css('background-color', 'red');
        },
        error: function (jqXHR, textStatus, errorThrown) {
          console.error('Error requesting turn order:', textStatus, errorThrown);
        }
      });
    } else {
      battle_entity_list.splice(index, 1);
      $this.find('i.glyphicon').removeClass('glyphicon-minus').addClass('glyphicon-plus');
      $this.css('background-color', 'green');

      // Remove name from turn order list
      const $turnOrderItem = $('.turn-order-item').filter(function () {
        return $(this).text() === name;
      });
      $turnOrderItem.remove();
    }
}

function drawLine(ctx, source, entity_uid, line_width=5, with_arrow=false, random_curve=false, strokeStyle='green', text=null) {
    // draw a green line from the source to the target
    var sourceTile = $('.tile[data-coords-x="' + source.x + '"][data-coords-y="' + source.y + '"]');
    var sourceTileRect = sourceTile[0].getBoundingClientRect();
    var tile = $('.tile[data-coords-id="' + entity_uid + '"]');
    var tileRect = tile[0].getBoundingClientRect();
    var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    ctx.beginPath();
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = line_width;
    var srcCenterX = sourceTileRect.left + sourceTileRect.width / 2 + scrollLeft;
    var srcCenterY = sourceTileRect.top + sourceTileRect.height / 2 + scrollTop;
    var centerX = tileRect.left + tileRect.width / 2 + scrollLeft;
    var centerY = tileRect.top + tileRect.height / 2 + scrollTop;
    
    if (random_curve) {
      var angle = Math.random() * (90 - 20) + 20; // Random angle between 10 and 30 degrees
      var radian = angle * (Math.PI / 180); // Convert angle to radians
      var controlX = (srcCenterX + centerX) / 2 + Math.cos(radian) * (centerY - srcCenterY) / 2;
      var controlY = (srcCenterY + centerY) / 2 + Math.sin(radian) * (centerY - srcCenterY) / 2;
      ctx.moveTo(srcCenterX, srcCenterY);
      ctx.quadraticCurveTo(controlX, controlY, centerX, centerY);
    } else {
      ctx.moveTo(srcCenterX, srcCenterY);
      ctx.lineTo(centerX, centerY);
    }
    
    if (with_arrow) {
 // Calculate arrowhead base angle relative to the line
      var headlen = 10;  // Length of the arrowhead lines
      ctx.lineTo(centerX, centerY);
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(centerX - headlen * Math.cos(angle - Math.PI / 6), centerY - headlen * Math.sin(angle - Math.PI / 6));
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(centerX - headlen * Math.cos(angle + Math.PI / 6), centerY - headlen * Math.sin(angle + Math.PI / 6));
    }

    ctx.stroke();
    if (text !== null) {
      // Text properties
      var textOffset = 15;  // Distance from the arrowhead

      // Determine if text should be above or below based on the y-direction of the line
      var textX = centerX + textOffset * Math.cos(angle);
      var textY = centerY + (centerY > srcCenterY ? 1 : -1) * textOffset * Math.sin(angle);
      ctx.fillStyle = strokeStyle;
      ctx.font = "16px Arial";
      ctx.textAlign = "center";  // Center the text on the calculated point
      ctx.fillText(text, textX, textY);
    }
}


function command(command) {
  ws.send(JSON.stringify({ type: 'command', user: 'username', message: { action: "command", command: command } }));
}

function centerOnTile(tile, highlight= false) {
  const $board = $('.tiles-container');
  const boardWidth = $(window).width();
  const boardHeight = $(window).height();
  const tileWidth = tile.width();
  const tileHeight = tile.height();
  var tileOffset = tile.offset();
  var tileLeft = tileOffset.left;
  var tileTop = tileOffset.top;
  const scrollLeft = tileLeft - (boardWidth / 2) + (tileWidth / 2);
  const scrollTop = tileTop - (boardHeight / 2) + (tileHeight / 2);
  $('.tile .entity').removeClass('focus-highlight');
  tile.find('.entity').addClass('focus-highlight');
  $('html, body').animate({
    scrollLeft: scrollLeft,
    scrollTop: scrollTop
  }, 500, function() {
    tile.fadeOut(150).fadeIn(150).fadeOut(150).fadeIn(150).fadeOut(150).fadeIn(150);
    if (highlight) {
      $('.tile').removeClass('focus-highlight-red');
      tile.addClass('focus-highlight-red');
    }
  });
  
}

function centerOnTileXY(x, y, highlight = false) {
  var tile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
  centerOnTile(tile, highlight);
}

function centerOnEntityId(id) {
  var tile = getTileForEntityId(id)
  centerOnTile(tile);
}

function getTileForEntityId(id) {
  return $('.tile[data-coords-id="' + id + '"]');
}

$(document).ready(function () {
  var active_background_sound = null;
  var mediaElementSource = null;
  var lastMovedEntityBeforeRefresh = null;
  var active_track_id = -1;
  console.log("Document ready");
  function playSound(url, track_id) {
    if (active_background_sound) {
      active_background_sound.pause();
      active_background_sound = null;
    }

    active_background_sound = new Audio('/assets/' + url);
    active_background_sound.loop = true;
    active_track_id = track_id;
    active_background_sound.play();
    $('.volume-slider').val(active_background_sound.volume * 100);
  }

  const username = $('body').data('username');
  const controls_entities = $('body').data('controls');
  const socket = io();

  var waitingForReaction = $('body').data('waiting-for-reaction');
  if (waitingForReaction) {
    $('#reaction-modal').modal('show');
  }

  socket.on('connect', function() {
    console.log("Connected to the server");
    socket.emit('register', {
      username: username
    });
  });

  function refreshTileSet(is_setup, pov=false, x=0, y=0, callback=null) {
    $.ajax({
      url: '/update',
      type: 'GET',
      data: { is_setup: is_setup, pov: pov, x: x, y: y },
      success: function (data) {
        lastMovedEntityBeforeRefresh = null;
        $('.tiles-container').html(data);
        if (callback!==null) {
          callback();
        }
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error refreshing tiles container:', textStatus, errorThrown);
      }
    });
  }

  function refreshTurnOrder() {
    $.ajax({
      url: '/turn_order',
      type: 'GET',
      success: function (data) {
        $('#turn-order').html(data);
        $('#battle-turn-order').show();
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error refreshing turn order:', textStatus, errorThrown);
      }
    });
  }

  function refreshTurn() {
    $.ajax({
      url: '/turn',
      type: 'GET',
      success: function (data) {
        $('.game-turn-container').html(data);
        $('.game-turn-container').show()
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error refreshing turn:', textStatus, errorThrown);
      }
    });
  }


  refreshTileSet()

  socket.on('message', function(data) {
    console.log('Message received:', data);
    switch (data.type) {
      case 'map':
        // update the map background image
        map_url = data.message
        $('.tiles-container').data('width', data.width);
        $('.tiles-container').data('height', data.height);
        $('.image-container img').attr('src', map_url);
        $('.image-container img').css('width', data.width + 'px');
        $('.image-container img').css('height', data.height + 'px');

        //resize parent container as well
        $('.image-container').css('width', data.width + 'px');
        $('.image-container').css('height', data.height + 'px');

        // update canvas with the new board width and height
        boardHeight = data.height;
        boardWidth = data.width;
        canvas.width = boardWidth + tile_size;
        canvas.height = boardHeight + tile_size;
        refreshTileSet();
        break;
      case 'move':
        console.log(data.message);
        var animation_buffer = data.message['animation_log'];

        var animatefunction = function(animation_log, animation_log_index) {
          if (animation_log_index >= animation_log.length) {
            refreshTileSet();
            return
          }

          var entity_uid = animation_log[animation_log_index][0];
          var path = animation_log[animation_log_index][1];
          var action = animation_log[animation_log_index][2];

          var tile = $('.tile[data-coords-id="' + entity_uid + '"]');

          if (action && (action["type"] == 'attack')) {
            var label = action["label"];
            drawLine(ctx, { x: tile.data('coords-x'), y: tile.data('coords-y') }, action["target"],
                    line_width=3, with_arrow=true, random_curve=true, strokeStyle='red',
                    text=label);
          } else if (action && action["type"] == 'spell') {
            var label = action["label"];
            drawLine(ctx, { x: tile.data('coords-x'), y: tile.data('coords-y') }, action["target"],
                    line_width=3, with_arrow=true, random_curve=true, strokeStyle='blue',
                    text=label);
          }
          console.log('Entity:', entity_uid, 'Path:', path);

          // animate movement of entity
          var tileRect = tile[0].getBoundingClientRect();
          var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
          var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          var prevX = tileRect.left + scrollLeft;
          var prevY = tileRect.top + scrollTop;

          var moveFunc = function(path, index) {
            if (index >= path.length) {
                animatefunction(animation_log, animation_log_index + 1);
              return;
            }
            console.log('Moving to:', path[index]);
            var x = path[index][0];
            var y = path[index][1];
            var newTile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
            var newTileRect = newTile[0].getBoundingClientRect();
            var newX = newTileRect.left  + scrollLeft;
            var newY = newTileRect.top + scrollTop;

            var deltaX = newX - prevX;
            var deltaY = newY - prevY;
            if ( deltaX === 0 && deltaY === 0) {
              moveFunc(path, index + 1);
              console.log('next 1');
            } else {
              setTimeout(function() {
                tile.css('top', newY);
                tile.css('left', newX);
                moveFunc(path, index + 1);
              }, 300);
            }
          }

          moveFunc(path, 1)
        }

        if (animation_buffer !== undefined) {
          animatefunction(animation_buffer, 0)
        } else {
          refreshTileSet();
        }
        break;
      case 'message':
        console.log(data.message); // log the message on the console
        break;
      case 'info':
        break;
      case 'error':
        console.error(data.message);
        break;
      case 'console':
        var console_message = data.message;
        $('#console-container #console').append('<p>' + console_message + '</p>');
        // scroll to the bottom of the console
        $('#console-container').scrollTop($('#console-container')[0].scrollHeight);
        break;
      case 'track':
        url = data.message.url;
        track_id = data.message.track_id;
        playSound(url, track_id);
        break;
      case 'prompt':
        var prompt_message = data.message;
        alert(prompt_message);
        var data_json = {
          response: "",
          callback: data.callback
        };

        $.ajax({
          url: '/response',
          type: 'POST',
          contentType: 'application/json',
          data: JSON.stringify(data_json),
          success: function (data) {
            console.log('Response sent successfully:', data);
          },
          error: function (jqXHR, textStatus, errorThrown) {
            console.error('Error sending response:', textStatus, errorThrown);
          }
        });
        break;
      case 'turn':
        refreshTurn();
        break;
      case 'focus':
        var x = data.message.x;
        var y = data.message.y;
        centerOnTileXY(x, y, true);
        break;
      case 'stoptrack':
        if (active_background_sound) {
          const audioCtx = new AudioContext();
          const source = audioCtx.createMediaElementSource(active_background_sound);
          const gainNode = audioCtx.createGain();
          source.connect(gainNode);
          gainNode.connect(audioCtx.destination);
          gainNode.gain.setValueAtTime(1, audioCtx.currentTime);
          gainNode.gain.linearRampToValueAtTime(0, audioCtx.currentTime + 2);
          gainNode.addEventListener('ended', function () {
            active_background_sound.pause();
            active_background_sound = null;
            active_track_id = -1;
          });
        }
        break;
      case 'volume':
        console.log('volume ' + data.message.volume);
        if (active_background_sound) {
          active_background_sound.volume = data.message.volume / 100;
          $('.volume-slider').val(data.message.volume, true);
        }
        break;
      case 'initiative':
        console.log('initiative ' + data.message);
        refreshTurnOrder();

        $('#start-initiative').hide();
        $('#start-battle').hide();
        $('#end-battle').show();
        break;
      case 'stop':
        $('#turn-order').html("");
        $('.game-turn-container').hide();
        $('#battle-turn-order').fadeOut()
        $('#start-initiative').show();
        $('#start-battle').show();
        $('#end-battle').hide();
        break;
      default:
        console.log('Unknown message type:', data.type);
    }
  });

  // recover startup state
  var currentSoundtrack = $('body').data('soundtrack-url')

  $('body').on('click', function (event) {
    if (currentSoundtrack) {
      var track_id = $('body').data('soundtrack-id')
      playSound(currentSoundtrack, track_id);
      currentSoundtrack = null;
    }
  });

  // Listen for changes on the volume slider
  $('.modal-content').on('input', '.volume-slider', function () {
    if (active_background_sound) {
      json_data = JSON.stringify({ volume: $(this).val() });
      $.ajax({
        url: '/volume',
        type: 'POST',
        data: json_data,
        contentType: 'application/json',
        success: function (data) {
          console.log('Volume updated successfully');
        },
        error: function (jqXHR, textStatus, errorThrown) {
          console.error('Error updating volume:', textStatus, errorThrown);
        }
      });
    }
  });

  $('.tiles-container').on('click', '.execute-action', function (e) {
    targetModeCallback(multiTargetList)
    targetMode = false
    multiTargetMode = false
    multiTargetList = []
    $('.add-to-target').hide();
    $('.popover-menu-2').hide();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    e.stopPropagation();
  })

  // Use event delegation to handle popover menu clicks
  $('.tiles-container').on('click', '.tile', function (e) {
    var tiles = $(this);
    if (targetMode) {
      var coordsx = $(this).data('coords-x');
      var coordsy = $(this).data('coords-y');
      targetModeCallback({ x: coordsx, y: coordsy })
      targetMode = false
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    } else
      if (moveMode) {
        // retrieve data attributes from the parent .tile element
        var coordsx = $(this).data('coords-x');
        var coordsy = $(this).data('coords-y');
        if (coordsx != source.x || coordsy != source.y) {
          moveMode = false
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          moveModeCallback(movePath)
          movePath = []
          //  ws.send(JSON.stringify({type: 'message', user: 'username', message: {action: "move", from: source, to: {x: coordsx, y: coordsy} }}));
        }
      } else {
          if (e.metaKey || e.ctrlKey) {
            var coordsx = $(this).data('coords-x');
            var coordsy = $(this).data('coords-y');
            refreshTileSet(false, true, coordsx, coordsy);
          } else
          if (e.metaKey || e.shiftKey) {
              var coordsx = $(this).data('coords-x');
              var coordsy = $(this).data('coords-y');
              $.ajax({
                url: '/focus',
                type: 'POST',
                data: { x: coordsx, y: coordsy },
                success: function (data) {
                  console.log('Focus request successful:', data);
                },
                error: function (jqXHR, textStatus, errorThrown) {
                  console.error('Error updating volume:', textStatus, errorThrown);
                }
              });
          } else {
            $('.tiles-container .popover-menu').hide();
            var entity_uid = $(this).data('coords-id');
            $.ajax({
              url: '/actions',
              type: 'GET',
              data: { id: entity_uid},
              success: function (data) {
                var popoverMenuContainer = $(tiles).find('.popover-menu');
                popoverMenuContainer.html(data);
                popoverMenuContainer.toggle();
    
                var tileRightEdge = popoverMenuContainer.offset().left + popoverMenuContainer.outerWidth();
                var windowRightEdge = $(window).width();
    
                if (windowRightEdge < tileRightEdge) {
                  var adjustTile = tileRightEdge - windowRightEdge;
                  popoverMenuContainer.css('left', '-=' + adjustTile);
                }
              },
              error: function (jqXHR, textStatus, errorThrown) {
                console.error('Error updating volume:', textStatus, errorThrown);
              }
            });
          }
      }
  });

  var moveMode = false, targetMode = false, multiTargetMode = false, multiTargetModeUnique=false;
  var movePath = [];
  var multiTargetList = [];
  var max_targets = 1;
  var targetModeCallback = null;
  var moveModeCallback = null;
  var targetModeMaxRange = 0;
  var source = null;
  var battle_setup = false;
  var battle_entity_list = [];
  var globalActionInfo = null;
  var globalOpts = null;
  var globalSourceEntity = null;
  
  var canvas = document.createElement('canvas');
  var tile_size = $('.tiles-container').data('tile-size');
  canvas.width = $('.tiles-container').data('width') + tile_size;
  canvas.height = $('.tiles-container').data('height') + tile_size;
  canvas.style.position = "absolute";
  canvas.style.zIndex = 999;
  canvas.style.pointerEvents = "none"; // Add this line
  const body = document.getElementsByTagName("body")[0];
  body.appendChild(canvas);
  var ctx = canvas.getContext('2d');

   $('.zoom-in').on('click', function() {
      scale += 0.1;
      document.getElementById('main-map-area').style.transform = `scale(${scale})`;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // ctx.setTransform(scale, 0, 0, scale, 0, 0);
  });

  $('.zoom-out').on('click', function() {
      scale -= 0.1;
      document.getElementById('main-map-area').style.transform = `scale(${scale})`;
      // scale the canvas context
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // ctx.setTransform(scale, 0, 0, scale, 0, 0);
  });

  function drawTargetLine(ctx, source, coordsx, coordsy, valid_target=true) {
    var currentDistance = Math.floor(Utils.euclideanDistance(source.x, source.y, coordsx, coordsy)) * 5;
    var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    var scrollTop = window.pageYOffset || document.documentElement.scrollTop;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    ctx.strokeStyle = 'red';
    ctx.lineWidth = 5;

    var x = coordsx;
    var y = coordsy;
    var sourceTile = $('.tile[data-coords-x="' + source.x + '"][data-coords-y="' + source.y + '"]');
    var tile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
    var sourceTileRect = sourceTile[0].getBoundingClientRect();
    var tileRect = tile[0].getBoundingClientRect();

    var srcCenterX = sourceTileRect.left + sourceTileRect.width / 2 + scrollLeft;
    var srcCenterY = sourceTileRect.top + sourceTileRect.height / 2 + scrollTop;

    var centerX = tileRect.left + tileRect.width / 2 + scrollLeft;
    var centerY = tileRect.top + tileRect.height / 2 + scrollTop;
    ctx.moveTo(srcCenterX, srcCenterY);
    ctx.lineTo(centerX, centerY);

    var arrowSize = 10;
    var angle = Math.atan2(centerY - srcCenterY, centerX - srcCenterX);
    var within_range = Math.floor(currentDistance) <= targetModeMaxRange;

    if (within_range && valid_target) {
      ctx.moveTo(centerX - arrowSize * Math.cos(angle - Math.PI / 6), centerY - arrowSize * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(centerX, centerY);
      ctx.lineTo(centerX - arrowSize * Math.cos(angle + Math.PI / 6), centerY - arrowSize * Math.sin(angle + Math.PI / 6));
    } else {
      ctx.moveTo(centerX - arrowSize, centerY - arrowSize);
      ctx.lineTo(centerX + arrowSize, centerY + arrowSize);
      ctx.moveTo(centerX + arrowSize, centerY - arrowSize);
      ctx.lineTo(centerX - arrowSize, centerY + arrowSize);
    }

    ctx.font = "20px Arial";
    ctx.fillStyle = "red";

    ctx.fillText(currentDistance + "ft", centerX, centerY + tileRect.height / 2);

    ctx.stroke();

  }

  $('.tiles-container').on('mouseover', '.tile', function () {
    var coordsx = $(this).data('coords-x');
    var coordsy = $(this).data('coords-y');
    var tooltip = $(this).data('tooltip');
    var x = coordsx;
    var y = coordsy;
    var tile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');

    if (targetMode) {
      $('.highlighted').removeClass('highlighted');
        $('.tile').css('z-index', 0);
        $(this).css('z-index', 999);

        var data_payload = JSON.stringify({
          "id": globalSourceEntity,
          "x" : x,
          "y" : y,
          "action_info" : globalActionInfo,
          "opts" : globalOpts
        });

        $.ajax({
          url: '/target',
          type: 'GET',
          data: { payload: data_payload },
          success: function (data) {
            console.log('Target request successful:', data);
            var adv_info = data.adv_info;
            var adv_mod = data.adv_mod;
            var attack_mod = data.attack_mod;
            var valid_target = data.valid_target;

            drawTargetLine(ctx, source, coordsx, coordsy, valid_target=valid_target);

            $.each(adv_info[0], function(index, value) {
              tooltip += '<p><span style="color: green;">+' + value + '</span></p>';
            })
            $.each(adv_info[1], function(index, value) {
              tooltip += '<p><span style="color: red;">-' + value + '</span></p>';
            })
            $('#coords-box').html('<p>X: ' + coordsx + '</p><p>Y: ' + coordsy + '</p>' + tooltip);
          },
          error: function (jqXHR, textStatus, errorThrown) {
            console.error('Error requesting target:', textStatus, errorThrown);
          }
       });


    } else {
      $('#coords-box').html('<p>X: ' + coordsx + '</p><p>Y: ' + coordsy + '</p>' + tooltip);
      if (moveMode &&
        (source.coordsx != coordsx || source.coordsy != coordsy)) {
        $.ajax({
          url: '/path',
          type: 'GET',
          data: { from: source, to: { x: coordsx, y: coordsy } },
          success: function (data) {
            // data is of the form [[0,0],[1,1],[2,2]]
            console.log('Path request successful:', data.path);
            $('.highlighted').removeClass('highlighted');
            // Highlight the squares returned by data
            if (data.cost.budget < 0) {
              return
            }

            var available_cost = (data.cost.original_budget - data.cost.budget) * 5
            var placeable = data.placeable
            var rect = canvas.getBoundingClientRect();
            var scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
            var scrollTop = window.pageYOffset || document.documentElement.scrollTop;

            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.beginPath();
            ctx.strokeStyle = 'red';
            ctx.lineWidth = 5;

            movePath = data.path

            data.path.forEach(function (coords, index) {
              var x = coords[0];
              var y = coords[1];
              var tile = $('.tile[data-coords-x="' + x + '"][data-coords-y="' + y + '"]');
              var tileRect = tile[0].getBoundingClientRect();
              var centerX = tileRect.left + tileRect.width / 2 + scrollLeft;
              var centerY = tileRect.top + tileRect.height / 2 + scrollTop;

              if (index === 0) {
                ctx.moveTo(centerX, centerY);
              } else {
                ctx.lineTo(centerX, centerY);
              }
              if (index === data.path.length - 1) {
                var arrowSize = 10;
                var angle = Math.atan2(centerY - prevY, centerX - prevX);
                if (placeable) {
                  ctx.moveTo(centerX - arrowSize * Math.cos(angle - Math.PI / 6), centerY - arrowSize * Math.sin(angle - Math.PI / 6));
                  ctx.lineTo(centerX, centerY);
                  ctx.lineTo(centerX - arrowSize * Math.cos(angle + Math.PI / 6), centerY - arrowSize * Math.sin(angle + Math.PI / 6));
                } else {
                  ctx.moveTo(centerX - arrowSize, centerY - arrowSize);
                  ctx.lineTo(centerX + arrowSize, centerY + arrowSize);
                  ctx.moveTo(centerX + arrowSize, centerY - arrowSize);
                  ctx.lineTo(centerX - arrowSize, centerY + arrowSize);
                }
                ctx.font = "20px Arial";
                ctx.fillStyle = "red";
                ctx.fillText(available_cost + "ft", centerX, centerY + tileRect.height / 2);
              }

              prevX = centerX;
              prevY = centerY;
            });
            ctx.stroke();

          },
          error: function (jqXHR, textStatus, errorThrown) {
            console.error('Error requesting path:', textStatus, errorThrown);
          }
        });
      }
    }

    
  });

  $("#add-all-entities", 'click', function(event) {
    debugger;
    $('.tile').each(function(elem) {
      var entity_uid = $(elem).data('coords-id');
      var btn = $('.tile btn.add-to-turn-order');

      addToInitiative(btn, entity_uid, battle_entity_list)
    })
  });

  $(document).on('keydown', function (event) {

    if (event.keyCode === 27) { // Escape or ESC key is pressed, cancel all ongoing UI interactions
      if (moveMode) {
        moveMode = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      if (targetMode) {
        targetMode = false;
        globalActionInfo = null;
        globalOpts = null;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }
      if (multiTargetMode) {
        multiTargetMode = false;
        multiTargetList = [];
        $('.add-to-target').hide();
        $('.popover-menu-2').hide();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
      }

      $('.tiles-container .popover-menu').hide();
    }
  });

  $('#main-map-area').on('contextmenu', function (e) {
    if (targetMode || multiTargetMode || moveMode) {
      e.preventDefault();
      // Add your code here to handle right-click event
      targetMode = false;
      multiTargetMode = false;
      moveMode = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      $('.add-to-target').hide();
      $('.popover-menu-2').hide();
    }
  });

  $('.tiles-container').on('click', '.add-to-target', function (e) {
    var entity_uid = $(this).closest('.tile').data('coords-id');
    var index = multiTargetList.indexOf(entity_uid);

    if (index === -1 || multiTargetModeUnique===false) {
      if (multiTargetList.length < max_targets) {
        multiTargetList.push(entity_uid);
        // set button to the remove state
        if (multiTargetModeUnique===true) {
          $(this).hide();
        }
        drawLine(ctx, source, entity_uid, line_width=3, with_arrow=false, random_curve=true);
        $('.tile[data-coords-id="' + source.entity_uid + '"] .popover-menu-2').show()
      }
    }
    e.stopPropagation();
  });

  //floating menu interaction
  $('#expand-menu').click(function () {
    $('#menu').fadeIn();
    $('#expand-menu').hide();
    $('#collapse-menu').show();
  })

  $('#collapse-menu').click(function () {
    $('#menu').fadeOut();
    $('#expand-menu').show();
    $('#collapse-menu').hide();
  })

  $('#start-battle').click(function () {
    $('#battle-turn-order').fadeIn()
    battle_setup = true
    refreshTileSet(true)
  });

  function showConsole() {
    $('#console-container').fadeIn();
    $('#open-console').html('Hide Console')
  }


  function hideConsole() {
    $('#console-container').fadeOut();
    $('#open-console').html('Show Console')
  }

  $('#open-console').click(function () {
    if ($('#console-container').is(':visible')) {
      hideConsole();
    } else {
      showConsole();
    }
  });

  $('#hide-combat-log').click(function () {
    hideConsole();
  });

  $('#start-initiative').click(function () {
    // Get the list of items in the battle turn order
    const $turnOrderItems = $('.turn-order-item');
    const battle_turn_order = $turnOrderItems.map(function () {
      const id = $(this).data('id');
      const group = $(this).find('.group-select').val();
      const controller = $(this).find('.controller-select').val();
      return { id, group, controller };
    }).get();

    // Convert to a json payload and send to the server which accepts json/application
    battle_turn_order_json = JSON.stringify({"battle_turn_order":  battle_turn_order});  // Convert to JSON string


    // Call the POST /battle endpoint with the list of items in the battle turn order
    $.ajax({
      url: '/battle',
      type: 'POST',
      contentType: 'application/json',
      data: battle_turn_order_json,
      success: function (data) {
        $('.add-to-turn-order').hide();
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error requesting battle:', textStatus, errorThrown);
      }
    });
  })

  $('#end-battle').click(function () {
    $.ajax({
      url: '/stop',
      type: 'POST',
      success: function (data) {
        console.log('Battle stopped successfully');
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error stopping battle:', textStatus, errorThrown);
      }
    });
  });

  $('.tiles-container').on('click', '.add-to-turn-order', function (event) {
    const $this = $(this);
    const { id, name } = $this.data();

    const index = battle_entity_list.findIndex(entity => entity.id === id);

    if (index === -1) {
      battle_entity_list.push({ id, group: 'a', name });
      $.ajax({
        url: '/add',
        type: 'GET',
        data: { id: id },
        success: function (data) {
          $('#turn-order').append(data);
          $this.find('i.glyphicon').removeClass('glyphicon-plus').addClass('glyphicon-minus');
          $this.css('background-color', 'red');
        },
        error: function (jqXHR, textStatus, errorThrown) {
          console.error('Error requesting turn order:', textStatus, errorThrown);
        }
      });
    } else {
      battle_entity_list.splice(index, 1);
      $this.find('i.glyphicon').removeClass('glyphicon-minus').addClass('glyphicon-plus');
      $this.css('background-color', 'green');

      // Remove name from turn order list
      const $turnOrderItem = $('.turn-order-item').filter(function () {
        return $(this).text() === name;
      });
      $turnOrderItem.remove();
    }

    event.stopPropagation();
  });

  // Remove turn order item on button click
  $('#turn-order').on('click', '.remove-turn-order-item', function () {
    $(this).nearest('#turn-order-item').remove();
  });

  $('#turn-order').on('click', '.token-image', function() {
    //highlight/focus on the entity
    var entity_uid = $(this).data('id');
    centerOnEntityId(entity_uid);

  })

  $('#turn-order').on('click', '#next-turn', function () {
    $.ajax({
      url: '/next_turn',
      type: 'POST',
      success: function (data) {
        console.log('Next turn request successful:', data);
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error requesting next turn:', textStatus, errorThrown);
      }
    });
  });

  $('#turn-order').on('click', '.turn-order-item', function () {
    var entity_uid = $(this).data('id');
    centerOnEntityId(entity_uid);
  });


  $('#select-soundtrack').click(function () {
    $.get('/tracks', { track_id: active_track_id }, function (data) {
      $('.modal-content').html(data);
      $('#modal-1').modal('show');
    });
  });

  $('.modal-content').on('click', '.play', function () {
    var trackId = $('input[name="track_id"]:checked').val();
    $.ajax({
      url: '/sound',
      type: 'POST',
      data: { track_id: trackId },
      success: function (data) {
        console.log('Sound request successful:', data);
        $('#modal-1').modal('hide');
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error requesting sound:', textStatus, errorThrown);
      }
    });
  });

  var currentAction = null;
  var currentIndex = 0;

  $('.actions-container').on('click', '.action-button', function (e) {
    e.stopPropagation();
    var action = $(this).data('action-type');
    var opts = $(this).data('action-opts');
    var entity_uid = $(this).closest('.tile').data('coords-id');
    var coordsx = $(this).closest('.tile').data('coords-x');
    var coordsy = $(this).closest('.tile').data('coords-y');

    if (entity_uid === undefined) {
      entity_uid = $(this).data('id')
    }

    if (coordsx === undefined) {
      coordsx = $(this).data('coords-x')
      coordsy = $(this).data('coords-y')
    }

    // disable moveMode
    if (moveMode) {
      moveMode = false
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    data = { id: entity_uid, action: action, opts: opts }
    json_data = JSON.stringify(data)
    $.ajax({
      url: '/action',
      type: 'POST',
      data: json_data,
      contentType: 'application/json',
      success: function (data) {

        switch (data.param[0].type) {
          case 'movement':
            moveModeCallback = function (path) {
              callback_data = {
                id: entity_uid,
                action: action,
                opts: opts,
                path: path
              }
              data_json = JSON.stringify(callback_data)
              $.ajax({
                url: '/action',
                type: 'POST',
                data: data_json,
                contentType: 'application/json',
                success: function (data) {
                  console.log('Action request successful:', data);
                  refreshTurn();
                },
                error: function (jqXHR, textStatus, errorThrown) {
                  console.error('Error requesting action:', textStatus, errorThrown);
                }
              });
            }

            $('.tiles-container .popover-menu').hide();
            moveMode = true
            source = { x: coordsx, y: coordsy }
            break;
          case 'select_spell':
            $.ajax({
              url: '/spells',
              type: 'GET',
              data: { id: entity_uid, action: action, opts: opts },
              success: function (data) {
                $('.modal-content').html(data);
                $('#modal-1').modal('show');
              },
              error: function (jqXHR, textStatus, errorThrown) {
                console.error('Error requesting spell:', textStatus, errorThrown);
              }
            });
            break;
          case 'select_target':
            $('.tiles-container .popover-menu').hide();
            $('#modal-1').modal('hide');

            source = { x: coordsx, y: coordsy, entity_uid: entity_uid }

            if (data.range_max === undefined) {
              targetModeMaxRange = data.range
            } else {
              targetModeMaxRange = data.range_max
            }

            if (data.target_hints !== undefined) {
              targetModeHints = data.target_hints;
              // highlight all tiles that are
              // valid targets using the passed entity_uid
              // targetModeHints should be a json array of uids
              $.each(targetModeHints, function (index, value) {
                var add_to_target_button = $('.tile[data-coords-id="' + value + '"] .add-to-target');
                add_to_target_button.show()
              });

              multiTargetMode = true
              max_targets = data.total_targets;
              if (data['unique_targets']===true) {
                multiTargetModeUnique = true;
              } else {
                multiTargetModeUnique = false;
              };

              var img = $('.tile[data-coords-id="' + entity_uid + '"] .execute-action img')
              img.attr('src', '/spells/spell_' + data.spell + '.png')
              targetMode = false
            } else {
              targetMode = true;
              globalActionInfo = action;
              globalOpts = opts;
              globalSourceEntity = entity_uid;
            }

            targetModeCallback = function (target) {
              let data = {
                id: entity_uid,
                action: action,
                opts: opts,
                target: target
              }
              json_data = JSON.stringify(data);
              $.ajax({
                url: '/action',
                type: 'POST',
                data: json_data,
                contentType: 'application/json',
                success: function (data) {
                  console.log('Action request successful:', data);
                  refreshTurn();
                },
                error: function (jqXHR, textStatus, errorThrown) {
                  console.error('Error requesting action:', textStatus, errorThrown);
                }
              });
            }

            break;
          default:
            console.log('Unknown action type:', data.param[0].type);
        }
        console.log('Action request successful:', data);
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error requesting action:', textStatus, errorThrown);
      }
    });
  });

  $('#turn-order').on('click', '#add-more', function () {
    if (battle_setup) {
      battle_setup = false
      refreshTileSet()
    } else {
      battle_setup = true
      refreshTileSet(true)
    }

  });

  $('.game-turn-container').on('click', '#player-end-turn', function() {
    $.ajax({
      url: '/end_turn',
      type: 'POST',
      data: {
      },
      success: function (data) {
        $('.game-turn-container').hide()
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error requesting action:', textStatus, errorThrown);
      }
    });
  });

  $('.floating-window').on('click', function() {
    var fwindow = $(this);
    var maxZIndex = 0;
    
    // Find the highest z-index value among all floating windows
    $('.floating-window').each(function() {
      var zIndex = parseInt($(this).css('z-index'));
      if (zIndex > maxZIndex) {
        maxZIndex = zIndex;
      }
    });
    
    // Set the clicked floating window's z-index to be higher than all others
    fwindow.css('z-index', maxZIndex + 1);
  });

  $(document).on('mouseenter', '.hide-action', function() {
    var entity_uid = $(this).closest('.tile').data('coords-id');
    $.ajax({
      url: '/hide',
      type: 'GET',
      data: { id: entity_uid },
      success: function (data) {
        var hiding_spots = data.hiding_spots;
        // highlight all tiles that are hiding spots, this is a
        // json array of x y coords
        $.each(hiding_spots, function (index, value) {
          var tile = $('.tile[data-coords-x="' + value[0] + '"][data-coords-y="' + value[1] + '"]');
          tile.css('background-color', 'rgba(0, 255, 0, 0.5)');
         });
      },
      error: function (jqXHR, textStatus, errorThrown) {
        console.error('Error requesting hide:', textStatus, errorThrown);
      }
    });
  })

  $(document).on('mouseleave', '.hide-action', function() {
    $('.tile').css('background-color', '');
  })

  Utils.draggable('#battle-turn-order');
  Utils.draggable('#console-container');

  if ($('body').data('battle-in-progress')) {
    $('#start-initiative').hide();
  }
});

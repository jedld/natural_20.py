// --- Global Helpers & Utilities ---

let scale = 1;

// Simple wrappers to reduce duplicate $.ajax boilerplate.
const ajaxGet = (url, data, onSuccess) => {
  $.ajax({
    url,
    type: 'GET',
    data,
    success: onSuccess,
    error: (jqXHR, textStatus, errorThrown) => {
      console.error(`Error with GET ${url}:`, textStatus, errorThrown);
    }
  });
};

const ajaxPost = (url, data, onSuccess, isJSON = false) => {
  $.ajax({
    url,
    type: 'POST',
    data: isJSON ? JSON.stringify(data) : data,
    contentType: isJSON ? 'application/json' : 'application/x-www-form-urlencoded',
    success: onSuccess,
    error: (jqXHR, textStatus, errorThrown) => {
      console.error(`Error with POST ${url}:`, textStatus, errorThrown);
    }
  });
};

// Returns the center coordinates of a tile element.
const getTileCenter = (selector) => {
  const $tile = $(selector);
  const rect = $tile[0].getBoundingClientRect();
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  return {
    x: rect.left + rect.width / 2 + scrollLeft,
    y: rect.top + rect.height / 2 + scrollTop,
  };
};

// Adds or removes an entity from the battle initiative.
function addToInitiative($btn, battleEntityList) {
  const { id, name } = $btn.data();
  const index = battleEntityList.findIndex(entity => entity.id === id);

  if (index === -1) {
    battleEntityList.push({ id, group: 'a', name });
    ajaxGet('/add', { id }, (data) => {
      $('#turn-order').append(data);
      $btn.find('i.glyphicon').removeClass('glyphicon-plus').addClass('glyphicon-minus');
      $btn.css('background-color', 'red');
    });
  } else {
    battleEntityList.splice(index, 1);
    $btn.find('i.glyphicon').removeClass('glyphicon-minus').addClass('glyphicon-plus');
    $btn.css('background-color', 'green');
    $('.turn-order-item').filter((_, el) => $(el).text() === name).remove();
  }
}

// Draws a line from a source tile to a target tile. Options let you customize
// the line width, stroke color, whether to add an arrowhead, use a curved path, etc.
function drawLine(ctx, source, targetSelector, options = {}) {
  const {
    lineWidth = 5,
    withArrow = false,
    randomCurve = false,
    strokeStyle = 'green',
    text = null,
  } = options;

  const srcCenter = getTileCenter(`.tile[data-coords-x="${source.x}"][data-coords-y="${source.y}"]`);
  const tgtCenter = getTileCenter(targetSelector);

  ctx.beginPath();
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = lineWidth;

  let angle = Math.atan2(tgtCenter.y - srcCenter.y, tgtCenter.x - srcCenter.x);

  if (randomCurve) {
    const randomAngle = (Math.random() * (90 - 20) + 20) * (Math.PI / 180);
    const controlX = (srcCenter.x + tgtCenter.x) / 2 + Math.cos(randomAngle) * (tgtCenter.y - srcCenter.y) / 2;
    const controlY = (srcCenter.y + tgtCenter.y) / 2 + Math.sin(randomAngle) * (tgtCenter.y - srcCenter.y) / 2;
    ctx.moveTo(srcCenter.x, srcCenter.y);
    ctx.quadraticCurveTo(controlX, controlY, tgtCenter.x, tgtCenter.y);
    angle = randomAngle; // update angle for arrow/text placement
  } else {
    ctx.moveTo(srcCenter.x, srcCenter.y);
    ctx.lineTo(tgtCenter.x, tgtCenter.y);
  }

  if (withArrow) {
    const headlen = 10;
    ctx.moveTo(tgtCenter.x, tgtCenter.y);
    ctx.lineTo(
      tgtCenter.x - headlen * Math.cos(angle - Math.PI / 6),
      tgtCenter.y - headlen * Math.sin(angle - Math.PI / 6)
    );
    ctx.moveTo(tgtCenter.x, tgtCenter.y);
    ctx.lineTo(
      tgtCenter.x - headlen * Math.cos(angle + Math.PI / 6),
      tgtCenter.y - headlen * Math.sin(angle + Math.PI / 6)
    );
  }

  ctx.stroke();

  if (text !== null) {
    const textOffset = 15;
    const textX = tgtCenter.x + textOffset * Math.cos(angle);
    const textY = tgtCenter.y + (tgtCenter.y > srcCenter.y ? 1 : -1) * textOffset * Math.sin(angle);
    ctx.fillStyle = strokeStyle;
    ctx.font = "16px Arial";
    ctx.textAlign = "center";
    ctx.fillText(text, textX, textY);
  }
}

// Sends a simple command via WebSocket.
function command(cmd) {
  ws.send(JSON.stringify({
    type: 'command',
    user: 'username',
    message: { action: "command", command: cmd }
  }));
}

// Centers the viewport on a given tile and (optionally) highlights it.
function centerOnTile($tile, highlight = false) {
  const boardWidth = $(window).width();
  const boardHeight = $(window).height();
  const tileWidth = $tile.width();
  const tileHeight = $tile.height();
  const { left, top } = $tile.offset();
  const scrollLeft = left - (boardWidth / 2) + (tileWidth / 2);
  const scrollTop = top - (boardHeight / 2) + (tileHeight / 2);

  $('.tile .entity').removeClass('focus-highlight');
  $tile.find('.entity').addClass('focus-highlight');

  $('html, body').animate({ scrollLeft, scrollTop }, 500, () => {
    $tile.fadeOut(150).fadeIn(150).fadeOut(150).fadeIn(150).fadeOut(150).fadeIn(150);
    if (highlight) {
      $('.tile').removeClass('focus-highlight-red');
      $tile.addClass('focus-highlight-red');
    }
  });
}

const centerOnTileXY = (x, y, highlight = false) => {
  const $tile = $(`.tile[data-coords-x="${x}"][data-coords-y="${y}"]`);
  centerOnTile($tile, highlight);
};

const centerOnEntityId = (id) => {
  const $tile = $(`.tile[data-coords-id="${id}"]`);
  centerOnTile($tile);
};


// --- Document Ready: Event Bindings & Main Logic ---
$(document).ready(() => {
  let active_background_sound = null;
  let lastMovedEntityBeforeRefresh = null;
  let active_track_id = -1;
  const battleEntityList = [];

  // Plays a background sound (stopping any previous one).
  const playSound = (url, track_id) => {
    if (active_background_sound) {
      active_background_sound.pause();
    }
    active_background_sound = new Audio(`/assets/${url}`);
    active_background_sound.loop = true;
    active_track_id = track_id;
    active_background_sound.play();
    $('.volume-slider').val(active_background_sound.volume * 100);
  };

  const username = $('body').data('username');
  const socket = io();
  if ($('body').data('waiting-for-reaction')) {
    $('#reaction-modal').modal('show');
  }

  socket.on('connect', () => {
    console.log("Connected to the server");
    socket.emit('register', { username });
  });

  // Refresh functions
  const refreshTileSet = (is_setup = false, pov = false, x = 0, y = 0, callback = null) => {
    ajaxGet('/update', { is_setup, pov, x, y }, (data) => {
      lastMovedEntityBeforeRefresh = null;
      $('.tiles-container').html(data);
      if (callback) callback();
    });
  };

  const refreshTurnOrder = () => {
    ajaxGet('/turn_order', {}, (data) => {
      $('#turn-order').html(data);
      $('#battle-turn-order').show();
    });
  };

  const refreshTurn = () => {
    ajaxGet('/turn', {}, (data) => {
      $('.game-turn-container').html(data).show();
    });
  };

  refreshTileSet();

  // --- Socket Message Handler ---
  socket.on('message', (data) => {
    console.log('Message received:', data);
    switch (data.type) {
      case 'map': {
        const { message: map_url, width, height } = data;
        $('.tiles-container').data({ width, height });
        $('.image-container img')
          .attr('src', map_url)
          .css({ width: `${width}px`, height: `${height}px` });
        $('.image-container').css({ width: `${width}px`, height: `${height}px` });
        const canvas = document.querySelector('canvas');
        canvas.width = width + $('.tiles-container').data('tile-size');
        canvas.height = height + $('.tiles-container').data('tile-size');
        refreshTileSet();
        break;
      }
      case 'move': {
        const animationBuffer = data.message.animation_log;
        const animateFunction = (animationLog, idx) => {
          if (idx >= animationLog.length) {
            refreshTileSet();
            return;
          }
          const [entity_uid, path, action] = animationLog[idx];
          const $tile = $(`.tile[data-coords-id="${entity_uid}"]`);
          if (action) {
            const opts = {
              lineWidth: 3,
              withArrow: true,
              randomCurve: true,
              strokeStyle: action.type === 'attack' ? 'red' : 'blue',
              text: action.label
            };
            drawLine(ctx, { x: $tile.data('coords-x'), y: $tile.data('coords-y') },
              `.tile[data-coords-id="${action.target}"]`, opts);
          }
          const tileRect = $tile[0].getBoundingClientRect();
          const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
          const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          let prevX = tileRect.left + scrollLeft;
          let prevY = tileRect.top + scrollTop;
          const moveFunc = (p, index) => {
            if (index >= p.length) {
              animateFunction(animationLog, idx + 1);
              return;
            }
            const [x, y] = p[index];
            const $newTile = $(`.tile[data-coords-x="${x}"][data-coords-y="${y}"]`);
            const newRect = $newTile[0].getBoundingClientRect();
            const newX = newRect.left + scrollLeft;
            const newY = newRect.top + scrollTop;
            if (newX === prevX && newY === prevY) {
              moveFunc(p, index + 1);
            } else {
              setTimeout(() => {
                $tile.css({ top: newY, left: newX });
                moveFunc(p, index + 1);
              }, 300);
            }
          };
          moveFunc(path, 1);
        };
        if (animationBuffer) {
          animateFunction(animationBuffer, 0);
        } else {
          refreshTileSet();
        }
        break;
      }
      case 'message':
        console.log(data.message);
        break;
      case 'error':
        console.error(data.message);
        break;
      case 'console':
        $('#console-container #console').append(`<p>${data.message}</p>`);
        $('#console-container').scrollTop($('#console-container')[0].scrollHeight);
        break;
      case 'track':
        playSound(data.message.url, data.message.track_id);
        break;
      case 'prompt': {
        alert(data.message);
        ajaxPost('/response', { response: "", callback: data.callback },
          (resp) => console.log('Response sent successfully:', resp), true);
        break;
      }
      case 'turn':
        refreshTurn();
        break;
      case 'focus':
        centerOnTileXY(data.message.x, data.message.y, true);
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
          gainNode.addEventListener('ended', () => {
            active_background_sound.pause();
            active_background_sound = null;
            active_track_id = -1;
          });
        }
        break;
      case 'volume':
        if (active_background_sound) {
          active_background_sound.volume = data.message.volume / 100;
          $('.volume-slider').val(data.message.volume);
        }
        break;
      case 'initiative':
        refreshTurnOrder();
        $('#start-initiative, #start-battle').hide();
        $('#end-battle').show();
        break;
      case 'stop':
        $('#turn-order').html("");
        $('.game-turn-container').hide();
        $('#battle-turn-order').fadeOut();
        $('#start-initiative, #start-battle').show();
        $('#end-battle').hide();
        break;
      case 'reaction':
        ajaxGet('/reaction', {}, (data) => {
          $('#reaction-modal .reaction-content').html(data);
          $('#reaction-modal').modal('show');
        });
        break;
      case 'dismiss_reaction':
        $('#reaction-modal').modal('hide');
        break;
      default:
        console.log('Unknown message type:', data.type);
    }
  });

  // Recover soundtrack state on first click.
  let currentSoundtrack = $('body').data('soundtrack-url');
  $('body').on('click', () => {
    if (currentSoundtrack) {
      playSound(currentSoundtrack, $('body').data('soundtrack-id'));
      currentSoundtrack = null;
    }
  });

  // --- Form & Slider Handlers ---
  $('#reaction-form').on('submit', (event) => {
    event.preventDefault();
    const reaction = $('#reaction-form input[name="reaction"]:checked').val();
    ajaxPost('/reaction', { reaction }, (data) => {
      console.log('Reaction submitted successfully:', data);
      $('#reaction-modal').modal('hide');
    });
  });

  $('.modal-content').on('input', '.volume-slider', function () {
    if (active_background_sound) {
      ajaxPost('/volume', { volume: $(this).val() },
        () => console.log('Volume updated successfully'), true);
    }
  });

  // --- Tile & Action Event Handlers ---
  $('.tiles-container').on('click', '.execute-action', (e) => {
    targetModeCallback(multiTargetList);
    targetMode = multiTargetMode = false;
    multiTargetList = [];
    $('.add-to-target, .popover-menu-2').hide();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    e.stopPropagation();
  });

  $('.tiles-container').on('click', '.tile', function (e) {
    const $tile = $(this);
    const coordsx = $tile.data('coords-x');
    const coordsy = $tile.data('coords-y');

    if (targetMode) {
      targetModeCallback({ x: coordsx, y: coordsy });
      targetMode = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    } else if (moveMode) {
      if (coordsx !== source.x || coordsy !== source.y) {
        moveMode = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        moveModeCallback(movePath);
        movePath = [];
      }
    } else {
      if (e.metaKey || e.ctrlKey) {
        refreshTileSet(false, true, coordsx, coordsy);
      } else if (e.metaKey || e.shiftKey) {
        ajaxPost('/focus', { x: coordsx, y: coordsy }, (data) => {
          console.log('Focus request successful:', data);
        });
      } else {
        $('.popover-menu').hide();
        let entity_uid = $tile.data('coords-id') || $tile.find('.object-container').data('id');
        ajaxGet('/actions', { id: entity_uid }, (data) => {
          const $menu = $tile.find('.popover-menu');
          $menu.html(data).toggle();
          const tileRightEdge = $menu.offset().left + $menu.outerWidth();
          const windowRightEdge = $(window).width();
          if (windowRightEdge < tileRightEdge) {
            $menu.css('left', `-=${tileRightEdge - windowRightEdge}`);
          }
        });
      }
    }
  });

  // Mode & State Variables
  let moveMode = false,
    targetMode = false,
    multiTargetMode = false,
    multiTargetModeUnique = false;
  let movePath = [],
    multiTargetList = [];
  let max_targets = 1;
  let targetModeCallback = null,
    moveModeCallback = null;
  let targetModeMaxRange = 0,
    source = null,
    battle_setup = false;
  let globalActionInfo = null,
    globalOpts = null,
    globalSourceEntity = null;

  // --- Canvas Setup ---
  const tile_size = $('.tiles-container').data('tile-size');
  const canvas = document.createElement('canvas');
  canvas.width = $('.tiles-container').data('width') + tile_size;
  canvas.height = $('.tiles-container').data('height') + tile_size;
  canvas.style.position = "absolute";
  canvas.style.zIndex = 999;
  canvas.style.pointerEvents = "none";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');

  $('.zoom-in').on('click', () => {
    scale += 0.1;
    $('#main-map-area').css('transform', `scale(${scale})`);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  $('.zoom-out').on('click', () => {
    scale -= 0.1;
    $('#main-map-area').css('transform', `scale(${scale})`);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  // Draws a target line from a source to a given set of coordinates.
  function drawTargetLine(ctx, source, coordsx, coordsy, valid_target = true) {
    const currentDistance = Math.floor(Utils.euclideanDistance(source.x, source.y, coordsx, coordsy)) * 5;
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.beginPath();
    ctx.strokeStyle = 'red';
    ctx.lineWidth = 5;
    const srcCenter = getTileCenter(`.tile[data-coords-x="${source.x}"][data-coords-y="${source.y}"]`);
    const tgtCenter = getTileCenter(`.tile[data-coords-x="${coordsx}"][data-coords-y="${coordsy}"]`);
    ctx.moveTo(srcCenter.x, srcCenter.y);
    ctx.lineTo(tgtCenter.x, tgtCenter.y);
    const arrowSize = 10;
    const angle = Math.atan2(tgtCenter.y - srcCenter.y, tgtCenter.x - srcCenter.x);
    if (Math.floor(currentDistance) <= targetModeMaxRange && valid_target) {
      ctx.moveTo(tgtCenter.x - arrowSize * Math.cos(angle - Math.PI / 6), tgtCenter.y - arrowSize * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(tgtCenter.x, tgtCenter.y);
      ctx.lineTo(tgtCenter.x - arrowSize * Math.cos(angle + Math.PI / 6), tgtCenter.y - arrowSize * Math.sin(angle + Math.PI / 6));
    } else {
      ctx.moveTo(tgtCenter.x - arrowSize, tgtCenter.y - arrowSize);
      ctx.lineTo(tgtCenter.x + arrowSize, tgtCenter.y + arrowSize);
      ctx.moveTo(tgtCenter.x + arrowSize, tgtCenter.y - arrowSize);
      ctx.lineTo(tgtCenter.x - arrowSize, tgtCenter.y + arrowSize);
    }
    ctx.font = "20px Arial";
    ctx.fillStyle = "red";
    ctx.fillText(`${currentDistance}ft`, tgtCenter.x, tgtCenter.y + $('.tile').height() / 2);
    ctx.stroke();
  }

  // Highlight tile info or draw movement/path data on hover.
  $('.tiles-container').on('mouseover', '.tile', function () {
    const coordsx = $(this).data('coords-x');
    const coordsy = $(this).data('coords-y');
    let tooltip = $(this).data('tooltip') || '';
    if (targetMode) {
      $('.highlighted').removeClass('highlighted');
      $('.tile').css('z-index', 0);
      $(this).css('z-index', 999);
      const data_payload = JSON.stringify({
        id: globalSourceEntity,
        x: coordsx,
        y: coordsy,
        action_info: globalActionInfo,
        opts: globalOpts
      });
      ajaxGet('/target', { payload: data_payload }, (data) => {
        const { adv_info, valid_target } = data;
        drawTargetLine(ctx, source, coordsx, coordsy, valid_target);
        if (adv_info) {
          adv_info[0].forEach(value => tooltip += `<p><span style="color: green;">+${value}</span></p>`);
          adv_info[1].forEach(value => tooltip += `<p><span style="color: red;">-${value}</span></p>`);
        }
        $('#coords-box').html(`<p>X: ${coordsx}</p><p>Y: ${coordsy}</p>${tooltip}`);
      });
    } else {
      $('#coords-box').html(`<p>X: ${coordsx}</p><p>Y: ${coordsy}</p>${tooltip}`);
      if (moveMode && (source.x !== coordsx || source.y !== coordsy)) {
        ajaxGet('/path', { from: source, to: { x: coordsx, y: coordsy } }, (data) => {
          if (data.cost.budget < 0) return;
          const available_cost = (data.cost.original_budget - data.cost.budget) * 5;
          movePath = data.path;
          const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
          const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.beginPath();
          ctx.strokeStyle = 'red';
          ctx.lineWidth = 5;
          let prevX, prevY;
          data.path.forEach((coords, index) => {
            const [x, y] = coords;
            const rect = $(`.tile[data-coords-x="${x}"][data-coords-y="${y}"]`)[0].getBoundingClientRect();
            const centerX = rect.left + rect.width / 2 + scrollLeft;
            const centerY = rect.top + rect.height / 2 + scrollTop;
            if (index === 0) {
              ctx.moveTo(centerX, centerY);
            } else {
              ctx.lineTo(centerX, centerY);
            }
            if (index === data.path.length - 1) {
              const arrowSize = 10;
              const angle = Math.atan2(centerY - prevY, centerX - prevX);
              if (data.placeable) {
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
              ctx.fillText(`${available_cost}ft`, centerX, centerY + $('.tile').height() / 2);
            }
            prevX = centerX;
            prevY = centerY;
          });
          ctx.stroke();
        });
      }
    }
  });

  // Example: add all entities to initiative.
  $("#add-all-entities").on('click', function (event) {
    $('.tile').each(function () {
      const entity_uid = $(this).data('coords-id');
      const $btn = $(this).find('button.add-to-turn-order');
      if (entity_uid && $btn.length) {
        addToInitiative($btn, battleEntityList);
      }
    });
  });

  // Cancel ongoing interactions on Escape.
  $(document).on('keydown', (event) => {
    if (event.keyCode === 27) {
      if (moveMode || targetMode || multiTargetMode) {
        moveMode = targetMode = multiTargetMode = false;
        multiTargetList = [];
        $('.add-to-target, .popover-menu-2, .popover-menu').hide();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        globalActionInfo = globalOpts = null;
      }
    }
  });

  // Cancel interactions on right-click.
  $('#main-map-area').on('contextmenu', function (e) {
    if (targetMode || multiTargetMode || moveMode) {
      e.preventDefault();
      targetMode = multiTargetMode = moveMode = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      $('.add-to-target, .popover-menu-2').hide();
    }
  });

  // Multi-target selection.
  $('.tiles-container').on('click', '.add-to-target', function (e) {
    const entity_uid = $(this).closest('.tile').data('coords-id');
    if (!multiTargetList.includes(entity_uid) || !multiTargetModeUnique) {
      if (multiTargetList.length < max_targets) {
        multiTargetList.push(entity_uid);
        if (multiTargetModeUnique) $(this).hide();
        drawLine(ctx, source, `.tile[data-coords-id="${entity_uid}"]`, { lineWidth: 3, withArrow: false, randomCurve: true });
        $(`.tile[data-coords-id="${source.entity_uid}"] .popover-menu-2`).show();
      }
    }
    e.stopPropagation();
  });

  // --- Floating Menu Handlers ---
  $('#expand-menu').click(() => {
    $('#menu').fadeIn();
    $('#expand-menu').hide();
    $('#collapse-menu').show();
  });

  $('#collapse-menu').click(() => {
    $('#menu').fadeOut();
    $('#expand-menu').show();
    $('#collapse-menu').hide();
  });

  $('#start-battle').click(() => {
    $('#battle-turn-order').fadeIn();
    battle_setup = true;
    refreshTileSet(true);
  });

  const showConsole = () => {
    $('#console-container').fadeIn();
    $('#open-console').html('Hide Console');
  };

  const hideConsole = () => {
    $('#console-container').fadeOut();
    $('#open-console').html('Show Console');
  };

  $('#open-console').click(() => {
    $('#console-container').is(':visible') ? hideConsole() : showConsole();
  });

  $('#hide-combat-log').click(hideConsole);

  $('#start-initiative').click(() => {
    const battle_turn_order = $('.turn-order-item').map(function () {
      const { id } = $(this).data();
      const group = $(this).find('.group-select').val();
      const controller = $(this).find('.controller-select').val();
      return { id, group, controller };
    }).get();
    ajaxPost('/battle', { battle_turn_order }, (data) => {
      $('.add-to-turn-order').hide();
    }, true);
  });

  $('#end-battle').click(() => {
    ajaxPost('/stop', {}, (data) => {
      console.log('Battle stopped successfully');
    });
  });

  $('.tiles-container').on('click', '.add-to-turn-order', function (event) {
    addToInitiative($(this), battleEntityList);
    event.stopPropagation();
  });

  $('#turn-order').on('click', '.remove-turn-order-item', function () {
    $(this).closest('#turn-order-item').remove();
  });

  $('#turn-order').on('click', '.token-image', function () {
    centerOnEntityId($(this).data('id'));
  });

  $('#turn-order').on('click', '#next-turn', function () {
    ajaxPost('/next_turn', {}, (data) => {
      console.log('Next turn request successful:', data);
    });
  });

  $('#turn-order').on('click', '.turn-order-item', function () {
    centerOnEntityId($(this).data('id'));
  });

  $('#select-soundtrack').click(() => {
    $.get('/tracks', { track_id: active_track_id }, (data) => {
      $('.modal-content').html(data);
      $('#modal-1').modal('show');
    });
  });

  $('.modal-content').on('click', '.play', function () {
    const trackId = $('input[name="track_id"]:checked').val();
    ajaxPost('/sound', { track_id: trackId }, (data) => {
      console.log('Sound request successful:', data);
      $('#modal-1').modal('hide');
    });
  });

  // --- Action Button Handler ---
  $('.actions-container').on('click', '.action-button', function (e) {
    e.stopPropagation();
    const action = $(this).data('action-type');
    const opts = $(this).data('action-opts');
    let entity_uid = $(this).closest('.tile').data('coords-id') ||
      $(this).data('id') ||
      $(this).closest('.tile').find('.object-container').data('id');
    let coordsx = $(this).closest('.tile').data('coords-x') !== undefined 
        ? $(this).closest('.tile').data('coords-x') 
        : $(this).data('coords-x');
    let coordsy = $(this).closest('.tile').data('coords-y') !== undefined 
        ? $(this).closest('.tile').data('coords-y') 
        : $(this).data('coords-y');

    if (moveMode) {
      moveMode = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    const dataPayload = { id: entity_uid, action, opts };
    ajaxPost('/action', dataPayload, (data) => {
      switch (data.param[0].type) {
        case 'movement':
          moveModeCallback = (path) => {
            ajaxPost('/action', { id: entity_uid, action, opts, path },
              (data) => {
                console.log('Action request successful:', data);
                refreshTurn();
              }, true);
          };
          $('.popover-menu').hide();
          moveMode = true;
          source = { x: coordsx, y: coordsy };
          break;
        case 'select_spell':
          ajaxGet('/spells', { id: entity_uid, action, opts }, (data) => {
            $('.modal-content').html(data);
            $('#modal-1').modal('show');
          });
          break;
        case 'select_item': {
          const $entity_tile = $(`.tile[data-coords-id="${entity_uid}"]`);
          ajaxGet('/usable_items', { id: entity_uid, action, opts }, (data) => {
            $entity_tile.find('.popover-menu').html(data);
          });
          break;
        }
        case 'select_target':
          $('.popover-menu').hide();
          $('#modal-1').modal('hide');
          source = { x: coordsx, y: coordsy, entity_uid };
          targetModeMaxRange = data.range_max !== undefined ? data.range_max : data.range;
          if (data.target_hints) {
            data.target_hints.forEach(value => {
              $(`.tile[data-coords-id="${value}"] .add-to-target`).show();
            });
            multiTargetMode = true;
            max_targets = data.total_targets;
            multiTargetModeUnique = data.unique_targets === true;
            $(`.tile[data-coords-id="${entity_uid}"] .execute-action img`).attr('src', `/spells/spell_${data.spell}.png`);
            targetMode = false;
          } else {
            targetMode = true;
            globalActionInfo = action;
            globalOpts = opts;
            globalSourceEntity = entity_uid;
          }
          targetModeCallback = (target) => {
            ajaxPost('/action', { id: entity_uid, action, opts, target },
              (data) => {
                console.log('Action request successful:', data);
                refreshTurn();
              }, true);
          };
          break;
        case 'select_items':
          function initiateTransfer() {
            ajaxGet('/items', { id: entity_uid, action, opts }, (data) => {
              $('.modal-content').html(data);
              $('#modal-1').modal('show');
              $('.loot-items-form').on('submit', function (e) {
                e.preventDefault();
                fromItems = [];
                fromItemsQty = [];
                $(this).find('input[name="selected_items_target"]').each(function () {
                  fromItems.push($(this).val());
                });

                $(this).find('input.transfer-qty').each(function () {
                  fromItemsQty.push($(this).val());
                });
                toItems = []
                toItemsQty = []     
                $(this).find('input[name="selected_items_source"]').each(function () {
                  toItems.push($(this).val());
                });

                $(this).find('input.transfer-qty-source').each(function () {
                  toItemsQty.push($(this).val());
                });

                const itemsToTransfer = {
                  from: {
                    items: fromItems,
                    qty: fromItemsQty
                  },
                  to: {
                    items: toItems,
                    qty: toItemsQty
                  }
                }
                opts['items'] = itemsToTransfer;

                ajaxPost('/action', { id: entity_uid, action, opts },
                  (data) => {
                    initiateTransfer();
                  }, true);
              });
            });
          }
          initiateTransfer();
          break;
        default:
          console.log('Unknown action type:', data.param[0].type);
      }
      console.log('Action request successful:', data);
    }, true);
  });

  $('#turn-order').on('click', '#add-more', function () {
    battle_setup = !battle_setup;
    refreshTileSet(battle_setup);
  });

  $('.game-turn-container').on('click', '#player-end-turn', function () {
    ajaxPost('/end_turn', {}, (data) => {
      // Optionally hide game turn container
    });
  });

  //on mouse over an action button if there is a target, highlight the target
  $('.actions-container').on('mouseover', '.action-button', function () {
    const opts = $(this).data('action-opts');
    if (opts['target'] !== undefined && opts['target'] !== '' && opts['target'] !== null) {
      const target = opts['target'];
      const $tile = $(`.object-container[data-id="${target}"]`);
      $tile.css('background-color', 'rgba(0, 255, 0, 0.5)');
    }
  });

  $('.actions-container').on('mouseleave', '.action-button', function () {
    const opts = $(this).data('action-opts');
    if (opts['target'] !== undefined && opts['target'] !== '' && opts['target'] !== null) {
      const target = opts['target'];
      const $tile = $(`.object-container[data-id="${target}"]`);
      $tile.css('background-color', '');
    }
  });

  $('.actions-container').on('click', '.action-end-turn', function () {
    ajaxPost('/end_turn', {}, (data) => {
      //hide actions
      $('.popover-menu').hide();
    });
  });

  $('.floating-window').on('click', function () {
    let maxZIndex = 0;
    $('.floating-window').each(function () {
      maxZIndex = Math.max(maxZIndex, parseInt($(this).css('z-index')) || 0);
    });
    $(this).css('z-index', maxZIndex + 1);
  });

  $(document).on('mouseenter', '.hide-action', function () {
    const entity_uid = $(this).closest('.tile').data('coords-id');
    ajaxGet('/hide', { id: entity_uid }, (data) => {
      data.hiding_spots.forEach(value => {
        $(`.tile[data-coords-x="${value[0]}"][data-coords-y="${value[1]}"]`).css('background-color', 'rgba(0, 255, 0, 0.5)');
      });
    });
  });

  $(document).on('mouseleave', '.hide-action', () => {
    $('.tile').css('background-color', '');
  });

  Utils.draggable('#battle-turn-order');
  Utils.draggable('#console-container');

  if ($('body').data('battle-in-progress')) {
    $('#start-initiative').hide();
  }
});

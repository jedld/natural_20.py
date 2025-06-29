// --- Global Helpers & Utilities ---

let scale = 1;
let keyboardMovementMode = false;
let keyboardMovementSource = null;
let keyboardMovementPath = [];
let keyboardMovementPivotPoints = [];
let globalCanvas = null;
let globalCtx = null;

const switchPOV = (entity_uid, canvas) => {
  ajaxPost("/switch_pov", { entity_uid }, (data) => {
    console.log("Switched POV:", data);
    if (data.background) {
      Utils.updateMapDisplay(data, canvas);
    }
    Utils.refreshTileSet(
      (is_setup = false),
      (pov = true),
      (x = 0),
      (y = 0),
      (entity_uid = entity_uid),
      () => {
        const $tile = $(`.tile[data-coords-id="${entity_uid}"]`);
        centerOnTile($tile);
      },
    );
  });
};

const ajaxPost = (url, data, onSuccess, isJSON = false) => {
  $.ajax({
    url,
    type: "POST",
    data: isJSON ? JSON.stringify(data) : data,
    contentType: isJSON
      ? "application/json"
      : "application/x-www-form-urlencoded",
    success: onSuccess,
    error: (jqXHR, textStatus, errorThrown) => {
      console.error(`Error with POST ${url}:`, textStatus, errorThrown);
    },
  });
};

// Returns the center coordinates of a tile element.
const getTileCenter = (selector) => {
  const $tile = $(selector);
  const rect = $tile[0].getBoundingClientRect();
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  const mainMapArea = $('#main-map-area')[0].getBoundingClientRect();
  return {
    x: rect.left - mainMapArea.left + rect.width / 2 + scrollLeft,
    y: rect.top - mainMapArea.top + rect.height / 2 + scrollTop
  };
};

// Adds or removes an entity from the battle initiative.
function addToInitiative($btn, battleEntityList) {
  const { id, name } = $btn.data();
  const index = battleEntityList.findIndex((entity) => entity.id === id);

  if (index === -1) {
    battleEntityList.push({ id, group: "a", name });
    Utils.ajaxGet("/add", { id }, (data) => {
      $("#turn-order").append(data);
      $btn
        .find("i.glyphicon")
        .removeClass("glyphicon-plus")
        .addClass("glyphicon-minus");
      $btn.css("background-color", "red");
    });
  } else {
    battleEntityList.splice(index, 1);
    $btn
      .find("i.glyphicon")
      .removeClass("glyphicon-minus")
      .addClass("glyphicon-plus");
    $btn.css("background-color", "green");
    $(".turn-order-item")
      .filter((_, el) => $(el).text() === name)
      .remove();
  }
}

// Draws a line from a source tile to a target tile. Options let you customize
// the line width, stroke color, whether to add an arrowhead, use a curved path, etc.
function drawLine(ctx, source, targetSelector, options = {}) {
  const {
    lineWidth = 5,
    withArrow = false,
    randomCurve = false,
    strokeStyle = "green",
    text = null,
  } = options;

  const srcCenter = getTileCenter(
    `.tile[data-coords-x="${source.x}"][data-coords-y="${source.y}"]`,
  );
  const tgtCenter = getTileCenter(targetSelector);

  ctx.beginPath();
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = lineWidth;

  let angle = Math.atan2(tgtCenter.y - srcCenter.y, tgtCenter.x - srcCenter.x);

  if (randomCurve) {
    const randomAngle = (Math.random() * (90 - 20) + 20) * (Math.PI / 180);
    const controlX =
      (srcCenter.x + tgtCenter.x) / 2 +
      (Math.cos(randomAngle) * (tgtCenter.y - srcCenter.y)) / 2;
    const controlY =
      (srcCenter.y + tgtCenter.y) / 2 +
      (Math.sin(randomAngle) * (tgtCenter.y - srcCenter.y)) / 2;
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
      tgtCenter.y - headlen * Math.sin(angle - Math.PI / 6),
    );
    ctx.moveTo(tgtCenter.x, tgtCenter.y);
    ctx.lineTo(
      tgtCenter.x - headlen * Math.cos(angle + Math.PI / 6),
      tgtCenter.y - headlen * Math.sin(angle + Math.PI / 6),
    );
  }

  ctx.stroke();

  if (text !== null) {
    const textOffset = 15;
    const textX = tgtCenter.x + textOffset * Math.cos(angle);
    const textY =
      tgtCenter.y +
      (tgtCenter.y > srcCenter.y ? 1 : -1) * textOffset * Math.sin(angle);
    ctx.fillStyle = strokeStyle;
    ctx.font = "16px Arial";
    ctx.textAlign = "center";
    ctx.fillText(text, textX, textY);
  }
}

// Sends a simple command via Socket.IO.
function command(cmd) {
  socket.emit('message', {
    type: "command",
    user: username,
    message: { action: "command", command: cmd }
  });
}

// Centers the viewport on a given tile and (optionally) highlights it.
function centerOnTile(tile, highlight = false) {
  const boardWidth = $(window).width();
  const boardHeight = $(window).height();
  const tileWidth = tile.width();
  const tileHeight = tile.height();
  const offset = tile.offset();
  const { left, top } = offset;
  const scrollLeft = left - boardWidth / 2 + tileWidth / 2;
  const scrollTop = top - boardHeight / 2 + tileHeight / 2;

  $(".tile .entity").removeClass("focus-highlight");
  tile.find(".entity").addClass("focus-highlight");

  $("html, body").animate({ scrollLeft, scrollTop }, 200, () => {
    tile.fadeOut(150).fadeIn(150);
    if (highlight) {
      $(".tile").removeClass("focus-highlight-red");
      tile.addClass("focus-highlight-red");
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

// Keyboard movement controls
function handleKeyboardMovement(key, entity_uid, coordsx, coordsy) {
  console.log("handleKeyboardMovement called with:", { key, entity_uid, coordsx, coordsy });
  
  if (!keyboardMovementMode) {
    // Initialize keyboard movement mode
    console.log("Initializing keyboard movement mode");
    keyboardMovementMode = true;
    keyboardMovementSource = { x: coordsx, y: coordsy };
    keyboardMovementPath = [];
    keyboardMovementPivotPoints = [];
    moveMode = false; // Disable mouse-based movement
    globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
  }

  let newX = keyboardMovementSource.x;
  let newY = keyboardMovementSource.y;

  // Calculate new position based on key
  switch(key) {
    case 'ArrowUp':
    case 'w':
    case 'W':
      newY--;
      break;
    case 'ArrowDown':
    case 's':
    case 'S':
      newY++;
      break;
    case 'ArrowLeft':
    case 'a':
    case 'A':
      newX--;
      break;
    case 'ArrowRight':
    case 'd':
    case 'D':
      newX++;
      break;
  }

  console.log("Attempting to move to:", { newX, newY });

  // Check if this is a backtracking move
  if (keyboardMovementPath.length > 0) {
    const lastMove = keyboardMovementPath[keyboardMovementPath.length - 1];
    const isBacktracking = 
      (key === 'ArrowUp' || key === 'w' || key === 'W') && lastMove[1] < newY ||
      (key === 'ArrowDown' || key === 's' || key === 'S') && lastMove[1] > newY ||
      (key === 'ArrowLeft' || key === 'a' || key === 'A') && lastMove[0] < newX ||
      (key === 'ArrowRight' || key === 'd' || key === 'D') && lastMove[0] > newX;

    if (isBacktracking) {
      console.log("Backtracking detected, canceling last move");
      // Remove the last move from the path
      keyboardMovementPath.pop();
      // Update source position to the previous position
      if (keyboardMovementPath.length > 0) {
        const newSource = keyboardMovementPath[keyboardMovementPath.length - 1];
        keyboardMovementSource = { x: newSource[0], y: newSource[1] };
      } else {
        keyboardMovementSource = { x: coordsx, y: coordsy };
      }
      // Redraw the path
      Utils.drawMovementPath(globalCtx, keyboardMovementPath, 0, true);
      return;
    }
  }

  // Check if the new position is valid
  Utils.ajaxGet(
    "/path",
    {
      from: keyboardMovementSource,
      to: { x: newX, y: newY },
      accumulatedPath: keyboardMovementPath.length > 0 ? JSON.stringify(keyboardMovementPath) : null
    },
    (data) => {
      console.log("Path check response:", data);
      if (data.cost.budget >= 0 && data.path) {
        // Update source position
        keyboardMovementSource = { x: newX, y: newY };
        
        // Add to path
        if (keyboardMovementPath.length > 0) {
          keyboardMovementPath.pop();
        }
        keyboardMovementPath = [...keyboardMovementPath, ...data.path];
        
        console.log("Updated path:", keyboardMovementPath);
        
        // Draw the path
        Utils.drawMovementPath(globalCtx, keyboardMovementPath, data.cost.budget, data.placeable);
      } else {
        console.log("Invalid move - path not available or budget exceeded");
      }
    }
  );
}

function executeKeyboardMovement(entity_uid, action, opts) {
  console.log("Executing keyboard movement");
  ajaxPost(
    "/action",
    {
      id: entity_uid,
      action: "MoveAction",
      opts: {
        action_type: "move",
        source: entity_uid
      },
      path: keyboardMovementPath
    },
    (data) => {
      console.log("Movement executed:", data);
      if (data.status === 'ok') {
        refreshTurn();
        // hide the popover menu
        $(".popover-menu").hide();
      } else if (data.param && data.param[0].type === "movement") {
        // Handle movement selection if needed
        moveModeCallback = (path) => {
          ajaxPost(
            "/action",
            { id: entity_uid, action, opts, path },
            (data) => {
              console.log("Action request successful:", data);
              refreshTurn();
            },
            true
          );
        };
        $(".popover-menu").hide();
        moveMode = true;
        source = { x: keyboardMovementSource.x, y: keyboardMovementSource.y };
        accumulatedPath = [];
        pivotPoints = [];
      }
      resetKeyboardMovement();
    },
    true
  );
}

function resetKeyboardMovement() {
  keyboardMovementMode = false;
  keyboardMovementSource = null;
  keyboardMovementPath = [];
  keyboardMovementPivotPoints = [];
  globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
}

// --- Document Ready: Event Bindings & Main Logic ---
$(document).ready(() => {
  let active_background_sound = null;
  let lastMovedEntityBeforeRefresh = null;
  let active_track_id = -1;
  const battleEntityList = [];

  let backgroundSoundStartTime = $("body").data("soundtrack-time");
  let pageRenderTime = new Date().getTime();

  // --- Canvas Setup ---
  const tile_size = $(".tiles-container").data("tile-size");
  globalCanvas = document.createElement("canvas");
  globalCanvas.width = window.innerWidth;
  globalCanvas.height = window.innerHeight;
  globalCanvas.style.position = "fixed";
  globalCanvas.style.top = "0";
  globalCanvas.style.left = "0";
  globalCanvas.style.width = "100%";
  globalCanvas.style.height = "100%";
  globalCanvas.style.zIndex = 1000;
  globalCanvas.style.pointerEvents = "none";
  $("body").append(globalCanvas);
  globalCtx = globalCanvas.getContext("2d");

  // Update canvas size on window resize
  $(window).on('resize', function() {
    globalCanvas.width = window.innerWidth;
    globalCanvas.height = window.innerHeight;
  });

  // Plays a background sound (stopping any previous one).
  const playSound = (url, track_id, volume, time_override = null) => {
    const elapsed = (Date.now() - pageRenderTime) / 1000;
    var seekTime;
    if (time_override !== null) {
      seekTime = time_override;
    } else {
      seekTime = backgroundSoundStartTime + elapsed;
    }

    if (active_background_sound) active_background_sound.pause();

    active_background_sound = new Audio(`/assets/${url}`);
    active_background_sound.loop = true;
    active_background_sound.currentTime = seekTime;
    active_background_sound.volume = volume ? volume / 100 : 0.5;
    active_track_id = track_id;
    active_background_sound.play();
    $(".volume-slider").val(active_background_sound.volume * 100);
  };

  const username = $("body").data("username");
  
  // Determine if we're running in AWS or locally
  const isAWS = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
  
  // Configure Socket.IO client with proper settings
  const socket = io({
    transports: ['websocket'],  // Prefer WebSocket only since we're using eventlet
    reconnection: true,
    reconnectionAttempts: 10,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 20000,
    autoConnect: true,
    path: '/socket.io',
    forceNew: false,
    multiplex: true,
    withCredentials: true,
    // In AWS, use the current hostname and protocol
    // In local development, use localhost
    host: isAWS ? window.location.hostname : 'localhost',
    port: isAWS ? window.location.port : '5001',
    // Add secure option for HTTPS
    secure: isAWS && window.location.protocol === 'https:'
  });
  
  if ($("body").data("waiting-for-reaction")) {
    $("#reaction-modal").modal("show");
  }

  socket.on("connect", () => {
    console.log("Connected to the server");
    socket.emit("register", { username });
  });
  
  socket.on('connect_error', (error) => {
    console.log('Connection error:', error);
  });

  socket.on('reconnect_attempt', (attemptNumber) => {
    console.log('Reconnection attempt:', attemptNumber);
  });

  socket.on('reconnect', () => {
    console.log('Reconnected successfully');
    // Re-register after reconnection
    socket.emit("register", { username });
  });

  socket.on('disconnect', (reason) => {
    console.log('Disconnected:', reason);
  });

  socket.on('error', (error) => {
    console.error('Socket error:', error);
  });

  const refreshTurnOrder = () => {
    Utils.ajaxGet("/turn_order", {}, (data) => {
      $("#turn-order").html(data);
      $("#battle-turn-order").show();
    });
  };

  const refreshTurn = () => {
    Utils.ajaxGet("/turn", {}, (data) => {
      $(".game-turn-container").html(data).show();
    });
  };

  Utils.refreshTileSet();

  // --- Socket Message Handler ---
  socket.on("message", (data) => {
    console.log("Message received:", data);
    switch (data.type) {
      case "refresh_map": {
        Utils.refreshTileSet();
        break;
      }
      case "map": {
        const { message: map_url, width, height, image_offset_px } = data;
        $(".tiles-container").data({ width, height });
        $(".image-container img")
          .attr("src", map_url)
          .css({ width: `${width}px`, objectFit: 'cover', objectPosition: 'top' });
        const tile_size = $(".tiles-container").data("tile-size");
        $(".image-container").css({
          height: `${height}px`,
          top: image_offset_px[1] + tile_size,
          left: image_offset_px[0] + tile_size,
        });
        const canvas = document.querySelector("canvas");
        canvas.width = width + tile_size;
        canvas.height = height + tile_size;
        Utils.refreshTileSet();
        break;
      }
      case "conversation": {
        // Handle real-time conversation updates
        const { entity_id, message } = data.message;
      
        // Find the tile with the entity
        const $tile = $(`.tile[data-coords-id="${entity_id}"]`);
        if ($tile.length) {
          // Check if conversation bubble already exists
          let $bubble = $tile.find('.conversation-bubble');
        
          if ($bubble.length) {
            // Update existing bubble
            $bubble.find('.bubble-content').text(message);
            $bubble.removeClass('minimized');
            $bubble.find('.bubble-content').show();
            $bubble.find('.bubble-minimized').hide();
          } else {
            // Create new bubble
            $bubble = $(`
              <div class="conversation-bubble">
                <div class="bubble-content">${message}</div>
                <div class="bubble-minimized" style="display: none;">
                  <i class="glyphicon glyphicon-comment"></i>
                </div>
                <button class="close-bubble" onclick="Utils.dismissBubble(this.parentElement); event.stopPropagation();">×</button>
              </div>
            `);
            $tile.append($bubble);
          }

          setTimeout(() => {
            $tile.find('.conversation-bubble').fadeOut(500, function() {
              $(this).remove();
            });
          }, 10000);
        }
        break;
      }
      case "move": {
        const animationBuffer = data.message.animation_log;
        const animateFunction = (animationLog, idx) => {
          if (idx >= animationLog.length) {
            Utils.refreshTileSet();
            return;
          }
          const [entity_uid, path, action] = animationLog[idx];
          const $tile = $(`.tile[data-coords-id="${entity_uid}"]`);
          if (action) {
            const opts = {
              lineWidth: 3,
              withArrow: true,
              randomCurve: true,
              strokeStyle: action.type === "attack" ? "red" : "blue",
              text: action.label,
            };
            drawLine(
              globalCtx,
              { x: $tile.data("coords-x"), y: $tile.data("coords-y") },
              `.tile[data-coords-id="${action.target}"]`,
              opts,
            );
          }
          const tileRect = $tile[0].getBoundingClientRect();
          const scrollLeft =
            window.pageXOffset || document.documentElement.scrollLeft;
          const scrollTop =
            window.pageYOffset || document.documentElement.scrollTop;
          let prevX = tileRect.left + scrollLeft;
          let prevY = tileRect.top + scrollTop;
          const moveFunc = (p, index) => {
            if (index >= p.length) {
              animateFunction(animationLog, idx + 1);
              return;
            }
            const [x, y] = p[index];
            const $newTile = $(
              `.tile[data-coords-x="${x}"][data-coords-y="${y}"]`,
            );
            const newRect = $newTile[0].getBoundingClientRect();
            const imageContainer = $('.image-container')[0].getBoundingClientRect();
            const tile_size = $('.tiles-container').data('tile-size');
            const newX = newRect.left - imageContainer.left + tile_size;
            const newY = newRect.top - imageContainer.top + tile_size;
            
            // Set initial position if this is the first move
            if (index === 0) {
              $tile.css({ 
                position: 'absolute',
                top: newY,
                left: newX
              });
              prevX = newX;
              prevY = newY;
              moveFunc(p, index + 1);
              return;
            }
            
            // Move to the next position in the path
            setTimeout(() => {
              $tile.css({ 
                position: 'absolute',
                top: newY,
                left: newX,
                transition: 'all 0.3s ease-in-out'
              });
              prevX = newX;
              prevY = newY;
              moveFunc(p, index + 1);
            }, 300);
          };
          moveFunc(path, 0); // Start from index 0 to set initial position
        };
        if (animationBuffer) {
          animateFunction(animationBuffer, 0);
        } else {
          Utils.refreshTileSet();
        }
        break;
      }
      case "message":
        console.log(data.message);
        break;
      case "error":
        console.error(data.message);
        break;
      case "console":
        $("#console-container #console").append(`<p>${data.message}</p>`);
        $("#console-container").scrollTop(
          $("#console-container")[0].scrollHeight,
        );
        break;
      case "track":
        console.log("Playing track:", data.message);
        playSound(
          data.message.url,
          data.message.track_id,
          data.message.volume,
          0,
        );
        break;
      case "prompt": {
        alert(data.message);
        ajaxPost(
          "/response",
          { response: "", callback: data.callback },
          (resp) => console.log("Response sent successfully:", resp),
          true,
        );
        break;
      }
      case "turn":
        refreshTurn();
        break;
      case "focus":
        centerOnTileXY(data.message.x, data.message.y, true);
        break;
      case "stoptrack":
        if (active_background_sound) {
          const audioCtx = new AudioContext();
          const source = audioCtx.createMediaElementSource(
            active_background_sound,
          );
          const gainNode = audioCtx.createGain();
          source.connect(gainNode);
          gainNode.connect(audioCtx.destination);
          gainNode.gain.setValueAtTime(1, audioCtx.currentTime);
          gainNode.gain.linearRampToValueAtTime(0, audioCtx.currentTime + 2);
          gainNode.addEventListener("ended", () => {
            active_background_sound.pause();
            active_background_sound = null;
            active_track_id = -1;
          });
        }
        break;
      case "volume":
        if (active_background_sound) {
          active_background_sound.volume = data.message.volume / 100;
          $(".volume-slider").val(data.message.volume);
        }
        break;
      case "initiative":
        refreshTurnOrder();
        $("#start-initiative, #start-battle").hide();
        $("#end-battle").show();
        break;
      case "stop":
        $("#turn-order").html("");
        $(".game-turn-container").hide();
        $("#battle-turn-order").fadeOut();
        $("#start-initiative, #start-battle").show();
        $("#end-battle").hide();
        break;
      case "reaction":
        Utils.ajaxGet("/reaction", {}, (data) => {
          $("#reaction-modal .reaction-content").html(data);
          $("#reaction-modal").modal("show");
        });
        break;
      case "dismiss_reaction":
        $("#reaction-modal").modal("hide");
        break;
      case "switch_map":
        var map_id = data.message.map;
        Utils.switchMap(map_id, globalCanvas);
        break;

      default:
        console.log("Unknown message type:", data.type);
    }
  });

  let currentSoundtrackId = $("body").data("soundtrack-id");
  $("body").on("click", () => {
    // Recover soundtrack state on first click.
    let currentSoundtrackUrl = $("body").data("soundtrack-url");
    let currentSoundtrackVolume = $("body").data("soundtrack-volume");
    if (currentSoundtrackId) {
      playSound(
        currentSoundtrackUrl,
        currentSoundtrackId,
        currentSoundtrackVolume,
      );
      currentSoundtrackId = null;
    }
  });

  // --- Form & Slider Handlers ---
  $("#reaction-form").on("submit", (event) => {
    event.preventDefault();
    const reaction = $('#reaction-form input[name="reaction"]:checked').val();
    ajaxPost("/reaction", { reaction }, (data) => {
      console.log("Reaction submitted successfully:", data);
      $("#reaction-modal").modal("hide");
    });
  });

  $("#modal-1 .modal-content").on("input", ".volume-slider", function () {
    if (active_background_sound) {
      ajaxPost(
        "/volume",
        { volume: $(this).val() },
        () => console.log("Volume updated successfully"),
        true,
      );
    }
  });

  $("#reloadModal").on("submit", "#reload-map-form", function (event) {
    event.preventDefault();
    ajaxPost("/reload_map", {}, (data) => {
      console.log("Reload request successful:", data);
      $("#reloadModal").modal("hide");
      Utils.refreshTileSet();
    });
  });

  $("#mapModal").on("change", "#map-select", function (event) {
    event.preventDefault();
    const map_id = $("#map-select").val();
    Utils.switchMap(map_id, globalCanvas);
  });

  // --- Tile & Action Event Handlers ---
  $(".tiles-container").on("click", ".execute-action", (e) => {
    targetModeCallback(multiTargetList);
    targetMode = multiTargetMode = false;
    valid_target_cache = {};
    multiTargetList = [];
    $(".add-to-target, .popover-menu-2").hide();
    globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
    e.stopPropagation();
  });

  $(".tiles-container").on("click", ".tile", function (e) {
    const $tile = $(this);
    const coordsx = $tile.data("coords-x");
    const coordsy = $tile.data("coords-y");

    if (targetMode) {
      targetModeCallback({ x: coordsx, y: coordsy });
      targetMode = false;
      valid_target_cache = {};
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
      $(".tile").css("border", "none");
    } else if (moveMode) {
      if (coordsx !== source.x || coordsy !== source.y) {
        moveMode = false;
        move_path_cache = {};
        globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
        $(".tile").css("border", "none");
        moveModeCallback(movePath);
        movePath = [];
      }
    } else {
      if (e.metaKey || e.ctrlKey) {
        Utils.refreshTileSet(false, true, coordsx, coordsy);
      } else if (e.metaKey || e.shiftKey) {
        ajaxPost("/focus", { x: coordsx, y: coordsy }, (data) => {
          console.log("Focus request successful:", data);
        });
      } else {
        $(".popover-menu").hide();
        let entity_uid =
          $tile.data("coords-id") || $tile.find(".object-container").data("id");
        Utils.ajaxGet("/actions", { id: entity_uid }, (data) => {
          const $menu = $tile.find(".popover-menu");
          $menu.html(data).toggle();
          const tileRightEdge = $menu.offset().left + $menu.outerWidth();
          const windowRightEdge = $(window).width();
          $menu.css("top", `${tile_size}px`);
          if (windowRightEdge < tileRightEdge) {
            $menu.css("left", `-=${tileRightEdge - windowRightEdge}`);
          }
        });
      }
    }
  });

  // Mode & State Variables
  let valid_target_cache = {};
  let move_path_cache = {};
  let currentPosition = null;
  let accumulatedPath = [];
  let pivotPoints = [];
  let moveMode = false,
    targetMode = false,
    coneMode = false,
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
  // Add debounce timer variable
  let pathDebounceTimer = null;

  $(".tiles-container").on(
    "click",
    ".show-note-btn, .object-note-overlay",
    function (e) {
      e.stopPropagation();
    },
  );

  $(".zoom-in").on("click", () => {
    scale += 0.1;
    $("#main-map-area").css({
      "transform": `scale(${scale})`,
      "transform-origin": "center center"
    });
    globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
  });

  $(".zoom-out").on("click", () => {
    scale -= 0.1;
    $("#main-map-area").css({
      "transform": `scale(${scale})`,
      "transform-origin": "center center"
    });
    globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
  });

  // Draws a target line from a source to a given set of coordinates.
  function drawTargetLine(ctx, source, coordsx, coordsy, valid_target = true) {
    const currentDistance =
      Math.floor(
        Utils.euclideanDistance(source.x, source.y, coordsx, coordsy),
      ) * 5;
    const scrollLeft =
      window.pageXOffset || document.documentElement.scrollLeft;
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    ctx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
    ctx.beginPath();
    ctx.strokeStyle = "red";
    ctx.lineWidth = 5;
    const srcCenter = getTileCenter(
      `.tile[data-coords-x="${source.x}"][data-coords-y="${source.y}"]`,
    );
    const tgtCenter = getTileCenter(
      `.tile[data-coords-x="${coordsx}"][data-coords-y="${coordsy}"]`,
    );
    ctx.moveTo(srcCenter.x, srcCenter.y);
    ctx.lineTo(tgtCenter.x, tgtCenter.y);
    const arrowSize = 10;
    const angle = Math.atan2(
      tgtCenter.y - srcCenter.y,
      tgtCenter.x - srcCenter.x,
    );
    if (Math.floor(currentDistance) <= targetModeMaxRange && valid_target) {
      ctx.moveTo(
        tgtCenter.x - arrowSize * Math.cos(angle - Math.PI / 6),
        tgtCenter.y - arrowSize * Math.sin(angle - Math.PI / 6),
      );
      ctx.lineTo(tgtCenter.x, tgtCenter.y);
      ctx.lineTo(
        tgtCenter.x - arrowSize * Math.cos(angle + Math.PI / 6),
        tgtCenter.y - arrowSize * Math.sin(angle + Math.PI / 6),
      );
    } else {
      ctx.moveTo(tgtCenter.x - arrowSize, tgtCenter.y - arrowSize);
      ctx.lineTo(tgtCenter.x + arrowSize, tgtCenter.y + arrowSize);
      ctx.moveTo(tgtCenter.x + arrowSize, tgtCenter.y - arrowSize);
      ctx.lineTo(tgtCenter.x - arrowSize, tgtCenter.y + arrowSize);
    }
    ctx.font = "20px Arial";
    ctx.fillStyle = "red";
    ctx.fillText(
      `${currentDistance}ft`,
      tgtCenter.x,
      tgtCenter.y + $(".tile").height() / 2,
    );
    ctx.stroke();
  }


  // Character switcher
  $('#floating-entity-portraits').on('click', '.floating-entity-portrait', function() {
    const entity_uid = $(this).data('id');
    switchPOV(entity_uid, globalCanvas);
  });

  // Highlight tile info or draw movement data on hover.
  $(".tiles-container").on("mouseover", ".tile", function () {
    const coordsx = $(this).data("coords-x");
    const coordsy = $(this).data("coords-y");
    let tooltip = $(this).data("tooltip") || "";
    if (targetMode) {
      $(".highlighted").removeClass("highlighted");
      $(".tile").css("z-index", 0);
      $(this).css("z-index", 999);
      const data_payload = JSON.stringify({
        id: globalSourceEntity,
        x: coordsx,
        y: coordsy,
        coneMode: coneMode,
        action_info: globalActionInfo,
        opts: globalOpts,
      });

      if (valid_target_cache[`${coordsx}-${coordsy}`]) {
        drawTargetLine(globalCtx, source, coordsx, coordsy, valid_target_cache[`${coordsx}-${coordsy}`]);
      } else {
        Utils.ajaxGet("/target", { payload: data_payload }, (data) => {
          const { adv_info, valid_target } = data;
          // cache the valid_target value based on the x, y coords

          if (data.target_squares && data.target_squares.length > 0) {
            // set the target squares
            // unset all tiles
            $(".tile").css("border", "none");
            data.target_squares.forEach((value) => {
              $(`.tile[data-coords-x="${value[0]}"][data-coords-y="${value[1]}"]`).css("border", "2px solid red");
            });
          } else {
            valid_target_cache[`${coordsx}-${coordsy}`] = valid_target;
            drawTargetLine(globalCtx, source, coordsx, coordsy, valid_target);
          }
            if (adv_info) {
              adv_info[0].forEach(
                (value) =>
                  (tooltip += `<p><span style="color: green;">+${value}</span></p>`),
              );
              adv_info[1].forEach(
                (value) =>
                  (tooltip += `<p><span style="color: red;">-${value}</span></p>`),
              );
            }

          $("#coords-box").html(
            `<p>X: ${coordsx}</p><p>Y: ${coordsy}</p>${tooltip}`,
          );
        });
      }
    } else {
      $("#coords-box").html(
        `<p>X: ${coordsx}</p><p>Y: ${coordsy}</p>${tooltip}`,
      );
      if (moveMode && (source.x !== coordsx || source.y !== coordsy)) {
        const cacheKey = `${source.x}-${source.y}-${coordsx}-${coordsy}-${pivotPoints.join("-")}`;

        // Function to process and draw movement path
        const processMovementData = (data) => {
          if (data.cost.budget < 0) return;

          const available_cost = (data.cost.original_budget - data.cost.budget) * 5;
          if (data.path) {
            // Create a new movement path starting with accumulated path
            movePath = [...accumulatedPath];
            if (accumulatedPath.length > 0) {
              movePath.pop();
            }

            // Store current position for potential pivot points
            currentPosition = {
              x: coordsx,
              y: coordsy,
              cost: available_cost,
              path: data.path
            };

            // Add the new path segment to the movement path
            movePath = [...movePath, ...data.path];
            // Draw the complete path
            Utils.drawMovementPath(globalCtx, movePath, available_cost, data.placeable);
          }
        };

        // Check if we have cached data for this path
        if (move_path_cache[cacheKey]) {
          processMovementData(move_path_cache[cacheKey]);
        } else {
          // Clear any existing timer
          if (pathDebounceTimer) {
            clearTimeout(pathDebounceTimer);
          }
          
          // Set a new timer to delay the path request
          pathDebounceTimer = setTimeout(() => {
            // Fetch path data from server
            Utils.ajaxGet(
              "/path",
              {
                from: source,
                to: { x: coordsx, y: coordsy },
                accumulatedPath: accumulatedPath.length > 0 ? JSON.stringify(accumulatedPath) : null
              },
              (data) => {
                // Cache the result
                move_path_cache[cacheKey] = data;
                processMovementData(data);
              }
            );
          }, 200); // 0.2 seconds delay
        }
      }
    }
  });

  // Add mouseout handler to clear the debounce timer
  $(".tiles-container").on("mouseout", ".tile", function() {
    if (pathDebounceTimer) {
      clearTimeout(pathDebounceTimer);
      pathDebounceTimer = null;
    }
  });

  // Example: add all entities to initiative.
  $("#add-all-entities").on("click", function (event) {
    $(".tile").each(function () {
      const entity_uid = $(this).data("coords-id");
      const $btn = $(this).find("button.add-to-turn-order");
      if (entity_uid && $btn.length) {
        addToInitiative($btn, battleEntityList);
      }
    });
  });

  // Cancel ongoing interactions on Escape.
  $(document).on("keydown", (event) => {
    if (event.keyCode === 27) {
      if (moveMode || targetMode || multiTargetMode || coneMode) {
        moveMode = targetMode = multiTargetMode = coneMode = false;
        accumulatedPath = [];
        pivotPoints = [];
        valid_target_cache = {};
        move_path_cache = {};
        multiTargetList = [];
        globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
        $(".tile").css("border", "none");
        globalActionInfo = globalOpts = null;
      }
      $(".add-to-target, .popover-menu-2, .popover-menu").hide();
    }
    // if 'q' is pressed, toggle move path
    if (event.keyCode === 81) {
      // get current mouse tile coords
      if (currentPosition) {
        const coordsx = currentPosition.x;
        const coordsy = currentPosition.y;
        if (source.x !== coordsx || source.y !== coordsy) {
          pivotPoints.push([source.x, source.y]);
          accumulatedPath = accumulatedPath.concat(currentPosition.path);
          source = { x: coordsx, y: coordsy };
        }
      }
    }
  });

  // Cancel interactions on right-click.
  $("#main-map-area").on("contextmenu", function (e) {
    if (targetMode || multiTargetMode || moveMode) {
      e.preventDefault();
      targetMode = multiTargetMode = moveMode = coneMode = false;
      accumulatedPath = [];
      pivotPoints = [];
      valid_target_cache = {};
      move_path_cache = {};
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
      $(".tile").css("border", "none");
      $(".add-to-target, .popover-menu-2").hide();
    }
  });

  // Multi-target selection.
  $(".tiles-container").on("click", ".add-to-target", function (e) {
    const entity_uid = $(this).closest(".tile").data("coords-id");
    if (!multiTargetList.includes(entity_uid) || !multiTargetModeUnique) {
      if (multiTargetList.length < max_targets) {
        multiTargetList.push(entity_uid);
        if (multiTargetModeUnique) $(this).hide();
        drawLine(globalCtx, source, coordsx, coordsy, {
          lineWidth: 3,
          withArrow: false,
          randomCurve: true,
        });
        $(
          `.tile[data-coords-id="${source.entity_uid}"] .popover-menu-2`,
        ).show();
      }
    }
    e.stopPropagation();
  });

  // --- Floating Menu Handlers ---
  $("#expand-menu").click(() => {
    $("#menu").fadeIn();
    $("#expand-menu").hide();
    $("#collapse-menu").show();
  });

  $("#collapse-menu").click(() => {
    $("#menu").fadeOut();
    $("#expand-menu").show();
    $("#collapse-menu").hide();
  });

  $("#start-battle").click(() => {
    $("#battle-turn-order").fadeIn();
    battle_setup = true;
    Utils.refreshTileSet(true);
  });

  const showConsole = () => {
    $("#console-container").fadeIn();
    $("#open-console").html("Hide Console");
  };

  const hideConsole = () => {
    $("#console-container").fadeOut();
    $("#open-console").html("Show Console");
  };

  $("#open-console").click(() => {
    $("#console-container").is(":visible") ? hideConsole() : showConsole();
  });

  $("#hide-combat-log").click(hideConsole);

  $("#start-initiative").click(() => {
    const battle_turn_order = $(".turn-order-item")
      .map(function () {
        const { id } = $(this).data();
        const group = $(this).find(".group-select").val();
        const controller = $(this).find(".controller-select").val();
        return { id, group, controller };
      })
      .get();
    ajaxPost(
      "/battle",
      { battle_turn_order },
      (data) => {
        $(".add-to-turn-order").hide();
      },
      true,
    );
  });

  $("#end-battle").click(() => {
    ajaxPost("/stop", {}, (data) => {
      console.log("Battle stopped successfully");
    });
  });

  $(".tiles-container").on("click", ".add-to-turn-order", function (event) {
    addToInitiative($(this), battleEntityList);
    event.stopPropagation();
  });

  $("#turn-order").on("click", ".remove-turn-order-item", function () {
    $(this).closest("#turn-order-item").remove();
  });

  $("#turn-order").on("click", ".token-image", function () {
    centerOnEntityId($(this).data("id"));
  });

  $("#turn-order").on("click", "#next-turn", function () {
    ajaxPost("/next_turn", {}, (data) => {
      console.log("Next turn request successful:", data);
    });
  });

  $("#turn-order").on("click", ".turn-order-item", function () {
    centerOnEntityId($(this).data("id"));
  });

  $("#select-soundtrack").click(() => {
    $.get("/tracks", { track_id: active_track_id }, (data) => {
      $("#modal-1 .modal-content").html(data);
      $("#modal-1").modal("show");
    });
  });

  $("#modal-1 .modal-content").on("click", ".play", function () {
    const trackId = $('input[name="track_id"]:checked').val();
    ajaxPost(
      "/sound",
      { track_id: trackId },
      (data) => {
        console.log("Sound request successful:", data);
        $("#modal-1").modal("hide");
      },
      (isJSON = true),
    );
  });

  $("#reload-map").click(() => {
    Utils.ajaxPost("/reload_map", {}, (data) => {
      console.log("Map reloaded successfully:", data);
      Utils.refreshTileSet();
    });
  });

  function handleAction(entity_uid, action, opts, coordsx, coordsy, data) {
    if (data.status === 'ok') {
      refreshTurn();
      // hide the popover menu
      $(".popover-menu").hide();
      return;
    }

    switch (data.param[0].type) {
      case "movement":
        moveModeCallback = (path) => {
          ajaxPost(
            "/action",
            { id: entity_uid, action, opts, path },
            (data) => {
              console.log("Action request successful:", data);
              refreshTurn();
            },
            true,
          );
        };
        $(".popover-menu").hide();
        moveMode = true;
        source = { x: coordsx, y: coordsy };
        accumulatedPath = [];
        pivotPoints = [];
        break;
      case "select_spell":
        Utils.ajaxGet("/spells", { id: entity_uid, action, opts }, (data) => {
          $("#modal-1 .modal-content").html(data);
          $("#modal-1").modal("show");
        });
        break;
      case "select_item": {
        const $entity_tile = $(`.tile[data-coords-id="${entity_uid}"]`);
        Utils.ajaxGet(
          "/usable_items",
          { id: entity_uid, action, opts },
          (data) => {
            $entity_tile.find(".popover-menu").html(data);
          },
        );
        break;
      }
      case "select_choice": {
        const choices = data.param[0].choices;
        // create a modal with a list of choices
        const $modal = $(
          '<div class="modal fade" id="select-choice-modal" tabindex="-1" role="dialog" aria-labelledby="select-choice-modal-label" aria-hidden="true">',
        );
        $modal.html(`
          <div class="modal-dialog" role="document">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title" id="select-choice-modal-label">Select an option</h5>
                <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                  <span aria-hidden="true">&times;</span>
                </button>
              </div>
              <div class="modal-body">
                <ul class="list-group">
                  ${choices.map((choice) => `<li class="list-group-item choice-item" data-choice="${choice[1]}">${choice[0]}</li>`).join("")}
                </ul>
              </div>
            </div>
          </div>
        `);
        $("body").append($modal);
        $modal.modal("show");

        // Add click handler directly to the modal
        $modal.on("click", ".choice-item", function () {
          const choice = $(this).data("choice");
          $modal.modal("hide");
          ajaxPost(
            "/action",
            { id: entity_uid, action, opts, choice },
            (data) => {
              $("#modal-1").modal("hide");
              opts["choice"] = choice;
              handleAction(entity_uid, action, opts, coordsx, coordsy, data);
            },
            true,
          );
        });
        break;
      }
      case "select_cone":
        $(".popover-menu").hide();
        $("#modal-1").modal("hide");
        source = { x: coordsx, y: coordsy, entity_uid };
        targetModeMaxRange =
          data.range_max !== undefined ? data.range_max : data.range;
          coneMode = true
          targetMode = true;
          globalActionInfo = action;
          globalOpts = opts;
          globalSourceEntity = entity_uid;
        targetModeCallback = (target) => {
          ajaxPost(
            "/action",
            { id: entity_uid, mode: 'cone', action, opts, target },
            (data) => {
              console.log("Action request successful:", data);
              refreshTurn();
            },
            true,
          );
        };
        break;
      case "select_target":
        $(".popover-menu").hide();
        $("#modal-1").modal("hide");
        source = { x: coordsx, y: coordsy, entity_uid };
        targetModeMaxRange =
          data.range_max !== undefined ? data.range_max : data.range;
        if (data.target_hints) {
          data.target_hints.forEach((value) => {
            $(`.tile[data-coords-id="${value}"] .add-to-target`).show();
          });
          multiTargetMode = true;
          max_targets = data.total_targets;
          multiTargetModeUnique = data.unique_targets === true;
          targetMode = false;
          coneMode = false;
          valid_target_cache = {};
        } else {
          targetMode = true;
          coneMode = false;
          globalActionInfo = action;
          globalOpts = opts;
          globalSourceEntity = entity_uid;
        }
        targetModeCallback = (target) => {
          ajaxPost(
            "/action",
            { id: entity_uid, action, opts, target },
            (data) => {
              console.log("Action request successful:", data);
              refreshTurn();
            },
            true,
          );
        };
        break;
      case "select_empty_space":
        $(".popover-menu").hide();
        $("#modal-1").modal("hide");

        source = { x: coordsx, y: coordsy, entity_uid };
        targetModeMaxRange =
          data.range_max !== undefined ? data.range_max : data.range;
        targetMode = true;
        globalActionInfo = action;
        globalOpts = opts;
        globalSourceEntity = entity_uid;
        targetModeCallback = (target) => {
          ajaxPost(
            "/action",
            { id: entity_uid, action, opts, target },
            (data) => {
              console.log("Action request successful:", data);
              refreshTurn();
            },
            true,
          );
        };
        break;
      case "select_items":
        function initiateTransfer() {
          Utils.ajaxGet("/items", { id: entity_uid, action, opts }, (data) => {
            $("#modal-1 .modal-content").html(data);
            $("#modal-1").modal("show");
            $(".loot-items-form").on("submit", function (e) {
              e.preventDefault();
              fromItems = [];
              fromItemsQty = [];
              $(this)
                .find('input[name="selected_items_target"]')
                .each(function () {
                  fromItems.push($(this).val());
                });

              $(this)
                .find("input.transfer-qty")
                .each(function () {
                  fromItemsQty.push($(this).val());
                });
              toItems = [];
              toItemsQty = [];
              $(this)
                .find('input[name="selected_items_source"]')
                .each(function () {
                  toItems.push($(this).val());
                });

              $(this)
                .find("input.transfer-qty-source")
                .each(function () {
                  toItemsQty.push($(this).val());
                });

              const itemsToTransfer = {
                from: {
                  items: fromItems,
                  qty: fromItemsQty,
                },
                to: {
                  items: toItems,
                  qty: toItemsQty,
                },
              };
              opts["items"] = itemsToTransfer;

              ajaxPost(
                "/action",
                { id: entity_uid, action, opts },
                (data) => {
                  initiateTransfer();
                },
                true,
              );
            });
          });
        }
        initiateTransfer();
        break;
      default:
        console.log("Unknown action type:", data.param[0].type);
    }
    console.log("Action request successful:", data);
  }

  // --- Action Button Handler ---
  $(".actions-container").on("click", ".action-button", function (e) {
    e.stopPropagation();
    const action = $(this).data("action-type");
    const opts = $(this).data("action-opts");
    let entity_uid =
      $(this).closest(".tile").data("coords-id") ||
      $(this).data("id") ||
      $(this).closest(".tile").find(".object-container").data("id");
    let coordsx =
      $(this).closest(".tile").data("coords-x") !== undefined
        ? $(this).closest(".tile").data("coords-x")
        : $(this).data("coords-x");
    let coordsy =
      $(this).closest(".tile").data("coords-y") !== undefined
        ? $(this).closest(".tile").data("coords-y")
        : $(this).data("coords-y");

    if (moveMode) {
      moveMode = false;
      accumulatedPath = [];
      move_path_cache = {};
      pivotPoints = [];
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
      $(".tile").css("border", "none");
    }
    const dataPayload = { id: entity_uid, action, opts };
    ajaxPost(
      "/action",
      dataPayload,
      (data) => handleAction(entity_uid, action, opts, coordsx, coordsy, data),
      true,
    );
  });

  // Add keyboard event handler for movement
  $(document).on("keydown", function(e) {
    // Check for popover menu instead of actions-container
    const $popoverMenu = $(".popover-menu:visible");
    if ($popoverMenu.length) {
      const $tile = $popoverMenu.closest(".tile");
      if ($tile.length) {
        const entity_uid = $tile.data("coords-id");
        const coordsx = $tile.data("coords-x");
        const coordsy = $tile.data("coords-y");

        console.log("Action bar visible for entity:", entity_uid, "at coords:", coordsx, coordsy);

        // Handle movement keys
        if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "w", "a", "s", "d", "W", "A", "S", "D"].includes(e.key)) {
          e.preventDefault(); // Prevent page scrolling
          console.log("Movement key pressed:", e.key);
          handleKeyboardMovement(e.key, entity_uid, coordsx, coordsy);
        }
        // Handle Enter key to execute movement
        else if (e.key === "Enter" && keyboardMovementMode) {
          e.preventDefault();
          console.log("Executing keyboard movement");
          const action = "move";
          const opts = {};
          executeKeyboardMovement(entity_uid, action, opts);
        }
        // Handle Escape key to cancel movement
        else if (e.key === "Escape" && keyboardMovementMode) {
          e.preventDefault();
          console.log("Cancelling keyboard movement");
          resetKeyboardMovement();
        }
      }
    }
  });

  $("#turn-order").on("click", "#add-more", function () {
    battle_setup = !battle_setup;
    Utils.refreshTileSet(battle_setup);
  });

  $(".game-turn-container").on("click", "#player-end-turn", function () {
    ajaxPost("/end_turn", {}, (data) => {
      // Optionally hide game turn container
    });
  });

  //on mouse over an action button if there is a target, highlight the target
  $(".actions-container").on("mouseover", ".action-button", function () {
    const opts = $(this).data("action-opts");
    if (
      opts["target"] !== undefined &&
      opts["target"] !== "" &&
      opts["target"] !== null
    ) {
      const target = opts["target"];
      const $tile = $(`.object-container[data-id="${target}"]`);
      $tile.css("background-color", "rgba(0, 255, 0, 0.5)");
    }
  });

  $(".actions-container").on("mouseleave", ".action-button", function () {
    const opts = $(this).data("action-opts");
    if (
      opts["target"] !== undefined &&
      opts["target"] !== "" &&
      opts["target"] !== null
    ) {
      const target = opts["target"];
      const $tile = $(`.object-container[data-id="${target}"]`);
      $tile.css("background-color", "");
    }
  });

  $(".actions-container").on("click", ".action-end-turn", function () {
    ajaxPost("/end_turn", {}, (data) => {
      //hide actions
      $(".popover-menu").hide();
    });
  });

  $(".floating-window").on("click", function () {
    let maxZIndex = 0;
    $(".floating-window").each(function () {
      maxZIndex = Math.max(maxZIndex, parseInt($(this).css("z-index")) || 0);
    });
    $(this).css("z-index", maxZIndex + 1);
  });

  $(document).on("mouseenter", ".hide-action", function () {
    const entity_uid = $(this).closest(".tile").data("coords-id");
    Utils.ajaxGet("/hide", { id: entity_uid }, (data) => {
      data.hiding_spots.forEach((value) => {
        $(
          `.tile[data-coords-x="${value[0]}"][data-coords-y="${value[1]}"]`,
        ).css("background-color", "rgba(0, 255, 0, 0.5)");
      });
    });
  });

  $(document).on("mouseleave", ".hide-action", () => {
    $(".tile").css("background-color", "");
  });

  Utils.draggable("#battle-turn-order");
  Utils.draggable("#console-container");

  if ($("body").data("battle-in-progress")) {
    $("#start-initiative").hide();
  }

  // Handle command form submission
  $("#command-form").on("submit", (e) => {
    e.preventDefault();
    const cmd = $("#command-input").val().trim();
    if (cmd === "") return;

    // send the command via WebSocket using the existing command function
    $.ajax({
      type: "POST",
      url: "/command",
      data: { command: cmd },
      success: (data) => {
        $("#command-output").append("> " + cmd + "\n");
        $("#command-input").val("");
        if (data.error) {
          console.log("Command request failed:", data);
          $("#command-output").append(data.error + "\n");
        } else {
          console.log("Command request successful:", data);
          $("#command-output").append(data + "\n");
        }
        // Scroll to bottom of output
        $("#command-output").scrollTop($("#command-output")[0].scrollHeight);
      },
    });
  });

  // Handle Enter key press in command input
  $("#command-input").on("keypress", function(e) {
    if (e.which === 13) { // Enter key
      $("#command-form").submit();
    }
  });

  // Append server responses tagged with type 'command_response' to the command output
  socket.on("command_response", (data) => {
    $("#command-output").append(data.message + "\n");
  });

  // Handle talk action
  function handleTalk(entityId) {
    $('#talkModal').modal('show');
   
    // Get the tile data to access conversation languages
    const $tile = $(`.tile[data-coords-id="${entityId}"]`);
    const languages = $tile.data('conversation-languages');

    const languagesArray = languages.split(',');
   
    // Populate language dropdown
    const $languageSelect = $('#languageSelect');
    $languageSelect.empty();
   
    // Add available languages to dropdown
    if (languages && languages.length > 0) {
      languagesArray.forEach(language => {
        if (language.trim() !== 'common') {
          $languageSelect.append(`<option value="${language}">${language}</option>`);
        } else {
          $languageSelect.append(`<option value="Common" selected>Common</option>`);
        }
      });
    }
   
    // Get nearby entities within earshot range (30ft)
    $.ajax({
      url: '/nearby_entities',
      type: 'GET',
      data: {
        entity_id: entityId,
        range: 30 // 30ft earshot range
      },
      success: (data) => {
        const $nearbyEntities = $('#nearbyEntities');
        $nearbyEntities.empty();
       
        if (data.entities && data.entities.length > 0) {
          data.entities.forEach(entity => {
            $nearbyEntities.append(`
              <label class="list-group-item">
                <input type="checkbox" name="targets" value="${entity.id}">
                ${entity.name} (${entity.distance}ft away)
              </label>
            `);
          });
        } else {
          $nearbyEntities.append('<div class="list-group-item">No entities within earshot range</div>');
        }
      }
    });

    $('#submitTalk').off('click').on('click', function() {
      const message = $('#talkMessage').val().trim();
      if (message) {
        const selectedTargets = [];
        $('input[name="targets"]:checked').each(function() {
          selectedTargets.push($(this).val());
        });
       
        const noSpecificTarget = $('#noSpecificTarget').is(':checked');
        const selectedLanguage = $('#languageSelect').val();
        const selectedVolume = $('input[name="speechVolume"]:checked');
        const distance_ft = parseInt(selectedVolume.data('distance'));
       
        $.ajax({
          url: '/talk',
          type: 'POST',
          contentType: 'application/json',
          data: JSON.stringify({
            entity_id: entityId,
            message: message,
            targets: selectedTargets,
            no_specific_target: noSpecificTarget,
            language: selectedLanguage,
            distance_ft: distance_ft
          }),
          success: (data) => {
            if (data.success) {
              $('#talkModal').modal('hide');
              $('#talkMessage').val('');
              $('input[name="targets"]').prop('checked', false);
              $('#noSpecificTarget').prop('checked', false);
            }
          }
        });
      }
    });
  }

  // Update the popover menu click handler
  $(document).on('click', '.talk-action', function(event) {
    event.stopPropagation();
    const $menu = $(this).closest('.popover-menu');
    const $tile = $(this).closest('.tile');
    const entityId = $tile.data('coords-id');
    handleTalk(entityId);
    $menu.hide();
  });

  $(document).on('click', '.conversation-bubble', function(event) {
    event.stopPropagation();
    Utils.toggleBubble(this);
  });

  // Handle dialog bubble clicks for dialog-capable entities
  function handleDialogBubbleClick(entityId, entityName) {
    console.log('Dialog bubble clicked for entity:', entityId, entityName);
    handleTalk(entityId);
  }

  $("#turn-order").on("change", ".group-select", function() {
    const $turnOrderItem = $(this).closest(".turn-order-item");
    const entity_uid = $turnOrderItem.data("id");
    console.log("Changing group for entity:", entity_uid); // Debug log
    const new_group = $(this).val();
    ajaxPost(
      "/update_group",
      { entity_uid, group: new_group },
      (data) => {
        console.log("Group updated successfully:", data);
      },
      true
    );
  });

  $("#turn-order").on("change", ".controller-select", function() {
    const $turnOrderItem = $(this).closest(".turn-order-item");
    const entity_uid = $turnOrderItem.data("id");
    console.log("Changing controller for entity:", entity_uid); // Debug log
    const new_controller = $(this).val();
    ajaxPost(
      "/update_controller",
      { entity_uid, controller: new_controller },
      (data) => {
        console.log("Controller updated successfully:", data);
      },
      true
    );
  });

  // AI Chatbot Interface Handlers
  let aiInitialized = false;

  // Initialize AI provider
  $("#initialize-ai, #draggable-initialize-ai").on("click", function() {
    // Determine which panel is active and get the appropriate form values
    let provider, apiKey, selectedModel;
    let isDraggable = $(this).attr("id") === "draggable-initialize-ai";
    
    if (isDraggable) {
      // Draggable panel is active
      provider = $("#draggable-ai-provider-select").val();
      apiKey = $("#draggable-ai-api-key").val();
      selectedModel = $("#draggable-ai-model-select").val();
    } else {
      // Modal is active
      provider = $("#ai-provider-select").val();
      apiKey = $("#ai-api-key").val();
      selectedModel = $("#ai-model-select").val();
    }
    
    if (provider === "mock") {
      // Mock provider doesn't need API key
      $.ajax({
        type: "POST",
        url: "/ai/initialize",
        data: { provider: provider },
        success: (data) => {
          if (data.success) {
            aiInitialized = true;
            if (isDraggable) {
              $("#draggable-ai-status").removeClass("label-default label-danger").addClass("label-success").text("Initialized");
              $("#draggable-chat-input, #draggable-send-chat").prop("disabled", false);
            } else {
              $("#ai-status").removeClass("label-default label-danger").addClass("label-success").text("Initialized");
              $("#chat-input, #send-chat").prop("disabled", false);
            }
            addChatMessage("system", "AI Assistant initialized successfully! How can I help you with your D&D game?", isDraggable);
          } else {
            if (isDraggable) {
              $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
            } else {
              $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
            }
            addChatMessage("system", "Failed to initialize AI: " + (data.error || "Unknown error"), isDraggable);
          }
        },
        error: () => {
          if (isDraggable) {
            $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
          } else {
            $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
          }
          addChatMessage("system", "Failed to initialize AI: Network error", isDraggable);
        }
      });
    } else if (provider === "ollama") {
      // Ollama provider
      const config = { provider: provider };
      if (apiKey) {
        config.base_url = apiKey;
      }
      if (selectedModel) {
        config.model = selectedModel;
      }
      
      $.ajax({
        type: "POST",
        url: "/ai/initialize",
        data: config,
        success: (data) => {
          if (data.success) {
            aiInitialized = true;
            if (isDraggable) {
              $("#draggable-ai-status").removeClass("label-default label-danger").addClass("label-success").text("Initialized");
              $("#draggable-chat-input, #draggable-send-chat").prop("disabled", false);
            } else {
              $("#ai-status").removeClass("label-default label-danger").addClass("label-success").text("Initialized");
              $("#chat-input, #send-chat").prop("disabled", false);
            }
            addChatMessage("system", `AI Assistant initialized successfully with ${data.model || 'Ollama'}! How can I help you with your D&D game?`, isDraggable);
          } else {
            if (isDraggable) {
              $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
            } else {
              $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
            }
            addChatMessage("system", "Failed to initialize AI: " + (data.error || "Unknown error"), isDraggable);
          }
        },
        error: () => {
          if (isDraggable) {
            $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
          } else {
            $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
          }
          addChatMessage("system", "Failed to initialize AI: Network error. Make sure Ollama is running.", isDraggable);
        }
      });
    } else {
      // Real providers need API key
      if (!apiKey) {
        addChatMessage("system", "Please enter an API key for the selected provider.", isDraggable);
        return;
      }
      
      $.ajax({
        type: "POST",
        url: "/ai/initialize",
        data: { 
          provider: provider,
          api_key: apiKey
        },
        success: (data) => {
          if (data.success) {
            aiInitialized = true;
            if (isDraggable) {
              $("#draggable-ai-status").removeClass("label-default label-danger").addClass("label-success").text("Initialized");
              $("#draggable-chat-input, #draggable-send-chat").prop("disabled", false);
            } else {
              $("#ai-status").removeClass("label-default label-danger").addClass("label-success").text("Initialized");
              $("#chat-input, #send-chat").prop("disabled", false);
            }
            addChatMessage("system", "AI Assistant initialized successfully! How can I help you with your D&D game?", isDraggable);
          } else {
            if (isDraggable) {
              $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
            } else {
              $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
            }
            addChatMessage("system", "Failed to initialize AI: " + (data.error || "Unknown error"), isDraggable);
          }
        },
        error: () => {
          if (isDraggable) {
            $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
          } else {
            $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
          }
          addChatMessage("system", "Failed to initialize AI: Network error", isDraggable);
        }
      });
    }
  });

  // Handle provider change for both modal and draggable panel
  $("#ai-provider-select, #draggable-ai-provider-select").on("change", function() {
    const provider = $(this).val();
    const isDraggable = $(this).attr("id") === "draggable-ai-provider-select";
    
    // Get the appropriate form elements based on which panel triggered the event
    let $apiKeyField, $modelRow, $apiKeyLabel, $apiKeyHelp;
    
    if (isDraggable) {
      $apiKeyField = $("#draggable-ai-api-key");
      $modelRow = $("#draggable-model-selection-row");
      $apiKeyLabel = $apiKeyField.prev("label");
      $apiKeyHelp = $apiKeyField.next("small");
    } else {
      $apiKeyField = $("#ai-api-key");
      $modelRow = $("#model-selection-row");
      $apiKeyLabel = $apiKeyField.prev("label");
      $apiKeyHelp = $apiKeyField.next("small");
    }

    if (provider === "mock") {
      $apiKeyField.prop("disabled", true).val("");
      $apiKeyLabel.text("API Key");
      $apiKeyHelp.text("");
      $modelRow.hide();
    } else if (provider === "ollama") {
      $apiKeyField.prop("disabled", false).val("http://localhost:11434");
      $apiKeyLabel.text("Ollama URL");
      $apiKeyHelp.text("Leave empty for localhost:11434 or enter custom URL");
      $modelRow.show();
      
      // Load models for the appropriate panel
      if (isDraggable) {
        loadDraggableOllamaModels();
      } else {
        loadOllamaModels();
      }
    } else {
      $apiKeyField.prop("disabled", false).val("");
      $apiKeyLabel.text("API Key");
      $apiKeyHelp.text("");
      $modelRow.hide();
    }
  });

  // Load Ollama models
  function loadOllamaModels() {
    // Use the API key from the modal panel
    const url = $("#ai-api-key").val() || "http://localhost:11434";
    
    $.ajax({
      type: "GET",
      url: "/ai/ollama/models",
      data: { base_url: url },
      success: (data) => {
        const $modelSelect = $("#ai-model-select");
        $modelSelect.empty();
        
        if (data.success && data.models && data.models.length > 0) {
          data.models.forEach(model => {
            $modelSelect.append(`<option value="${model}">${model}</option>`);
          });
          addChatMessage("system", `Found ${data.models.length} Ollama models. Please select one and initialize.`);
          // Sync with draggable panel
          syncModelSelections();
        } else {
          $modelSelect.append('<option value="">No models found</option>');
          addChatMessage("system", "No Ollama models found. Please make sure Ollama is running and has models installed.");
        }
      },
      error: () => {
        const $modelSelect = $("#ai-model-select");
        $modelSelect.empty().append('<option value="">Failed to load models</option>');
        addChatMessage("system", "Failed to load Ollama models. Please check your Ollama installation and connection.");
      }
    });
  }

  // Refresh models button
  $("#refresh-models").on("click", function() {
    if ($("#ai-provider-select").val() === "ollama") {
      loadOllamaModels();
    }
  });

  // Initialize provider select on page load for both panels
  $("#ai-provider-select, #draggable-ai-provider-select").trigger("change");

  // Handle chat form submission
  $("#chat-form, #draggable-chat-form").on("submit", function(e) {
    e.preventDefault();
    if (!aiInitialized) {
      const isDraggable = $(this).attr("id") === "draggable-chat-form";
      addChatMessage("system", "Please initialize the AI assistant first.", isDraggable);
      return;
    }
    
    const isDraggable = $(this).attr("id") === "draggable-chat-form";
    const $input = isDraggable ? $("#draggable-chat-input") : $("#chat-input");
    const $sendButton = isDraggable ? $("#draggable-send-chat") : $("#send-chat");
    
    const message = $input.val().trim();
    if (message === "") return;
    
    // Add user message to chat
    addChatMessage("user", message, isDraggable);
    $input.val("");
    
    // Disable input while processing
    $input.prop("disabled", true);
    $sendButton.prop("disabled", true);
    
    // Add processing indicator
    const processingId = addProcessingMessage(isDraggable);
    
    // Set up timeout indicators for longer processing times
    const timeout1 = setTimeout(() => {
      updateProcessingMessage(processingId, "Processing your request", isDraggable);
    }, 3000);
    
    const timeout2 = setTimeout(() => {
      updateProcessingMessage(processingId, "Gathering game data", isDraggable);
    }, 8000);
    
    const timeout3 = setTimeout(() => {
      updateProcessingMessage(processingId, "Almost done", isDraggable);
    }, 15000);
    
    // Send message to AI
    $.ajax({
      type: "POST",
      url: "/ai/chat",
      data: { message: message },
      success: (data) => {
        // Clear timeouts
        clearTimeout(timeout1);
        clearTimeout(timeout2);
        clearTimeout(timeout3);
        
        // Remove processing indicator
        removeProcessingMessage(processingId, isDraggable);
        
        if (data.success) {
          addChatMessage("assistant", data.response, isDraggable);
        } else {
          addChatMessage("system", "Error: " + (data.error || "Unknown error"), isDraggable);
        }
        $input.prop("disabled", false);
        $sendButton.prop("disabled", false);
        $input.focus();
      },
      error: () => {
        // Clear timeouts
        clearTimeout(timeout1);
        clearTimeout(timeout2);
        clearTimeout(timeout3);
        
        // Remove processing indicator
        removeProcessingMessage(processingId, isDraggable);
        
        addChatMessage("system", "Network error occurred while communicating with AI.", isDraggable);
        $input.prop("disabled", false);
        $sendButton.prop("disabled", false);
        $input.focus();
      }
    });
  });

  // Clear chat history
  $("#clear-chat, #draggable-clear-chat").on("click", function() {
    const isDraggable = $(this).attr("id") === "draggable-clear-chat";
    if (confirm("Are you sure you want to clear the chat history?")) {
      const $chatContainer = isDraggable ? $("#draggable-chat-messages") : $("#chat-messages");
      $chatContainer.html('<div class="chat-message system"><strong>AI Assistant:</strong> Chat history cleared. How can I help you?</div>');
      
      // Clear server-side history
      $.ajax({
        type: "POST",
        url: "/ai/clear-history",
        success: (data) => {
          console.log("Chat history cleared");
        }
      });
    }
  });

  // Get game context
  $("#get-context, #draggable-get-context").on("click", function() {
    const isDraggable = $(this).attr("id") === "draggable-get-context";
    $.ajax({
      type: "GET",
      url: "/ai/context",
      success: (data) => {
        if (data.success) {
          addChatMessage("system", "Game context retrieved and sent to AI assistant.", isDraggable);
        } else {
          addChatMessage("system", "Failed to get game context: " + (data.error || "Unknown error"), isDraggable);
        }
      },
      error: () => {
        addChatMessage("system", "Failed to get game context: Network error", isDraggable);
      }
    });
  });

  // Helper function to add a processing message with animated dots
  function addProcessingMessage(isDraggable = false) {
    const timestamp = new Date().toLocaleTimeString();
    const processingId = 'processing-' + Date.now();
    const $chatContainer = isDraggable ? $("#draggable-chat-messages") : $("#chat-messages");
    const messageHtml = `
      <div id="${processingId}" class="chat-message assistant processing">
        <strong>AI Assistant (${timestamp}):</strong> 
        <span class="processing-text">Thinking</span><span class="processing-dots">...</span>
      </div>
    `;
    $chatContainer.append(messageHtml);
    
    // Scroll to bottom
    $chatContainer.scrollTop($chatContainer[0].scrollHeight);
    
    return processingId;
  }

  // Helper function to update processing message text
  function updateProcessingMessage(processingId, text, isDraggable = false) {
    const $processing = $(`#${processingId}`);
    if ($processing.length) {
      $processing.find('.processing-text').text(text);
    }
  }

  // Helper function to remove a processing message
  function removeProcessingMessage(processingId, isDraggable = false) {
    $(`#${processingId}`).remove();
  }

  // Helper function to clean thinking tags from responses
  function cleanThinkingTags(content) {
    if (!content || typeof content !== 'string') {
      return content;
    }
    
    // Remove thinking tags and their content
    let cleaned = content.replace(/<think>.*?<\/think>/gs, '');
    cleaned = cleaned.replace(/<reasoning>.*?<\/reasoning>/gs, '');
    cleaned = cleaned.replace(/<thought>.*?<\/thought>/gs, '');
    
    // Remove reasoning blocks that start with "Okay, so" or similar
    cleaned = cleaned.replace(/Okay, so.*?(?=\[FUNCTION_CALL:|$)/gs, '');
    cleaned = cleaned.replace(/Let me.*?(?=\[FUNCTION_CALL:|$)/gs, '');
    cleaned = cleaned.replace(/I need to.*?(?=\[FUNCTION_CALL:|$)/gs, '');
    
    // Clean up extra whitespace and newlines
    cleaned = cleaned.replace(/\n\s*\n/g, '\n');
    cleaned = cleaned.trim();
    
    return cleaned;
  }

  // Helper function to add chat messages
  function addChatMessage(role, content, isDraggable = false) {
    const timestamp = new Date().toLocaleTimeString();
    let messageClass = "chat-message";
    let prefix = "";
    let $chatContainer;
    
    // Determine which chat container to use
    if (isDraggable) {
      $chatContainer = $("#draggable-chat-messages");
    } else {
      $chatContainer = $("#chat-messages");
    }
    
    // Clean thinking tags from content (safety measure)
    const cleanedContent = cleanThinkingTags(content);
    
    switch(role) {
      case "user":
        messageClass += " user";
        prefix = `<strong>You (${timestamp}):</strong>`;
        break;
      case "assistant":
        messageClass += " assistant";
        prefix = `<strong>AI Assistant (${timestamp}):</strong>`;
        break;
      case "system":
        messageClass += " system";
        prefix = `<strong>System (${timestamp}):</strong>`;
        break;
    }
    
    const messageHtml = `<div class="${messageClass}">${prefix} ${cleanedContent}</div>`;
    $chatContainer.append(messageHtml);
    
    // Scroll to bottom
    $chatContainer.scrollTop($chatContainer[0].scrollHeight);
  }

  // AI Chat Panel Draggable Functionality
  let isDragging = false;
  let isResizing = false;
  let currentX;
  let currentY;
  let initialX;
  let initialY;
  let xOffset = 0;
  let yOffset = 0;
  let initialWidth;
  let initialHeight;
  let initialResizeX;
  let initialResizeY;

  // Toggle AI Chat Panel
  $("#toggle-ai-chat").on("click", function() {
    const $panel = $("#ai-chat-panel");
    if ($panel.is(":visible")) {
      $panel.hide();
      $(this).removeClass("btn-success").addClass("btn-primary");
    } else {
      $panel.show();
      $(this).removeClass("btn-primary").addClass("btn-success");
    }
  });

  // Close AI Chat Panel
  $("#close-chat").on("click", function() {
    $("#ai-chat-panel").hide();
    $("#toggle-ai-chat").removeClass("btn-success").addClass("btn-primary");
  });

  // Minimize AI Chat Panel
  $("#minimize-chat").on("click", function() {
    const $panel = $("#ai-chat-panel");
    const $body = $panel.find(".panel-body");
    
    if ($panel.hasClass("minimized")) {
      $panel.removeClass("minimized");
      $body.show();
      $(this).find("i").removeClass("glyphicon-plus").addClass("glyphicon-minus");
    } else {
      $panel.addClass("minimized");
      $body.hide();
      $(this).find("i").removeClass("glyphicon-minus").addClass("glyphicon-plus");
    }
  });

  // Drag functionality for AI Chat Panel
  $("#ai-chat-panel .panel-header").on("mousedown", function(e) {
    // Don't start drag if clicking on buttons or their icons
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'I' || $(e.target).closest('button').length) {
      return;
    }
    
    const $panel = $("#ai-chat-panel");
    initialX = e.clientX - xOffset;
    initialY = e.clientY - yOffset;
    
    isDragging = true;
    $panel.addClass("dragging");
    
    // Prevent text selection during drag
    e.preventDefault();
  });

  // Resize functionality for AI Chat Panel
  $("#ai-chat-panel .resize-handle").on("mousedown", function(e) {
    const $panel = $("#ai-chat-panel");
    initialResizeX = e.clientX;
    initialResizeY = e.clientY;
    initialWidth = $panel.width();
    initialHeight = $panel.height();
    
    isResizing = true;
    $panel.addClass("resizing");
    
    e.preventDefault();
    e.stopPropagation();
  });

  $(document).on("mousemove", function(e) {
    if (isDragging) {
      e.preventDefault();
      
      currentX = e.clientX - initialX;
      currentY = e.clientY - initialY;
      
      xOffset = currentX;
      yOffset = currentY;
      
      setTranslate(currentX, currentY, $("#ai-chat-panel"));
    } else if (isResizing) {
      e.preventDefault();
      
      const deltaX = e.clientX - initialResizeX;
      const deltaY = e.clientY - initialResizeY;
      
      const newWidth = Math.max(300, initialWidth + deltaX);
      const newHeight = Math.max(400, initialHeight + deltaY);
      
      const $panel = $("#ai-chat-panel");
      $panel.css({
        width: newWidth + 'px',
        height: newHeight + 'px'
      });
    }
  });

  $(document).on("mouseup", function() {
    if (isDragging) {
      isDragging = false;
      $("#ai-chat-panel").removeClass("dragging");
      
      // Save position after a short delay to ensure smooth transition
      setTimeout(savePanelPosition, 100);
    } else if (isResizing) {
      isResizing = false;
      $("#ai-chat-panel").removeClass("resizing");
      
      // Save size to localStorage
      const $panel = $("#ai-chat-panel");
      localStorage.setItem("aiChatPanelSize", JSON.stringify({
        width: $panel.width(),
        height: $panel.height()
      }));
    }
  });

  function setTranslate(xPos, yPos, el) {
    // Keep panel within viewport bounds
    const $el = $(el);
    const rect = $el[0].getBoundingClientRect();
    const windowWidth = $(window).width();
    const windowHeight = $(window).height();
    
    // Constrain to viewport with some padding
    const padding = 20;
    if (xPos < -rect.width + padding) xPos = -rect.width + padding;
    if (xPos > windowWidth - padding) xPos = windowWidth - padding;
    if (yPos < 0) yPos = 0;
    if (yPos > windowHeight - padding) yPos = windowHeight - padding;
    
    // Use transform3d for better performance
    $el.css("transform", `translate3d(${xPos}px, ${yPos}px, 0)`);
  }

  // Save panel position to localStorage
  function savePanelPosition() {
    const $panel = $("#ai-chat-panel");
    const transform = $panel.css("transform");
    if (transform && transform !== "none") {
      localStorage.setItem("aiChatPanelPosition", transform);
    }
  }

  // Load panel position and size from localStorage
  function loadPanelPosition() {
    const savedPosition = localStorage.getItem("aiChatPanelPosition");
    const savedSize = localStorage.getItem("aiChatPanelSize");
    
    if (savedPosition) {
      $("#ai-chat-panel").css("transform", savedPosition);
    }
    
    if (savedSize) {
      try {
        const size = JSON.parse(savedSize);
        $("#ai-chat-panel").css({
          width: size.width + 'px',
          height: size.height + 'px'
        });
      } catch (e) {
        console.log("Failed to parse saved size");
      }
    }
  }

  // Handle window resize to keep panel in bounds
  $(window).on("resize", function() {
    const $panel = $("#ai-chat-panel");
    if ($panel.is(":visible")) {
      const rect = $panel[0].getBoundingClientRect();
      const windowWidth = $(window).width();
      const windowHeight = $(window).height();
      
      let needsReposition = false;
      let newX = xOffset;
      let newY = yOffset;
      
      // Check if panel is outside viewport bounds
      if (rect.right > windowWidth) {
        newX = windowWidth - rect.width - 20;
        needsReposition = true;
      }
      if (rect.left < 0) {
        newX = 20;
        needsReposition = true;
      }
      if (rect.bottom > windowHeight) {
        newY = windowHeight - rect.height - 20;
        needsReposition = true;
      }
      if (rect.top < 0) {
        newY = 20;
        needsReposition = true;
      }
      
      if (needsReposition) {
        xOffset = newX;
        yOffset = newY;
        setTranslate(newX, newY, $panel);
        savePanelPosition();
      }
    }
  });

  // Load Ollama models for draggable panel
  function loadDraggableOllamaModels() {
    // Use the API key from the draggable panel
    const url = $("#draggable-ai-api-key").val() || "http://localhost:11434";
    
    $.ajax({
      type: "GET",
      url: "/ai/ollama/models",
      data: { base_url: url },
      success: (data) => {
        const $modelSelect = $("#draggable-ai-model-select");
        $modelSelect.empty();
        
        if (data.success && data.models && data.models.length > 0) {
          data.models.forEach(model => {
            $modelSelect.append(`<option value="${model}">${model}</option>`);
          });
          addChatMessage("system", `Found ${data.models.length} Ollama models. Please select one and initialize.`, true);
          // Sync with modal panel
          syncModelSelections();
        } else {
          $modelSelect.append('<option value="">No models found</option>');
          addChatMessage("system", "No Ollama models found. Please make sure Ollama is running and has models installed.", true);
        }
      },
      error: (xhr, status, error) => {
        const $modelSelect = $("#draggable-ai-model-select");
        $modelSelect.empty().append('<option value="">Failed to load models</option>');
        addChatMessage("system", "Failed to load Ollama models. Please check your Ollama installation and connection.", true);
      }
    });
  }

  // Sync model selections between modal and draggable panel
  function syncModelSelections() {
    const modalModel = $("#ai-model-select").val();
    const draggableModel = $("#draggable-ai-model-select").val();
    
    // If one has a selection and the other doesn't, sync them
    if (modalModel && !draggableModel) {
      $("#draggable-ai-model-select").val(modalModel);
    } else if (draggableModel && !modalModel) {
      $("#ai-model-select").val(draggableModel);
    }
  }

  // Handle model selection changes to sync between panels
  $("#ai-model-select, #draggable-ai-model-select").on("change", function() {
    const selectedModel = $(this).val();
    const isDraggable = $(this).attr("id") === "draggable-ai-model-select";
    
    if (isDraggable) {
      $("#ai-model-select").val(selectedModel);
    } else {
      $("#draggable-ai-model-select").val(selectedModel);
    }
  });

  // Refresh models button for draggable panel
  $("#draggable-refresh-models").on("click", function() {
    if ($("#draggable-ai-provider-select").val() === "ollama") {
      loadDraggableOllamaModels();
      // Also refresh the modal models to keep them in sync
      loadOllamaModels();
    }
  });

  // Load position on page load
  $(document).ready(function() {
    loadPanelPosition();
  });

  // Handle window resize to keep panel in bounds
});

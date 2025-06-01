// --- Global Helpers & Utilities ---

let scale = 1;

const switchPOV = (entity_uid, canvas) => {
  ajaxPost("/switch_pov", { entity_uid }, (data) => {
    console.log("Switched POV:", data);
    Utils.refreshTileSet(
      (is_setup = false),
      (pov = true),
      (x = 0),
      (y = 0),
      (entity_uid = entity_uid),
      () => {
        if (data.background) {
         
          $("#main-map-area .image-container img").css({
            width: `${data.width}px`,
            objectFit: 'cover',
            objectPosition: 'top',
          });
          $("#main-map-area .image-container").css({
            height: `${data.height}px`,
          });
          $("#main-map-area .tiles-container").data({
            width: data.width,
            height: data.height,
          });
          $(".image-container").css({ height: data.height });
          $(".image-container img").css({ width: data.width });
          const tile_size = $('.tiles-container').data('tile-size');
          $('.image-container').css({top: data.image_offset_px[1] + tile_size, left: data.image_offset_px[0] + tile_size});
          canvas.width = data.width + tile_size;
          canvas.height = data.height + tile_size;
          $("#main-map-area .image-container img").attr("src", data.background);
          $('body').attr('data-current-map', data.name);
        }
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
  var canvas = document.createElement("canvas");
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  canvas.style.position = "fixed";
  canvas.style.top = "0";
  canvas.style.left = "0";
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  canvas.style.zIndex = 1000;
  canvas.style.pointerEvents = "none";
  $("body").append(canvas);
  var ctx = canvas.getContext("2d");

  // Update canvas size on window resize
  $(window).on('resize', function() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
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
              ctx,
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
        Utils.switchMap(map_id, canvas);
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
    Utils.switchMap(map_id, canvas);
  });

  // --- Tile & Action Event Handlers ---
  $(".tiles-container").on("click", ".execute-action", (e) => {
    targetModeCallback(multiTargetList);
    targetMode = multiTargetMode = false;
    valid_target_cache = {};
    multiTargetList = [];
    $(".add-to-target, .popover-menu-2").hide();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
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
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      $(".tile").css("border", "none");
    } else if (moveMode) {
      if (coordsx !== source.x || coordsy !== source.y) {
        moveMode = false;
        move_path_cache = {};
        ctx.clearRect(0, 0, canvas.width, canvas.height);
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
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  $(".zoom-out").on("click", () => {
    scale -= 0.1;
    $("#main-map-area").css({
      "transform": `scale(${scale})`,
      "transform-origin": "center center"
    });
    ctx.clearRect(0, 0, canvas.width, canvas.height);
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
    ctx.clearRect(0, 0, canvas.width, canvas.height);
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
    switchPOV(entity_uid, canvas);
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
        drawTargetLine(ctx, source, coordsx, coordsy, valid_target_cache[`${coordsx}-${coordsy}`]);
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
            drawTargetLine(ctx, source, coordsx, coordsy, valid_target);
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
            Utils.drawMovementPath(ctx, movePath, available_cost, data.placeable);
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
        ctx.clearRect(0, 0, canvas.width, canvas.height);
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
      ctx.clearRect(0, 0, canvas.width, canvas.height);
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
        drawLine(ctx, source, `.tile[data-coords-id="${entity_uid}"]`, {
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
      ctx.clearRect(0, 0, canvas.width, canvas.height);
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
      },
    });
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
});

// --- Global Helpers & Utilities ---

// Game Time Formatting Functions
function formatGameTime(totalSeconds) {
  const days = Math.floor(totalSeconds / (24 * 60 * 60));
  const hours = Math.floor((totalSeconds % (24 * 60 * 60)) / (60 * 60));
  const minutes = Math.floor((totalSeconds % (60 * 60)) / 60);
  const seconds = totalSeconds % 60;
  
  const parts = [];
  if (days > 0) parts.push(`${days} day${days !== 1 ? 's' : ''}`);
  if (hours > 0) parts.push(`${hours} hour${hours !== 1 ? 's' : ''}`);
  if (minutes > 0) parts.push(`${minutes} minute${minutes !== 1 ? 's' : ''}`);
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds} second${seconds !== 1 ? 's' : ''}`);
  
  return parts.join(', ');
}

function updateGameTimeDisplay(gameTimeSeconds) {
  const formattedTime = formatGameTime(gameTimeSeconds);
  $('#game-time-text').text(formattedTime);
}

let scale = 1;
let keyboardMovementMode = false;
let keyboardMovementSource = null;
let keyboardMovementPath = [];
let keyboardMovementPivotPoints = [];
let globalCanvas = null;
let globalCtx = null;
let talkToEntityMode = false; // Flag to track when user is talking to an entity
let dialogMessageProcessing = false; // Flag to track if a dialog message is being processed

// Ghost token system for pending moves
let pendingMoves = new Map(); // entityId -> { sourceX, sourceY, targetX, targetY, ghostElement }
let moveRequestTimeouts = new Map(); // entityId -> timeoutId for cleanup

// Mode & State Variables (global scope for access by functions)
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
// Jump UI state for movement
let jumpMode = false;          // toggled within movement to mark a jump segment
let jumpStartIndex = null;     // index within movePath where jump starts (inclusive)
let lastPathForJump = null;    // cache the last data.path returned while hovering
let max_targets = 1;
let targetModeCallback = null,
  moveModeCallback = null;
let targetModeMaxRange = 0,
  source = null,
  battle_setup = false;
let globalActionInfo = null,
  globalOpts = null,
  globalSourceEntity = null;
let pathDebounceTimer = null;

// Event queue system for FIFO processing
class EventQueue {
  constructor() {
    this.queue = [];
    this.processing = false;
    this.maxQueueSize = 100; // Prevent memory leaks
    this.processedCount = 0;
    this.debugMode = false; // Set to true for debugging
  }

  setDebugMode(enabled) {
    this.debugMode = enabled;
  }

  getStatus() {
    return {
      queueLength: this.queue.length,
      processing: this.processing,
      processedCount: this.processedCount,
      maxQueueSize: this.maxQueueSize
    };
  }

  enqueue(event) {
    if (this.queue.length >= this.maxQueueSize) {
      console.warn('Event queue is full, dropping oldest event');
      this.queue.shift();
    }

    if (this.debugMode) {
      console.log(`[EventQueue] Enqueuing event: ${event.type}, queue length: ${this.queue.length + 1}`);
    }

    this.queue.push(event);
    this.processNext();
  }

  async processNext() {
    if (this.processing || this.queue.length === 0) {
      return;
    }

    this.processing = true;

    while (this.queue.length > 0) {
      const event = this.queue.shift();
      this.processedCount++;

      if (this.debugMode) {
        console.log(`[EventQueue] Processing event #${this.processedCount}: ${event.type}, remaining: ${this.queue.length}`);
      }

      try {
        await this.processEvent(event);

        // Add a small delay between events to ensure smooth visual transitions
        // Especially important for movement events that involve animations
        if (event.type === 'move' && this.queue.length > 0) {
          await new Promise(resolve => setTimeout(resolve, 100));
        }
      } catch (error) {
        console.error('Error processing event:', error, event);
      }
    }

    this.processing = false;

    if (this.debugMode) {
      console.log(`[EventQueue] Processing complete. Total processed: ${this.processedCount}`);
    }
  }

  async processEvent(data) {
    return new Promise((resolve) => {
      if (this.debugMode) {
        console.log(`[EventQueue] Processing event: ${data.type}`, data);
      } else {
        console.log("Processing event:", data);
      }

      switch (data.type) {
        case "refresh_map": {
          Utils.refreshTileSet();
          updateDraggableEntityClasses();
          // Clean up any pending moves since map is refreshing
          cleanupAllPendingMoves();
          resolve();
          break;
        }
        case "map": {
          this.processMapEvent(data, resolve);
          break;
        }
        case "conversation": {
          this.processConversationEvent(data, resolve);
          break;
        }
        case "move": {
          this.processMoveEvent(data, resolve);
          break;
        }
        case "message":
          console.log(data.message);
          resolve();
          break;
        case "error":
          console.error(data.message);
          resolve();
          break;
        case "console":
          $("#console-container #console").append(`<p>${data.message}</p>`);
          $("#console-container").scrollTop(
            $("#console-container")[0].scrollHeight,
          );
          resolve();
          break;
        case "track":
          console.log("Playing track:", data.message);
          playSound(
            data.message.url,
            data.message.track_id,
            data.message.volume,
            0,
          );

          // Update DM Sound Manager state when track changes
          if (typeof DMSoundManager !== 'undefined') {
            DMSoundManager.currentTrackId = data.message.track_id || data.message.id;
            DMSoundManager.isPlaying = true;
            // Update UI if the modal is open
            if ($('#modal-1').hasClass('in') || $('#modal-1').is(':visible')) {
              DMSoundManager.updateUI();
            }
          }

          resolve();
          break;
        case "prompt": {
          alert(data.message);
          ajaxPost(
            "/response",
            { response: "", callback: data.callback },
            (resp) => {
              console.log("Response sent successfully:", resp);
              resolve();
            },
            true,
          );
          break;
        }
        case "turn":
          refreshTurn();
          // Update game time if provided in the message
          if (data.message && data.message.game_time !== undefined) {
            updateGameTimeDisplay(data.message.game_time);
          }
          resolve();
          break;
        case "focus":
          centerOnTileXY(data.message.x, data.message.y, true);
          resolve();
          break;
        case "stoptrack":
          this.processStopTrackEvent(data, resolve);
          break;
        case "volume":
          if (active_background_sound) {
            active_background_sound.volume = data.message.volume / 100;
            $(".volume-slider").val(data.message.volume);

            // Update DM Sound Manager if volume changed externally
            if (typeof DMSoundManager !== 'undefined' && DMSoundManager.currentTrackId && DMSoundManager.currentTrackId !== "-1") {
              DMSoundManager.setTrackVolume(DMSoundManager.currentTrackId, data.message.volume);
              // Update UI if the modal is open
              if ($('#modal-1').hasClass('in') || $('#modal-1').is(':visible')) {
                $('.volume-display').text(data.message.volume + '%');
                DMSoundManager.updateVolumeDisplays();
              }
            }

            // Apply user volume control on top of DM volume change
            if (typeof UserVolumeControl !== 'undefined') {
              setTimeout(() => UserVolumeControl.applyUserVolume(), 50);
            }
          }
          resolve();
          break;
        case "initiative":
          refreshTurnOrder();
          $("#start-initiative, #start-battle").hide();
          $("#end-battle").show();
          resolve();
          break;
        case "stop":
          $("#turn-order").html("");
          $(".game-turn-container").hide();
          $("#battle-turn-order").fadeOut();
          $("#start-initiative, #start-battle").show();
          $("#end-battle").hide();
          resolve();
          break;
        case "reaction":
          Utils.ajaxGet("/reaction", {}, (data) => {
            $("#reaction-modal .reaction-content").html(data);
            $("#reaction-modal").modal("show");
            resolve();
          });
          break;
        case "dismiss_reaction":
          $("#reaction-modal").modal("hide");
          resolve();
          break;
        case "switch_map":
          var map_id = data.message.map;
          Utils.switchMap(map_id, globalCanvas, () => {
            createGlobalCanvas();
            resolve();
          });
          break;
        case "command_response":
          $("#command-output").append(data.message + "\n");
          resolve();
          break;
        default:
          console.log("Unknown message type:", data.type);
          resolve();
      }
    });
  }

  processMapEvent(data, resolve) {
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
    $("#tiles-area").css({
      top: -tile_size + image_offset_px[1],
      left: -tile_size + image_offset_px[0],
    })
    const canvas = document.querySelector("canvas");
    canvas.width = width + tile_size;
    canvas.height = height + tile_size;
    Utils.refreshTileSet();
    resolve();
  }

  processConversationEvent(data, resolve) {
    // Handle real-time conversation updates
    const { entity_id, message, targets } = data.message;

    // Validate required fields
    if (!entity_id || !message) {
      console.warn('Invalid conversation event received:', data.message);
      resolve();
      return;
    }

    // Check if dialog panel is open and if this entity matches the current dialog
    const $dialogPanel = $('#jrpgDialogPanel');
    const currentDialogEntityId = $('#dialogEntityName').data('entity-id');
    const currentPovEntity = Chat.getCurrentPovEntity();

    // Check if this message should be shown in dialog panel:
    // 1. Dialog panel is open and this entity matches the current dialog entity
    // 2. OR this message is directed to the current POV entity (targets includes current POV)
    const shouldShowInDialog = $dialogPanel.is(':visible') && (
      currentDialogEntityId === entity_id ||
      (targets && Array.isArray(targets) && targets.includes(currentPovEntity))
    );

    // Check if this message is directed to the current POV entity (for potential dialog opening)
    const isDirectedToPov = targets && Array.isArray(targets) && targets.includes(currentPovEntity);

    if (shouldShowInDialog) {
      // Dialog panel is open and this entity matches - show message in dialog
      console.log('Adding conversation message to dialog panel:', message);

      try {
        // Get the entity name for display
        const $entityTile = $(`.tile[data-coords-id="${entity_id}"]`);
        let entityName = 'Entity';
        if ($entityTile.length) {
          const $nameplate = $entityTile.find('.nameplate');
          if ($nameplate.length) {
            entityName = $nameplate.text();
          } else {
            entityName = $entityTile.data('entity-name') || 'Entity';
          }
        }

        // Add the message to the dialog chat
        Chat.addDialogMessage('entity', message, 'entity');
      } catch (error) {
        console.error('Error adding message to dialog modal:', error);
        // Fallback to showing conversation bubble
        Chat.showConversationBubble(entity_id, message);
      }
    } else if (isDirectedToPov && !$dialogPanel.is(':visible')) {
      // Message is directed to current POV but dialog panel is not open
      // Show conversation bubble and optionally provide a way to open dialog
      console.log('Message directed to POV entity, but dialog panel not open:', message);
      showDialogTriggerBubble(entity_id, message);
    } else {
      // Show conversation bubble on tile as before
      Chat.showConversationBubble(entity_id, message);
    }
    resolve();
  }

  processMoveEvent(data, resolve) {
    const animationBuffer = data.message.animation_log;
    const animateFunction = (animationLog, idx) => {
      if (idx >= animationLog.length) {
        console.log('Animation sequence complete, refreshing tile set');
        Utils.refreshTileSet();
        resolve();
        return;
      }
      const entry = animationLog[idx];
      // Skip non-array entries (e.g., perception objects) safely
      if (!Array.isArray(entry)) {
        if (entry && typeof entry === 'object' && entry.type === 'perception') {
          // Optionally, we could visualize perception targets here.
          // For now, just skip to next animation segment.
          console.debug('Skipping non-movement animation entry:', entry);
        }
        animateFunction(animationLog, idx + 1);
        return;
      }
      const [entity_uid, path, action] = entry;
      const $tile = $(`.tile[data-coords-id="${entity_uid}"]`);
      if (action && action.target) {
        // Check if both source and target tiles exist before drawing action line
        const $targetTile = $(`.tile[data-coords-id="${action.target}"]`);
        if ($tile.length > 0 && $targetTile.length > 0) {
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
        } else {
          console.warn('Action line drawing skipped: source or target tile not found', {
            entity_uid,
            target: action.target,
            sourceFound: $tile.length > 0,
            targetFound: $targetTile.length > 0
          });
        }
      }

      // Check if the entity tile exists before proceeding with animation
      if (!$tile.length) {
        console.warn('Entity tile not found, skipping animation for:', entity_uid);
        animateFunction(animationLog, idx + 1);
        return;
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
          // Clean up transition properties when animation is complete
          $tile.css('transition', '');
          // Animation for this entity is complete, move to next entity
          animateFunction(animationLog, idx + 1);
          return;
        }
        const [x, y] = p[index];
        const $newTile = $(
          `.tile[data-coords-x="${x}"][data-coords-y="${y}"]`,
        );

        // Check if the target tile exists
        if (!$newTile.length) {
          console.warn('Target tile not found, skipping move step:', { x, y, entity_uid });
          moveFunc(p, index + 1);
          return;
        }

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
          // Continue immediately to next step
          moveFunc(p, index + 1);
          return;
        }

        // Clear any existing transition to ensure clean state
        $tile.css('transition', 'none');

        // Use requestAnimationFrame to ensure the transition is properly set
        requestAnimationFrame(() => {
          $tile.css({
            position: 'absolute',
            top: newY,
            left: newX,
            transition: 'all 0.3s ease-in-out'
          });

          // Listen for the transition end event to ensure precise timing
          const transitionEndHandler = (e) => {
            if (e.target === $tile[0] && (e.propertyName === 'top' || e.propertyName === 'left')) {
              $tile.off('transitionend', transitionEndHandler);
              prevX = newX;
              prevY = newY;
              moveFunc(p, index + 1);
            }
          };

          $tile.on('transitionend', transitionEndHandler);

          // Fallback timeout in case transitionend doesn't fire
          setTimeout(() => {
            $tile.off('transitionend', transitionEndHandler);
            prevX = newX;
            prevY = newY;
            moveFunc(p, index + 1);
          }, 350); // Slightly longer than transition time as fallback
        });
      };

      // Start the movement sequence for this entity
  if (Array.isArray(path) && path.length > 0) {
        moveFunc(path, 0);
      } else {
        // No path to animate, move to next entity immediately
        animateFunction(animationLog, idx + 1);
      }
    };

    if (animationBuffer && animationBuffer.length > 0) {
      animateFunction(animationBuffer, 0);
    } else {
      // console.log('>>>>>>>>>>>>>>>>>>>>');
      // Utils.refreshTileSet();
      resolve();
    }
  }

  processStopTrackEvent(data, resolve) {
    if (!active_background_sound) { resolve(); return; }

    // Simple fade-out using element volume, then stop and resolve
    let steps = 10;
    const originalVolume = active_background_sound.volume;
    const stepDown = originalVolume / steps;
    const interval = setInterval(() => {
      if (!active_background_sound) { clearInterval(interval); resolve(); return; }
      const nextVol = Math.max(0, active_background_sound.volume - stepDown);
      active_background_sound.volume = nextVol;
      if (nextVol <= 0) {
        clearInterval(interval);
        try { active_background_sound.pause(); } catch (e) {}
        active_background_sound = null;
        active_track_id = -1;

        // Update DM Sound Manager state
        if (typeof DMSoundManager !== 'undefined') {
          DMSoundManager.currentTrackId = "-1";
          DMSoundManager.isPlaying = false;
          if ($('#modal-1').hasClass('in') || $('#modal-1').is(':visible')) {
            DMSoundManager.updateUI();
          }
        }
        resolve();
      }
    }, 50);
  }
}

// Create global event queue instance
const eventQueue = new EventQueue();

// Add debug panel for monitoring event queue
function createEventQueueDebugPanel() {
  const debugPanel = $(`
    <div id="event-queue-debug" style="position: fixed; top: 10px; right: 10px; 
         background: rgba(0,0,0,0.8); color: white; padding: 10px; 
         border-radius: 5px; font-family: monospace; font-size: 12px; 
         z-index: 9999; display: none;">
      <div><strong>Event Queue Status</strong></div>
      <div>Queue Length: <span id="queue-length">0</span></div>
      <div>Processing: <span id="processing-status">false</span></div>
      <div>Total Processed: <span id="processed-count">0</span></div>
      <div>
        <button onclick="eventQueue.setDebugMode(true)">Enable Debug</button>
        <button onclick="eventQueue.setDebugMode(false)">Disable Debug</button>
        <button onclick="toggleEventQueueDebug()">Hide</button>
      </div>
    </div>
  `);

  $('body').append(debugPanel);
}

function updateEventQueueDebugPanel() {
  const status = eventQueue.getStatus();
  $('#queue-length').text(status.queueLength);
  $('#processing-status').text(status.processing);
  $('#processed-count').text(status.processedCount);
}

function toggleEventQueueDebug() {
  $('#event-queue-debug').toggle();
}

// Update debug panel every 100ms when visible
setInterval(() => {
  if ($('#event-queue-debug').is(':visible')) {
    updateEventQueueDebugPanel();
  }
}, 100);

// Add keyboard shortcut to toggle debug panel (Ctrl+Shift+Q)
$(document).keydown(function (e) {
  if (e.ctrlKey && e.shiftKey && e.keyCode === 81) { // Q key
    if ($('#event-queue-debug').length === 0) {
      createEventQueueDebugPanel();
    }
    toggleEventQueueDebug();
  }
});

// Global functions used by EventQueue and other components
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

// Global variables used by EventQueue and other components
let active_background_sound = null;
let active_track_id = -1;
let backgroundSoundStartTime = null;
let pageRenderTime = null;

const switchPOV = (entity_uid, canvas) => {
  // Close all interactive UI elements before switching characters
  if (Utils && Utils.closeAllInteractiveElements) {
    Utils.closeAllInteractiveElements();
  } else {
    // Fallback for older versions or if Utils is not available
    $(".popover-menu, .popover-menu-2").hide();
    $('#targetSelectionModal').modal('hide');
    targetMode = multiTargetMode = moveMode = coneMode = false;
    $(".add-to-target").hide();
    $(".highlighted").removeClass("highlighted");
    $(".target-selection, .active-selection").hide();
    $(".die-roll-component:visible").hide();
    if (globalCanvas && globalCtx) {
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
    }
  }

  ajaxPost("/switch_pov", { entity_uid }, (data) => {
    console.log("Switched POV:", data);
    if (data.background) {
      Utils.updateMapDisplay(data, canvas);
      // Apply map-default effect if provided and DM has no active override.
      // If no default and no DM override, clear any previous effects.
      try {
        if (!data.dm_active && typeof Effects !== 'undefined') {
          if (data.map_default_effect && Effects.applyEffect) {
            Effects.applyEffect(data.map_default_effect);
          } else if (Effects.stopAll) {
            Effects.stopAll();
          }
        }
      } catch (e) { console.warn('Failed to apply/clear effect on POV switch', e); }
      // Ask server to (re)send effects after map switch in case client missed anything
      try { if (typeof socket !== 'undefined' && socket && socket.emit) socket.emit('request_effects'); } catch (e) {}
    }
    // update the pov entity id in the body data
    $('body').attr('data-pov-entity', data.pov_entity);
    Utils.refreshTileSet(
      (is_setup = false),
      (pov = true),
      (x = 0),
      (y = 0),
      (entity_uid = entity_uid),
      () => {
        const $tile = $(`.tile[data-coords-id="${entity_uid}"]`);
        createGlobalCanvas();
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

// DM Sound Manager - Enhanced soundtrack control for DMs
const DMSoundManager = {
  // Store volume preferences for each track
  trackVolumes: {},
  currentTrackId: null,
  isPlaying: false,

  // Load track volumes from localStorage
  loadTrackVolumes: function () {
    const saved = localStorage.getItem('dmTrackVolumes');
    if (saved) {
      try {
        this.trackVolumes = JSON.parse(saved);
      } catch (e) {
        console.warn('Failed to load track volumes:', e);
        this.trackVolumes = {};
      }
    }
  },

  // Save track volumes to localStorage
  saveTrackVolumes: function () {
    try {
      localStorage.setItem('dmTrackVolumes', JSON.stringify(this.trackVolumes));
    } catch (e) {
      console.warn('Failed to save track volumes:', e);
    }
  },

  // Get saved volume for a track (default 50)
  getTrackVolume: function (trackId) {
    return this.trackVolumes[trackId] || 50;
  },

  // Set volume for a track
  setTrackVolume: function (trackId, volume) {
    this.trackVolumes[trackId] = volume;
    this.saveTrackVolumes();
  },

  // Switch to a track (one-click switching)
  switchToTrack: function (trackId) {
    if (trackId === this.currentTrackId && this.isPlaying) {
      // Same track and playing - toggle pause
      this.togglePlayPause();
      return;
    }

    // Different track or resuming - switch to it
    const volume = this.getTrackVolume(trackId);

    // Send track switch request to server
    ajaxPost(
      "/sound",
      { track_id: trackId },
      (data) => {
        console.log("Track switched successfully:", data);
        this.currentTrackId = trackId;
        this.isPlaying = trackId !== "-1";

        // Update global state
        active_track_id = trackId;

        // If stopping music, clear the audio
        if (trackId === "-1") {
          if (active_background_sound) {
            active_background_sound.pause();
            active_background_sound = null;
          }
        }

        this.updateUI();
      },
      true
    );

    // Also send volume if not stopping
    if (trackId !== "-1") {
      setTimeout(() => {
        ajaxPost(
          "/volume",
          { volume: volume },
          () => console.log("Volume set for track:", trackId, volume),
          true
        );
      }, 100);
    }
  },

  // Toggle play/pause for current track
  togglePlayPause: function () {
    if (this.currentTrackId && this.currentTrackId !== "-1") {
      if (this.isPlaying) {
        // Pause - stop the track
        ajaxPost(
          "/sound",
          { track_id: "-1" },
          (data) => {
            console.log("Track paused successfully:", data);
            // Keep track ID but mark as not playing (paused state)
            this.isPlaying = false;
            this.updateUI();
          },
          true
        );
      } else {
        // Resume - play the track again
        const volume = this.getTrackVolume(this.currentTrackId);
        ajaxPost(
          "/sound",
          { track_id: this.currentTrackId },
          (data) => {
            console.log("Track resumed successfully:", data);
            this.isPlaying = true;
            this.updateUI();
          },
          true
        );

        // Set volume
        setTimeout(() => {
          ajaxPost(
            "/volume",
            { volume: volume },
            () => console.log("Volume restored for resumed track:", volume),
            true
          );
        }, 100);
      }
    }
  },

  // Stop current track
  stopTrack: function () {
    ajaxPost(
      "/sound",
      { track_id: "-1" },
      (data) => {
        console.log("Track stopped successfully:", data);
        this.currentTrackId = "-1";
        this.isPlaying = false;
        active_track_id = -1;

        if (active_background_sound) {
          active_background_sound.pause();
          active_background_sound = null;
        }

        this.updateUI();
      },
      true
    );
  },

  // Update UI elements
  updateUI: function () {
    const currentDisplay = $('#current-track-display');
    const playBtn = $('.play-btn');
    const pauseBtn = $('.pause-btn');
    const stopBtn = $('.stop-btn');
    const volumeSection = $('.volume-controls');

    // Update current track display
    if (this.currentTrackId && this.currentTrackId !== "-1") {
      const trackItem = $(`.track-item[data-track-id="${this.currentTrackId}"]`);
      const trackName = trackItem.find('.track-name').text().replace('🎵 ', '');
      currentDisplay.text(trackName);

      // Show/hide playback controls
      if (this.isPlaying) {
        playBtn.hide();
        pauseBtn.show();
        stopBtn.show();
        volumeSection.show();
      } else {
        playBtn.show();
        pauseBtn.hide();
        stopBtn.hide();
        volumeSection.hide();
      }
    } else {
      currentDisplay.text('None');
      playBtn.hide();
      pauseBtn.hide();
      stopBtn.hide();
      volumeSection.hide();
    }

    // Update track list highlighting
    $('.track-item').removeClass('active-track');
    if (this.currentTrackId) {
      $(`.track-item[data-track-id="${this.currentTrackId}"]`).addClass('active-track');
    }

    // Update volume displays
    this.updateVolumeDisplays();
  },

  // Update volume displays for all tracks
  updateVolumeDisplays: function () {
    $('.track-item').each((index, element) => {
      const $element = $(element);
      const trackId = $element.data('track-id');
      if (trackId && trackId !== "-1") {
        const volume = this.getTrackVolume(trackId);
        $element.find('.track-vol-display').text(volume);
      }
    });
  },

  // Set volume for current track
  setCurrentVolume: function (volume) {
    if (this.currentTrackId && this.currentTrackId !== "-1") {
      this.setTrackVolume(this.currentTrackId, volume);

      // Send to server
      ajaxPost(
        "/volume",
        { volume: volume },
        () => console.log("Volume updated for current track:", volume),
        true
      );

      // Update display
      $('.volume-display').text(volume + '%');
      this.updateVolumeDisplays();
    }
  },

  // Initialize the sound manager
  init: function () {
    this.loadTrackVolumes();

    // Get current state from active_track_id
    this.currentTrackId = active_track_id;
    this.isPlaying = active_background_sound !== null;

    this.updateUI();
  }
};

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

  // Update DM Sound Manager state
  if (typeof DMSoundManager !== 'undefined') {
    DMSoundManager.currentTrackId = track_id;
    DMSoundManager.isPlaying = true;
  }

  // Apply user volume control if available (for non-DM users)
  if (typeof UserVolumeControl !== 'undefined') {
    setTimeout(() => UserVolumeControl.applyUserVolume(), 100);
  }
};

// User Volume Control System (for non-DM users)
const UserVolumeControl = {
  // Get user's saved volume preference (0-100)
  getUserVolume: function () {
    const saved = localStorage.getItem('userMusicVolume');
    return saved !== null ? parseInt(saved) : 70; // Default to 70%
  },

  // Save user's volume preference
  setUserVolume: function (volume) {
    localStorage.setItem('userMusicVolume', volume.toString());
  },

  // Get user's mute preference
  getUserMuted: function () {
    return localStorage.getItem('userMusicMuted') === 'true';
  },

  // Save user's mute preference
  setUserMuted: function (muted) {
    localStorage.setItem('userMusicMuted', muted.toString());
  },

  // Apply user volume on top of DM volume
  applyUserVolume: function () {
    if (active_background_sound) {
      const dmVolume = parseFloat($('body').attr('data-soundtrack-volume')) || 50;
      const userVolume = this.getUserVolume();
      const isMuted = this.getUserMuted();

      // Calculate effective volume: DM volume * user volume multiplier
      const effectiveVolume = isMuted ? 0 : (dmVolume / 100) * (userVolume / 100);
      active_background_sound.volume = Math.max(0, Math.min(1, effectiveVolume));

      // Update widget display
      this.updateWidget();
    }
  },

  // Update the music control widget
  updateWidget: function () {
    const widget = $('#music-control-widget');
    const userVolume = this.getUserVolume();
    const isMuted = this.getUserMuted();
    const trackName = $('body').attr('data-soundtrack-id') || 'No music playing';

    // Update track name
    $('#current-track-name').text(trackName);

    // Update volume slider
    $('#user-volume-slider').val(userVolume);
    $('#volume-display').text(userVolume + '%');

    // Update mute button
    const muteIcon = $('#mute-icon');
    const muteText = $('#mute-text');
    if (isMuted) {
      muteIcon.removeClass('glyphicon-volume-up').addClass('glyphicon-volume-off');
      muteText.text('Unmute');
      $('#mute-toggle').addClass('btn-warning').removeClass('btn-default');
    } else {
      muteIcon.removeClass('glyphicon-volume-off').addClass('glyphicon-volume-up');
      muteText.text('Mute');
      $('#mute-toggle').removeClass('btn-warning').addClass('btn-default');
    }

    // Show widget if music is playing
    if (active_background_sound && trackName !== 'No music playing') {
      widget.show().addClass('fade-in');
    } else {
      widget.hide();
    }
  },

  // Initialize the user volume control system
  init: function () {
    const self = this;

    // Set up volume slider
    $('#user-volume-slider').on('input', function () {
      const volume = parseInt($(this).val());
      self.setUserVolume(volume);
      self.applyUserVolume();
    });

    // Set up mute toggle
    $('#mute-toggle').on('click', function () {
      const isMuted = !self.getUserMuted();
      self.setUserMuted(isMuted);
      self.applyUserVolume();
    });

    // Set up widget collapse/expand
    $('#toggle-music-widget').on('click', function () {
      $('#music-control-widget').toggleClass('collapsed');
    });

    // Initialize widget state
    this.updateWidget();

    // Apply saved volume if music is already playing
    if (active_background_sound) {
      this.applyUserVolume();
    }
  }
};

// Returns the center coordinates of a tile element.
const getTileCenter = ($tile) => {
  if (typeof $tile === 'string') {
    $tile = $($tile);
  }
  if (!$tile.length || !$tile[0] || !$tile[0].getBoundingClientRect) {
    console.warn('getTileCenter: invalid tile or tile not found', $tile);
    return null;
  }
  const rect = $tile[0].getBoundingClientRect();
  const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
  const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
  const tile_size = $('.tiles-container').data('tile-size');
  return {
    x: rect.left + scrollLeft + tile_size / 2,
    y: rect.top + scrollTop + tile_size / 2
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
function drawLine(ctx, from, to, opts = {}) {
  const {
    lineWidth = 5,
    withArrow = false,
    randomCurve = false,
    strokeStyle = "green",
    text = null,
  } = opts;

  // Ensure from and to are objects with x and y
  // If to is a selector string, convert to jQuery object and extract x/y
  let fromCoords = from;
  let toCoords = to;
  if (typeof from === 'string') {
    const $fromTile = $(from);
    fromCoords = { x: $fromTile.data('coords-x'), y: $fromTile.data('coords-y') };
  }
  if (typeof to === 'string') {
    const $toTile = $(to);
    toCoords = { x: $toTile.data('coords-x'), y: $toTile.data('coords-y') };
  }

  // Now get centers
  const fromCenter = getTileCenter($(`.tile[data-coords-x="${fromCoords.x}"][data-coords-y="${fromCoords.y}"]`));
  const toCenter = getTileCenter($(`.tile[data-coords-x="${toCoords.x}"][data-coords-y="${toCoords.y}"]`));

  // Check if we successfully got tile centers
  if (!fromCenter || !toCenter) {
    console.warn('drawLine: Could not find valid tile centers', { fromCoords, toCoords });
    return;
  }

  ctx.save();
  ctx.lineWidth = lineWidth;
  ctx.strokeStyle = strokeStyle;

  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  let angle = Math.atan2(dy, dx);

  // Draw the main line
  ctx.beginPath();
  if (randomCurve) {
    // Create a nice curve by offsetting control point along the perpendicular
    const midX = (fromCenter.x + toCenter.x) / 2;
    const midY = (fromCenter.y + toCenter.y) / 2;
    const len = Math.hypot(dx, dy) || 1;
    // Perpendicular unit vector
    const nx = -dy / len;
    const ny = dx / len;
    // Offset magnitude: 25% of segment length with slight randomness
    const mag = Math.max(20, len * (0.25 + Math.random() * 0.1));
    const dir = Math.random() < 0.5 ? -1 : 1;
    const controlX = midX + nx * mag * dir;
    const controlY = midY + ny * mag * dir;
    ctx.moveTo(fromCenter.x, fromCenter.y);
    ctx.quadraticCurveTo(controlX, controlY, toCenter.x, toCenter.y);
  } else {
    ctx.moveTo(fromCenter.x, fromCenter.y);
    ctx.lineTo(toCenter.x, toCenter.y);
  }

  // Draw arrow if needed
  if (withArrow) {
    const headlen = 10;
    ctx.moveTo(toCenter.x, toCenter.y);
    ctx.lineTo(
      toCenter.x - headlen * Math.cos(angle - Math.PI / 6),
      toCenter.y - headlen * Math.sin(angle - Math.PI / 6),
    );
    ctx.moveTo(toCenter.x, toCenter.y);
    ctx.lineTo(
      toCenter.x - headlen * Math.cos(angle + Math.PI / 6),
      toCenter.y - headlen * Math.sin(angle + Math.PI / 6),
    );
  }

  ctx.stroke();

  if (text !== null) {
    const textOffset = 15;
    const textX = toCenter.x + textOffset * Math.cos(angle);
    const textY =
      toCenter.y +
      (toCenter.y > fromCenter.y ? 1 : -1) * textOffset * Math.sin(angle);
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

// Function to show target selection modal
const showTargetSelectionModal = (targets, position, actionData = null) => {
  const $modal = $('#targetSelectionModal');
  const $targetList = $('#targetList');

  // Clear previous content
  $targetList.empty();

  // Add target options
  targets.forEach((target, index) => {
    const $targetOption = $(`
      <div class="target-option" data-target-id="${target.id}" data-target-type="${target.type}">
        <img class="target-image" src="${target.image || ''}" alt="${target.name}" style="${!target.image ? 'display: none;' : ''}">
        <div class="target-info">
          <div class="target-name">${target.name}</div>
          <div class="target-type">${target.type}</div>
        </div>
      </div>
    `);

    $targetOption.on('click', function () {
      // Remove selection from all options
      $('.target-option').removeClass('selected');
      // Add selection to clicked option
      $(this).addClass('selected');
    });

    $targetList.append($targetOption);
  });

  // Handle modal confirmation
  $modal.off('click', '.btn-primary').on('click', '.btn-primary', function () {
    const $selectedTarget = $('.target-option.selected');
    if ($selectedTarget.length > 0) {
      const targetId = $selectedTarget.data('target-id');
      const targetType = $selectedTarget.data('target-type');

      // Close modal
      $modal.modal('hide');

      if (actionData) {
        // This is a multiple target case - call the action again with the specific target
        const newActionData = { ...actionData };
        if (targetType === 'position') {
          // For position targets, use coordinates
          newActionData.target = { x: position.x, y: position.y };
        } else {
          // For entity/object targets, use the target ID
          newActionData.target = targetId;
        }

        // Call the action again with the specific target
        ajaxPost("/action", newActionData, (data) => {
          console.log("Action request successful:", data);
          refreshTurn();
        }, true);
      } else {
        // This is a regular target mode case
        if (targetType === 'position') {
          // For position targets, use coordinates
          targetModeCallback({ x: position.x, y: position.y });
        } else {
          // For entity/object targets, use the target ID
          targetModeCallback({ target_id: targetId, x: position.x, y: position.y });
        }
      }

      // Reset target mode
      targetMode = false;
      valid_target_cache = {};
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
      $(".tile").css("border", "none");
    }
  });

  // Handle modal cancellation
  $modal.off('hidden.bs.modal').on('hidden.bs.modal', function () {
    // Reset target mode if modal is closed without selection
    targetMode = false;
    valid_target_cache = {};
    globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
    $(".tile").css("border", "none");
  });

  // Show the modal
  $modal.modal('show');
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
  switch (key) {
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
      Utils.drawMovementPath(globalCtx, keyboardMovementPath, 0, true, null);
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
        Utils.drawMovementPath(globalCtx, keyboardMovementPath, data.cost.budget, data.placeable, data.terrain_info);
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

function createGlobalCanvas() {
  if (globalCanvas) {
    document.body.removeChild(globalCanvas);
  }
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
}

// Check if user is DM
function isDM() {
  return $('body').data('role') && $('body').data('role').includes('dm');
}

// Update draggable entity classes for proper cursor styling
function updateDraggableEntityClasses() {
  if (!isDM()) return;

  $('.tile').removeClass('has-draggable-entity');
  $('.tile').each(function () {
    const $tile = $(this);
    const entityId = $tile.data("coords-id");

    // Add class if tile has an entity or NPC
    if (entityId && $tile.find('.entity, .npc').length) {
      $tile.addClass('has-draggable-entity');
    }
  });
}

// --- Ghost Token System Functions ---
// Move entity to target position
function moveEntityTo(entityId, targetX, targetY) {
  // Check if there's already a pending move for this entity
  if (pendingMoves.has(entityId)) {
    console.log(`Entity ${entityId} already has a pending move, ignoring new request`);
    return;
  }

  // Find the source tile using coords-id
  const $sourceTile = $(`.tile[data-coords-id="${entityId}"]`);
  
  if (!$sourceTile.length) {
    console.error(`Could not find source tile for entity with ID: ${entityId}`);
  } else {
    const sourceX = $sourceTile.data('coords-x');
    const sourceY = $sourceTile.data('coords-y');
    const $sourceEntity = $sourceTile.find('.entity, .npc').first();
    
    if ($sourceEntity.length) {
      console.log(`Creating ghost token for entity ${entityId} moving from (${sourceX}, ${sourceY}) to (${targetX}, ${targetY})`);
      // Create ghost token at target position
      createGhostToken(entityId, sourceX, sourceY, targetX, targetY, $sourceEntity);
      
      // Mark source entity as pending move
      $sourceEntity.addClass('entity-pending-move');
    }
  }

  $.ajax({
    url: '/dm_move_entity',
    method: 'POST',
    contentType: 'application/json',
    data: JSON.stringify({
      entity_id: entityId,
      x: targetX,
      y: targetY
    }),
    success: function (response) {
      if (response.success) {
        console.log(`Entity ${entityId} moved to (${targetX}, ${targetY})`);
        // Clean up ghost token and pending state
        cleanupPendingMove(entityId);
        // The server will emit a refresh_map message, so no need to manually refresh
      } else {
        alert('Failed to move entity: ' + (response.error || 'Unknown error'));
        cleanupPendingMove(entityId);
      }
    },
    error: function (xhr, status, error) {
      console.error('Error moving entity:', error);
      alert('Error moving entity: ' + error);
      cleanupPendingMove(entityId);
    }
  });
}

// Create a ghost token at the target location
function createGhostToken(entityId, sourceX, sourceY, targetX, targetY, $sourceEntity) {
  // Don't create ghost if target is same as source
  if (sourceX === targetX && sourceY === targetY) {
    console.log('Target is same as source, skipping ghost token creation');
    return;
  }

  const $targetTile = $(`.tile[data-coords-x="${targetX}"][data-coords-y="${targetY}"]`);
  if (!$targetTile.length) {
    console.error(`Could not find target tile at (${targetX}, ${targetY})`);
    return;
  }

  // Clone the entity for the ghost
  const $ghost = $sourceEntity.clone();
  $ghost.removeClass('entity npc').addClass('entity-move-ghost');
  $ghost.removeAttr('data-entity-id'); // Remove ID to avoid conflicts
  $ghost.removeAttr('data-entity-uid');
  $ghost.removeAttr('data-entityId');
  
  // Add ghost to target tile
  $targetTile.append($ghost);
  
  // Store pending move info
  pendingMoves.set(entityId, {
    sourceX: sourceX,
    sourceY: sourceY, 
    targetX: targetX,
    targetY: targetY,
    ghostElement: $ghost
  });

  // Set up timeout to clean up ghost if request takes too long (30 seconds)
  const timeoutId = setTimeout(() => {
    console.warn(`Move request for entity ${entityId} timed out, cleaning up ghost`);
    cleanupPendingMove(entityId);
  }, 30000);
  
  moveRequestTimeouts.set(entityId, timeoutId);
}

// Clean up pending move state and ghost token
function cleanupPendingMove(entityId) {
  console.log(`Cleaning up pending move for entity: ${entityId}`);
  const pendingMove = pendingMoves.get(entityId);
  if (pendingMove) {
    // Remove ghost token
    if (pendingMove.ghostElement) {
      pendingMove.ghostElement.remove();
      console.log(`Removed ghost token for entity: ${entityId}`);
    }
    pendingMoves.delete(entityId);
  }

  // Clear timeout
  const timeoutId = moveRequestTimeouts.get(entityId);
  if (timeoutId) {
    clearTimeout(timeoutId);
    moveRequestTimeouts.delete(entityId);
  }

  // Remove pending move styling from source entity using coords-id
  const $sourceTile = $(`.tile[data-coords-id="${entityId}"]`);
  if ($sourceTile.length) {
    $sourceTile.find('.entity, .npc').removeClass('entity-pending-move');
  }
}

// Clean up all pending moves (useful for page refresh or errors)
function cleanupAllPendingMoves() {
  for (const entityId of pendingMoves.keys()) {
    cleanupPendingMove(entityId);
  }
}

// Move PC entity to target position (with ghost token support)
function movePCEntityTo(entityUid, targetX, targetY) {
  // Check if there's already a pending move for this entity
  if (pendingMoves.has(entityUid)) {
    console.log(`PC ${entityUid} already has a pending move, ignoring new request`);
    return;
  }

  // Find the source tile using coords-id
  const $sourceTile = $(`.tile[data-coords-id="${entityUid}"]`);
  
  if (!$sourceTile.length) {
    console.log(`Could not find source tile for PC entity with UID: ${entityUid}, proceeding with move anyway`);
  } else {
    const sourceX = $sourceTile.data('coords-x');
    const sourceY = $sourceTile.data('coords-y');
    const $sourceEntity = $sourceTile.find('.entity, .npc').first();
    
    if ($sourceEntity.length) {
      console.log(`Creating ghost token for PC ${entityUid} moving from (${sourceX}, ${sourceY}) to (${targetX}, ${targetY})`);
      // Create ghost token at target position
      createGhostToken(entityUid, sourceX, sourceY, targetX, targetY, $sourceEntity);
      
      // Mark source entity as pending move
      $sourceEntity.addClass('entity-pending-move');
    }
  }

  ajaxPost("/move_entity", {
    entity_uid: entityUid,
    x: targetX,
    y: targetY
  }, (data) => {
    if (data.status === 'ok') {
      console.log("PC moved successfully:", data.entity_uid);
      cleanupPendingMove(entityUid);
    } else {
      alert("Failed to move PC: " + (data.error || "Unknown error"));
      cleanupPendingMove(entityUid);
    }
  }, true);
}

// --- Document Ready: Event Bindings & Main Logic ---
$(document).ready(() => {
  let lastMovedEntityBeforeRefresh = null;
  const battleEntityList = [];

  // Initialize global variables
  backgroundSoundStartTime = $("body").data("soundtrack-time");
  pageRenderTime = new Date().getTime();

  // Initialize game time display
  const gameTimeElement = $('#game-time-text');
  if (gameTimeElement.length > 0) {
    const initialGameTime = gameTimeElement.data('seconds');
    if (initialGameTime !== undefined) {
      updateGameTimeDisplay(initialGameTime);
    }
  }

  // Initialize user volume control for non-DM users
  if (typeof UserVolumeControl !== 'undefined' && $('#music-control-widget').length > 0) {
    UserVolumeControl.init();
  }

  // --- Canvas Setup ---
  const tile_size = $(".tiles-container").data("tile-size");

  // Update draggable entity classes for cursor styling
  updateDraggableEntityClasses();

  createGlobalCanvas();
  // Update canvas size on window resize
  $(window).on('resize', function () {
    globalCanvas.width = window.innerWidth;
    globalCanvas.height = window.innerHeight;
  });

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

  // Initialize effects socket handlers if Effects exists
  if (typeof Effects !== 'undefined' && Effects.initSocketHandlers) {
    try {
      Effects.initSocketHandlers(socket);
  // Ask the server to resend any active or map-default effects now that handlers are registered
  try { socket.emit('request_effects'); } catch (e) { console.warn('Failed to request effects', e); }
    } catch (e) {
      console.warn('Failed to init Effects socket handlers', e);
    }
  }

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

  Utils.refreshTileSet();

  // --- Socket Message Handler ---
  socket.on("message", (data) => {
    // Enqueue the event for FIFO processing
    eventQueue.enqueue(data);
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

      // Update user volume control widget after music starts
      if (typeof UserVolumeControl !== 'undefined') {
        setTimeout(() => UserVolumeControl.updateWidget(), 200);
      }
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
    const volume = parseInt($(this).val());
    $('.volume-display').text(volume + '%');

    if (active_background_sound) {
      // Update DM Sound Manager volume
      if (typeof DMSoundManager !== 'undefined') {
        DMSoundManager.setCurrentVolume(volume);
      } else {
        // Fallback to original behavior
        ajaxPost(
          "/volume",
          { volume: volume },
          () => console.log("Volume updated successfully"),
          true,
        );
      }
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
    Utils.switchMap(map_id, globalCanvas, () => {
      createGlobalCanvas();
    });
  });

  // Handle tile-based map selection
  $("#mapModal").on("click", ".map-card", function (event) {
    const mapName = $(this).data("map-name");
    if (!mapName) return; // ignore non-map tiles (e.g., create-new)
    Utils.switchMap(mapName, globalCanvas, () => {
      createGlobalCanvas();
    });
  });

  // Handle create new map tile
  $("#mapModal").on("click", "#create-new-map", function () {
    // simple prompt for map name
    let mapName = window.prompt("Enter a name for the new map (letters, numbers, underscores):", "new_map");
    if (!mapName) return;
    mapName = (mapName || "").trim().toLowerCase().replace(/[^a-z0-9_\-]/g, "_");
    if (!mapName) {
      alert("Invalid map name.");
      return;
    }
    let width = parseInt(window.prompt("Map width (tiles)", "16"), 10);
    let height = parseInt(window.prompt("Map height (tiles)", "8"), 10);
    if (isNaN(width) || isNaN(height)) { width = 16; height = 8; }
    width = Math.max(2, Math.min(100, width));
    height = Math.max(2, Math.min(100, height));
    ajaxPost(
      "/create_map",
      { name: mapName, width, height },
      (data) => {
        if (data && data.error) {
          alert(data.error);
          return;
        }
        // Add the new tile to the grid if not present
        const $grid = $("#map-grid");
        if ($grid.length && $grid.find(`.map-card[data-map-name='${mapName}']`).length === 0) {
          const tileHtml = `
            <div class="map-card" data-map-name="${mapName}">
              <div class="upload-overlay">
                <button class="btn btn-xs btn-default upload-map-bg" title="Upload background" data-map-name="${mapName}">
                  <span class="glyphicon glyphicon-upload"></span>
                </button>
                <button class="btn btn-xs btn-danger delete-map" title="Delete map" data-map-name="${mapName}">
                  <span class="glyphicon glyphicon-trash"></span>
                </button>
                <input type="file" class="map-bg-input" data-map-name="${mapName}" accept="image/*" style="display:none;" />
              </div>
              <img class="map-thumb" src="/assets/maps/${mapName}.png" alt="${mapName}" onerror="this.onerror=null;this.src='/static/info.png';">
              <div class="map-name">${mapName}</div>
            </div>`;
          $(tileHtml).insertBefore($("#create-new-map"));
        }
        // Switch to the new map
        Utils.switchMap(mapName, globalCanvas, () => {
          createGlobalCanvas();
        });
      }
    );
  });

  // Trigger file chooser for upload button
  $("#mapModal").on("click", ".upload-map-bg", function (e) {
    e.stopPropagation();
    const mapName = $(this).data('map-name');
    $(this).closest('.map-card').find(`.map-bg-input[data-map-name='${mapName}']`).trigger('click');
  });

  // Handle delete map with warnings
  $("#mapModal").on("click", ".delete-map", function (e) {
    e.stopPropagation();
    const mapName = $(this).data('map-name');
    if (!mapName) return;
    // Show warnings
    const warn1 = `Delete map "${mapName}"? This will remove its YAML and background image.`;
    const warn2 = 'This action cannot be undone. Are you sure?';
    if (!window.confirm(warn1)) return;
    if (!window.confirm(warn2)) return;

    ajaxPost('/delete_map', { name: mapName }, (resp) => {
      if (resp && resp.error) {
        alert(resp.error);
        return;
      }
      // Remove tile from UI
      $(`.map-card[data-map-name='${mapName}']`).remove();

      // If current map deleted, switch to index or any remaining map
      const currentMap = $('body').attr('data-current-map');
      if (currentMap === mapName) {
        const $first = $("#map-grid .map-card[data-map-name]").first();
        const target = $first.data('map-name') || 'index';
        Utils.switchMap(target, globalCanvas, () => {
          createGlobalCanvas();
        });
      }
    });
  });

  // Handle image file selection and upload
  $("#mapModal").on("change", ".map-bg-input", function () {
    const input = this;
    const files = input.files;
    const mapName = $(this).data('map-name');
    if (!files || files.length === 0) return;
    const formData = new FormData();
    formData.append('map', mapName);
    formData.append('image', files[0]);

    $.ajax({
      url: '/upload_map_background',
      type: 'POST',
      data: formData,
      processData: false,
      contentType: false,
      success: (data) => {
        if (data && data.error) {
          alert(data.error);
          return;
        }
        // Refresh tile thumbnail
        const $tile = $(`.map-card[data-map-name='${mapName}'] .map-thumb`);
        $tile.attr('src', `/assets/maps/${mapName}.png?ts=${Date.now()}`);

        // If currently on this map, update background immediately
        const currentMap = $('body').attr('data-current-map');
        if (currentMap === mapName && data.background) {
          const resp = { background: data.background, name: mapName, width: $("#tiles-area").data('width'), height: $("#tiles-area").data('height'), image_offset_px: [0,0] };
          Utils.updateMapDisplay(resp, globalCanvas);
        }
      },
      error: (jqXHR) => {
        alert('Upload failed');
      }
    });
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
      // Check if there are multiple valid targets at this position
      if (globalActionInfo && (globalActionInfo === 'AttackAction' || globalActionInfo === 'LinkedAttackAction' || globalActionInfo === 'SpellAction')) {
        Utils.ajaxGet("/targets_at_position", {
          entity_id: globalSourceEntity,
          x: coordsx,
          y: coordsy,
          action_info: globalActionInfo,
          opts: JSON.stringify(globalOpts || {})
        }, (data) => {
          if (data.success && data.targets && data.targets.length > 1) {
            // Show target selection modal
            showTargetSelectionModal(data.targets, { x: coordsx, y: coordsy });
          } else {
            // Single target or no targets, proceed normally
            targetModeCallback({ x: coordsx, y: coordsy });
            targetMode = false;
            valid_target_cache = {};
            globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
            $(".tile").css("border", "none");
          }
        });
      } else {
        // Not a point target action, proceed normally
        targetModeCallback({ x: coordsx, y: coordsy });
        targetMode = false;
        valid_target_cache = {};
        globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
        $(".tile").css("border", "none");
      }
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

          // Ensure the popover menu stays on top after being shown
          if (Utils && Utils.ensurePopoverMenusOnTop) {
            Utils.ensurePopoverMenusOnTop();
          }
        });
      }
    }
  });

  $(".tiles-container").on(
    "click",
    ".show-note-btn, .object-note-overlay",
    function (e) {
      e.stopPropagation();
      // Call the note modal function if it's a note button
      if ($(this).hasClass('show-note-btn')) {
        Utils.showNoteModal(this);
      }
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
  $('#floating-entity-portraits').on('click', '.floating-entity-portrait', function () {
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
            lastPathForJump = data.path;

            // Add the new path segment to the movement path
            movePath = [...movePath, ...data.path];
            // Draw the complete path; if jumpMode, suppress base arrow to avoid double arrows
            Utils.drawMovementPath(
              globalCtx,
              movePath,
              available_cost,
              data.placeable,
              data.terrain_info,
              { suppressArrow: jumpMode }
            );

            // If in jump mode, draw a curved green segment preview and enforce jump range limit
            if (jumpMode && movePath.length > 1) {
              const entity_uid = $("body").attr('data-pov-entity');
              // Decide running vs standing: if we moved at least 2 tiles before the jump start, it's running
              const preJumpLen = jumpStartIndex !== null ? Math.max(0, jumpStartIndex) : movePath.length - 1;
              const running = preJumpLen >= 1; // running if we had at least one step before jump start
              Utils.ajaxGet('/jump_info', { id: entity_uid, running: running ? 1 : 0 }, (jdata) => {
                const grids = jdata.grids || jdata.running_grids || 0;
                // Determine start and end indices for the jump segment
                const startIdx = (jumpStartIndex !== null) ? jumpStartIndex : (movePath.length - 2);
                let maxEndIdx = Math.min(movePath.length - 1, startIdx + grids);
                // Draw curved line from start to clamped end
                const from = { x: movePath[startIdx][0], y: movePath[startIdx][1] };
                const to = { x: movePath[maxEndIdx][0], y: movePath[maxEndIdx][1] };
                // Always render a smooth curve even for straight (horizontal/vertical) jumps by forcing a control offset
                drawLine(globalCtx, from, to, { lineWidth: 4, withArrow: true, randomCurve: true, strokeStyle: 'green', text: 'Jump' });

                // Optionally visualize disallowed further squares beyond maxEndIdx by marking borders
                $(".tile").css("border", "none");
                for (let i = maxEndIdx + 1; i < movePath.length; i++) {
                  const x = movePath[i][0], y = movePath[i][1];
                  $(`.tile[data-coords-x="${x}"][data-coords-y="${y}"]`).css('border', '2px solid #999');
                }
              });
            }
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
          }, 50); // 0.1 seconds delay
        }
      }
    }
  });

  // Add mouseout handler to clear the debounce timer
  $(".tiles-container").on("mouseout", ".tile", function () {
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
  jumpMode = false;
  jumpStartIndex = null;
  lastPathForJump = null;
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
    // Toggle jump mode with 'J' key
    if (event.key && event.key.toLowerCase() === 'j') {
      if (moveMode) {
        // Toggle
        jumpMode = !jumpMode;
        if (!jumpMode) {
          jumpStartIndex = null;
          // clear any jump overlay by redrawing base path
          if (movePath && movePath.length > 1 && typeof Utils.drawMovementPath === 'function') {
            Utils.drawMovementPath(globalCtx, movePath, currentPosition ? currentPosition.cost : 0, true, null, { suppressArrow: false });
            $(".tile").css("border", "none");
          }
        } else {
          // entering jump mode: mark current end as start
          jumpStartIndex = (movePath && movePath.length > 0) ? (movePath.length - 1) : null;
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
  jumpMode = false;
  jumpStartIndex = null;
  lastPathForJump = null;
      globalCtx.clearRect(0, 0, globalCanvas.width, globalCanvas.height);
      $(".tile").css("border", "none");
      $(".add-to-target, .popover-menu-2").hide();
    }
  });

  // Multi-target selection.
  $(".tiles-container").on("click", ".add-to-target", function (e) {
    const $tile = $(this).closest(".tile");
    const entity_uid = $tile.data("coords-id");
    const coordsx = $tile.data("coords-x");
    const coordsy = $tile.data("coords-y");
    if (!multiTargetList.includes(entity_uid) || !multiTargetModeUnique) {
      if (multiTargetList.length < max_targets) {
        multiTargetList.push(entity_uid);
        if (multiTargetModeUnique) $(this).hide();
        drawLine(globalCtx, source, { x: coordsx, y: coordsy }, {
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

  // Drag and drop functionality for turn order reordering (DM only)
  let draggedElement = null;
  let draggedIndex = -1;

  $("#turn-order").on("dragstart", ".turn-order-item[draggable='true']", function (e) {
    // Only allow dragging from the drag handle or empty areas, not from form elements
    const target = e.originalEvent.target;
    if (target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'BUTTON' ||
        target.closest('input, select, button')) {
      e.preventDefault();
      return false;
    }
    
    draggedElement = this;
    draggedIndex = $(this).index();
    $(this).addClass("dragging");
    
    // Set drag data
    e.originalEvent.dataTransfer.effectAllowed = "move";
    e.originalEvent.dataTransfer.setData("text/html", this.outerHTML);
    
    console.log("Started dragging entity:", $(this).data("id"));
  });

  $("#turn-order").on("dragend", ".turn-order-item[draggable='true']", function (e) {
    $(this).removeClass("dragging");
    $(".turn-order-item").removeClass("drag-over drag-over-bottom");
    draggedElement = null;
    draggedIndex = -1;
  });

  $("#turn-order").on("dragover", ".turn-order-item", function (e) {
    e.preventDefault();
    e.originalEvent.dataTransfer.dropEffect = "move";
    
    if (this !== draggedElement) {
      const rect = this.getBoundingClientRect();
      const midpoint = rect.top + rect.height / 2;
      const mouseY = e.originalEvent.clientY;
      
      $(".turn-order-item").removeClass("drag-over drag-over-bottom");
      
      if (mouseY < midpoint) {
        $(this).addClass("drag-over");
      } else {
        $(this).addClass("drag-over-bottom");
      }
    }
  });

  $("#turn-order").on("drop", ".turn-order-item", function (e) {
    e.preventDefault();
    
    if (this !== draggedElement) {
      const targetIndex = $(this).index();
      const rect = this.getBoundingClientRect();
      const midpoint = rect.top + rect.height / 2;
      const mouseY = e.originalEvent.clientY;
      
      let newIndex = targetIndex;
      if (mouseY >= midpoint) {
        newIndex = targetIndex + 1;
      }
      
      // Adjust for moving elements within the same container
      if (draggedIndex < newIndex) {
        newIndex--;
      }
      
      // Get the new order of entity IDs
      const $turnOrderItems = $("#turn-order .turn-order-item");
      const entityOrder = [];
      
      $turnOrderItems.each(function(index) {
        if (this !== draggedElement) {
          entityOrder.push($(this).data("id"));
        }
      });
      
      // Insert the dragged element at the new position
      const draggedEntityId = $(draggedElement).data("id");
      entityOrder.splice(newIndex, 0, draggedEntityId);
      
      console.log("Reordering initiative:", entityOrder);
      
      // Send the new order to the server
      ajaxPost("/reorder_initiative", 
        { entity_order: entityOrder }, 
        (data) => {
          if (data.status === 'ok') {
            console.log("Initiative reordered successfully");
            // Refresh the turn order display
            refreshTurnOrder();
          } else {
            console.error("Failed to reorder initiative:", data.error);
            alert("Failed to reorder initiative: " + (data.error || "Unknown error"));
          }
        },
        true
      );
    }
    
    $(".turn-order-item").removeClass("drag-over drag-over-bottom");
  });

  // Prevent default drag behavior on the turn order container
  $("#turn-order").on("dragover", function(e) {
    e.preventDefault();
  });

  // Prevent dragging when clicking on form elements
  $("#turn-order").on("mousedown", "input, select, button", function(e) {
    e.stopPropagation();
  });

  $("#select-soundtrack").click(() => {
    $.get("/tracks", { track_id: active_track_id }, (data) => {
      $("#modal-1 .modal-content").html(data);
      $("#modal-1").modal("show");

      // Initialize DM Sound Manager after modal loads
      setTimeout(() => {
        DMSoundManager.init();
      }, 100);
    });
  });

  // Character Builder menu entry
  $(document).on('click', '#character-builder', function() {
    window.location.href = '/character_builder';
  });

  // NPC Spawner functionality
  $("#toggle-npc-spawner").click(() => {
    const $npcSpawner = $("#npc-spawner");
    if ($npcSpawner.is(":visible")) {
      $npcSpawner.hide();
    } else {
      loadAvailableNPCs();
      $npcSpawner.show();
    }
  });

  $("#close-npc-spawner").click(() => {
    $("#npc-spawner").hide();
  });

  // Load available NPCs function
  function loadAvailableNPCs() {
    $.get("/available_npcs", (data) => {
      if (data.npcs) {
        displayNPCs(data.npcs);
      }
    }).fail((jqXHR) => {
      console.error("Failed to load NPCs:", jqXHR.responseJSON ? jqXHR.responseJSON.error : jqXHR.statusText);
      $("#npc-list").html('<div class="alert alert-danger">Failed to load NPCs</div>');
    });
  }

  // Display NPCs in the spawner window
  function displayNPCs(npcs) {
    const $npcList = $("#npc-list");
    $npcList.empty();

    npcs.forEach((npc) => {
      const $npcItem = $(`
        <div class="npc-item" draggable="true" data-npc-type="${npc.id}" title="AC: ${npc.ac}, HP: ${npc.hp}">
          <img class="npc-item-image" src="/assets/${npc.image}" alt="${npc.name}" onerror="this.onerror=null;this.src='/static/assets/token_player.png'">
          <div class="npc-item-info">
            <div class="npc-item-name">${npc.name}</div>
            <div class="npc-item-type">CR ${npc.cr} • ${npc.size} • AC ${npc.ac}</div>
          </div>
        </div>
      `);
      $npcList.append($npcItem);
    });
  }

  // NPC search functionality
  $("#npc-search-input").on("input", function() {
    const searchTerm = $(this).val().toLowerCase();
    $(".npc-item").each(function() {
      const npcName = $(this).find(".npc-item-name").text().toLowerCase();
      if (npcName.includes(searchTerm)) {
        $(this).show();
      } else {
        $(this).hide();
      }
    });
  });

  // NPC drag and drop functionality
  let draggedNPC = null;
  let draggedObject = null;

  $("#npc-list").on("dragstart", ".npc-item", function(e) {
    draggedNPC = $(this).data("npc-type");
    $(this).addClass("dragging");
    e.originalEvent.dataTransfer.effectAllowed = "copy";
    e.originalEvent.dataTransfer.setData("text/plain", draggedNPC);
    
    // Add visual feedback for empty tiles
    $("body").addClass("npc-drag-active");
    $(".tile").each(function() {
      if ($(this).find(".entity").length === 0) {
        $(this).addClass("empty-tile-highlight");
      }
    });
    
    console.log("Started dragging NPC:", draggedNPC);
  });

  $("#npc-list").on("dragend", ".npc-item", function(e) {
    $(this).removeClass("dragging");
    $(".tile").removeClass("battlefield-drop-zone drag-over empty-tile-highlight");
    $("body").removeClass("npc-drag-active");
    draggedNPC = null;
  });

  // Battlefield drop zone functionality
  $(".tiles-container").on("dragover", ".tile", function(e) {
    if (draggedNPC || draggedObject) {
      e.preventDefault();
      e.originalEvent.dataTransfer.dropEffect = "copy";
      
      const $tile = $(this);
      
      if (draggedNPC) {
        // Only show drop zone for NPCs if tile is empty
        const hasEntity = $tile.find(".entity").length > 0;
        if (!hasEntity) {
          $(".tile").removeClass("drag-over");
          $tile.addClass("battlefield-drop-zone drag-over");
        }
      } else if (draggedObject) {
        // Objects can be placed anywhere, so always show drop zone
        $(".tile").removeClass("drag-over");
        $tile.addClass("battlefield-drop-zone drag-over");
      }
    }
  });

  $(".tiles-container").on("dragleave", ".tile", function(e) {
    if (draggedNPC || draggedObject) {
      $(this).removeClass("drag-over");
    }
  });

  $(".tiles-container").on("drop", ".tile", function(e) {
    e.preventDefault();
    
    const $tile = $(this);
    const x = parseInt($tile.data("coords-x"));
    const y = parseInt($tile.data("coords-y"));
    
    if (draggedNPC) {
      // Handle NPC spawning (only on empty tiles)
      const hasEntity = $tile.find(".entity").length > 0;
      if (!hasEntity) {
        console.log(`Spawning ${draggedNPC} at (${x}, ${y})`);
        
        ajaxPost("/spawn_npc", {
          npc_type: draggedNPC,
          x: x,
          y: y
        }, (data) => {
          if (data.status === 'ok') {
            console.log("NPC spawned successfully:", data.entity_uid);
          } else {
            alert("Failed to spawn NPC: " + (data.error || "Unknown error"));
          }
        }, true);
      } else {
        console.log("Cannot place NPC: position is occupied");
      }
    } else if (draggedObject) {
      // Handle object spawning (can be placed anywhere)
      console.log(`Spawning ${draggedObject} at (${x}, ${y})`);
      
      ajaxPost("/spawn_object", {
        object_type: draggedObject,
        x: x,
        y: y
      }, (data) => {
        if (data.status === 'ok') {
          console.log("Object spawned successfully:", data.entity_uid);
        } else {
          alert("Failed to spawn object: " + (data.error || "Unknown error"));
        }
      }, true);
    } else if ($('body').hasClass('pc-drag-active')) {
      // Handle PC placement/movement (only on empty tiles)
      const hasEntity = $tile.find(".entity").length > 0;
      if (!hasEntity) {
        const draggedData = e.originalEvent.dataTransfer.getData('text/plain');
        if (draggedData) {
          console.log(`Moving PC ${draggedData} to (${x}, ${y})`);
          
          // Use ghost token for PC moves too
          movePCEntityTo(draggedData, x, y);
        }
      } else {
        console.log("Cannot place PC: position is occupied");
      }
    }
    
    $(".tile").removeClass("battlefield-drop-zone drag-over");
  });

  // PC Spawner functionality
  $("#toggle-pc-spawner").click(() => {
    const $pcSpawner = $("#pc-spawner");
    if ($pcSpawner.is(":visible")) {
      $pcSpawner.hide();
    } else {
      loadPCs();
      $pcSpawner.show();
    }
  });

  $("#close-pc-spawner").click(() => {
    $("#pc-spawner").hide();
  });

  // Load PCs from server
  function loadPCs() {
    Utils.ajaxGet("/available_pcs", {}, (data) => {
      if (data.status === 'ok') {
        displayPCs(data.pcs);
      } else {
        console.error("Failed to load PCs:", data.error);
        $("#pc-list").html('<div class="alert alert-danger">Failed to load PCs</div>');
      }
    });
  }

  // Display PCs in the spawner window
  function displayPCs(pcs) {
    const $pcList = $("#pc-list");
    $pcList.empty();

    if (!pcs || pcs.length === 0) {
      $pcList.append('<div class="alert alert-info">No player characters available</div>');
      return;
    }

    pcs.forEach((pc) => {
      const classInfo = pc.class_and_level.length > 0 ? `Lvl ${pc.class_and_level[0][1] || '?'} ${pc.class_and_level[0][0] || 'Unknown'}` : 'Unknown Class';
      
      const $pcItem = $(`
        <div class="pc-item" draggable="true" data-entity-uid="${pc.entity_uid}" title="${pc.race} ${classInfo}">
          <img class="pc-item-image" src="/assets/${pc.token_image}" alt="${pc.name}" onerror="this.onerror=null;this.src='/static/assets/token_player.png'">
          <div class="pc-item-info">
            <div class="pc-item-name">${pc.label}</div>
            <div class="pc-item-type">${pc.race} ${classInfo}</div>
          </div>
        </div>
      `);
      
      // Add drag event handlers for PCs
      $pcItem.on('dragstart', (e) => {
        e.originalEvent.dataTransfer.setData('text/plain', pc.entity_uid);
        e.originalEvent.dataTransfer.effectAllowed = 'move';
        $(e.currentTarget).addClass('dragging');
        $('body').addClass('pc-drag-active');
        
        // Add visual feedback for empty tiles
        $(".tile").each(function() {
          if ($(this).find(".entity").length === 0) {
            $(this).addClass("empty-tile-highlight");
          }
        });
      });

      $pcItem.on('dragend', (e) => {
        $(e.currentTarget).removeClass('dragging');
        $('body').removeClass('pc-drag-active');
        $(".tile").removeClass("battlefield-drop-zone drag-over empty-tile-highlight");
      });

      $pcList.append($pcItem);
    });

    // Add search functionality for PCs
    $("#pc-search-input").off('input').on('input', function() {
      const searchTerm = $(this).val().toLowerCase();
      $(".pc-item").each(function() {
        const pcName = $(this).find('.pc-item-name').text().toLowerCase();
        const pcType = $(this).find('.pc-item-type').text().toLowerCase();
        if (pcName.includes(searchTerm) || pcType.includes(searchTerm)) {
          $(this).show();
        } else {
          $(this).hide();
        }
      });
    });
  }

  // Object Spawner functionality
  $("#toggle-object-spawner").click(() => {
    const $objectSpawner = $("#object-spawner");
    if ($objectSpawner.is(":visible")) {
      $objectSpawner.hide();
    } else {
      loadAvailableObjects();
      $objectSpawner.show();
    }
  });

  $("#close-object-spawner").click(() => {
    $("#object-spawner").hide();
  });

  // Load available objects function
  function loadAvailableObjects() {
    $.get("/available_objects", (data) => {
      if (data.objects) {
        displayObjects(data.objects);
      }
    }).fail((jqXHR) => {
      console.error("Failed to load objects:", jqXHR.responseJSON ? jqXHR.responseJSON.error : jqXHR.statusText);
      $("#object-list").html('<div class="alert alert-danger">Failed to load objects</div>');
    });
  }

  // Display objects in the spawner window
  function displayObjects(objects) {
    const $objectList = $("#object-list");
    $objectList.empty();

    if (!objects || objects.length === 0) {
      $objectList.append('<div class="alert alert-info">No objects available</div>');
      return;
    }

    objects.forEach((object) => {
      const passableText = object.passable ? "Passable" : "Blocks Movement";
      const opaqueText = object.opaque ? "Opaque" : "Transparent";
      
      const $objectItem = $(`
        <div class="object-item" draggable="true" data-object-type="${object.id}" title="${object.description || object.name}">
          <img class="object-item-image" src="/assets/editor/${object.image}" alt="${object.name}">
          <div class="object-item-info">
            <div class="object-item-name">${object.name}</div>
            <div class="object-item-type">AC ${object.ac} • HP ${object.hp} • ${passableText}</div>
          </div>
        </div>
      `);
      
      // Add drag event handlers for objects
      $objectItem.on('dragstart', (e) => {
        draggedObject = $(e.currentTarget).data('object-type');
        $(e.currentTarget).addClass('dragging');
        e.originalEvent.dataTransfer.effectAllowed = 'copy';
        e.originalEvent.dataTransfer.setData('text/plain', draggedObject);
        
        // Add visual feedback for tiles
        $('body').addClass('object-drag-active');
        $(".tile").each(function() {
          $(this).addClass("empty-tile-highlight");
        });
        
        console.log("Started dragging object:", draggedObject);
      });

      $objectItem.on('dragend', (e) => {
        $(e.currentTarget).removeClass('dragging');
        $('body').removeClass('object-drag-active');
        $(".tile").removeClass("battlefield-drop-zone drag-over empty-tile-highlight");
        draggedObject = null;
      });

      $objectList.append($objectItem);
    });

    // Add search functionality for objects
    $("#object-search-input").off('input').on('input', function() {
      const searchTerm = $(this).val().toLowerCase();
      $(".object-item").each(function() {
        const objectName = $(this).find('.object-item-name').text().toLowerCase();
        const objectType = $(this).find('.object-item-type').text().toLowerCase();
        if (objectName.includes(searchTerm) || objectType.includes(searchTerm)) {
          $(this).show();
        } else {
          $(this).hide();
        }
      });
    });
  }

  // (Deprecated confirm-based handler removed; see unified modal-based handler below)

  // Handle action-bar delete button clicks (also used in turn order)
  $(document).on('click', '.delete-entity-btn', function(e) {
    e.preventDefault();
    e.stopPropagation();
    
    const entityUid = $(this).data('entity-uid');
    let entityName = 'this entity';
    
    // Try to find a nearby name label if in turn order
    const $row = $(this).closest('.turn-order-item');
    if ($row.length) {
      entityName = $row.find('.entity-label').text() || entityName;
    } else {
      // If triggered from tile action bar, try to infer from nameplate in tile
      const $tile = $(this).closest('.tile');
      const $nameplate = $tile.find('.nameplate');
      if ($nameplate.length) {
        entityName = $nameplate.text();
      }
    }
    
    $('#entityToDeleteName').text(entityName);
    $('#deleteEntityModal').modal('show');
    $('#confirmDeleteEntity').data('entity-uid', entityUid);
  });

  // Handle confirmation modal delete button
  $('#confirmDeleteEntity').click(function() {
    const entityUid = $(this).data('entity-uid');
    
    if (entityUid) {
      ajaxPost("/delete_entity", {
        entity_uid: entityUid
      }, (data) => {
        if (data.status === 'ok') {
          console.log("Entity deleted successfully:", data.entity_uid);
          $('#deleteEntityModal').modal('hide');
          // The map will be updated via socket message
        } else {
          alert("Failed to delete entity: " + (data.error || "Unknown error"));
        }
      }, true);
    }
  });

  // DM Sound Manager Event Handlers
  $("#modal-1 .modal-content").on("click", ".track-item", function () {
    const trackId = $(this).data('track-id');
    DMSoundManager.switchToTrack(trackId);
  });

  $("#modal-1 .modal-content").on("click", ".play-btn", function () {
    DMSoundManager.togglePlayPause();
  });

  $("#modal-1 .modal-content").on("click", ".pause-btn", function () {
    DMSoundManager.togglePlayPause();
  });

  $("#modal-1 .modal-content").on("click", ".stop-btn", function () {
    DMSoundManager.stopTrack();
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
          // If a jump segment was marked, compute manual_jump indices
          let manual_jump = null;
          if (Array.isArray(path) && jumpStartIndex !== null && jumpStartIndex >= 0) {
            // end index defaults to the last element in path when jump mode was active
            const _endIndex = (lastPathForJump && lastPathForJump.length > 0)
              ? (path.length - 1) // last segment end
              : (path.length - 1);
            if (_endIndex >= jumpStartIndex) {
              manual_jump = [jumpStartIndex, _endIndex];
            }
          }
          ajaxPost(
            "/action",
            { id: entity_uid, action, opts, path, manual_jump },
            (data) => {
              console.log("Action request successful:", data);
              refreshTurn();
            },
            true,
          );
          // reset jump UI state after commit
          jumpMode = false;
          jumpStartIndex = null;
          lastPathForJump = null;
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
            // Ensure the popover menu stays on top after content update
            if (Utils && Utils.ensurePopoverMenusOnTop) {
              Utils.ensurePopoverMenusOnTop();
            }
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
          // Handle both coordinate-based and target_id-based targeting
          const actionData = { id: entity_uid, action, opts };

          if (target.target_id) {
            // Use target_id for specific entity/object targeting
            actionData.target = target.target_id;
          } else {
            // Use coordinates for position-based targeting
            actionData.target = target;
          }

          ajaxPost(
            "/action",
            actionData,
            (data) => {
              if (data.status === 'multiple_targets') {
                let target_list = data.entities; // list of [label, entity_uid]

                // Convert the target list to the format expected by showTargetSelectionModal
                const targets = target_list.map(([label, entity_uid]) => ({
                  id: entity_uid,
                  name: label,
                  type: 'entity',
                  image: null // Could be enhanced to include entity images
                }));

                // Show the target selection modal with the original action data
                showTargetSelectionModal(targets, { x: target.x, y: target.y }, { id: entity_uid, action, opts });
              }
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

        source = { x: coordsx, y: coordsy, mode: 'point_target', entity_uid };
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
  $(document).on("keydown", function (e) {
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
  $("#command-input").on("keypress", function (e) {
    if (e.which === 13) { // Enter key
      $("#command-form").submit();
    }
  });

  // Append server responses tagged with type 'command_response' to the command output
  socket.on("command_response", (data) => {
    // Enqueue command response events for FIFO processing
    eventQueue.enqueue(data);
  });

  // Handle talk action
  function handleTalk(entityId) {
    // Check if we're in talk to entity mode (JRPG dialog)
    if (talkToEntityMode) {
      // Use the JRPG dialog modal instead
      handleDialogBubbleClick(entityId, 'Entity');
      return;
    }

    // Original talk modal behavior
    $('#talkModal').modal('show');

    // Get the tile data to access conversation languages
    const povEntity = Chat.getCurrentPovEntity();
    const $tile = $(`.tile[data-coords-id="${povEntity}"]`);
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

    $('#submitTalk').off('click').on('click', function () {
      const message = $('#talkMessage').val().trim();
      if (message) {
        const selectedTargets = [];
        $('input[name="targets"]:checked').each(function () {
          selectedTargets.push($(this).val());
        });

        const noSpecificTarget = $('#noSpecificTarget').is(':checked');
        const selectedLanguage = $('#languageSelect').val();
        const selectedVolume = $('input[name="speechVolume"]:checked');
        const distance_ft = 10;

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
  $(document).on('click', '.talk-action', function (event) {
    event.stopPropagation();
    event.preventDefault();
    const $menu = $(this).closest('.popover-menu');
    const $tile = $(this).closest('.tile');
    const entityId = $tile.data('coords-id');

    // Ensure we're not in talk to entity mode for regular talk actions
    talkToEntityMode = false;

    handleTalk(entityId);
    $menu.hide();
  });

  $(document).on('click', '.conversation-bubble', function (event) {
    event.stopPropagation();
    Utils.toggleBubble(this);
  });

  // Handle dialog bubble clicks for dialog-capable entities
  function handleDialogBubbleClick(entityId, entityName) {
    console.log('Dialog bubble clicked for entity:', entityId, entityName);

    // Set talk to entity mode flag
    talkToEntityMode = true;

    // Show the JRPG dialog panel
    $('#jrpgDialogPanel').show();

    // Update panel title to indicate talk to entity mode
    $('#jrpgDialogPanelLabel').text('Talk to Entity');


    // Load entity information for the profile panel
    loadEntityProfile(entityId);

    // Load conversation languages
    loadDialogLanguages(entityId);

    // Initialize chat interface
    initializeDialogChat(entityId);

    // Add welcome message with the provided entity name
    const currentPovEntity = Chat.getCurrentPovEntity();
    if (currentPovEntity) {
      Chat.addDialogMessage('system', `You are now talking to ${entityName || 'this entity'}.`, 'system');
    } else {
      Chat.addDialogMessage('system', `Welcome to the conversation with ${entityName || 'this entity'}!`, 'system');
    }
  }

  // Load entity profile information
  function loadEntityProfile(entityId) {
    // Get entity information from the tile data
    const $tile = $(`.tile[data-coords-id="${entityId}"]`);

    // Get entity name from the tile label or entity name
    let entityName = 'Unknown Entity';
    const $nameplate = $tile.find('.nameplate');
    if ($nameplate.length) {
      entityName = $nameplate.text();
    } else {
      // Try to get from entity data attribute
      entityName = $tile.data('entity-name') || 'Unknown Entity';
    }

    // Set entity name initially and store entity ID
    $('#dialogEntityName').text(entityName).data('entity-id', entityId);

    // Get entity portrait (use the entity image if available)
    const $entityImg = $tile.find('.npc');
    if ($entityImg.length) {
      const portraitSrc = $entityImg.attr('src');
      $('#dialogEntityPortrait').attr('src', portraitSrc);
    } else {
      // Use a default portrait and prevent repeated load attempts
      const $portrait = $('#dialogEntityPortrait');
      $portrait.attr('onerror', "this.onerror=null;this.src='/static/assets/token_player.png'");
      $portrait.attr('src', '/static/assets/token_player.png');
    }

    // Load detailed entity information via AJAX
    $.ajax({
      url: '/entity_info',
      type: 'GET',
      data: { entity_id: entityId },
      success: (data) => {
        if (data.success) {
          const entity = data.entity;

          // Update entity name with the proper name from server
          if (entity.name) {
            $('#dialogEntityName').text(entity.name).data('entity-id', entityId);
          }

          // Update entity stats
          $('#dialogEntityHP').text(`${entity.hp || 0}/${entity.max_hp || 0}`);
          $('#dialogEntityAC').text(entity.ac || 'Unknown');
          $('#dialogEntityLevel').text(entity.level || 'Unknown');
          $('#dialogEntityRace').text(entity.race || 'Unknown');
          $('#dialogEntityClass').text(entity.class || 'Unknown');

          // Update description
          $('#dialogEntityDescription').text(entity.description || 'No description available.');
        } else {
          // Set default values if entity info not available
          $('#dialogEntityHP').text('0/0');
          $('#dialogEntityAC').text('Unknown');
          $('#dialogEntityLevel').text('Unknown');
          $('#dialogEntityRace').text('Unknown');
          $('#dialogEntityClass').text('Unknown');
          $('#dialogEntityDescription').text('Entity information not available.');
        }
      },
      error: () => {
        // Set default values on error
        $('#dialogEntityHP').text('0/0');
        $('#dialogEntityAC').text('Unknown');
        $('#dialogEntityLevel').text('Unknown');
        $('#dialogEntityRace').text('Unknown');
        $('#dialogEntityClass').text('Unknown');
        $('#dialogEntityDescription').text('Entity information not available.');
      }
    });
  }

  // Load available languages for the dialog
  function loadDialogLanguages(entityId) {
    const $tile = $(`.tile[data-coords-id="${Chat.getCurrentPovEntity()}"]`);
    const languages = $tile.data('conversation-languages');

    const $languageSelect = $('#dialogLanguageSelect');
    $languageSelect.empty();

    if (languages && languages.length > 0) {
      const languagesArray = languages.split(',');
      languagesArray.forEach(language => {
        const lang = language.trim();
        if (lang !== 'common') {
          $languageSelect.append(`<option value="${lang}">${lang}</option>`);
        } else {
          $languageSelect.append(`<option value="Common" selected>Common</option>`);
        }
      });
    } else {
      $languageSelect.append(`<option value="Common" selected>Common</option>`);
    }
  }

  // Initialize the dialog chat interface
  function initializeDialogChat(entityId) {
    // Clear previous messages
    $('#dialogChatMessages').empty();

    // Handle send message button
    $('#dialogSendMessage').off('click').on('click', function () {
      sendDialogMessage(entityId);
    });

    // Handle Enter key in chat input
    $('#dialogChatInput').off('keypress').on('keypress', function (e) {
      if (e.which === 13) { // Enter key
        e.preventDefault(); // Prevent default to avoid form submission
        sendDialogMessage(entityId);
      }
    });

    // Handle volume button clicks
    $('.volume-btn').off('click').on('click', function () {
      $('.volume-btn').removeClass('active');
      $(this).addClass('active');
    });

    loadDialogHistory(entityId);

    // Handle mode toggle button
    $('#toggleTalkMode').off('click').on('click', function () {
      talkToEntityMode = !talkToEntityMode;
      updateTalkModeDisplay();
    });

    // Focus on input
    $('#dialogChatInput').focus();
  }

  // Update the display based on talk mode
  function updateTalkModeDisplay() {
    if (talkToEntityMode) {
      $('#dialogModeIndicator').show();
      $('#jrpgDialogPanelLabel').text('Talk to Entity');
      $('#toggleTalkMode').removeClass('btn-info').addClass('btn-warning').html('<i class="glyphicon glyphicon-comment"></i> Regular Mode');
      Chat.addDialogMessage('system', 'Switched to Talk to Entity mode. You are now talking to the entity.', 'system');
    } else {
      $('#dialogModeIndicator').hide();
      $('#jrpgDialogPanelLabel').text('Dialog');
      $('#toggleTalkMode').removeClass('btn-warning').addClass('btn-info').html('<i class="glyphicon glyphicon-comment"></i> Talk Mode');
      Chat.addDialogMessage('system', 'Switched to Regular Dialog mode.', 'system');
    }
  }

  // Send a message in the dialog
  function sendDialogMessage(entityId) {
    const message = $('#dialogChatInput').val().trim();
    if (!message) return;

    // Prevent multiple messages from being sent simultaneously
    if (dialogMessageProcessing) return;

    dialogMessageProcessing = true;

    const selectedLanguage = $('#dialogLanguageSelect').val();
    const selectedVolume = $('.volume-btn.active');
    const distance_ft = 10;

    // Add player message to chat
    Chat.addDialogMessage('player', message, 'player');

    // Clear input
    $('#dialogChatInput').val('');

    // Disable input and send button while processing
    const $input = $('#dialogChatInput');
    const $sendButton = $('#dialogSendMessage');
    const $languageSelect = $('#dialogLanguageSelect');
    const $inputContainer = $('.chat-input-container');

    $input.prop('disabled', true);
    $sendButton.prop('disabled', true).html('<i class="glyphicon glyphicon-refresh spinning"></i> Sending...');
    $languageSelect.prop('disabled', true);
    $inputContainer.addClass('disabled');

    // Add waiting indicator
    const waitingId = addWaitingIndicator();

    // Set up timeout indicators for longer processing times
    const timeout1 = setTimeout(() => {
      updateWaitingIndicator(waitingId, "Processing your message...");
    }, 2000);

    const timeout2 = setTimeout(() => {
      updateWaitingIndicator(waitingId, "Entity is thinking...");
    }, 5000);

    const timeout3 = setTimeout(() => {
      updateWaitingIndicator(waitingId, "Almost ready to respond...");
    }, 10000);

    // Determine the source entity based on mode
    let sourceEntityId = entityId;
    if (talkToEntityMode) {
      // In talk to entity mode, the POV user is talking to the entity
      // We need to get the current POV user's entity ID
      const currentPovEntity = Chat.getCurrentPovEntity();
      if (currentPovEntity) {
        sourceEntityId = currentPovEntity;
      }
    }

    // Send message to server
    $.ajax({
      url: '/talk',
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({
        entity_id: sourceEntityId,
        message: message,
        targets: talkToEntityMode ? [entityId] : [], // In talk mode, target the entity being talked to
        no_specific_target: !talkToEntityMode, // Only set to true if not in talk mode
        language: selectedLanguage,
        distance_ft: distance_ft
      }),
      success: (data) => {
        // Clear timeouts
        clearTimeout(timeout1);
        clearTimeout(timeout2);
        clearTimeout(timeout3);

        // Remove waiting indicator
        removeWaitingIndicator(waitingId);

        // Re-enable input and send button
        $input.prop('disabled', false);
        $sendButton.prop('disabled', false).html('<i class="glyphicon glyphicon-send"></i> Send');
        $languageSelect.prop('disabled', false);
        $inputContainer.removeClass('disabled');
        $input.focus();

        // Reset processing flag
        dialogMessageProcessing = false;

        if (data.success) {
          // Add entity response if provided
          if (data.response) {
            Chat.addDialogMessage('entity', data.response, 'entity');
          }
        } else {
          Chat.addDialogMessage('system', 'Message sent successfully.', 'system');
        }
      },
      error: () => {
        // Clear timeouts
        clearTimeout(timeout1);
        clearTimeout(timeout2);
        clearTimeout(timeout3);

        // Remove waiting indicator
        removeWaitingIndicator(waitingId);

        // Re-enable input and send button
        $input.prop('disabled', false);
        $sendButton.prop('disabled', false).html('<i class="glyphicon glyphicon-send"></i> Send');
        $languageSelect.prop('disabled', false);
        $inputContainer.removeClass('disabled');
        $input.focus();

        // Reset processing flag
        dialogMessageProcessing = false;

        Chat.addDialogMessage('system', 'Failed to send message.', 'system');
      }
    });
  }



  // Helper function to show a regular conversation bubble


  // Helper function to show a dialog-trigger conversation bubble
  function showDialogTriggerBubble(entity_id, message) {
    const $tile = $(`.tile[data-coords-id="${entity_id}"]`);
    if ($tile.length) {
      // Create a special conversation bubble that can open the dialog
      let $bubble = $tile.find('.conversation-bubble');

      if ($bubble.length) {
        // Update existing bubble
        $bubble.find('.bubble-content').text(message);
        $bubble.removeClass('minimized');
        $bubble.find('.bubble-content').show();
        $bubble.find('.bubble-minimized').hide();
      } else {
        // Create new bubble with click handler to open dialog
        $bubble = $(`
          <div class="conversation-bubble dialog-trigger" style="cursor: pointer;">
            <div class="bubble-content">${message}</div>
            <div class="bubble-minimized" style="display: none;">
              <i class="glyphicon glyphicon-comment"></i>
            </div>
            <div class="dialog-indicator" style="position: absolute; top: -5px; right: -5px; background: #4CAF50; color: white; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.3);">
              <i class="glyphicon glyphicon-chevron-right"></i>
            </div>
            <button class="close-bubble" onclick="Utils.dismissBubble(this.parentElement); event.stopPropagation();">×</button>
          </div>
        `);

        // Add click handler to open dialog modal
        $bubble.on('click', function (e) {
          if (!$(e.target).hasClass('close-bubble')) {
            const entityName = $tile.find('.nameplate').text() || $tile.data('entity-name') || 'Entity';
            handleDialogBubbleClick(entity_id, entityName);
          }
        });

        $tile.append($bubble);
      }

      setTimeout(() => {
        $tile.find('.conversation-bubble').fadeOut(500, function () {
          $(this).remove();
        });
      }, 15000); // Longer timeout for dialog-trigger bubbles
    }
  }

  // Add a waiting indicator to the dialog chat
  function addWaitingIndicator() {
    const waitingId = 'waiting-' + Date.now();
    const waitingHtml = `
      <div id="${waitingId}" class="dialog-chat-message waiting">
        <div class="message-sender">System</div>
        <div class="message-content">
          <i class="glyphicon glyphicon-refresh spinning"></i> Waiting for response...
        </div>
        <div class="message-timestamp">${new Date().toLocaleTimeString()}</div>
      </div>
    `;

    $('#dialogChatMessages').append(waitingHtml);

    // Scroll to bottom
    const $messages = $('#dialogChatMessages');
    $messages.scrollTop($messages[0].scrollHeight);

    return waitingId;
  }

  // Update the waiting indicator message
  function updateWaitingIndicator(waitingId, message) {
    const $waiting = $(`#${waitingId}`);
    if ($waiting.length) {
      $waiting.find('.message-content').html(`<i class="glyphicon glyphicon-refresh spinning"></i> ${message}`);
    }
  }

  // Remove the waiting indicator
  function removeWaitingIndicator(waitingId) {
    const $waiting = $(`#${waitingId}`);
    if ($waiting.length) {
      $waiting.fadeOut(300, function () {
        $(this).remove();
      });
    }
  }

  // Load dialog history
  function loadDialogHistory(entityId) {
    $.ajax({
      url: '/dialog_history',
      type: 'GET',
      data: {
        entity_id: entityId,
        entity_pov: Chat.getCurrentPovEntity()
      },
      dataType: 'json',
      beforeSend: () => {
        $('#dialogChatMessages').html('<div class="loading">Loading history...</div>');
      },
      success: (data) => {
        if (data.success) {
          const $historyContainer = $('#dialogChatMessages');
          $historyContainer.empty();

          if (data.history && data.history.length > 0) {
            data.history.forEach(entry => {
              const messageHtml = `
                <div class="dialog-chat-message ${entry.type}">
                  <div class="message-sender">${entry.source}</div>
                  <div class="message-content">${entry.message}</div>
                </div>
              `;
              $historyContainer.append(messageHtml);
            });
          } else {
            $historyContainer.append('<div class="no-history">No conversation history available.</div>');
          }
          // Show the history modal
          $('#dialogHistoryModal').modal('show');
        } else {
          $('#dialogHistoryContainer').html('<div class="error">Failed to load history.</div>');
        }
      },
      error: () => {
        $('#dialogHistoryContainer').html('<div class="error">Error loading history.</div>');
      }
    });
  }


  // Reset talk to entity mode when panel is closed
  $('#close-dialog').on('click', function () {
    $('#jrpgDialogPanel').hide();
    talkToEntityMode = false;
    $('#dialogModeIndicator').hide();
    $('#jrpgDialogPanelLabel').text('Dialog');
    console.log('Talk to entity mode reset');
  });

  // Minimize dialog panel
  $('#minimize-dialog').on('click', function () {
    const $panel = $('#jrpgDialogPanel');
    const $body = $panel.find('.dialog-panel-body');
    const $header = $panel.find('.dialog-panel-header');

    if ($body.is(':visible')) {
      $body.hide();
      $panel.css('height', '60px');
      $(this).html('<i class="glyphicon glyphicon-plus"></i>');
    } else {
      $body.show();
      $panel.css('height', '600px');
      $(this).html('<i class="glyphicon glyphicon-minus"></i>');
    }
  });

  $("#turn-order").on("change", ".group-select", function () {
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

  $("#turn-order").on("change", ".controller-select", function () {
    const $turnOrderItem = $(this).closest(".turn-order-item");
    const entity_uid = $turnOrderItem.data("id");
    console.log("Changing controller for entity:", entity_uid); // Debug log
    const new_controller = $(this).val();
    ajaxPost(
      "/update_controller",
      { entity_uid, controller: new_controller, action: "set" },
      (data) => {
        console.log("Controller updated successfully:", data);
      },
      true
    );
  });

  // DM can change default NPC controller from AI tab
  $(document).on("change", "#default-npc-controller", function () {
    const value = $(this).val();
    ajaxPost(
      "/update_npc_default_controller",
      { value },
      (data) => {
        console.log("Default NPC controller set to:", data);
      },
      true
    );
  });


  $(".tiles-container").on('click', '.dialog-bubble', function (event) {
    event.stopPropagation();
    event.preventDefault();
    const entityId = $(this).data('id');
    const entityName = $(this).data('name');
    handleDialogBubbleClick(entityId, entityName);
  });

  // DM Entity Drag and Drop functionality
  let isDraggingEntity = false;
  let draggedEntityId = null;
  let draggedEntityTile = null;
  let dragOffset = { x: 0, y: 0 };
  let dragGhost = null;
  // Delay actual drag until cursor moves past a small threshold
  let dragPending = false;
  let dragStartX = 0, dragStartY = 0;
  let dragTileCenterX = 0, dragTileCenterY = 0;

  // Mouse down on entity tile (start drag)
  $(".tiles-container").on("mousedown", ".tile", function (e) {
    // Only allow DMs to drag entities
    if (!isDM()) return;

    // Only respond to primary button
    if (e.button !== 0) return;

    const $tile = $(this);
    const entityId = $tile.data("coords-id");

    // Only allow dragging if there's an entity on this tile
    if (!entityId || !$tile.find('.entity, .npc').length) return;

    // Prevent dragging if clicking on action buttons or other interactive elements
    if ($(e.target).closest('.popover-menu, .popover-menu-2, .action-button, .add-to-turn-order, .dialog-bubble, .conversation-bubble, .close-bubble, .add-to-target').length) {
      return;
    }

    // Prepare for potential drag (defer actual drag start until movement threshold exceeded)
    draggedEntityId = entityId;
    draggedEntityTile = $tile;
    const tileRect = $tile[0].getBoundingClientRect();
    const tileSize = $(".tiles-container").data("tile-size");
    dragTileCenterX = tileRect.left + tileSize / 2;
    dragTileCenterY = tileRect.top + tileSize / 2;
    dragOffset.x = e.clientX - dragTileCenterX;
    dragOffset.y = e.clientY - dragTileCenterY;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    dragPending = true;

    // Prevent text selection from starting
    e.preventDefault();
    e.stopPropagation();
  });

  // Mouse move (update drag ghost position)
  $(document).on("mousemove", function (e) {
    // If we have a pending drag but haven't started, check threshold (to avoid accidental clicks)
    if (dragPending && !isDraggingEntity) {
      const dx = e.clientX - dragStartX;
      const dy = e.clientY - dragStartY;
      const distance = Math.sqrt(dx * dx + dy * dy);
      if (distance > 5) {
        // Start the actual drag now
        isDraggingEntity = true;

        // Create drag ghost element centered on the tile
        createDragGhost(draggedEntityTile, dragTileCenterX, dragTileCenterY);

        // Add dragging class for visual feedback
        draggedEntityTile.addClass('entity-dragging');
        $('body').addClass('entity-dragging-active');

        // Hide popover menus during drag
        $('.popover-menu').hide();
      }
    }

    if (!isDraggingEntity || !dragGhost) return;

    // Update ghost position - center the ghost on the mouse cursor
    const tileSize = $(".tiles-container").data("tile-size");
    dragGhost.css({
      left: (e.clientX - tileSize / 2) + 'px',
      top: (e.clientY - tileSize / 2) + 'px'
    });

    // Highlight target tile
    const elementBelow = document.elementFromPoint(e.clientX, e.clientY);
    const $targetTile = $(elementBelow).closest('.tile');

    // Remove previous highlight
    $('.tile').removeClass('drag-target-highlight');

    if ($targetTile.length && $targetTile[0] !== draggedEntityTile[0]) {
      $targetTile.addClass('drag-target-highlight');
    }
  });

  // Mouse up (complete drag or cancel)
  $(document).on("mouseup", function (e) {
    // Clear pending drag if not started
    if (dragPending && !isDraggingEntity) {
      dragPending = false;
      draggedEntityId = null;
      draggedEntityTile = null;
      return;
    }

    if (!isDraggingEntity) return;

    // Find the target tile
    const elementBelow = document.elementFromPoint(e.clientX, e.clientY);
    const $targetTile = $(elementBelow).closest('.tile');

    if ($targetTile.length && $targetTile[0] !== draggedEntityTile[0]) {
      // Valid drop target
      const targetX = $targetTile.data("coords-x");
      const targetY = $targetTile.data("coords-y");

      if (targetX !== undefined && targetY !== undefined) {
        // Perform the move via API
        moveEntityTo(draggedEntityId, targetX, targetY);
      }
    }

    // Clean up drag state
    cleanupDrag();
  });

  // Cancel drag on escape key
  $(document).on("keydown", function (e) {
    if (e.key === "Escape" && isDraggingEntity) {
      cleanupDrag();
    }
  });

  // Create drag ghost element
  function createDragGhost($sourceTile, x, y) {
    const $entity = $sourceTile.find('.entity, .npc').first();
    if (!$entity.length) return;

    const tileSize = $(".tiles-container").data("tile-size");

    dragGhost = $('<div>')
      .addClass('entity-drag-ghost')
      .css({
        position: 'fixed',
        left: (x - tileSize / 2) + 'px',
        top: (y - tileSize / 2) + 'px',
        width: tileSize + 'px',
        height: tileSize + 'px',
        zIndex: 10000,
        pointerEvents: 'none',
        opacity: 0.7,
        border: '2px solid #007bff',
        borderRadius: '4px',
        backgroundColor: 'rgba(0, 123, 255, 0.1)'
      });

    // Clone the entity image
    const $entityClone = $entity.clone();
    $entityClone.css({
      position: 'relative',
      top: '0',
      left: '0',
      transform: 'none'
    });

    dragGhost.append($entityClone);
    $('body').append(dragGhost);
  }

  // Clean up drag state
  function cleanupDrag() {
    isDraggingEntity = false;
  dragPending = false;
    draggedEntityId = null;

    if (draggedEntityTile) {
      draggedEntityTile.removeClass('entity-dragging');
      draggedEntityTile = null;
    }

    if (dragGhost) {
      dragGhost.remove();
      dragGhost = null;
    }

    // Remove target highlights and global dragging class
    $('.tile').removeClass('drag-target-highlight');
    $('body').removeClass('entity-dragging-active');
  }

  Chat.init();

  // Make dialog panel draggable and resizable
  makeDialogPanelDraggable();
  makeDialogPanelResizable();
  
  // Make floating windows draggable
  makeFloatingWindowsDraggable();

  // Handle window resize to keep panel in bounds
  
  // Clean up ghost tokens on page unload
  $(window).on('beforeunload', function() {
    cleanupAllPendingMoves();
  });
});

// Function to make dialog panel draggable
function makeDialogPanelDraggable() {
  const $panel = $('#jrpgDialogPanel');
  const $header = $panel.find('.dialog-panel-header');
  let isDragging = false;
  let startX, startY, startLeft, startTop;

  $header.on('mousedown', function (e) {
    if (e.target.tagName === 'BUTTON' || $(e.target).closest('button').length) {
      return; // Don't drag if clicking on buttons
    }

    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    startLeft = parseInt($panel.css('left'));
    startTop = parseInt($panel.css('top'));

    $panel.css('cursor', 'grabbing');
    e.preventDefault();
  });

  $(document).on('mousemove', function (e) {
    if (!isDragging) return;

    const deltaX = e.clientX - startX;
    const deltaY = e.clientY - startY;

    const newLeft = startLeft + deltaX;
    const newTop = startTop + deltaY;

    // Keep panel within window bounds
    const maxLeft = window.innerWidth - $panel.outerWidth();
    const maxTop = window.innerHeight - $panel.outerHeight();

    $panel.css({
      left: Math.max(0, Math.min(newLeft, maxLeft)) + 'px',
      top: Math.max(0, Math.min(newTop, maxTop)) + 'px'
    });
  });

  $(document).on('mouseup', function () {
    if (isDragging) {
      isDragging = false;
      $panel.css('cursor', 'default');
    }
  });
}

// Function to make dialog panel resizable
function makeDialogPanelResizable() {
  const $panel = $('#jrpgDialogPanel');
  const $resizeHandle = $panel.find('.dialog-resize-handle');
  let isResizing = false;
  let startX, startY, startWidth, startHeight;

  $resizeHandle.on('mousedown', function (e) {
    isResizing = true;
    startX = e.clientX;
    startY = e.clientY;
    startWidth = $panel.outerWidth();
    startHeight = $panel.outerHeight();

    e.preventDefault();
    e.stopPropagation();
  });

  $(document).on('mousemove', function (e) {
    if (!isResizing) return;

    const deltaX = e.clientX - startX;
    const deltaY = e.clientY - startY;

    const newWidth = startWidth + deltaX;
    const newHeight = startHeight + deltaY;

    // Minimum size constraints
    const minWidth = 400;
    const minHeight = 300;

    // Maximum size constraints (keep within window)
    const maxWidth = window.innerWidth - parseInt($panel.css('left'));
    const maxHeight = window.innerHeight - parseInt($panel.css('top'));

    const finalWidth = Math.max(minWidth, Math.min(newWidth, maxWidth));
    const finalHeight = Math.max(minHeight, Math.min(newHeight, maxHeight));

    $panel.css({
      width: finalWidth + 'px',
      height: finalHeight + 'px'
    });
  });

  $(document).on('mouseup', function () {
    if (isResizing) {
      isResizing = false;
    }
  });
}

// Function to make floating windows draggable
function makeFloatingWindowsDraggable() {
  $('.floating-window').each(function() {
    const $panel = $(this);
    const $header = $panel.find('.header');
    let isDragging = false;
    let startX, startY, startLeft, startTop;

    $header.on('mousedown', function (e) {
      if (e.target.tagName === 'BUTTON' || $(e.target).closest('button').length) {
        return; // Don't drag if clicking on buttons
      }

      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      startLeft = parseInt($panel.css('left')) || 0;
      startTop = parseInt($panel.css('top')) || 0;

      $panel.css('cursor', 'grabbing');
      e.preventDefault();
    });

    $(document).on('mousemove', function (e) {
      if (!isDragging) return;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      const newLeft = startLeft + deltaX;
      const newTop = startTop + deltaY;

      // Keep panel within window bounds
      const maxLeft = window.innerWidth - $panel.outerWidth();
      const maxTop = window.innerHeight - $panel.outerHeight();

      $panel.css({
        left: Math.max(0, Math.min(newLeft, maxLeft)) + 'px',
        top: Math.max(0, Math.min(newTop, maxTop)) + 'px'
      });
    });

    $(document).on('mouseup', function () {
      if (isDragging) {
        isDragging = false;
        $panel.css('cursor', 'default');
      }
    });
  });
}

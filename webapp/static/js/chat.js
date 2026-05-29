const Chat = Object.assign({}, window.LocalConversationChatBindings || {}, {
    // Helper function to add a processing message with animated dots
    addProcessingMessage: function (isDraggable = false) {
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
    },

    updateProcessingMessage: function (processingId, text, isDraggable = false) {
        const $processing = $(`#${processingId}`);
        if ($processing.length) {
            $processing.find('.processing-text').text(text);
        }
    },

    removeProcessingMessage: function (processingId, isDraggable = false) {
        $(`#${processingId}`).remove();
    },
    cleanThinkingTags: function (content) {
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
    },
    getTranscriptText: function (isDraggable = false) {
        const $chatContainer = isDraggable ? $("#draggable-chat-messages") : $("#chat-messages");
        return $chatContainer.find(".chat-message").map(function () {
            return $(this).text().replace(/\s+/g, " ").trim();
        }).get().filter(Boolean).join("\n\n");
    },
    selectTranscript: function (isDraggable = false) {
        const container = (isDraggable ? $("#draggable-chat-messages") : $("#chat-messages"))[0];
        if (!container) {
            return;
        }

        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(container);
        selection.removeAllRanges();
        selection.addRange(range);
    },
    copyTranscript: async function (isDraggable = false) {
        const transcript = Chat.getTranscriptText(isDraggable);
        const $button = isDraggable ? $("#draggable-copy-chat-transcript") : $("#copy-chat-transcript");

        if (!transcript) {
            return;
        }

        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(transcript);
            } else {
                const $temp = $("<textarea>")
                    .css({
                        position: "fixed",
                        top: "-9999px",
                        left: "-9999px"
                    })
                    .val(transcript)
                    .appendTo("body");
                $temp[0].focus();
                $temp[0].select();
                document.execCommand("copy");
                $temp.remove();
            }

            if ($button.length) {
                const originalHtml = $button.html();
                $button.html('<i class="glyphicon glyphicon-ok"></i> Copied');
                setTimeout(function () {
                    $button.html(originalHtml);
                }, 1500);
            }
        } catch (error) {
            console.warn("Clipboard copy failed, selecting transcript instead", error);
            Chat.selectTranscript(isDraggable);
        }
    },
    addChatMessage: function (role, content, isDraggable = false) {
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
        const cleanedContent = Chat.cleanThinkingTags(content);

        switch (role) {
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

        const messageHtml = `<div class="${messageClass}">${prefix} ${Chat.escapeHtml(cleanedContent)}</div>`;
        $chatContainer.append(messageHtml);

        // Scroll to bottom
        $chatContainer.scrollTop($chatContainer[0].scrollHeight);
    },
    assistantChatTargets: function () {
        const targets = [];
        if ($("#chat-messages").length) {
            targets.push(false);
        }
        if ($("#draggable-chat-messages").length) {
            targets.push(true);
        }
        return targets;
    },
    showAssistantWelcomeBanner: function (label) {
        const modelLabel = label || "ready";
        const welcomeText =
            "Ready (" +
            modelLabel +
            "). Uses the same server LLM as NPCs and dialogs. How can I help with your D&D game?";
        const welcome =
            '<div class="chat-message system"><strong>AI Assistant:</strong> ' +
            Chat.escapeHtml(welcomeText) +
            "</div>";
        Chat.assistantChatTargets().forEach(function (isDraggable) {
            const $chatContainer = isDraggable ? $("#draggable-chat-messages") : $("#chat-messages");
            $chatContainer.html(welcome);
        });
    },
    renderAssistantChatHistory: function (history) {
        Chat.assistantChatTargets().forEach(function (isDraggable) {
            const $chatContainer = isDraggable ? $("#draggable-chat-messages") : $("#chat-messages");
            $chatContainer.empty();
            history.forEach(function (msg) {
                if (msg && (msg.role === "user" || msg.role === "assistant")) {
                    Chat.addChatMessage(msg.role, msg.content, isDraggable);
                }
            });
        });
    },
    loadAssistantChatHistory: function (modelLabel) {
        $.ajax({
            type: "GET",
            url: "/ai/history",
            dataType: "json",
            timeout: 15000,
            success: function (data) {
                if (data && data.success && Array.isArray(data.history) && data.history.length > 0) {
                    Chat.renderAssistantChatHistory(data.history);
                    return;
                }
                Chat.showAssistantWelcomeBanner(modelLabel);
            },
            error: function () {
                Chat.showAssistantWelcomeBanner(modelLabel);
            },
        });
    },
    getCurrentPovEntity: () => {
        // Try to get from the floating portraits
        const $currentPov = $('#floating-entity-portraits .floating-entity-portrait.current-pov');
        if ($currentPov.length) {
            const id = $currentPov.data('id');
            if (id && id !== 'None') {
                return id;
            }
        }

        const povEntityId = $('body').data('pov-entity');

        if (povEntityId && povEntityId !== 'None') {
            return povEntityId;
        }

        // If we can't determine POV, return null
        return null;
    },
    escapeHtml: function (content) {
        return $('<div>').text(content || '').html();
    },
    showConversationBubble: function (entity_id, message) {
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
                $tile.find('.conversation-bubble').fadeOut(500, function () {
                    $(this).remove();
                });
            }, 10000);
        }
    },
    addDialogMessage: function (sender, content, type, options) {
        const timestamp = new Date().toLocaleTimeString();
        options = options || {};
        const narrativeEntries = Array.isArray(options.narrative)
            ? options.narrative.filter((entry) => `${entry || ''}`.trim().length > 0)
            : [];
        const narrativeHtml = narrativeEntries.map((entry) => (
            `<div class="dialog-message-aside">${Chat.escapeHtml(entry)}</div>`
        )).join('');

        // Determine the display name based on mode and sender
        let displayName = sender;
        if (options.displayName) {
            displayName = options.displayName;
        } else if (talkToEntityMode) {
            if (sender === 'player') {
                // Get the current POV entity name
                const currentPovEntity = Chat.getCurrentPovEntity();
                if (currentPovEntity) {
                    const $povTile = $(`.tile[data-coords-id="${currentPovEntity}"]`);
                    const $nameplate = $povTile.find('.nameplate');
                    if ($nameplate.length) {
                        displayName = $nameplate.text();
                    } else {
                        displayName = 'You';
                    }
                } else {
                    displayName = 'You';
                }
            } else if (sender === 'entity') {
                // Get the entity being talked to
                const $entityTile = $(`.tile[data-coords-id="${$('#dialogEntityName').data('entity-id')}"]`);
                const $nameplate = $entityTile.find('.nameplate');
                if ($nameplate.length) {
                    displayName = $nameplate.text();
                } else {
                    displayName = 'Entity';
                }
            }
        }

        const messageHtml = `
      <div class="dialog-chat-message ${type}">
        <div class="message-sender">${displayName}</div>
        <div class="message-content">${Chat.escapeHtml(content)}</div>
        ${narrativeHtml}
        <div class="message-timestamp">${timestamp}</div>
      </div>
    `;

        $('#dialogChatMessages').append(messageHtml);

        // Scroll to bottom
        const $messages = $('#dialogChatMessages');
        $messages.scrollTop($messages[0].scrollHeight);
    },

    init: function () {
        Chat.initLocalConversationPanel();
        let aiInitialized = false;

        function applyAssistantReady(info) {
            try {
                aiInitialized = true;
                const label = info.current_model || info.provider_type || "ready";
                $("#chat-input, #send-chat, #draggable-chat-input, #draggable-send-chat").prop(
                    "disabled",
                    false
                );
                Chat.loadAssistantChatHistory(label);
            } catch (err) {
                console.error("[Chat] applyAssistantReady failed:", err);
                showAssistantUnavailable("Assistant UI failed to update. Check the browser console.");
            }
        }

        function showAssistantUnavailable(msg) {
            const m =
                msg ||
                "No LLM provider is available. Set LLM_PROVIDER and required keys in the server environment, then restart the app or reload the page.";
            const block =
                '<div class="chat-message system"><strong>AI Assistant:</strong> ' + Chat.escapeHtml(m) + "</div>";
            if ($("#chat-messages").length) {
                $("#chat-messages").html(block);
            }
            if ($("#draggable-chat-messages").length) {
                $("#draggable-chat-messages").html(block);
            }
            $("#chat-input, #send-chat, #draggable-chat-input, #draggable-send-chat").prop("disabled", true);
        }

        function syncAssistantFromServer() {
            const baseAjax = { dataType: "json", timeout: 45000 };

            $.ajax(
                $.extend({}, baseAjax, {
                    type: "GET",
                    url: "/ai/provider-info",
                    success: function (data) {
                        if (data && data.success && data.info && data.info.initialized === true) {
                            applyAssistantReady(data.info);
                            return;
                        }
                        $.ajax(
                            $.extend({}, baseAjax, {
                                type: "POST",
                                url: "/ai/initialize-from-env",
                                success: function (again) {
                                    if (
                                        again &&
                                        again.success &&
                                        again.info &&
                                        again.info.initialized === true
                                    ) {
                                        applyAssistantReady(again.info);
                                    } else {
                                        showAssistantUnavailable();
                                    }
                                },
                                error: function (_xhr, status) {
                                    const detail =
                                        status === "timeout"
                                            ? "Timed out contacting the server LLM. Check Ollama/llama.cpp is running or increase timeouts."
                                            : "Could not sync LLM from server configuration.";
                                    showAssistantUnavailable(detail);
                                },
                            })
                        );
                    },
                    error: function (_xhr, status) {
                        if (status === "timeout") {
                            showAssistantUnavailable(
                                "Timed out loading provider info. Check your connection and reload."
                            );
                        } else {
                            showAssistantUnavailable(
                                "Could not read LLM status (DM session required for the AI assistant)."
                            );
                        }
                    },
                })
            );
        }

        syncAssistantFromServer();

        // Handle chat form submission
        $("#chat-form, #draggable-chat-form").on("submit", function (e) {
            e.preventDefault();
            if (!aiInitialized) {
                const isDraggable = $(this).attr("id") === "draggable-chat-form";
                Chat.addChatMessage(
                    "system",
                    "AI assistant is not ready yet. Wait for the server LLM to sync, or check LLM_PROVIDER / keys and reload.",
                    isDraggable
                );
                return;
            }

            const isDraggable = $(this).attr("id") === "draggable-chat-form";
            const $input = isDraggable ? $("#draggable-chat-input") : $("#chat-input");
            const $sendButton = isDraggable ? $("#draggable-send-chat") : $("#send-chat");

            const message = $input.val().trim();
            if (message === "") return;

            // Add user message to chat
            Chat.addChatMessage("user", message, isDraggable);
            $input.val("");

            // Disable input while processing
            $input.prop("disabled", true);
            $sendButton.prop("disabled", true);

            // Add processing indicator
            const processingId = Chat.addProcessingMessage(isDraggable);

            // Set up timeout indicators for longer processing times
            const timeout1 = setTimeout(() => {
                Chat.updateProcessingMessage(processingId, "Processing your request", isDraggable);
            }, 3000);

            const timeout2 = setTimeout(() => {
                Chat.updateProcessingMessage(processingId, "Gathering game data", isDraggable);
            }, 8000);

            const timeout3 = setTimeout(() => {
                Chat.updateProcessingMessage(processingId, "Almost done", isDraggable);
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
                    Chat.removeProcessingMessage(processingId, isDraggable);

                    if (data.success) {
                        Chat.addChatMessage("assistant", data.response, isDraggable);
                    } else {
                        Chat.addChatMessage("system", "Error: " + (data.error || "Unknown error"), isDraggable);
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
                    Chat.removeProcessingMessage(processingId, isDraggable);

                    Chat.addChatMessage("system", "Network error occurred while communicating with AI.", isDraggable);
                    $input.prop("disabled", false);
                    $sendButton.prop("disabled", false);
                    $input.focus();
                }
            });
        });

        // Clear chat history
        $("#clear-chat, #draggable-clear-chat").on("click", function () {
            if (confirm("Are you sure you want to clear the chat history?")) {
                const cleared =
                    '<div class="chat-message system"><strong>AI Assistant:</strong> Chat history cleared. How can I help you?</div>';
                Chat.assistantChatTargets().forEach(function (isDraggable) {
                    const $chatContainer = isDraggable ? $("#draggable-chat-messages") : $("#chat-messages");
                    $chatContainer.html(cleared);
                });

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
        $("#get-context, #draggable-get-context").on("click", function () {
            const isDraggable = $(this).attr("id") === "draggable-get-context";
            $.ajax({
                type: "GET",
                url: "/ai/context",
                success: (data) => {
                    if (data.success) {
                        Chat.addChatMessage("system", "Game context retrieved and sent to AI assistant.", isDraggable);
                    } else {
                        Chat.addChatMessage("system", "Failed to get game context: " + (data.error || "Unknown error"), isDraggable);
                    }
                },
                error: () => {
                    Chat.addChatMessage("system", "Failed to get game context: Network error", isDraggable);
                }
            });
        });

        // AI Chat Panel — drag/resize using fixed left/top.
        // Document mousemove/mouseup are registered only while dragging/resizing (same idea as
        // initLocalConversationDrag), so we avoid running jQuery handlers on every pointer move.
        const AI_CHAT_LAYOUT_KEY = "aiChatPanelLayout_v2";
        const AI_CHAT_INTERACT_NS = "aiChatPanelInteract";
        let aiChatInteractState = null;

        function normalizeAiChatPanelPx($panel) {
            if (!$panel.length) {
                return;
            }
            const el = $panel[0];
            const rect = el.getBoundingClientRect();
            $panel.css({
                left: Math.round(rect.left) + "px",
                top: Math.round(rect.top) + "px",
                right: "auto",
                bottom: "auto",
                transform: "none",
            });
        }

        function saveAiChatPanelLayout() {
            const $panel = $("#ai-chat-panel");
            if (!$panel.length) {
                return;
            }
            try {
                localStorage.setItem(
                    AI_CHAT_LAYOUT_KEY,
                    JSON.stringify({
                        left: parseInt($panel.css("left"), 10) || 0,
                        top: parseInt($panel.css("top"), 10) || 0,
                        width: $panel.outerWidth(),
                        height: $panel.outerHeight(),
                    })
                );
            } catch (e) {
                console.warn("[Chat] saveAiChatPanelLayout failed", e);
            }
        }

        function loadAiChatPanelLayout() {
            const $panel = $("#ai-chat-panel");
            if (!$panel.length) {
                return;
            }
            const raw = localStorage.getItem(AI_CHAT_LAYOUT_KEY);
            if (!raw) {
                return;
            }
            try {
                const layout = JSON.parse(raw);
                if (layout.width) {
                    $panel.css("width", layout.width + "px");
                }
                if (layout.height) {
                    $panel.css("height", layout.height + "px");
                }
                if (typeof layout.left === "number") {
                    $panel.css("left", layout.left + "px");
                }
                if (typeof layout.top === "number") {
                    $panel.css("top", layout.top + "px");
                }
                $panel.css({ right: "auto", bottom: "auto", transform: "none" });
            } catch (e) {
                console.warn("[Chat] loadAiChatPanelLayout failed", e);
            }
        }

        function detachAiChatInteractListeners() {
            $(document).off("mousemove." + AI_CHAT_INTERACT_NS + " mouseup." + AI_CHAT_INTERACT_NS);
        }

        function endAiChatInteract($panel) {
            detachAiChatInteractListeners();
            aiChatInteractState = null;
            if ($panel && $panel.length) {
                $panel.removeClass("dragging").css("cursor", "");
            }
            saveAiChatPanelLayout();
        }

        $("#toggle-ai-chat").on("click", function () {
            const $panel = $("#ai-chat-panel");
            if ($panel.is(":visible")) {
                $panel.hide();
                $(this).removeClass("btn-success").addClass("btn-primary");
            } else {
                normalizeAiChatPanelPx($panel);
                $panel.show();
                $(this).removeClass("btn-primary").addClass("btn-success");
            }
        });

        $("#close-chat").on("click", function () {
            $("#ai-chat-panel").hide();
            $("#toggle-ai-chat").removeClass("btn-success").addClass("btn-primary");
        });

        $("#minimize-chat").on("click", function () {
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

        $("#ai-chat-panel .panel-header").on("mousedown", function (e) {
            if (e.target.tagName === "BUTTON" || e.target.tagName === "I" || $(e.target).closest("button").length) {
                return;
            }
            const $panel = $("#ai-chat-panel");
            if (!$panel.length) {
                return;
            }
            detachAiChatInteractListeners();
            normalizeAiChatPanelPx($panel);

            const panelW = $panel.outerWidth();
            const panelH = $panel.outerHeight();
            aiChatInteractState = {
                mode: "drag",
                startX: e.clientX,
                startY: e.clientY,
                startLeft: parseInt($panel.css("left"), 10) || 0,
                startTop: parseInt($panel.css("top"), 10) || 0,
                panelW,
                panelH,
            };

            $panel.addClass("dragging").css("cursor", "grabbing");
            e.preventDefault();

            $(document)
                .on("mousemove." + AI_CHAT_INTERACT_NS, function (moveEv) {
                    if (!aiChatInteractState || aiChatInteractState.mode !== "drag") {
                        return;
                    }
                    moveEv.preventDefault();
                    const st = aiChatInteractState;
                    const dx = moveEv.clientX - st.startX;
                    const dy = moveEv.clientY - st.startY;
                    let nl = st.startLeft + dx;
                    let nt = st.startTop + dy;
                    const vw = window.innerWidth;
                    const vh = window.innerHeight;
                    nl = Math.max(0, Math.min(nl, vw - st.panelW));
                    nt = Math.max(0, Math.min(nt, vh - st.panelH));
                    $panel.css({ left: nl + "px", top: nt + "px" });
                })
                .on("mouseup." + AI_CHAT_INTERACT_NS, function () {
                    endAiChatInteract($panel);
                });
        });

        $("#ai-chat-panel .resize-handle").on("mousedown", function (e) {
            const $panel = $("#ai-chat-panel");
            if (!$panel.length) {
                return;
            }
            detachAiChatInteractListeners();
            normalizeAiChatPanelPx($panel);
            e.preventDefault();
            e.stopPropagation();

            const left = parseInt($panel.css("left"), 10) || 0;
            const top = parseInt($panel.css("top"), 10) || 0;
            aiChatInteractState = {
                mode: "resize",
                startX: e.clientX,
                startY: e.clientY,
                w0: $panel.outerWidth(),
                h0: $panel.outerHeight(),
                left,
                top,
            };

            $(document)
                .on("mousemove." + AI_CHAT_INTERACT_NS, function (moveEv) {
                    if (!aiChatInteractState || aiChatInteractState.mode !== "resize") {
                        return;
                    }
                    moveEv.preventDefault();
                    const st = aiChatInteractState;
                    const dx = moveEv.clientX - st.startX;
                    const dy = moveEv.clientY - st.startY;
                    let nw = Math.max(300, st.w0 + dx);
                    let nh = Math.max(400, st.h0 + dy);
                    const vw = window.innerWidth;
                    const vh = window.innerHeight;
                    nw = Math.min(nw, vw - st.left);
                    nh = Math.min(nh, vh - st.top);
                    $panel.css({ width: nw + "px", height: nh + "px" });
                })
                .on("mouseup." + AI_CHAT_INTERACT_NS, function () {
                    endAiChatInteract($panel);
                });
        });

        $(window).on("resize.aiChatPanel", function () {
            const $panel = $("#ai-chat-panel");
            if (!$panel.length || !$panel.is(":visible")) {
                return;
            }
            normalizeAiChatPanelPx($panel);
            const rect = $panel[0].getBoundingClientRect();
            const ww = $(window).width();
            const wh = $(window).height();
            let nl = rect.left;
            let nt = rect.top;
            if (rect.right > ww) {
                nl = ww - rect.width - 20;
            }
            if (rect.left < 0) {
                nl = 20;
            }
            if (rect.bottom > wh) {
                nt = wh - rect.height - 20;
            }
            if (rect.top < 0) {
                nt = 20;
            }
            $panel.css({ left: nl + "px", top: nt + "px", right: "auto", transform: "none" });
            saveAiChatPanelLayout();
        });

        $("#copy-chat-transcript").on("click", function () {
            Chat.copyTranscript(false);
        });
        $("#select-chat-transcript").on("click", function () {
            Chat.selectTranscript(false);
        });
        $("#draggable-copy-chat-transcript").on("click", function () {
            Chat.copyTranscript(true);
        });
        $("#draggable-select-chat-transcript").on("click", function () {
            Chat.selectTranscript(true);
        });
        loadAiChatPanelLayout();

    }
});
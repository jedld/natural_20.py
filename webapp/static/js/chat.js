const Chat = {
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
    loadOllamaModels: function () {
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
                    Chat.addChatMessage("system", `Found ${data.models.length} Ollama models. Please select one and initialize.`);
                    // Sync with draggable panel
                    syncModelSelections();
                } else {
                    $modelSelect.append('<option value="">No models found</option>');
                    Chat.addChatMessage("system", "No Ollama models found. Please make sure Ollama is running and has models installed.");
                }
            },
            error: () => {
                const $modelSelect = $("#ai-model-select");
                $modelSelect.empty().append('<option value="">Failed to load models</option>');
                Chat.addChatMessage("system", "Failed to load Ollama models. Please check your Ollama installation and connection.");
            }
        });
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

        const messageHtml = `<div class="${messageClass}">${prefix} ${cleanedContent}</div>`;
        $chatContainer.append(messageHtml);

        // Scroll to bottom
        $chatContainer.scrollTop($chatContainer[0].scrollHeight);
    },
    init: function () {
        // Refresh models button
        $("#refresh-models").on("click", function () {
            if ($("#ai-provider-select").val() === "ollama") {
                Chat.loadOllamaModels();
            }
        });
        // Initialize provider select on page load for both panels
        $("#ai-provider-select, #draggable-ai-provider-select").trigger("change");

        // Handle chat form submission
        $("#chat-form, #draggable-chat-form").on("submit", function (e) {
            e.preventDefault();
            if (!aiInitialized) {
                const isDraggable = $(this).attr("id") === "draggable-chat-form";
                Chat.addChatMessage("system", "Please initialize the AI assistant first.", isDraggable);
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

        // AI Chatbot Interface Handlers
        let aiInitialized = false;

        // Initialize AI provider
        $("#initialize-ai, #draggable-initialize-ai").on("click", function () {
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
                            Chat.addChatMessage("system", "AI Assistant initialized successfully! How can I help you with your D&D game?", isDraggable);
                        } else {
                            if (isDraggable) {
                                $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                            } else {
                                $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                            }
                            Chat.addChatMessage("system", "Failed to initialize AI: " + (data.error || "Unknown error"), isDraggable);
                        }
                    },
                    error: () => {
                        if (isDraggable) {
                            $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                        } else {
                            $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                        }
                        Chat.addChatMessage("system", "Failed to initialize AI: Network error", isDraggable);
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
                            Chat.addChatMessage("system", `AI Assistant initialized successfully with ${data.model || 'Ollama'}! How can I help you with your D&D game?`, isDraggable);
                        } else {
                            if (isDraggable) {
                                $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                            } else {
                                $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                            }
                            Chat.addChatMessage("system", "Failed to initialize AI: " + (data.error || "Unknown error"), isDraggable);
                        }
                    },
                    error: () => {
                        if (isDraggable) {
                            $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                        } else {
                            $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                        }
                        Chat.addChatMessage("system", "Failed to initialize AI: Network error. Make sure Ollama is running.", isDraggable);
                    }
                });
            } else {
                // Real providers need API key
                if (!apiKey) {
                    Chat.addChatMessage("system", "Please enter an API key for the selected provider.", isDraggable);
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
                            Chat.addChatMessage("system", "AI Assistant initialized successfully! How can I help you with your D&D game?", isDraggable);
                        } else {
                            if (isDraggable) {
                                $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                            } else {
                                $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                            }
                            Chat.addChatMessage("system", "Failed to initialize AI: " + (data.error || "Unknown error"), isDraggable);
                        }
                    },
                    error: () => {
                        if (isDraggable) {
                            $("#draggable-ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                        } else {
                            $("#ai-status").removeClass("label-default label-success").addClass("label-danger").text("Failed");
                        }
                        Chat.addChatMessage("system", "Failed to initialize AI: Network error", isDraggable);
                    }
                });
            }
        });

        // Handle provider change for both modal and draggable panel
        $("#ai-provider-select, #draggable-ai-provider-select").on("change", function () {
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
        $("#toggle-ai-chat").on("click", function () {
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
        $("#close-chat").on("click", function () {
            $("#ai-chat-panel").hide();
            $("#toggle-ai-chat").removeClass("btn-success").addClass("btn-primary");
        });

        // Minimize AI Chat Panel
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

        // Drag functionality for AI Chat Panel
        $("#ai-chat-panel .panel-header").on("mousedown", function (e) {
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
        $("#ai-chat-panel .resize-handle").on("mousedown", function (e) {
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

        $(document).on("mousemove", function (e) {
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

        $(document).on("mouseup", function () {
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
        $(window).on("resize", function () {
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
        $("#ai-model-select, #draggable-ai-model-select").on("change", function () {
            const selectedModel = $(this).val();
            const isDraggable = $(this).attr("id") === "draggable-ai-model-select";

            if (isDraggable) {
                $("#ai-model-select").val(selectedModel);
            } else {
                $("#draggable-ai-model-select").val(selectedModel);
            }
        });

        // Refresh models button for draggable panel
        $("#draggable-refresh-models").on("click", function () {
            if ($("#draggable-ai-provider-select").val() === "ollama") {
                loadDraggableOllamaModels();
                // Also refresh the modal models to keep them in sync
                loadOllamaModels();
            }
        });

        // Load position on page load
        $(document).ready(function () {
            loadPanelPosition();
        });

    }
};
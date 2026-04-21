const Chat = {
    localConversation: {
        initialized: false,
        dragInitialized: false,
        minimized: false,
        unreadCount: 0,
        selectedTargets: new Set(),
        entitiesById: {},
        reachableEntities: [],
        louderVoiceEntities: [],
        heardOnlyEntities: [],
        refreshTimerId: null,
        mentionAutocomplete: {
            query: '',
            tokenStart: -1,
            tokenEnd: -1,
            activeIndex: 0,
            suggestions: [],
            visible: false,
        },
    },
    localConversationStorageKey: 'natural20.localConversationPanel.position',
    localConversationMinimizedStorageKey: 'natural20.localConversationPanel.minimized',
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
    loadLlamaCppModels: function () {
        const url = $("#ai-api-key").val() || "http://localhost:8011";

        $.ajax({
            type: "GET",
            url: "/ai/llama_cpp/models",
            data: { base_url: url },
            success: (data) => {
                const $modelSelect = $("#ai-model-select");
                $modelSelect.empty();

                if (data.success && data.models && data.models.length > 0) {
                    data.models.forEach(model => {
                        $modelSelect.append(`<option value="${model}">${model}</option>`);
                    });
                    Chat.addChatMessage("system", `Found ${data.models.length} llama.cpp models. Please select one and initialize.`);
                    syncModelSelections();
                } else {
                    $modelSelect.append('<option value="">No models found</option>');
                    Chat.addChatMessage("system", "No llama.cpp models found. Please make sure the server is running and exposing /v1/models.");
                }
            },
            error: () => {
                const $modelSelect = $("#ai-model-select");
                $modelSelect.empty().append('<option value="">Failed to load models</option>');
                Chat.addChatMessage("system", "Failed to load llama.cpp models. Please check the server URL and connection.");
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
    getCurrentPovEntity: () => {
        // Try to get from the floating portraits
        const $currentPov = $('#floating-entity-portraits .floating-entity-portrait.current-pov');
        if ($currentPov.length) {
            return $currentPov.data('id');
        }

        const povEntityId = $('body').data('pov-entity');

        if (povEntityId) {
            return povEntityId;
        }

        // If we can't determine POV, return null
        return null;
    },
    escapeHtml: function (content) {
        return $('<div>').text(content || '').html();
    },
    getLocalConversationVolume: function () {
        return $('#localConversationVolume').val() || 'normal';
    },
    speechDistanceForVolume: function (volume) {
        switch (`${volume || 'normal'}`.toLowerCase()) {
            case 'whisper':
                return 5;
            case 'shout':
                return 60;
            default:
                return 30;
        }
    },
    getEffectiveConversationVolume: function (message, selectedVolume) {
        const normalizedVolume = `${selectedVolume || 'normal'}`.toLowerCase();
        if (normalizedVolume !== 'normal') {
            return normalizedVolume;
        }
        return /!/.test(`${message || ''}`) ? 'shout' : 'normal';
    },
    clampLocalConversationPanelPosition: function (left, top, panelWidth, panelHeight) {
        const margin = 8;
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
        const maxLeft = Math.max(margin, viewportWidth - panelWidth - margin);
        const maxTop = Math.max(margin, viewportHeight - panelHeight - margin);
        return {
            left: Math.min(Math.max(margin, left), maxLeft),
            top: Math.min(Math.max(margin, top), maxTop),
        };
    },
    saveLocalConversationPanelPosition: function ($panel) {
        if (!$panel.length || window.innerWidth <= 768 || Chat.localConversation.minimized) {
            return;
        }

        const position = {
            left: Math.round(parseFloat($panel.css('left')) || 0),
            top: Math.round(parseFloat($panel.css('top')) || 0),
        };
        try {
            window.localStorage.setItem(Chat.localConversationStorageKey, JSON.stringify(position));
        } catch (_) {
        }
    },
    applyLocalConversationPanelPosition: function (position) {
        const $panel = $('#localConversationPanel');
        if (!$panel.length) {
            return;
        }

        if (Chat.localConversation.minimized) {
            Chat.applyLocalConversationMinimizedLayout($panel);
            return;
        }

        if (window.innerWidth <= 768) {
            $panel.css({ left: '', top: '', right: '', bottom: '', width: '', height: '', minHeight: '', maxHeight: '' });
            return;
        }

        const panelWidth = $panel.outerWidth() || 360;
        const panelHeight = $panel.outerHeight() || 430;
        let nextLeft = position && Number.isFinite(position.left)
            ? position.left
            : Math.max(8, (window.innerWidth || 0) - panelWidth - 20);
        let nextTop = position && Number.isFinite(position.top) ? position.top : 96;
        const clamped = Chat.clampLocalConversationPanelPosition(nextLeft, nextTop, panelWidth, panelHeight);
        $panel.css({
            left: `${clamped.left}px`,
            top: `${clamped.top}px`,
            right: 'auto',
            bottom: 'auto',
            width: '',
            height: '',
            minHeight: '',
            maxHeight: '',
        });
    },
    applyLocalConversationMinimizedLayout: function ($panel) {
        const $targetPanel = $panel && $panel.length ? $panel : $('#localConversationPanel');
        if (!$targetPanel.length) {
            return;
        }

        if (window.innerWidth <= 768) {
            $targetPanel.css({
                left: '10px',
                right: '10px',
                top: '',
                bottom: '10px',
                width: 'auto',
                height: 'auto',
                minHeight: '0',
                maxHeight: 'none',
            });
            return;
        }

        $targetPanel.css({
            left: '',
            top: '',
            right: '240px',
            bottom: '20px',
            width: '260px',
            height: 'auto',
            minHeight: '0',
            maxHeight: 'none',
        });
    },
    restoreLocalConversationPanelPosition: function () {
        let savedPosition = null;
        try {
            savedPosition = JSON.parse(window.localStorage.getItem(Chat.localConversationStorageKey) || 'null');
        } catch (_) {
            savedPosition = null;
        }
        Chat.applyLocalConversationPanelPosition(savedPosition);
    },
    loadLocalConversationMinimizedState: function () {
        try {
            return window.localStorage.getItem(Chat.localConversationMinimizedStorageKey) === 'true';
        } catch (_) {
            return false;
        }
    },
    saveLocalConversationMinimizedState: function () {
        try {
            window.localStorage.setItem(Chat.localConversationMinimizedStorageKey, Chat.localConversation.minimized ? 'true' : 'false');
        } catch (_) {
        }
    },
    updateLocalConversationUnreadBadge: function () {
        const unreadCount = Chat.localConversation.unreadCount || 0;
        const $badge = $('#localConversationUnreadBadge');
        if (!$badge.length) {
            return;
        }

        if (unreadCount > 0) {
            $badge.text(unreadCount > 99 ? '99+' : `${unreadCount}`).addClass('visible');
        } else {
            $badge.text('0').removeClass('visible');
        }
    },
    resetLocalConversationUnreadCount: function () {
        Chat.localConversation.unreadCount = 0;
        Chat.updateLocalConversationUnreadBadge();
    },
    setLocalConversationMinimized: function (minimized) {
        const $panel = $('#localConversationPanel');
        const $button = $('#localConversationMinimize');
        if (!$panel.length) {
            return;
        }

        Chat.localConversation.minimized = !!minimized;
        $panel.toggleClass('minimized', Chat.localConversation.minimized).removeClass('dragging');

        if (Chat.localConversation.minimized) {
            Chat.applyLocalConversationMinimizedLayout($panel);
            Chat.hideLocalMentionSuggestions();
            $button.attr('title', 'Restore local chat').find('i').removeClass('glyphicon-minus').addClass('glyphicon-plus');
        } else {
            $panel.css({
                width: '',
                height: '',
                minHeight: '',
                maxHeight: '',
            });
            Chat.restoreLocalConversationPanelPosition();
            Chat.resetLocalConversationUnreadCount();
            $button.attr('title', 'Minimize local chat').find('i').removeClass('glyphicon-plus').addClass('glyphicon-minus');
        }

        Chat.saveLocalConversationMinimizedState();
        Chat.updateLocalConversationUnreadBadge();
    },
    toggleLocalConversationMinimized: function () {
        Chat.setLocalConversationMinimized(!Chat.localConversation.minimized);
    },
    initLocalConversationDrag: function () {
        if (Chat.localConversation.dragInitialized) {
            return;
        }
        Chat.localConversation.dragInitialized = true;

        const $panel = $('#localConversationPanel');
        const $header = $('#localConversationPanel .local-conversation-header');
        if (!$panel.length || !$header.length) {
            return;
        }

        let dragState = null;

        const stopDrag = function () {
            if (!dragState) {
                return;
            }
            $panel.removeClass('dragging');
            Chat.saveLocalConversationPanelPosition($panel);
            dragState = null;
            $(document).off('mousemove.localConversationDrag mouseup.localConversationDrag');
        };

        $header.on('mousedown', function (event) {
            if (window.innerWidth <= 768) {
                return;
            }
            if (Chat.localConversation.minimized) {
                return;
            }
            if ($(event.target).closest('button, input, select, textarea, a, label').length) {
                return;
            }

            const offset = $panel.offset();
            dragState = {
                startX: event.clientX,
                startY: event.clientY,
                startLeft: offset ? offset.left : parseFloat($panel.css('left')) || 0,
                startTop: offset ? offset.top : parseFloat($panel.css('top')) || 0,
                width: $panel.outerWidth() || 360,
                height: $panel.outerHeight() || 430,
            };
            $panel.css({ right: 'auto', bottom: 'auto' }).addClass('dragging');

            $(document)
                .on('mousemove.localConversationDrag', function (moveEvent) {
                    if (!dragState) {
                        return;
                    }
                    const nextLeft = dragState.startLeft + (moveEvent.clientX - dragState.startX);
                    const nextTop = dragState.startTop + (moveEvent.clientY - dragState.startY);
                    const clamped = Chat.clampLocalConversationPanelPosition(nextLeft, nextTop, dragState.width, dragState.height);
                    $panel.css({
                        left: `${clamped.left}px`,
                        top: `${clamped.top}px`,
                    });
                })
                .on('mouseup.localConversationDrag', stopDrag);

            event.preventDefault();
        });

        $(window).on('resize.localConversationPanel', function () {
            if (Chat.localConversation.minimized) {
                Chat.applyLocalConversationMinimizedLayout($panel);
            } else {
                Chat.restoreLocalConversationPanelPosition();
            }
        });

        Chat.restoreLocalConversationPanelPosition();
    },
    setLocalConversationStatus: function (content) {
        $('#localConversationStatus').text(content);
    },
    describeAcousticPenalty: function (entity) {
        if (!entity || !entity.acoustic_penalty_ft) {
            return '';
        }
        if (entity.acoustic_summary) {
            return `through ${entity.acoustic_summary}`;
        }
        return `with ${entity.acoustic_penalty_ft}ft acoustic loss`;
    },
    insertLocalMention: function (handle) {
        const $input = $('#localConversationInput');
        const existing = $input.val() || '';
        const mentionToken = `@${handle}`;
        if (existing.includes(mentionToken)) {
            $input.focus();
            return;
        }
        const nextValue = `${existing.trim()} ${mentionToken}`.trim() + ' ';
        $input.val(nextValue).focus();
        Chat.hideLocalMentionSuggestions();
    },
    getLocalMentionCandidates: function () {
        const state = Chat.localConversation;
        const candidates = Object.values(state.entitiesById || {});
        const deduped = [];
        const seen = new Set();

        candidates.forEach((entity) => {
            if (!entity || !entity.id || !entity.mention_handle || seen.has(entity.id)) {
                return;
            }
            seen.add(entity.id);
            deduped.push(entity);
        });

        deduped.sort((left, right) => {
            const leftReachable = left.reachable_now ? 0 : 1;
            const rightReachable = right.reachable_now ? 0 : 1;
            if (leftReachable !== rightReachable) {
                return leftReachable - rightReachable;
            }
            return `${left.name || left.mention_handle}`.localeCompare(`${right.name || right.mention_handle}`);
        });

        return deduped;
    },
    getLocalMentionMatch: function (value, caretIndex) {
        const text = `${value || ''}`;
        const caret = Number.isFinite(caretIndex) ? caretIndex : text.length;
        const textBeforeCaret = text.slice(0, caret);
        const match = textBeforeCaret.match(/(^|\s)@([A-Za-z0-9_-]*)$/);
        if (!match) {
            return null;
        }

        const tokenStart = textBeforeCaret.lastIndexOf('@');
        if (tokenStart < 0) {
            return null;
        }

        return {
            query: match[2] || '',
            tokenStart: tokenStart,
            tokenEnd: caret,
        };
    },
    describeLocalMentionCandidate: function (entity) {
        if (!entity) {
            return '';
        }
        if (entity.reachable_now) {
            return 'reachable';
        }
        if (entity.minimum_volume) {
            return `needs ${entity.minimum_volume}`;
        }
        if (entity.status === 'too_far') {
            return 'heard only';
        }
        return entity.status || '';
    },
    renderLocalMentionSuggestions: function () {
        const autocomplete = Chat.localConversation.mentionAutocomplete;
        const $container = $('#localConversationMentionSuggestions');
        if (!$container.length) {
            return;
        }

        if (!autocomplete.visible || !autocomplete.suggestions.length) {
            $container.empty().hide();
            return;
        }

        $container.empty();
        autocomplete.suggestions.forEach((entity, index) => {
            const activeClass = index === autocomplete.activeIndex ? ' active' : '';
            const label = Chat.escapeHtml(entity.name || entity.mention_handle);
            const handle = Chat.escapeHtml(entity.mention_handle);
            const status = Chat.escapeHtml(Chat.describeLocalMentionCandidate(entity));
            $container.append(`
                <button type="button" class="local-conversation-mention-suggestion${activeClass}" data-index="${index}" data-handle="${entity.mention_handle}">
                    <span class="local-conversation-mention-label">
                        <strong>${label}</strong>
                        <span>@${handle}</span>
                    </span>
                    <span class="local-conversation-mention-status">${status}</span>
                </button>
            `);
        });
        $container.show();
    },
    hideLocalMentionSuggestions: function () {
        Chat.localConversation.mentionAutocomplete = {
            query: '',
            tokenStart: -1,
            tokenEnd: -1,
            activeIndex: 0,
            suggestions: [],
            visible: false,
        };
        $('#localConversationMentionSuggestions').empty().hide();
    },
    updateLocalMentionSuggestions: function () {
        const $input = $('#localConversationInput');
        if (!$input.length) {
            return;
        }

        const value = $input.val() || '';
        const match = Chat.getLocalMentionMatch(value, $input[0].selectionStart);
        if (!match) {
            Chat.hideLocalMentionSuggestions();
            return;
        }

        const normalizedQuery = match.query.toLowerCase();
        const suggestions = Chat.getLocalMentionCandidates().filter((entity) => {
            const handle = `${entity.mention_handle || ''}`.toLowerCase();
            const name = `${entity.name || ''}`.toLowerCase();
            return !normalizedQuery || handle.startsWith(normalizedQuery) || name.includes(normalizedQuery);
        }).slice(0, 6);

        if (!suggestions.length) {
            Chat.hideLocalMentionSuggestions();
            return;
        }

        const previous = Chat.localConversation.mentionAutocomplete;
        const nextActiveIndex = suggestions.findIndex((entity) => previous.suggestions[previous.activeIndex] && entity.id === previous.suggestions[previous.activeIndex].id);
        Chat.localConversation.mentionAutocomplete = {
            query: match.query,
            tokenStart: match.tokenStart,
            tokenEnd: match.tokenEnd,
            activeIndex: nextActiveIndex >= 0 ? nextActiveIndex : 0,
            suggestions: suggestions,
            visible: true,
        };
        Chat.renderLocalMentionSuggestions();
    },
    moveLocalMentionSelection: function (direction) {
        const autocomplete = Chat.localConversation.mentionAutocomplete;
        if (!autocomplete.visible || !autocomplete.suggestions.length) {
            return false;
        }
        const count = autocomplete.suggestions.length;
        autocomplete.activeIndex = (autocomplete.activeIndex + direction + count) % count;
        Chat.renderLocalMentionSuggestions();
        return true;
    },
    applyLocalMentionSuggestion: function (handle) {
        const autocomplete = Chat.localConversation.mentionAutocomplete;
        const $input = $('#localConversationInput');
        if (!$input.length) {
            return;
        }

        const input = $input[0];
        const value = $input.val() || '';
        const tokenStart = autocomplete.tokenStart;
        const tokenEnd = autocomplete.tokenEnd >= tokenStart ? autocomplete.tokenEnd : (input.selectionStart || value.length);
        if (tokenStart < 0) {
            Chat.insertLocalMention(handle);
            return;
        }

        const before = value.slice(0, tokenStart);
        const after = value.slice(tokenEnd);
        const replacement = `@${handle} `;
        const nextValue = `${before}${replacement}${after}`;
        const nextCaret = before.length + replacement.length;

        $input.val(nextValue).focus();
        try {
            input.setSelectionRange(nextCaret, nextCaret);
        } catch (_) {
        }
        Chat.hideLocalMentionSuggestions();
    },
    handleLocalMentionKeydown: function (event) {
        const autocomplete = Chat.localConversation.mentionAutocomplete;
        if (!autocomplete.visible || !autocomplete.suggestions.length) {
            return false;
        }

        if (event.key === 'ArrowDown') {
            event.preventDefault();
            return Chat.moveLocalMentionSelection(1);
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            return Chat.moveLocalMentionSelection(-1);
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            Chat.hideLocalMentionSuggestions();
            return true;
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
            event.preventDefault();
            const selected = autocomplete.suggestions[autocomplete.activeIndex];
            if (selected) {
                Chat.applyLocalMentionSuggestion(selected.mention_handle);
                return true;
            }
        }
        return false;
    },
    toggleLocalConversationTarget: function (entityId) {
        const state = Chat.localConversation;
        if (state.selectedTargets.has(entityId)) {
            state.selectedTargets.delete(entityId);
        } else {
            state.selectedTargets.add(entityId);
        }
        Chat.renderLocalConversationTargets();
    },
    renderLocalConversationTargets: function () {
        const state = Chat.localConversation;
        const $container = $('#localConversationTargets');
        $container.empty();

                const sections = [
                        {
                                title: 'Can Talk Now',
                                entities: state.reachableEntities || [],
                                selectable: true,
                            describe: (entity) => {
                                const acousticNote = Chat.describeAcousticPenalty(entity);
                                return acousticNote
                                    ? `${entity.distance}ft away, hears like ${entity.adjusted_distance_ft}ft ${acousticNote}`
                                    : `${entity.distance}ft away, reachable at this volume`;
                            },
                        },
                        {
                                title: 'Need Louder Voice',
                                entities: state.louderVoiceEntities || [],
                                selectable: false,
                            describe: (entity) => {
                                const acousticNote = Chat.describeAcousticPenalty(entity);
                                const tail = acousticNote ? ` ${acousticNote}` : '';
                                return `Need ${entity.minimum_volume} to reply (${entity.distance}ft, treated like ${entity.adjusted_distance_ft}ft)${tail}`;
                            },
                        },
                        {
                                title: 'Heard, Too Far To Reply',
                                entities: state.heardOnlyEntities || [],
                                selectable: false,
                            describe: (entity) => {
                                const acousticNote = Chat.describeAcousticPenalty(entity);
                                const tail = acousticNote ? ` ${acousticNote}` : '';
                                return `Out of reply range (${entity.distance}ft, treated like ${entity.adjusted_distance_ft}ft)${tail}`;
                            },
                        },
                ];

                const anyEntities = sections.some((section) => section.entities.length);
                if (!anyEntities) {
            $container.append('<div class="local-conversation-empty">No nearby listeners.</div>');
            return;
        }

                sections.forEach((section) => {
                        if (!section.entities.length) {
                                return;
                        }

                        $container.append(`<div class="local-conversation-section"><div class="local-conversation-section-title">${Chat.escapeHtml(section.title)}</div></div>`);
                        const $section = $container.find('.local-conversation-section').last();

                        section.entities.forEach((entity) => {
                                const activeClass = section.selectable && state.selectedTargets.has(entity.id) ? ' active' : '';
                                const disabledClass = section.selectable ? '' : ' disabled';
                                const name = Chat.escapeHtml(entity.name);
                                const handle = Chat.escapeHtml(entity.mention_handle);
                                const meta = section.describe(entity);
                                $section.append(`
                                    <div class="local-conversation-target-row">
                                        <button type="button" class="local-conversation-target${activeClass}${disabledClass}" data-entity-id="${entity.id}" ${section.selectable ? '' : 'data-disabled="true"'}>
                                            <strong>${name}</strong>
                                            <span>@${handle} · ${Chat.escapeHtml(meta)}</span>
                                        </button>
                                        <button type="button" class="btn btn-xs btn-default local-conversation-mention" data-handle="${entity.mention_handle}" title="Insert @mention">
                                            @
                                        </button>
                                    </div>
                                `);
                        });
        });
    },
    renderLocalConversationLanguages: function (languages) {
        const $select = $('#localConversationLanguage');
        const currentValue = $select.val() || 'Common';
        const uniqueLanguages = [];
        (languages || ['common']).forEach((language) => {
            const normalized = `${language}`.trim();
            if (!normalized) {
                return;
            }
            if (!uniqueLanguages.includes(normalized)) {
                uniqueLanguages.push(normalized);
            }
        });

        $select.empty();
        uniqueLanguages.forEach((language) => {
            const normalized = language.toLowerCase() === 'common' ? 'Common' : language;
            $select.append(`<option value="${Chat.escapeHtml(normalized)}">${Chat.escapeHtml(normalized)}</option>`);
        });

        if (uniqueLanguages.some((language) => language.toLowerCase() === `${currentValue}`.toLowerCase())) {
            $select.val(currentValue);
        }
    },
    appendLocalConversationMessage: function (payload) {
        if (!payload || !payload.message || !$('#localConversationMessages').length) {
            return;
        }

        const $messages = $('#localConversationMessages');
        $messages.find('.local-conversation-empty').remove();

        const currentPovEntity = Chat.getCurrentPovEntity();
        const isOwnMessage = payload.entity_id === currentPovEntity;
        const speakerName = Chat.escapeHtml(payload.speaker_name || payload.entity_id || 'Unknown');
        const targetNames = (payload.target_names || []).length ? ` to ${Chat.escapeHtml(payload.target_names.join(', '))}` : '';
        const volume = Chat.escapeHtml(payload.volume || 'normal');
                const replyStatus = Chat.localConversation.entitiesById[payload.entity_id];
                let note = '';
                if (!isOwnMessage && replyStatus) {
                        if (replyStatus.status === 'requires_louder_voice') {
                        note = `You heard this, but need ${replyStatus.minimum_volume} to reply.${replyStatus.acoustic_summary ? ` Path attenuation: ${replyStatus.acoustic_summary}.` : ''}`;
                        } else if (replyStatus.status === 'too_far') {
                        note = `You heard this, but the speaker is outside your talking range.${replyStatus.acoustic_summary ? ` Path attenuation: ${replyStatus.acoustic_summary}.` : ''}`;
                        }
                }
        const timestamp = new Date().toLocaleTimeString();
        const messageHtml = `
          <div class="local-conversation-message${isOwnMessage ? ' own' : ''}">
            <div class="local-conversation-message-header">
              <span><strong>${speakerName}</strong>${targetNames}</span>
              <span>${volume} · ${timestamp}</span>
            </div>
            <div class="local-conversation-message-body">${Chat.escapeHtml(payload.message)}</div>
                        ${note ? `<div class="local-conversation-message-note">${Chat.escapeHtml(note)}</div>` : ''}
          </div>
        `;
        $messages.append(messageHtml);
        $messages.scrollTop($messages[0].scrollHeight);

        if (Chat.localConversation.minimized && !isOwnMessage) {
            Chat.localConversation.unreadCount += 1;
            Chat.updateLocalConversationUnreadBadge();
        }
    },
    handleLocalConversationEvent: function (payload) {
        Chat.appendLocalConversationMessage(payload);
        Chat.refreshLocalConversationPresence({ silent: true });
    },
    refreshLocalConversationPresence: function (options = {}) {
        const currentPovEntity = Chat.getCurrentPovEntity();
        if (!currentPovEntity) {
            Chat.localConversation.entitiesById = {};
            Chat.localConversation.selectedTargets.clear();
            Chat.renderLocalConversationTargets();
            Chat.setLocalConversationStatus('Select a point-of-view character to see who can hear you.');
            $('#localConversationSpeaker').text('No active speaker');
            return;
        }

        $.ajax({
            type: 'GET',
            url: '/conversation_presence',
            data: {
                entity_id: currentPovEntity,
                volume: Chat.getLocalConversationVolume(),
            },
            success: (data) => {
                const state = Chat.localConversation;
                state.entitiesById = {};
                (data.entities || []).forEach((entity) => {
                    state.entitiesById[entity.id] = entity;
                });
                state.reachableEntities = data.reachable_entities || [];
                state.louderVoiceEntities = data.requires_louder_voice_entities || [];
                state.heardOnlyEntities = data.heard_only_entities || [];

                state.selectedTargets = new Set(
                    Array.from(state.selectedTargets).filter((entityId) => {
                        const entity = state.entitiesById[entityId];
                        return entity && entity.reachable_now;
                    })
                );

                $('#localConversationSpeaker').text(`${data.speaker.name} speaking ${data.volume}`);
                Chat.renderLocalConversationLanguages(data.speaker.languages || ['Common']);
                Chat.renderLocalConversationTargets();
                const statusParts = [];
                if ((state.reachableEntities || []).length) {
                    statusParts.push(`${state.reachableEntities.length} can hear you at ${data.volume}`);
                }
                if ((state.louderVoiceEntities || []).length) {
                    statusParts.push(`${state.louderVoiceEntities.length} heard nearby speech but need a louder reply`);
                }
                if ((state.heardOnlyEntities || []).length) {
                    statusParts.push(`${state.heardOnlyEntities.length} are audible but too far to answer`);
                }
                Chat.setLocalConversationStatus(
                    statusParts.length
                        ? `${statusParts.join('. ')}.`
                        : `Nobody nearby can currently hear ${data.speaker.name}.`
                );
                Chat.updateLocalMentionSuggestions();
            },
            error: () => {
                if (!options.silent) {
                    Chat.setLocalConversationStatus('Unable to refresh nearby listeners right now.');
                }
            }
        });
    },
    sendLocalConversationMessage: function () {
        const currentPovEntity = Chat.getCurrentPovEntity();
        const message = ($('#localConversationInput').val() || '').trim();
        if (!currentPovEntity || !message) {
            return;
        }

        const $sendButton = $('#localConversationSend');
        const $input = $('#localConversationInput');
        $sendButton.prop('disabled', true);
        $input.prop('disabled', true);

        $.ajax({
            type: 'POST',
            url: '/talk',
            contentType: 'application/json',
            data: JSON.stringify({
                entity_id: currentPovEntity,
                message: message,
                targets: Array.from(Chat.localConversation.selectedTargets),
                language: $('#localConversationLanguage').val(),
                volume: Chat.getEffectiveConversationVolume(message, Chat.getLocalConversationVolume()),
            }),
            success: () => {
                $('#localConversationInput').val('');
                $sendButton.prop('disabled', false);
                $input.prop('disabled', false).focus();
                Chat.hideLocalMentionSuggestions();
                Chat.localConversation.selectedTargets.clear();
                Chat.renderLocalConversationTargets();
                Chat.refreshLocalConversationPresence({ silent: true });
            },
            error: () => {
                $sendButton.prop('disabled', false);
                $input.prop('disabled', false).focus();
                Chat.setLocalConversationStatus('Failed to send local message.');
            }
        });
    },
    initLocalConversationPanel: function () {
        if (Chat.localConversation.initialized) {
            return;
        }
        Chat.localConversation.initialized = true;
        Chat.initLocalConversationDrag();
        Chat.localConversation.minimized = Chat.loadLocalConversationMinimizedState();
        Chat.updateLocalConversationUnreadBadge();

        $('#localConversationMinimize').on('click', function () {
            Chat.toggleLocalConversationMinimized();
        });

        $('#localConversationRefresh').on('click', function () {
            Chat.refreshLocalConversationPresence();
        });

        $('#localConversationVolume').on('change', function () {
            Chat.refreshLocalConversationPresence();
        });

        $('#localConversationSend').on('click', function () {
            Chat.sendLocalConversationMessage();
        });

        $('#localConversationInput').on('input click focus', function () {
            Chat.updateLocalMentionSuggestions();
        });

        $('#localConversationInput').on('keydown', function (e) {
            if (Chat.handleLocalMentionKeydown(e)) {
                return;
            }
            if (e.which === 13) {
                e.preventDefault();
                Chat.sendLocalConversationMessage();
            }
        });

        $('#localConversationInput').on('blur', function () {
            window.setTimeout(function () {
                Chat.hideLocalMentionSuggestions();
            }, 100);
        });

        $('#localConversationPanel .local-conversation-header-main').on('click', function () {
            if (Chat.localConversation.minimized) {
                Chat.setLocalConversationMinimized(false);
            }
        });

        $('#localConversationTargets').on('click', '.local-conversation-target', function () {
            if ($(this).data('disabled')) {
                return;
            }
            Chat.toggleLocalConversationTarget($(this).data('entity-id'));
        });

        $('#localConversationTargets').on('click', '.local-conversation-mention', function () {
            Chat.insertLocalMention($(this).data('handle'));
        });

        $('#localConversationMentionSuggestions').on('mousedown', '.local-conversation-mention-suggestion', function (event) {
            event.preventDefault();
            Chat.applyLocalMentionSuggestion($(this).data('handle'));
        });

        Chat.refreshLocalConversationPresence({ silent: true });
        Chat.localConversation.refreshTimerId = window.setInterval(function () {
            Chat.refreshLocalConversationPresence({ silent: true });
        }, 5000);

        Chat.setLocalConversationMinimized(Chat.localConversation.minimized);
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
    addDialogMessage: function (sender, content, type) {
        const timestamp = new Date().toLocaleTimeString();

        // Determine the display name based on mode and sender
        let displayName = sender;
        if (talkToEntityMode) {
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
        <div class="message-content">${content}</div>
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
        // Refresh models button
        $("#refresh-models").on("click", function () {
            if ($("#ai-provider-select").val() === "ollama") {
                Chat.loadOllamaModels();
            } else if ($("#ai-provider-select").val() === "llama_cpp") {
                Chat.loadLlamaCppModels();
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
            } else if (provider === "ollama" || provider === "llama_cpp") {
                // Local model providers
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
                            const providerLabel = provider === "llama_cpp" ? "llama.cpp" : "Ollama";
                            Chat.addChatMessage("system", `AI Assistant initialized successfully with ${data.model || providerLabel}! How can I help you with your D&D game?`, isDraggable);
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
                        const providerLabel = provider === "llama_cpp" ? "llama.cpp" : "Ollama";
                        Chat.addChatMessage("system", `Failed to initialize AI: Network error. Make sure ${providerLabel} is running.`, isDraggable);
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
                    Chat.loadOllamaModels();
                }
            } else if (provider === "llama_cpp") {
                $apiKeyField.prop("disabled", false).val("http://localhost:8011");
                $apiKeyLabel.text("llama.cpp URL");
                $apiKeyHelp.text("Leave empty for http://localhost:8011 or enter custom URL");
                $modelRow.show();

                if (isDraggable) {
                    loadDraggableLlamaCppModels();
                } else {
                    Chat.loadLlamaCppModels();
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

        function loadDraggableLlamaCppModels() {
            const url = $("#draggable-ai-api-key").val() || "http://localhost:8011";

            $.ajax({
                type: "GET",
                url: "/ai/llama_cpp/models",
                data: { base_url: url },
                success: (data) => {
                    const $modelSelect = $("#draggable-ai-model-select");
                    $modelSelect.empty();

                    if (data.success && data.models && data.models.length > 0) {
                        data.models.forEach(model => {
                            $modelSelect.append(`<option value="${model}">${model}</option>`);
                        });
                        addChatMessage("system", `Found ${data.models.length} llama.cpp models. Please select one and initialize.`, true);
                        syncModelSelections();
                    } else {
                        $modelSelect.append('<option value="">No models found</option>');
                        addChatMessage("system", "No llama.cpp models found. Please make sure the server is running and exposing /v1/models.", true);
                    }
                },
                error: () => {
                    const $modelSelect = $("#draggable-ai-model-select");
                    $modelSelect.empty().append('<option value="">Failed to load models</option>');
                    addChatMessage("system", "Failed to load llama.cpp models. Please check the server URL and connection.", true);
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
                Chat.loadOllamaModels();
            } else if ($("#draggable-ai-provider-select").val() === "llama_cpp") {
                loadDraggableLlamaCppModels();
                Chat.loadLlamaCppModels();
            }
        });

        // Load position on page load
        $(document).ready(function () {
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

            loadPanelPosition();
        });

    }
};
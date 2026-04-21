window.LocalConversationChatBindings = {
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
        const nextLeft = position && Number.isFinite(position.left)
            ? position.left
            : Math.max(8, (window.innerWidth || 0) - panelWidth - 20);
        const nextTop = position && Number.isFinite(position.top) ? position.top : 96;
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
                const narrativeEntries = Array.isArray(payload.narrative)
                        ? payload.narrative.filter((entry) => `${entry || ''}`.trim().length > 0)
                        : [];
                const narrativeHtml = narrativeEntries.map((entry) => (
                        `<div class="local-conversation-message-aside">${Chat.escapeHtml(entry)}</div>`
                )).join('');
        const messageHtml = `
          <div class="local-conversation-message${isOwnMessage ? ' own' : ''}">
            <div class="local-conversation-message-header">
              <span><strong>${speakerName}</strong>${targetNames}</span>
              <span>${volume} · ${timestamp}</span>
            </div>
            <div class="local-conversation-message-body">${Chat.escapeHtml(payload.message)}</div>
                        ${narrativeHtml}
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

        $('#localConversationInput').on('keydown', function (event) {
            if (Chat.handleLocalMentionKeydown(event)) {
                return;
            }
            if (event.which === 13) {
                event.preventDefault();
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
};
from flask import jsonify, request, session
import re
import time

from natural20.player_character import PlayerCharacter
from natural20.utils.animal_communication import has_animal_communication
from natural20.utils.conversation import (
    entity_label,
    format_entity_gear_for_conversation,
    mention_handle_for,
    normalize_speech_mode,
    resolve_named_targets,
    resolve_mention_targets,
    speech_distance_for,
    unique_entities,
)
from natural20.utils.gibberish import gibberish


# Recognises a player's request to attempt an Insight (Wisdom) check.
# Examples that match (case-insensitive):
#   "insight check"                       "[insight check]"
#   "I want to roll insight on @Garrick"  "/insight"
#   "Insight check on the merchant about his prices"
#   "make an insight check"
PLAYER_INSIGHT_PATTERNS = [
    re.compile(r'^\s*/?\s*insight(?:\s+check)?\b', re.IGNORECASE),
    re.compile(r'^\s*\[\s*insight(?:\s+check)?[^\]]*\]', re.IGNORECASE),
    re.compile(r'\b(?:make|do|roll|attempt|try|perform)\s+(?:an?\s+)?insight\s+check\b', re.IGNORECASE),
    re.compile(r'\binsight\s+check\s+(?:on|against|of|for)\b', re.IGNORECASE),
    re.compile(r'\broll(?:ing)?\s+insight\b', re.IGNORECASE),
]

BEAST_DIALECT_TO_BASE_LANGUAGE = {
    'sheep': 'beast',
}

# Pulls a "target" and an optional "purpose" clause out of an insight request.
# We try a few common phrasings; whichever matches first wins.
_INSIGHT_TARGET_PURPOSE_PATTERNS = [
    re.compile(
        r'insight(?:\s+check)?\s+on\s+(?P<target>@?[\w\'\- ]+?)'
        r'(?:\s+(?:about|regarding|for|to(?:\s+(?:see|determine|tell|find\s+out))?)\s+(?P<purpose>.+))?$',
        re.IGNORECASE,
    ),
    re.compile(
        r'insight(?:\s+check)?\s+against\s+(?P<target>@?[\w\'\- ]+?)'
        r'(?:\s+(?:about|regarding|for)\s+(?P<purpose>.+))?$',
        re.IGNORECASE,
    ),
]


def is_player_insight_request(message):
    """Return True when the player's message is asking to roll Insight."""
    if not message:
        return False
    text = str(message).strip()
    if not text:
        return False
    for pattern in PLAYER_INSIGHT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def parse_player_insight_request(message):
    """Extract a (target_spec, purpose) tuple from the player's message.

    Either field may be ``None`` if the request is too vague.
    """
    text = (message or '').strip()
    target_spec = None
    purpose = None
    for pattern in _INSIGHT_TARGET_PURPOSE_PATTERNS:
        match = pattern.search(text)
        if match:
            target_spec = (match.group('target') or '').strip(' .,!?') or None
            purpose = (match.group('purpose') or '').strip(' .,!?') or None
            break

    # Fall back: anything after the first "about"/"regarding"/"because"
    if purpose is None:
        about_match = re.search(
            r'\b(?:about|regarding|because|to\s+see|to\s+determine|to\s+tell|to\s+find\s+out)\s+(?P<rest>.+)$',
            text,
            re.IGNORECASE,
        )
        if about_match:
            purpose = about_match.group('rest').strip(' .,!?') or None
    return target_spec, purpose


class ConversationService:
    def __init__(
        self,
        current_game_getter,
        game_session,
        socketio,
        entity_rag_handler_getter,
        llm_conversation_handler_getter,
        roles_for_username_getter,
        entity_owners_getter,
        entities_controlled_by_getter,
        logins_getter,
        logger,
    ):
        self._current_game_getter = current_game_getter
        self.game_session = game_session
        self.socketio = socketio
        self._entity_rag_handler_getter = entity_rag_handler_getter
        self._llm_conversation_handler_getter = llm_conversation_handler_getter
        self._roles_for_username_getter = roles_for_username_getter
        self._entity_owners_getter = entity_owners_getter
        self._entities_controlled_by_getter = entities_controlled_by_getter
        self._logins_getter = logins_getter
        self.logger = logger
        self._conversation_presence_cache: dict = {}
        self._CONVERSANCE_PRESENCE_CACHE_TTL = 15.0  # Reduce expensive acoustic recomputation on debounced refreshes

    @property
    def current_game(self):
        return self._current_game_getter()

    @property
    def llm_conversation_handler(self):
        return self._llm_conversation_handler_getter()

    @property
    def entity_rag_handler(self):
        return self._entity_rag_handler_getter()

    @property
    def roles_for_username(self):
        return self._roles_for_username_getter()

    @property
    def entity_owners(self):
        return self._entity_owners_getter()

    @property
    def entities_controlled_by(self):
        return self._entities_controlled_by_getter()

    @property
    def logins(self):
        return self._logins_getter() or []

    def entity_audience_usernames(self, entities, include_dm=True):
        recipients = set()
        for entity in entities or []:
            if entity is None:
                continue
            recipients.update(self.entity_owners(entity))

        if include_dm:
            for login in self.logins:
                roles = login.get('role') or []
                if 'dm' in roles and login.get('name'):
                    recipients.add(login['name'].lower())

        return recipients

    def conversation_audience_usernames(self, source_entity, processed_conversations=None, targets=None, include_dm=True):
        audience_entities = [source_entity]
        for receiver, _message, directed_to in (processed_conversations or []):
            audience_entities.append(receiver)
            audience_entities.extend(directed_to or [])
        audience_entities.extend(targets or [])
        return self.entity_audience_usernames(audience_entities, include_dm=include_dm)

    def conversation_visible_whisper_usernames(self, source_entity, audible_usernames=None):
        audible_usernames = {str(username).lower() for username in (audible_usernames or []) if username}

        try:
            battle_map = self.current_game.get_map_for_entity(source_entity)
        except Exception:
            battle_map = None

        if battle_map is None:
            return set()

        visible_usernames = set()
        candidate_usernames = {
            str(login.get('name')).lower()
            for login in self.logins
            if login.get('name')
        }
        candidate_usernames.update({str(username).lower() for username in self.current_game.username_to_sid.keys() if username})

        for username in candidate_usernames:
            if username in audible_usernames:
                continue

            roles = self.roles_for_username(username)
            if roles and 'dm' in roles:
                continue

            listener = self.conversation_listener_for_username(username)
            if listener is None or listener == source_entity:
                continue

            try:
                listener_map = self.current_game.get_map_for_entity(listener)
            except Exception:
                listener_map = None

            if listener_map is not None and listener_map != battle_map:
                continue

            try:
                if battle_map.can_see(listener, source_entity):
                    visible_usernames.add(username)
            except Exception:
                continue

        return visible_usernames

    def conversation_payload(self, entity, message, targets=None, volume=None, distance_ft=None, mentioned_targets=None, language=None, visual_only_usernames=None, narrative=None):
        targets = unique_entities(targets or [])
        mentioned_targets = unique_entities(mentioned_targets or [])
        return {
            'entity_id': entity.entity_uid,
            'speaker_name': entity_label(entity),
            'message': message,
            'narrative': [str(entry).strip() for entry in (narrative or []) if str(entry).strip()],
            'language': (language or 'common').lower(),
            'targets': [target.entity_uid for target in targets],
            'target_names': [entity_label(target) for target in targets],
            'mentioned_targets': [target.entity_uid for target in mentioned_targets],
            'mentioned_handles': [mention_handle_for(target) for target in mentioned_targets],
            'volume': normalize_speech_mode(mode=volume, distance_ft=distance_ft),
            'distance_ft': speech_distance_for(mode=volume, distance_ft=distance_ft),
            'visual_only_usernames': [str(username).lower() for username in (visual_only_usernames or []) if username],
        }

    def conversation_listener_for_username(self, username):
        try:
            listener = self.current_game.get_pov_entity_for_user(username)
        except Exception:
            listener = None
        if listener is not None:
            return listener

        try:
            controlled_entities = self.entities_controlled_by(username)
        except Exception:
            controlled_entities = []
        return controlled_entities[0] if controlled_entities else None

    def listener_understands_language(self, listener, language):
        if listener is None:
            return False
        normalized_language = str(language or 'common').strip().lower()
        if normalized_language in {'animal', 'animals', 'beasts', 'beast_speech'}:
            normalized_language = 'beast'
        try:
            languages = getattr(listener, 'languages', lambda: [])() or []
        except Exception:
            languages = []
        normalized_languages = {str(item).strip().lower() for item in languages if item}

        if normalized_language == 'beast' and has_animal_communication(self.game_session, entity=listener):
            return True

        base_language = BEAST_DIALECT_TO_BASE_LANGUAGE.get(normalized_language)
        if base_language and base_language in normalized_languages:
            return True

        return normalized_language in normalized_languages

    def render_conversation_payload_for_username(self, username, source_entity, payload):
        payload_for_user = dict(payload)
        language = payload_for_user.get('language') or 'common'
        normalized_username = str(username).lower() if username else username

        if not username:
            return payload_for_user

        roles = self.roles_for_username(username)
        if roles and 'dm' in roles:
            return payload_for_user

        if username in set(self.entity_owners(source_entity)):
            return payload_for_user

        if normalized_username in set(payload_for_user.get('visual_only_usernames') or []):
            payload_for_user['message'] = 'You can see them whispering, but cannot hear the words.'
            payload_for_user['visual_only'] = True
            return payload_for_user

        listener = self.conversation_listener_for_username(username)
        if self.listener_understands_language(listener, language):
            return payload_for_user

        payload_for_user['message'] = gibberish(payload_for_user.get('message', ''), language=language)
        return payload_for_user

    def resolve_conversation_targets(self, source_entity, primary_targets=None, message=None):
        explicit_targets = []
        for entity_uid in primary_targets or []:
            target = self.current_game.get_entity_by_uid(entity_uid)
            if target is None:
                try:
                    target = self.game_session.entity_by_uid(entity_uid)
                except Exception:
                    target = None
            if target is not None:
                explicit_targets.append(target)

        try:
            battle_map = self.current_game.get_map_for_entity(source_entity)
        except Exception:
            battle_map = None
        candidate_entities = []
        if battle_map is not None:
            try:
                candidate_entities = [entity for entity in battle_map.entities if entity != source_entity]
            except Exception:
                candidate_entities = []

        mentioned_targets = resolve_mention_targets(message or '', candidate_entities)
        inferred_targets = []
        if not explicit_targets and not mentioned_targets:
            inferred_targets = resolve_named_targets(message or '', candidate_entities)

        return unique_entities(explicit_targets + mentioned_targets + inferred_targets), unique_entities(mentioned_targets)

    def select_conversation_responders(self, processed_conversations, source_entity, targeted_entities=None, latest_message=None, language='common', volume='normal'):
        targeted_entities = unique_entities(targeted_entities or [])
        eligible_receivers = unique_entities([
            receiver for receiver, _rendered_message, _directed_to in (processed_conversations or [])
            if receiver.entity_uid != source_entity.entity_uid and receiver.is_npc() and receiver.dialog
        ])

        if not eligible_receivers:
            return []

        if targeted_entities:
            targeted_uids = {target.entity_uid for target in targeted_entities}
            targeted_receivers = [receiver for receiver in eligible_receivers if receiver.entity_uid in targeted_uids]
            if targeted_receivers:
                return targeted_receivers

        llm_conversation_handler = self.llm_conversation_handler
        if len(eligible_receivers) > 1 and llm_conversation_handler is not None and hasattr(llm_conversation_handler, 'route_conversation_responders'):
            routed_receivers = llm_conversation_handler.route_conversation_responders(
                source_entity,
                eligible_receivers,
                latest_message=latest_message or '',
                targeted_entities=targeted_entities,
                language=language,
                volume=volume,
            )
            if routed_receivers is not None:
                return routed_receivers

        return eligible_receivers[:1]

    def emit_conversation_to_usernames(self, usernames, payload, source_entity=None):
        for recipient_username in usernames:
            rendered_payload = self.render_conversation_payload_for_username(recipient_username, source_entity, payload) if source_entity is not None else payload
            sids = self.current_game.username_to_sid.get(recipient_username, [])
            for sid in sids:
                self.socketio.emit('message', {'type': 'conversation', 'message': rendered_payload}, to=sid)

    def conversation_status_summary(self, entity):
        statuses = []
        try:
            statuses = list(getattr(entity, 'statuses', []) or [])
        except Exception:
            statuses = []
        return [str(status).strip().replace('_', ' ') for status in statuses if status]

    def conversation_effect_summary(self, entity):
        effect_names = []
        current_effects = getattr(entity, 'current_effects', None)
        if not callable(current_effects):
            return effect_names

        try:
            effects = current_effects() or []
        except Exception:
            effects = []

        for effect in effects:
            if isinstance(effect, dict):
                effect_name = effect.get('effect') or effect.get('name')
            else:
                effect_name = effect
            if effect_name:
                effect_names.append(str(effect_name).strip().replace('_', ' '))
        return effect_names

    def conversation_goal_summary(self, entity):
        try:
            get_goal = getattr(self.current_game, 'get_short_term_goal', None)
            if not callable(get_goal):
                return None
            goal_state = get_goal(entity)
        except Exception:
            goal_state = None

        if not isinstance(goal_state, dict):
            return None
        if goal_state.get('status') != 'active':
            return None
        goal_text = str(goal_state.get('goal') or '').strip()
        return goal_text or None

    def conversation_attitude_toward_speaker(self, receiver, speaker):
        if receiver is None or speaker is None:
            return 'unknown'

        try:
            battle = self.current_game.get_current_battle()
        except Exception:
            battle = None

        if battle is not None:
            try:
                if battle.opposing(receiver, speaker):
                    return 'hostile'
            except Exception:
                pass
            try:
                if battle.allies(receiver, speaker):
                    return 'allied'
            except Exception:
                pass

        receiver_group = getattr(receiver, 'group', None)
        speaker_group = getattr(speaker, 'group', None)
        if receiver_group and speaker_group:
            if receiver_group == speaker_group:
                return 'allied'
            try:
                if self.game_session.opposing(receiver_group, speaker_group):
                    return 'hostile'
            except Exception:
                pass
            return 'wary'

        try:
            receiver_owners = set(self.entity_owners(receiver))
            speaker_owners = set(self.entity_owners(speaker))
            if receiver_owners and speaker_owners and receiver_owners.intersection(speaker_owners):
                return 'allied'
        except Exception:
            pass

        return 'guarded'

    def conversation_pressure_summary(self, receiver):
        pressures = []

        hp = getattr(receiver, 'hp', None)
        max_hp = getattr(receiver, 'max_hp', None)
        try:
            if max_hp and hp is not None and max_hp > 0 and hp <= max(1, max_hp // 3):
                pressures.append('badly hurt')
        except Exception:
            pass

        statuses = self.conversation_status_summary(receiver)
        if statuses:
            pressures.append(f"statuses: {', '.join(statuses[:4])}")

        effects = self.conversation_effect_summary(receiver)
        if effects:
            pressures.append(f"active effects: {', '.join(effects[:3])}")

        goal_text = self.conversation_goal_summary(receiver)
        if goal_text:
            pressures.append(f"active goal: {goal_text}")

        try:
            battle = self.current_game.get_current_battle()
        except Exception:
            battle = None
        if battle is not None:
            try:
                if battle.entity_state_for(receiver) is not None:
                    pressures.append('currently in combat')
            except Exception:
                pressures.append('currently in combat')

        return '; '.join(pressures) if pressures else 'no special pressure beyond the current conversation'

    def conversation_response_prompt(self, receiver, speaker):
        target_entities = self.entity_rag_handler.get_conversation_targets(receiver, speaker=speaker)

        def _languages_for(target):
            try:
                langs = getattr(target, 'languages', lambda: [])() or []
            except Exception:
                langs = []
            return [str(lang).strip() for lang in langs if str(lang).strip()]

        target_handles = []
        for target in target_entities:
            langs = _languages_for(target)
            lang_note = f" speaks: {', '.join(langs)}" if langs else " speaks: unknown"
            target_handles.append(f"@{mention_handle_for(target)} ({entity_label(target)};{lang_note})")

        handles_text = ', '.join(target_handles) if target_handles else 'speaker'

        receiver_languages = _languages_for(receiver)
        receiver_languages_text = ', '.join(receiver_languages) if receiver_languages else 'common'

        speaker_languages = _languages_for(speaker) if speaker is not None else []
        if speaker is not None:
            speaker_label = entity_label(speaker)
            if speaker_languages:
                speaker_language_text = (
                    f"The speaker {speaker_label} understands: {', '.join(speaker_languages)}."
                )
            else:
                speaker_language_text = (
                    f"The speaker {speaker_label}'s known languages are unknown to you."
                )
        else:
            speaker_language_text = "No specific speaker is addressing you."

        shared_with_speaker = sorted(
            {lang.lower() for lang in receiver_languages}
            & {lang.lower() for lang in speaker_languages}
        )
        if shared_with_speaker:
            shared_text = ', '.join(shared_with_speaker)
        else:
            shared_text = 'none in common'

        stance_text = self.conversation_attitude_toward_speaker(receiver, speaker)
        pressure_text = self.conversation_pressure_summary(receiver)
        gear_text = format_entity_gear_for_conversation(receiver, self.game_session)
        return (
            "\n\nConversation response rules:\n"
            "- You may choose not to speak. If you do not want to respond, output exactly [NO_RESPONSE].\n"
            "- If you do speak, stay in character and return only optional control tags plus the spoken line.\n"
            "- Keep spoken dialogue as speech only. Do not mix narration into the spoken line.\n"
            "- If you want to include third-person storytelling, stage direction, or internal/emotive scene description, put it in one or more tags like [ASIDE: ...] after the spoken line.\n"
            "- Any [ASIDE: ...] content must be third person only. Do not use first-person narration in asides.\n"
            "- Do not reveal private mental judgments a listener could not directly observe (for example, trustworthiness verdicts). Ask for a social check with [REQUEST_CHECK: skill=persuasion, target=speaker] or [REQUEST_CHECK: skill=intimidation, target=speaker] instead.\n"
            "- You may explicitly refuse to answer, stonewall, deflect, demand proof, threaten the speaker, or tell them to leave if that fits your background, alignment, attitude, current danger, injuries, fear, active effects, duties, or goals. If you refuse out loud, say so in character; use [NO_RESPONSE] only when you stay completely silent.\n"
            "- If someone else was clearly addressed, another speaker already answered, or the latest line is only an acknowledgement, prefer [NO_RESPONSE].\n"
            "- Do not repeat the same warning or biography if you already said it and nothing materially changed. Prefer [NO_RESPONSE] instead.\n"
            "- You may direct your speech with [TO: speaker], [TO: @handle], [TO: @handle1, @handle2], or [TO: all].\n"
            "- You may choose loudness with [VOLUME: whisper], [VOLUME: normal], or [VOLUME: shout]. If omitted, the server will choose the quietest volume that reaches your chosen listeners.\n"
            "- You may speak a different language with [in <language>]. Pick a language your intended listeners actually understand. If a listener does not share your current language, switch to a common tongue you both know (typically [in common]) so they can reply, unless you are deliberately keeping them out of the conversation.\n"
            "- You may move toward someone or something with [APPROACH: target=@handle, distance=5]. This moves up to one full out-of-combat move.\n"
            "- You may use an object with [INTERACT: target=<name or @handle>, action=<interaction>].\n"
            "- You may offer an item with [OFFER_ITEM: item=<item_slug>, target=speaker|@handle]. This creates an Accept Item Yes/No prompt for the target.\n"
            "- You may privately assess whether someone seems truthful with [INSIGHT: target=speaker] or [INSIGHT: target=@handle]. The server will roll insight, use DM-only context, and regenerate your reply with the result.\n"
            "- You may ask someone to make a social check with [REQUEST_CHECK: skill=persuasion, target=speaker] or [REQUEST_CHECK: skill=intimidation, target=@handle]. This is logged to the relevant players.\n"
            "- You may create a persistent short-term autonomous task with [SET_GOAL: short description].\n"
            "- During autonomous follow-up you may end that task with [GOAL_COMPLETE] or [GOAL_GIVE_UP].\n"
            "- Only describe wielding, drawing, brandishing, or threatening with weapons and items listed under your gear below. Do not invent equipment.\n"
            f"- Current stance toward the speaker: {stance_text}.\n"
            f"- Current pressures and circumstances: {pressure_text}.\n"
            f"- Languages you ({entity_label(receiver)}) speak: {receiver_languages_text}.\n"
            f"- {speaker_language_text}\n"
            f"- Languages you share with the speaker: {shared_text}.\n"
            f"- Nearby handles you can address right now: {handles_text}.\n"
            f"\nYour gear and inventory (authoritative; do not contradict):\n{gear_text}\n"
        )

    def conversation_recipient_usernames(self, entity, include_requester=True):
        recipients = set(self.entity_owners(entity))

        if include_requester:
            requester = session.get('username')
            if requester:
                recipients.add(requester)

        for login in self.logins:
            roles = login.get('role') or []
            if 'dm' in roles and login.get('name'):
                recipients.add(login['name'].lower())

        return recipients

    def effective_talk_volume(self, message, requested_volume=None, requested_distance_ft=None):
        normalized_volume = normalize_speech_mode(mode=requested_volume, distance_ft=requested_distance_ft)
        if normalized_volume == 'normal' and '!' in (message or ''):
            normalized_volume = 'shout'
        return normalized_volume

    def dialog_history_response(self, entity_id, entity_pov_id=None):
        if not entity_id:
            return {'error': 'Entity ID is required'}, 400

        entity = self.current_game.get_entity_by_uid(entity_id)
        if not entity:
            return {'error': 'Entity not found'}, 404

        if entity_pov_id:
            entity_pov = self.current_game.get_entity_by_uid(entity_pov_id)
            history = entity.conversation_history(entity_pov)
            return {
                'success': True,
                'history': history,
                'entity_id': entity_id,
                'entity_name': entity.label(),
                'entity_pov': entity_pov.entity_uid,
            }, 200

        return {
            'success': True,
            'history': [],
            'entity_id': entity_id,
            'entity_name': entity.label(),
            'entity_pov': False,
        }, 200

    # ── Journal chat commands ──────────────────────────────────────────
    def _emit_dm_private_message(self, speaker, message_text, extra=None):
        """Send a private DM-voiced message to the speaker (and DMs)."""
        payload = {
            'entity_id': None,
            'speaker_name': 'Dungeon Master',
            'message': message_text,
            'narrative': [],
            'language': 'common',
            'targets': [getattr(speaker, 'entity_uid', None)],
            'target_names': [entity_label(speaker)] if speaker is not None else [],
            'mentioned_targets': [],
            'mentioned_handles': [],
            'volume': 'normal',
            'distance_ft': 0,
            'visual_only_usernames': [],
            'system': True,
        }
        if isinstance(extra, dict):
            payload.update(extra)
        try:
            usernames = self.entity_audience_usernames([speaker], include_dm=True)
            self.emit_conversation_to_usernames(usernames, payload, source_entity=None)
        except Exception:
            pass
        return payload

    def _handle_journal_chat_command(self, speaker, raw_message):
        """Parse and execute a /journal slash command from local chat.

        Returns ``(dict, 200)`` so callers can short-circuit ``talk``.
        """
        # Strip leading "/journal" then read sub-command + remainder.
        body = raw_message[len('/journal'):].strip()
        if not body:
            sub = 'help'
            arg = ''
        else:
            parts = body.split(None, 1)
            sub = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ''

        if not hasattr(speaker, 'add_journal_entry'):
            self._emit_dm_private_message(
                speaker,
                "Only player characters can keep a journal.",
            )
            return {'success': True, 'journal': 'unsupported'}, 200

        if sub in ('add', 'note', 'log'):
            if not arg:
                self._emit_dm_private_message(
                    speaker,
                    "Usage: /journal add <your note>",
                )
                return {'success': True, 'journal': 'usage'}, 200
            entry = speaker.add_journal_entry(arg, kind='chat', source='chat')
            if entry:
                db = getattr(self.current_game, 'campaign_log_db', None)
                if db is not None:
                    try:
                        db.append_journal_entry(speaker.entity_uid, entry)
                    except Exception as exc:
                        self.logger.debug(f"Campaign journal log skipped: {exc}")
            self._emit_dm_private_message(
                speaker,
                f"Journal entry recorded ({len(speaker.journal)} total).",
                extra={'journal_action': 'added', 'journal_entry': entry},
            )
            return {'success': True, 'journal': 'added', 'entry': entry}, 200

        if sub in ('search', 'find'):
            if not arg:
                self._emit_dm_private_message(
                    speaker,
                    "Usage: /journal search <query>",
                )
                return {'success': True, 'journal': 'usage'}, 200
            results = speaker.search_journal(query=arg)
            if not results:
                self._emit_dm_private_message(
                    speaker,
                    f"No journal entries match \"{arg}\".",
                )
                return {'success': True, 'journal': 'empty'}, 200
            recent = results[-5:]
            preview_lines = [
                f"• {self._format_journal_preview(e)}" for e in reversed(recent)
            ]
            preview = '\n'.join(preview_lines)
            extra_count = max(0, len(results) - len(recent))
            suffix = f"\n(+{extra_count} more)" if extra_count else ''
            self._emit_dm_private_message(
                speaker,
                f"Found {len(results)} journal entries matching \"{arg}\":\n{preview}{suffix}",
                extra={'journal_action': 'search', 'journal_results': results},
            )
            return {'success': True, 'journal': 'search', 'results': results}, 200

        if sub in ('list', 'recent', 'show'):
            try:
                limit = int(arg) if arg else 5
            except ValueError:
                limit = 5
            limit = max(1, min(limit, 25))
            results = speaker.search_journal(limit=limit)
            if not results:
                self._emit_dm_private_message(
                    speaker,
                    "Your journal is empty.",
                )
                return {'success': True, 'journal': 'empty'}, 200
            preview = '\n'.join(
                f"• {self._format_journal_preview(e)}" for e in reversed(results)
            )
            self._emit_dm_private_message(
                speaker,
                f"Last {len(results)} journal entries:\n{preview}",
                extra={'journal_action': 'list', 'journal_results': results},
            )
            return {'success': True, 'journal': 'list', 'results': results}, 200

        # Help / unknown
        self._emit_dm_private_message(
            speaker,
            "Journal commands: /journal add <text>, /journal search <query>, /journal list [N]",
        )
        return {'success': True, 'journal': 'help'}, 200

    @staticmethod
    def _format_journal_preview(entry):
        text = (entry.get('text') or '').strip().replace('\n', ' ')
        if len(text) > 140:
            text = text[:137] + '...'
        ts = (entry.get('ts') or '')[:19].replace('T', ' ')
        kind = entry.get('kind') or 'note'
        return f"[{kind} {ts}] {text}"

    # ── Journal chat commands ──────────────────────────────────────────
    def _emit_dm_private_message(self, speaker, message_text, extra=None):
        """Send a private DM-voiced message to the speaker (and DMs)."""
        payload = {
            'entity_id': None,
            'speaker_name': 'Dungeon Master',
            'message': message_text,
            'narrative': [],
            'language': 'common',
            'targets': [getattr(speaker, 'entity_uid', None)],
            'target_names': [entity_label(speaker)] if speaker is not None else [],
            'mentioned_targets': [],
            'mentioned_handles': [],
            'volume': 'normal',
            'distance_ft': 0,
            'visual_only_usernames': [],
            'system': True,
        }
        if isinstance(extra, dict):
            payload.update(extra)
        try:
            usernames = self.entity_audience_usernames([speaker], include_dm=True)
            self.emit_conversation_to_usernames(usernames, payload, source_entity=None)
        except Exception:
            pass
        return payload

    def _handle_journal_chat_command(self, speaker, raw_message):
        """Parse and execute a /journal slash command from local chat.

        Returns ``(dict, 200)`` so callers can short-circuit ``talk``.
        """
        # Strip leading "/journal" then read sub-command + remainder.
        body = raw_message[len('/journal'):].strip()
        if not body:
            sub = 'help'
            arg = ''
        else:
            parts = body.split(None, 1)
            sub = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ''

        if not hasattr(speaker, 'add_journal_entry'):
            self._emit_dm_private_message(
                speaker,
                "Only player characters can keep a journal.",
            )
            return {'success': True, 'journal': 'unsupported'}, 200

        if sub in ('add', 'note', 'log'):
            if not arg:
                self._emit_dm_private_message(
                    speaker,
                    "Usage: /journal add <your note>",
                )
                return {'success': True, 'journal': 'usage'}, 200
            entry = speaker.add_journal_entry(arg, kind='chat', source='chat')
            if entry:
                db = getattr(self.current_game, 'campaign_log_db', None)
                if db is not None:
                    try:
                        db.append_journal_entry(speaker.entity_uid, entry)
                    except Exception as exc:
                        self.logger.debug(f"Campaign journal log skipped: {exc}")
            self._emit_dm_private_message(
                speaker,
                f"Journal entry recorded ({len(speaker.journal)} total).",
                extra={'journal_action': 'added', 'journal_entry': entry},
            )
            return {'success': True, 'journal': 'added', 'entry': entry}, 200

        if sub in ('search', 'find'):
            if not arg:
                self._emit_dm_private_message(
                    speaker,
                    "Usage: /journal search <query>",
                )
                return {'success': True, 'journal': 'usage'}, 200
            results = speaker.search_journal(query=arg)
            if not results:
                self._emit_dm_private_message(
                    speaker,
                    f"No journal entries match \"{arg}\".",
                )
                return {'success': True, 'journal': 'empty'}, 200
            recent = results[-5:]
            preview_lines = [
                f"• {self._format_journal_preview(e)}" for e in reversed(recent)
            ]
            preview = '\n'.join(preview_lines)
            extra_count = max(0, len(results) - len(recent))
            suffix = f"\n(+{extra_count} more)" if extra_count else ''
            self._emit_dm_private_message(
                speaker,
                f"Found {len(results)} journal entries matching \"{arg}\":\n{preview}{suffix}",
                extra={'journal_action': 'search', 'journal_results': results},
            )
            return {'success': True, 'journal': 'search', 'results': results}, 200

        if sub in ('list', 'recent', 'show'):
            try:
                limit = int(arg) if arg else 5
            except ValueError:
                limit = 5
            limit = max(1, min(limit, 25))
            results = speaker.search_journal(limit=limit)
            if not results:
                self._emit_dm_private_message(
                    speaker,
                    "Your journal is empty.",
                )
                return {'success': True, 'journal': 'empty'}, 200
            preview = '\n'.join(
                f"• {self._format_journal_preview(e)}" for e in reversed(results)
            )
            self._emit_dm_private_message(
                speaker,
                f"Last {len(results)} journal entries:\n{preview}",
                extra={'journal_action': 'list', 'journal_results': results},
            )
            return {'success': True, 'journal': 'list', 'results': results}, 200

        # Help / unknown
        self._emit_dm_private_message(
            speaker,
            "Journal commands: /journal add <text>, /journal search <query>, /journal list [N]",
        )
        return {'success': True, 'journal': 'help'}, 200

    @staticmethod
    def _format_journal_preview(entry):
        text = (entry.get('text') or '').strip().replace('\n', ' ')
        if len(text) > 140:
            text = text[:137] + '...'
        ts = (entry.get('ts') or '')[:19].replace('T', ' ')
        kind = entry.get('kind') or 'note'
        return f"[{kind} {ts}] {text}"

    def _emit_player_insight_payload(self, speaker, message_text, target=None,
                                     roll_total=None, dc=None, assessment=None,
                                     reason=None, vague=False, clarification=None,
                                     purpose=None):
        """Send a private insight-check result/clarification to the player + DM only."""
        payload = {
            'entity_id': getattr(target, 'entity_uid', None),
            'speaker_name': 'Dungeon Master',
            'message': message_text,
            'narrative': [],
            'language': 'common',
            'targets': [getattr(speaker, 'entity_uid', None)],
            'target_names': [entity_label(speaker)] if speaker is not None else [],
            'mentioned_targets': [],
            'mentioned_handles': [],
            'volume': 'normal',
            'distance_ft': 0,
            'visual_only_usernames': [],
            'system': True,
            'insight_check': {
                'observer': entity_label(speaker) if speaker is not None else None,
                'target': entity_label(target) if target is not None else None,
                'roll_total': roll_total,
                'dc': dc,
                'assessment': assessment,
                'reason': reason,
                'vague': bool(vague),
                'clarification': clarification,
                'purpose': purpose,
            },
        }
        usernames = self.entity_audience_usernames([speaker], include_dm=True)
        self.emit_conversation_to_usernames(usernames, payload, source_entity=None)
        return payload

    def _resolve_insight_target(self, speaker, target_spec, explicit_targets, mentioned_targets):
        """Pick the NPC the player wants to read."""
        # 1) explicit/mentioned NPC targets (NPCs only, ignore the speaker)
        for candidate in list(mentioned_targets or []) + list(explicit_targets or []):
            if candidate is None or candidate == speaker:
                continue
            if hasattr(candidate, 'is_npc') and candidate.is_npc():
                return candidate

        # 2) explicit textual target via "insight check on <name>"
        if target_spec:
            rag_handler = self.entity_rag_handler
            if rag_handler is not None and hasattr(rag_handler, 'resolve_named_target'):
                try:
                    candidate = rag_handler.resolve_named_target(speaker, target_spec, speaker=speaker)
                except Exception:
                    candidate = None
                if candidate is not None and candidate != speaker and getattr(candidate, 'is_npc', lambda: False)():
                    return candidate

        # 3) fall back to the most recent NPC that spoke to the player
        memory = list(getattr(speaker, 'memory_buffer', []) or [])
        for entry in reversed(memory):
            source = entry.get('source') if isinstance(entry, dict) else None
            if source is None or source == speaker:
                continue
            if getattr(source, 'is_npc', lambda: False)():
                return source

        return None

    def _latest_npc_statement(self, speaker, target):
        """Return the most recent statement made by ``target`` to ``speaker``."""
        memory = list(getattr(speaker, 'memory_buffer', []) or [])
        for entry in reversed(memory):
            if not isinstance(entry, dict):
                continue
            source = entry.get('source')
            if source is target:
                text = entry.get('message') or ''
                if str(text).strip():
                    return str(text).strip()
        return ''

    def handle_player_insight_request(self, speaker, message,
                                      explicit_targets=None,
                                      mentioned_targets=None):
        """Resolve a player's "Insight Check" request privately.

        Returns the standard ``(dict, status)`` tuple expected by ``/talk``.
        The player's message is **not** forwarded to NPCs.
        """
        target_spec, purpose = parse_player_insight_request(message)
        target = self._resolve_insight_target(speaker, target_spec,
                                              explicit_targets or [],
                                              mentioned_targets or [])

        if target is None:
            self._emit_player_insight_payload(
                speaker,
                "Whom would you like to read? Try 'Insight check on @<name> about <topic>'.",
                vague=True,
                clarification='missing_target',
            )
            return {'success': True, 'insight': 'needs_target'}, 200

        # Look up something concrete to read. If the player did not give a
        # purpose and the NPC has not actually said anything yet, ask them to
        # be more specific instead of rolling.
        latest_statement = self._latest_npc_statement(speaker, target)
        if not purpose and not latest_statement:
            self._emit_player_insight_payload(
                speaker,
                f"What about {entity_label(target)} are you trying to read? "
                "(e.g. 'are they lying about the missing caravan?')",
                target=target,
                vague=True,
                clarification='missing_purpose',
            )
            return {'success': True, 'insight': 'needs_purpose'}, 200

        statement_for_check = purpose or latest_statement
        description = (
            f"Insight check on {entity_label(target)}"
            + (f" about: {purpose}" if purpose else '')
        )

        # Roll the player's Insight check.
        try:
            roll = speaker.insight_check(description=description)
        except Exception as exc:
            self.logger.error(f"Insight check failed for {entity_label(speaker)}: {exc}")
            self._emit_player_insight_payload(
                speaker,
                "Your insight check could not be completed.",
                target=target,
                vague=True,
                clarification='roll_failed',
                purpose=purpose,
            )
            return {'success': False, 'error': 'insight_roll_failed'}, 500

        roll_total = None
        try:
            roll_total = roll.result()
        except Exception:
            roll_total = None

        # Re-use the existing DM-LLM adjudicator that powers NPC-side insight
        # so the verdict honours backstory + recent conversation context.
        rag_handler = self.entity_rag_handler
        llm_conversation_handler = self.llm_conversation_handler
        assessment = 'uncertain'
        reason = 'There is not enough reliable evidence to be sure.'
        if rag_handler is not None and llm_conversation_handler is not None \
                and hasattr(rag_handler, '_evaluate_insight_assessment'):
            try:
                verdict = rag_handler._evaluate_insight_assessment(
                    observer=speaker,
                    target=target,
                    statement=statement_for_check,
                    roll=roll,
                    llm_conversation_handler=llm_conversation_handler,
                )
            except Exception as exc:
                self.logger.error(f"Insight adjudication failed: {exc}")
                verdict = None
            if isinstance(verdict, dict):
                assessment = verdict.get('assessment', assessment)
                reason = verdict.get('reason', reason)

        verdict_label = {
            'truthful': 'They appear to be telling the truth.',
            'lie': 'You sense deception.',
            'uncertain': 'You cannot tell for sure.',
        }.get(assessment, 'You cannot tell for sure.')

        try:
            roll_repr = str(roll) if roll is not None else ''
        except Exception:
            roll_repr = ''
        if roll_repr and roll_total is not None:
            roll_text = f"Insight check ({roll_repr}) = {roll_total}"
        elif roll_total is not None:
            roll_text = f"Insight check: {roll_total}"
        else:
            roll_text = "Insight check"
        message_text = (
            f"{roll_text} on {entity_label(target)}. {verdict_label} {reason}"
        )

        self._emit_player_insight_payload(
            speaker,
            message_text,
            target=target,
            roll_total=roll_total,
            assessment=assessment,
            reason=reason,
            purpose=purpose,
        )

        # Log the social check restricted to participating entities. Match the
        # roll-breakdown style used by the rest of the combat log (e.g.
        # "1d20(15)+6 = 21") so DMs can see how the result was reached.
        if rag_handler is not None and hasattr(rag_handler, '_log_social_check'):
            try:
                roll_breakdown = ''
                try:
                    roll_str = str(roll) if roll is not None else ''
                except Exception:
                    roll_str = ''
                if roll_str and roll_total is not None:
                    roll_breakdown = f"{roll_str} = {roll_total}"
                elif roll_total is not None:
                    roll_breakdown = f"total {roll_total}"
                rag_handler._log_social_check(
                    f"{entity_label(speaker)} attempts an Insight check on "
                    f"{entity_label(target)} ({roll_breakdown}): {assessment}.",
                    entities=[speaker, target],
                )
            except Exception:
                pass

        return {
            'success': True,
            'insight': {
                'target': getattr(target, 'entity_uid', None),
                'roll_total': roll_total,
                'assessment': assessment,
                'reason': reason,
            },
        }, 200

    def _persist_conversation_line(
        self,
        speaker,
        message,
        *,
        targets=None,
        volume=None,
        language=None,
        narrative=None,
        username=None,
    ):
        db = getattr(self.current_game, 'campaign_log_db', None)
        if db is None or not message:
            return
        target_labels = []
        for target in targets or []:
            try:
                target_labels.append(entity_label(target))
            except Exception:
                target_labels.append(getattr(target, 'entity_uid', str(target)))
        try:
            db.append_conversation(
                speaker_uid=getattr(speaker, 'entity_uid', None),
                speaker_label=entity_label(speaker),
                message=message,
                targets=[getattr(t, 'entity_uid', None) for t in (targets or [])],
                target_labels=target_labels,
                volume=volume,
                language=language,
                username=username,
                narrative=narrative,
            )
        except Exception as exc:
            self.logger.debug(f"Campaign conversation log skipped: {exc}")

    def talk_response(self, data, conversation_system_prompt):
        entity_id = data.get('entity_id')
        message = data.get('message')
        language = data.get('language')
        primary_targets = data.get('targets', [])
        volume = self.effective_talk_volume(message, requested_volume=data.get('volume'), requested_distance_ft=data.get('distance_ft'))
        distance_ft = speech_distance_for(mode=volume, distance_ft=data.get('distance_ft'))
        if not entity_id or not message:
            return {'error': 'Entity ID and message are required'}, 400

        entity = self.current_game.get_entity_by_uid(entity_id)
        if not entity:
            return {'error': 'Entity not found'}, 404

        if isinstance(entity, PlayerCharacter):
            self.current_game.increment_game_time(entity)

        # Slash-command shortcut: PCs can ask the DM to manage their personal
        # journal directly from local chat. These commands never broadcast to
        # NPCs or other players. Supported forms:
        #   /journal add <text>      → append a note
        #   /journal search <query>  → return matching entries (private)
        #   /journal list [N]        → return the last N entries (default 5)
        if isinstance(entity, PlayerCharacter) and isinstance(message, str):
            stripped = message.strip()
            if stripped.lower().startswith('/journal'):
                return self._handle_journal_chat_command(entity, stripped)

        entity_targets, mentioned_targets = self.resolve_conversation_targets(entity, primary_targets=primary_targets, message=message)

        # Player-side meta requests (e.g. "Insight Check on @Garrick about his
        # story") are handled privately and never broadcast to NPCs.
        if (isinstance(entity, PlayerCharacter)
                and is_player_insight_request(message)):
            return self.handle_player_insight_request(
                entity,
                message,
                explicit_targets=entity_targets,
                mentioned_targets=mentioned_targets,
            )

        try:
            processed_conversations = entity.send_conversation(
                message,
                distance_ft=distance_ft,
                targets=entity_targets,
                language=language,
                volume=volume,
            )
        except TypeError:
            processed_conversations = entity.send_conversation(
                message,
                distance_ft=distance_ft,
                targets=entity_targets,
                language=language,
            )

        delivered_targets = unique_entities([
            receiver for receiver, _processed_message, directed_to in processed_conversations
            if receiver in (directed_to or [])
        ])
        speaker_payload = self.conversation_payload(
            entity,
            message,
            targets=delivered_targets,
            volume=volume,
            distance_ft=distance_ft,
            mentioned_targets=mentioned_targets,
            language=language,
        )
        speaker_audience = self.conversation_audience_usernames(entity, processed_conversations, targets=delivered_targets)
        visual_whisper_usernames = set()
        if speaker_payload['volume'] == 'whisper':
            visual_whisper_usernames = self.conversation_visible_whisper_usernames(entity, audible_usernames=speaker_audience)
            if visual_whisper_usernames:
                speaker_payload['visual_only_usernames'] = sorted(visual_whisper_usernames)
        self.emit_conversation_to_usernames(speaker_audience | visual_whisper_usernames, speaker_payload, source_entity=entity)
        self._persist_conversation_line(
            entity,
            message,
            targets=delivered_targets,
            volume=volume,
            language=language,
            username=session.get('username'),
        )

        # Bridge the spoken message into the battle event pipeline so any
        # readied "on_command" actions (e.g. familiar drinks a healing potion
        # when its master shouts "drink!") get a chance to fire. We pass the
        # raw message text plus the explicit recipient list so triggers can
        # match on phrase substrings.
        try:
            battle = self.current_game.get_current_battle()
        except Exception:
            battle = None
        if battle is not None and getattr(battle, 'started', False) \
                and getattr(battle, 'readied_actions', None):
            try:
                battle.trigger_event('on_command', entity, {
                    'target': entity,
                    'message': message,
                    'targets': list(delivered_targets or []),
                    'volume': volume,
                })
            except Exception:
                # Conversation must never be blocked by a downstream
                # readied-action error.
                pass

        eligible_receivers = self.select_conversation_responders(
            processed_conversations,
            entity,
            targeted_entities=delivered_targets,
            latest_message=message,
            language=language,
            volume=volume,
        )

        llm_conversation_handler = self.llm_conversation_handler
        for receiver in eligible_receivers:
            attributes = receiver.ability_scores
            attributes_str = "\n".join([f"{key}: {value}" for key, value in attributes.items()])
            gear_summary = format_entity_gear_for_conversation(receiver, self.game_session)
            system_prompt = conversation_system_prompt.format(
                backstory=receiver.backstory(),
                name=receiver.label(),
                attributes=attributes_str,
                alignment=receiver.alignment().replace("_", " "),
                languages=", ".join(receiver.languages()),
                gear=gear_summary,
            )
            system_prompt += self.conversation_response_prompt(receiver, entity)
            llm_conversation_handler.create_conversation(receiver.entity_uid, system_prompt)
            try:
                llm_conversation_handler.conversations[receiver.entity_uid]['system_prompt'] = system_prompt
            except Exception:
                pass
            llm_conversation_handler.update_conversation_history(receiver.entity_uid, receiver.conversation_buffer)

            self.logger.info(f"generating response for {receiver.label()}")
            response = llm_conversation_handler.generate_response(receiver.entity_uid)
            self.logger.info(f"response for {receiver.label()}: {response}")
            reply_plan = self.entity_rag_handler.build_conversation_response_plan(
                response,
                receiver,
                entity,
                llm_conversation_handler,
            )
            if reply_plan['skip']:
                self.entity_rag_handler.apply_response_plan_directives(reply_plan, receiver, speaker=entity)
                continue

            reply_distance_ft = speech_distance_for(mode=reply_plan['volume'])
            try:
                response_conversations = receiver.send_conversation(
                    reply_plan['message'],
                    distance_ft=reply_distance_ft,
                    targets=reply_plan['targets'],
                    language=reply_plan['language'],
                    volume=reply_plan['volume'],
                )
            except TypeError:
                response_conversations = receiver.send_conversation(
                    reply_plan['message'],
                    distance_ft=reply_distance_ft,
                    targets=reply_plan['targets'],
                    language=reply_plan['language'],
                )
            recipient_usernames = self.conversation_audience_usernames(receiver, response_conversations, targets=reply_plan['targets'])
            visual_whisper_usernames = set()
            if reply_plan['volume'] == 'whisper':
                visual_whisper_usernames = self.conversation_visible_whisper_usernames(receiver, audible_usernames=recipient_usernames)
            self.emit_conversation_to_usernames(
                recipient_usernames | visual_whisper_usernames,
                self.conversation_payload(
                    receiver,
                    reply_plan['message'],
                    targets=reply_plan['targets'],
                    volume=reply_plan['volume'],
                    distance_ft=reply_distance_ft,
                    language=reply_plan['language'],
                    visual_only_usernames=visual_whisper_usernames,
                    narrative=reply_plan.get('narrative') or [],
                ),
                source_entity=receiver,
            )
            self._persist_conversation_line(
                receiver,
                reply_plan['message'],
                targets=reply_plan['targets'],
                volume=reply_plan['volume'],
                language=reply_plan['language'],
                narrative=reply_plan.get('narrative') or [],
            )
            self.entity_rag_handler.apply_response_plan_directives(reply_plan, receiver, speaker=entity)

        return {
            'success': True,
            'resolved_target_ids': [target.entity_uid for target in delivered_targets],
            'mentioned_target_ids': [target.entity_uid for target in mentioned_targets],
            'volume': volume,
            'distance_ft': distance_ft,
        }, 200

    def conversation_presence_response(self, entity_id=None, username=None, volume=None, range_value=None):
        if not entity_id and username:
            current_pov = self.current_game.get_pov_entity_for_user(username)
            entity_id = getattr(current_pov, 'entity_uid', None)

        if not entity_id:
            return {'error': 'Entity ID is required'}, 400

        cache_key = (entity_id, volume, range_value)
        now = time.monotonic()
        cached = self._conversation_presence_cache.get(cache_key)
        if cached is not None:
            age = now - cached['_ts']
            if age < self._CONVERSANCE_PRESENCE_CACHE_TTL:
                cached_result = cached.copy()
                del cached_result['_ts']
                return cached_result, 200

        entity = self.current_game.get_entity_by_uid(entity_id)
        if not entity:
            return {'error': 'Entity not found'}, 404

        normalized_volume = normalize_speech_mode(mode=volume, distance_ft=range_value)
        distance_ft = speech_distance_for(mode=normalized_volume, distance_ft=range_value)
        audible = self.entity_rag_handler.get_nearby_entities(entity, distance_ft, volume=normalized_volume, include_extended=True)

        reachable_entities = [entry for entry in audible if entry.get('reachable_now')]
        louder_voice_entities = [entry for entry in audible if entry.get('status') == 'requires_louder_voice']
        heard_only_entities = [entry for entry in audible if entry.get('status') == 'too_far']

        result = {
            'speaker': {
                'id': entity.entity_uid,
                'name': entity_label(entity),
                'languages': entity.languages() or ['common'],
            },
            'volume': normalized_volume,
            'distance_ft': distance_ft,
            'entities': audible,
            'reachable_entities': reachable_entities,
            'requires_louder_voice_entities': louder_voice_entities,
            'heard_only_entities': heard_only_entities,
        }

        self._conversation_presence_cache[cache_key] = result.copy()
        self._conversation_presence_cache[cache_key]['_ts'] = now
        return result, 200

    def nearby_entities_response(self, entity_id, volume=None, range_value=None):
        normalized_volume = normalize_speech_mode(mode=volume, distance_ft=range_value)
        range_ft = speech_distance_for(mode=normalized_volume, distance_ft=range_value)

        if not entity_id:
            return {'error': 'Entity ID is required'}, 400

        entity = self.current_game.get_entity_by_uid(entity_id)
        if not entity:
            return {'error': 'Entity not found'}, 404

        response = self.entity_rag_handler.get_nearby_entities(entity, range_ft, volume=normalized_volume)
        return {'entities': response}, 200


def register_conversation_routes(app, conversation_service, conversation_system_prompt_getter):
    def dialog_history():
        payload, status_code = conversation_service.dialog_history_response(
            request.args.get('entity_id'),
            request.args.get('entity_pov', None),
        )
        return jsonify(payload), status_code

    def talk():
        payload, status_code = conversation_service.talk_response(
            request.get_json() or {},
            conversation_system_prompt_getter(),
        )
        return jsonify(payload), status_code

    def conversation_presence():
        payload, status_code = conversation_service.conversation_presence_response(
            entity_id=request.args.get('entity_id'),
            username=session.get('username'),
            volume=request.args.get('volume'),
            range_value=request.args.get('range'),
        )
        return jsonify(payload), status_code

    def nearby_entities():
        payload, status_code = conversation_service.nearby_entities_response(
            entity_id=request.args.get('entity_id'),
            volume=request.args.get('volume'),
            range_value=request.args.get('range'),
        )
        return jsonify(payload), status_code

    app.add_url_rule('/dialog_history', endpoint='dialog_history', view_func=dialog_history, methods=['GET'])
    app.add_url_rule('/talk', endpoint='talk', view_func=talk, methods=['POST'])
    app.add_url_rule('/conversation_presence', endpoint='conversation_presence', view_func=conversation_presence, methods=['GET'])
    app.add_url_rule('/nearby_entities', endpoint='nearby_entities', view_func=nearby_entities, methods=['GET'])
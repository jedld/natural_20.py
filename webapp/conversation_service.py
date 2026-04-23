from flask import jsonify, request, session

from natural20.player_character import PlayerCharacter
from natural20.utils.conversation import (
    entity_label,
    mention_handle_for,
    normalize_speech_mode,
    resolve_named_targets,
    resolve_mention_targets,
    speech_distance_for,
    unique_entities,
)
from natural20.utils.gibberish import gibberish


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
        try:
            languages = getattr(listener, 'languages', lambda: [])() or []
        except Exception:
            languages = []
        normalized_languages = {str(item).strip().lower() for item in languages if item}
        return str(language or 'common').strip().lower() in normalized_languages

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
            "- You may privately assess whether someone seems truthful with [INSIGHT: target=speaker] or [INSIGHT: target=@handle]. The server will roll insight, use DM-only context, and regenerate your reply with the result.\n"
            "- You may ask someone to make a social check with [REQUEST_CHECK: skill=persuasion, target=speaker] or [REQUEST_CHECK: skill=intimidation, target=@handle]. This is logged to the relevant players.\n"
            "- You may create a persistent short-term autonomous task with [SET_GOAL: short description].\n"
            "- During autonomous follow-up you may end that task with [GOAL_COMPLETE] or [GOAL_GIVE_UP].\n"
            f"- Current stance toward the speaker: {stance_text}.\n"
            f"- Current pressures and circumstances: {pressure_text}.\n"
            f"- Languages you ({entity_label(receiver)}) speak: {receiver_languages_text}.\n"
            f"- {speaker_language_text}\n"
            f"- Languages you share with the speaker: {shared_text}.\n"
            f"- Nearby handles you can address right now: {handles_text}.\n"
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

        entity_targets, mentioned_targets = self.resolve_conversation_targets(entity, primary_targets=primary_targets, message=message)

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
            system_prompt = conversation_system_prompt.format(
                backstory=receiver.backstory(),
                name=receiver.label(),
                attributes=attributes_str,
                alignment=receiver.alignment().replace("_", " "),
                languages=", ".join(receiver.languages()),
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

        entity = self.current_game.get_entity_by_uid(entity_id)
        if not entity:
            return {'error': 'Entity not found'}, 404

        normalized_volume = normalize_speech_mode(mode=volume, distance_ft=range_value)
        distance_ft = speech_distance_for(mode=normalized_volume, distance_ft=range_value)
        audible = self.entity_rag_handler.get_nearby_entities(entity, distance_ft, volume=normalized_volume, include_extended=True)

        reachable_entities = [entry for entry in audible if entry.get('reachable_now')]
        louder_voice_entities = [entry for entry in audible if entry.get('status') == 'requires_louder_voice']
        heard_only_entities = [entry for entry in audible if entry.get('status') == 'too_far']

        return {
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
        }, 200

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
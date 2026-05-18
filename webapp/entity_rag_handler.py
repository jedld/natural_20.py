"""
Entity RAG Handler

This module handles the Retrieval-Augmented Generation (RAG) aspects of entity conversations,
including inventory queries, observation requests, and language parsing.
"""

import re
import json
import logging
import time
from typing import List, Tuple, Dict, Any, Optional
from natural20.action import Action
from natural20.actions.interact_action import InteractAction
from natural20.actions.move_action import MoveAction
from natural20.ai.path_compute import PathCompute
from natural20.entity import Entity
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.concern.generic_event_handler import GenericEventHandler
from natural20.utils.conversation import (
    SPEECH_MODE_ORDER,
    audible_entities,
    conversation_reachability,
    entity_label,
    mention_handle_for,
    normalize_speech_mode,
    resolve_mention_targets,
    unique_entities,
)

logger = logging.getLogger('werkzeug')
CONTROL_DIRECTIVE_PATTERN = re.compile(r'\[(no_response|to|volume)(?:\s*:\s*([^\]]*))?\]', re.IGNORECASE)
ACTION_DIRECTIVE_PATTERN = re.compile(r'\[(approach|interact|request_check|set_goal|goal_complete|goal_give_up)(?:\s*:\s*([^\]]*))?\]', re.IGNORECASE)
INSIGHT_DIRECTIVE_PATTERN = re.compile(r'\[insight(?:\s*:\s*([^\]]*))?\]', re.IGNORECASE)
ASIDE_DIRECTIVE_PATTERN = re.compile(r'\[(aside|narration|stage_direction)(?:\s*:\s*([^\]]*))?\]', re.IGNORECASE)
NARRATIVE_FIRST_PERSON_SUBSTITUTIONS = [
    (re.compile(r"\bI['\u2019]m\b", re.IGNORECASE), 'they are'),
    (re.compile(r"\bI['\u2019]ve\b", re.IGNORECASE), 'they have'),
    (re.compile(r"\bI['\u2019]ll\b", re.IGNORECASE), 'they will'),
    (re.compile(r"\bI['\u2019]d\b", re.IGNORECASE), 'they would'),
    (re.compile(r"\bwe['\u2019]re\b", re.IGNORECASE), 'they are'),
    (re.compile(r"\bwe['\u2019]ve\b", re.IGNORECASE), 'they have'),
    (re.compile(r"\bwe['\u2019]ll\b", re.IGNORECASE), 'they will'),
    (re.compile(r"\bwe['\u2019]d\b", re.IGNORECASE), 'they would'),
    (re.compile(r"\bI\b", re.IGNORECASE), 'they'),
    (re.compile(r"\bme\b", re.IGNORECASE), 'them'),
    (re.compile(r"\bmy\b", re.IGNORECASE), 'their'),
    (re.compile(r"\bmine\b", re.IGNORECASE), 'theirs'),
    (re.compile(r"\bmyself\b", re.IGNORECASE), 'themself'),
    (re.compile(r"\bwe\b", re.IGNORECASE), 'they'),
    (re.compile(r"\bus\b", re.IGNORECASE), 'them'),
    (re.compile(r"\bour\b", re.IGNORECASE), 'their'),
    (re.compile(r"\bours\b", re.IGNORECASE), 'theirs'),
    (re.compile(r"\bourselves\b", re.IGNORECASE), 'themselves'),
]
NON_OBSERVABLE_TRUST_PATTERN = re.compile(
    r"\b(?:do(?:es)?\s+not\s+trust|don['\u2019]?t\s+trust|cannot\s+trust|can['\u2019]?t\s+trust|"
    r"distrusts?|mistrusts?|trusts?)\b",
    re.IGNORECASE,
)


class EntityRAGHandler:
    """
    Handles RAG (Retrieval-Augmented Generation) operations for entity conversations.
    
    This class extracts and processes special commands in entity responses that require
    real-time game state information, such as inventory queries and observation requests.
    """
    
    def __init__(self, game_session: Session, current_game):
        """
        Initialize the Entity RAG Handler.
        
        Args:
            game_session: The current game session
            current_game: The current game instance
        """
        self.game_session = game_session
        self.current_game = current_game
    
    def process_entity_response(self, response: str, receiver: Entity, speaker: Entity = None, llm_conversation_handler=None) -> Tuple[str, str]:
        """
        Process an entity response for RAG commands and return the cleaned response and language.
        
        Args:
            response: The raw response from the LLM
            receiver: The entity receiving the response
            llm_conversation_handler: The LLM conversation handler instance

        Returns:
            Tuple of (language, cleaned_response)
        """
        if llm_conversation_handler is None and speaker is not None and hasattr(speaker, 'generate_response'):
            llm_conversation_handler = speaker
            speaker = None

        plan = self.build_conversation_response_plan(
            response,
            receiver,
            llm_conversation_handler=llm_conversation_handler,
        )
        return plan['language'], plan['message']

    def parse_response_controls(self, response: str) -> Dict[str, Any]:
        controls = {
            'no_response': False,
            'target_spec': None,
            'volume': None,
            'response': response or '',
        }

        def _replace(match):
            directive = (match.group(1) or '').strip().lower()
            value = (match.group(2) or '').strip()
            if directive == 'no_response':
                controls['no_response'] = True
            elif directive == 'to' and value:
                controls['target_spec'] = value
            elif directive == 'volume' and value:
                controls['volume'] = normalize_speech_mode(mode=value)
            return ''

        controls['response'] = CONTROL_DIRECTIVE_PATTERN.sub(_replace, controls['response']).strip()
        return controls

    def get_conversation_targets(self, receiver: Entity, speaker: Entity = None) -> List[Entity]:
        candidates = []
        if speaker is not None and speaker != receiver:
            candidates.append(speaker)

        try:
            battle_map = self.current_game.get_map_for_entity(receiver)
        except Exception:
            battle_map = None

        if battle_map is not None:
            try:
                reachability = conversation_reachability(receiver, battle_map, mode='shout')
            except Exception:
                reachability = []

            for entry in reachability:
                target = entry.get('entity')
                if target is not None and target != receiver:
                    candidates.append(target)

        return unique_entities(candidates)

    def resolve_response_targets(self, receiver: Entity, speaker: Entity = None, target_spec: Optional[str] = None) -> List[Entity]:
        candidates = self.get_conversation_targets(receiver, speaker=speaker)
        if not target_spec:
            return [speaker] if speaker is not None else []

        resolved_targets = []
        mention_tokens = []
        include_all = False
        for token in re.split(r'[,;\n]+', target_spec):
            normalized = token.strip()
            if not normalized:
                continue
            lowered = normalized.lower().lstrip('@')
            if lowered in {'speaker', 'you'} and speaker is not None:
                resolved_targets.append(speaker)
            elif lowered == 'all':
                include_all = True
            else:
                mention_tokens.append(f"@{lowered}")

        if include_all:
            resolved_targets.extend(candidates)
        if mention_tokens:
            resolved_targets.extend(resolve_mention_targets(' '.join(mention_tokens), candidates))

        resolved_targets = [target for target in unique_entities(resolved_targets) if target != receiver]
        if resolved_targets:
            return resolved_targets
        return [speaker] if speaker is not None else []

    def plan_response_volume(self, receiver: Entity, targets: List[Entity], volume: Optional[str] = None) -> Tuple[Optional[str], List[Entity]]:
        if not targets:
            return None, []

        try:
            battle_map = self.current_game.get_map_for_entity(receiver)
        except Exception:
            battle_map = None

        if battle_map is None:
            return normalize_speech_mode(mode=volume), list(targets)

        if volume:
            selected_mode = normalize_speech_mode(mode=volume)
            reachability = {
                entry['entity'].entity_uid: entry
                for entry in conversation_reachability(receiver, battle_map, mode=selected_mode)
            }
            reachable_targets = [
                target for target in targets
                if reachability.get(target.entity_uid, {}).get('reachable_now')
            ]
            return (selected_mode if reachable_targets else None), reachable_targets

        reachability = {
            entry['entity'].entity_uid: entry
            for entry in conversation_reachability(receiver, battle_map, mode='whisper')
        }
        reachable_targets = []
        required_mode_index = 0
        for target in targets:
            entry = reachability.get(target.entity_uid)
            minimum_volume = entry.get('minimum_volume') if entry else None
            if minimum_volume is None:
                continue
            reachable_targets.append(target)
            required_mode_index = max(required_mode_index, SPEECH_MODE_ORDER.index(minimum_volume))

        if not reachable_targets:
            return None, []
        return SPEECH_MODE_ORDER[required_mode_index], reachable_targets

    def build_conversation_response_plan(self, response: str, receiver: Entity, speaker: Entity = None, llm_conversation_handler=None) -> Dict[str, Any]:
        plan = {
            'language': 'common',
            'message': '',
            'narrative': [],
            'targets': [],
            'volume': None,
            'skip': True,
            'approach': None,
            'interact': None,
            'request_check': None,
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
        }
        if not response:
            return plan

        language, processed_response = self.parse_language_from_response(response)
        if hasattr(receiver, 'languages') and receiver.languages():
            language = self.validate_language_for_entity(language, receiver)

        processed_response = self._process_rag_commands(processed_response, speaker, receiver, llm_conversation_handler)
        rerendered_language, processed_response = self.parse_language_from_response(processed_response)
        if rerendered_language != 'common' or language == 'common':
            if hasattr(receiver, 'languages') and receiver.languages():
                language = self.validate_language_for_entity(rerendered_language, receiver)
            else:
                language = rerendered_language

        action_directives = self.parse_action_directives(processed_response, receiver, speaker=speaker)
        processed_response = action_directives['response']
        plan.update({
            'approach': action_directives['approach'],
            'interact': action_directives['interact'],
            'request_check': action_directives['request_check'],
            'set_goal': action_directives['set_goal'],
            'goal_complete': action_directives['goal_complete'],
            'goal_give_up': action_directives['goal_give_up'],
        })

        controls = self.parse_response_controls(processed_response)
        if controls['no_response']:
            return plan

        message, narrative = self.extract_narrative_asides(
            controls['response'],
            llm_conversation_handler=llm_conversation_handler,
        )
        narrative = self.normalize_narrative_asides(narrative)
        narrative, inferred_request_check = self.enforce_narrative_visibility_constraints(
            narrative,
            receiver=receiver,
            speaker=speaker,
        )
        if plan['request_check'] is None and inferred_request_check is not None:
            plan['request_check'] = inferred_request_check
        if not message:
            return plan

        targets = self.resolve_response_targets(receiver, speaker=speaker, target_spec=controls.get('target_spec'))
        volume, targets = self.plan_response_volume(receiver, targets, volume=controls.get('volume'))
        if not targets or not volume:
            return plan

        plan.update({
            'language': language,
            'message': message,
            'narrative': narrative,
            'targets': targets,
            'volume': volume,
            'skip': False,
        })
        return plan

    def extract_narrative_asides(self, response_text: str, llm_conversation_handler=None) -> Tuple[str, List[str]]:
        asides = []

        def _replace(match):
            value = (match.group(2) or '').strip()
            if value:
                asides.append(value)
            return ''

        cleaned = ASIDE_DIRECTIVE_PATTERN.sub(_replace, response_text or '')
        cleaned = re.sub(r'\[.*?\]', '', cleaned).strip()

        if asides:
            return cleaned, asides

        if '\n' not in cleaned:
            return cleaned, []

        split = self._extract_narrative_asides_via_llm(cleaned, llm_conversation_handler)
        if split is None:
            return cleaned, []

        spoken = (split.get('spoken') or '').strip()
        narrative = [entry.strip() for entry in (split.get('narrative') or []) if str(entry).strip()]
        if spoken:
            return spoken, narrative
        return cleaned, narrative

    def _extract_narrative_asides_via_llm(self, message: str, llm_conversation_handler=None) -> Optional[Dict[str, Any]]:
        if llm_conversation_handler is None:
            return None

        llm_handler = getattr(llm_conversation_handler, 'llm_hander', None)
        if llm_handler is None:
            return None

        messages = [
            {
                'role': 'system',
                'content': (
                    'Separate an NPC reply into spoken dialogue and narrative aside text. '
                    'Return JSON only with keys spoken and narrative. '
                    'spoken must be a single string that contains only what is spoken aloud. '
                    'narrative must be an array of strings for third-person or stage-direction text not spoken aloud.'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps({'reply': message}, ensure_ascii=True),
            },
        ]

        try:
            raw_response = llm_handler.send_message(messages)
        except Exception:
            return None

        if not raw_response:
            return None

        payload_text = str(raw_response).strip()
        json_match = re.search(r'\{.*\}', payload_text, re.DOTALL)
        if json_match:
            payload_text = json_match.group(0)

        try:
            payload = json.loads(payload_text)
        except Exception:
            return None

        spoken = payload.get('spoken')
        narrative = payload.get('narrative')

        if spoken is None and not narrative:
            return None

        if isinstance(narrative, str):
            narrative = [narrative]
        if not isinstance(narrative, list):
            narrative = []

        return {
            'spoken': str(spoken or ''),
            'narrative': [str(item) for item in narrative if str(item).strip()],
        }

    def normalize_narrative_asides(self, narrative: List[str]) -> List[str]:
        normalized = []
        for entry in narrative or []:
            text = str(entry or '').strip()
            if not text:
                continue

            rewritten = text
            for pattern, replacement in NARRATIVE_FIRST_PERSON_SUBSTITUTIONS:
                rewritten = pattern.sub(replacement, rewritten)

            rewritten = re.sub(
                r'(^|[.!?]\s+)(they)\b',
                lambda match: f"{match.group(1)}They",
                rewritten,
            )

            normalized.append(rewritten)
        return normalized

    def enforce_narrative_visibility_constraints(self, narrative: List[str], receiver: Entity = None, speaker: Entity = None) -> Tuple[List[str], Optional[Dict[str, Any]]]:
        filtered = []
        removed_non_observable = []

        for entry in narrative or []:
            text = str(entry or '').strip()
            if not text:
                continue

            if NON_OBSERVABLE_TRUST_PATTERN.search(text):
                removed_non_observable.append(text)
                continue

            filtered.append(text)

        inferred_request_check = None
        if removed_non_observable and speaker is not None:
            inferred_skill = self.infer_requested_social_check_skill(
                receiver,
                speaker,
                removed_non_observable,
            )
            inferred_request_check = {
                'skill': inferred_skill,
                'target': speaker,
                'target_spec': 'speaker',
                'dc': None,
            }

        return filtered, inferred_request_check

    def conversation_attitude_toward_speaker(self, receiver: Entity, speaker: Entity) -> str:
        if receiver is None or speaker is None:
            return 'unknown'

        try:
            battle = self.current_game.get_current_battle()
        except Exception:
            battle = None

        if battle is not None:
            try:
                if battle.opposing(receiver, speaker) is True:
                    return 'hostile'
            except Exception:
                pass
            try:
                if battle.allies(receiver, speaker) is True:
                    return 'allied'
            except Exception:
                pass

        receiver_group = getattr(receiver, 'group', None)
        speaker_group = getattr(speaker, 'group', None)
        if receiver_group and speaker_group:
            if receiver_group == speaker_group:
                return 'allied'
            try:
                if self.game_session.opposing(receiver_group, speaker_group) is True:
                    return 'hostile'
            except Exception:
                pass
            return 'wary'

        try:
            receiver_owners = set(self.current_game.entity_owners(receiver))
            speaker_owners = set(self.current_game.entity_owners(speaker))
            if receiver_owners and speaker_owners and receiver_owners.intersection(speaker_owners):
                return 'allied'
        except Exception:
            pass

        return 'guarded'

    def infer_requested_social_check_skill(self, receiver: Entity, speaker: Entity, removed_entries: List[str]) -> str:
        attitude = self.conversation_attitude_toward_speaker(receiver, speaker)
        removed_text = ' '.join(str(item or '') for item in (removed_entries or [])).lower()

        intimidation_cues = (
            'threat', 'threaten', 'menace', 'menacing', 'snarl', 'growl',
            'afraid of', 'terrified of', 'fear', 'flinch', 'back away',
            'cower', 'intimidat',
        )
        has_intimidation_cue = any(cue in removed_text for cue in intimidation_cues)

        if attitude == 'hostile' or has_intimidation_cue:
            return 'intimidation'
        return 'persuasion'

    def parse_action_directives(self, response: str, actor: Entity, speaker: Entity = None) -> Dict[str, Any]:
        directives = {
            'response': response or '',
            'approach': None,
            'interact': None,
            'request_check': None,
            'set_goal': None,
            'goal_complete': False,
            'goal_give_up': False,
        }

        def _replace(match):
            directive = (match.group(1) or '').strip().lower()
            value = (match.group(2) or '').strip()

            if directive == 'approach':
                params = self._parse_named_params(value, positional_keys=('target', 'distance'))
                target_spec = params.get('target') or params.get('entity') or params.get('object')
                target = self.resolve_named_target(actor, target_spec, speaker=speaker, include_objects=True)
                try:
                    distance_ft = int(float(params.get('distance', params.get('distance_ft', 5))))
                except (TypeError, ValueError):
                    distance_ft = 5
                directives['approach'] = {
                    'target': target,
                    'target_spec': target_spec,
                    'distance_ft': max(0, distance_ft),
                }
            elif directive == 'interact':
                params = self._parse_named_params(value, positional_keys=('target', 'action'))
                target_spec = params.get('target') or params.get('entity') or params.get('object')
                target = self.resolve_named_target(actor, target_spec, speaker=speaker, include_objects=True)
                directives['interact'] = {
                    'target': target,
                    'target_spec': target_spec,
                    'action': params.get('action'),
                }
            elif directive == 'request_check':
                params = self._parse_named_params(value, positional_keys=('skill', 'target'))
                skill = (params.get('skill') or params.get('check') or '').strip().lower()
                target_spec = params.get('target') or params.get('entity') or 'speaker'
                target = self.resolve_named_target(actor, target_spec, speaker=speaker, include_objects=False)
                try:
                    dc = int(params['dc']) if params.get('dc') is not None else None
                except (TypeError, ValueError):
                    dc = None
                if skill in {'persuasion', 'intimidation'} and target is not None:
                    directives['request_check'] = {
                        'skill': skill,
                        'target': target,
                        'target_spec': target_spec,
                        'dc': dc,
                    }
            elif directive == 'set_goal' and value:
                directives['set_goal'] = value.strip()
            elif directive == 'goal_complete':
                directives['goal_complete'] = True
            elif directive == 'goal_give_up':
                directives['goal_give_up'] = True
            return ''

        directives['response'] = ACTION_DIRECTIVE_PATTERN.sub(_replace, directives['response']).strip()
        return directives

    def _parse_named_params(self, raw_value: str, positional_keys=()):
        parsed = {}
        positional_values = []

        for part in re.split(r'[,;]', raw_value or ''):
            segment = part.strip()
            if not segment:
                continue
            if '=' in segment:
                key, value = segment.split('=', 1)
                parsed[key.strip().lower()] = value.strip()
            else:
                positional_values.append(segment)

        for index, key in enumerate(positional_keys):
            if key not in parsed and index < len(positional_values):
                parsed[key] = positional_values[index]

        return parsed

    def resolve_named_target(self, actor: Entity, target_spec: Optional[str], speaker: Entity = None, include_objects: bool = False):
        if not target_spec:
            return None

        normalized = target_spec.strip()
        lowered = normalized.lower().lstrip('@')
        if lowered in {'speaker', 'you'}:
            return speaker

        try:
            target = self.game_session.entity_by_uid(normalized)
            if target is not None:
                return target
        except Exception:
            pass

        battle_map = self.current_game.get_map_for_entity(actor)
        if battle_map is None:
            return None

        candidates = [entity for entity in battle_map.entities if entity != actor]
        if include_objects:
            candidates.extend(list(battle_map.interactable_objects.keys()))
        if speaker is not None and speaker not in candidates and speaker != actor:
            candidates.append(speaker)

        exact_match = None
        partial_match = None
        for candidate in candidates:
            candidate_handle = mention_handle_for(candidate).lower()
            candidate_label = entity_label(candidate).lower()
            candidate_uid = str(getattr(candidate, 'entity_uid', ''))
            if lowered == candidate_handle or normalized == candidate_uid:
                return candidate
            if candidate_label == normalized.lower():
                exact_match = candidate
            elif normalized.lower() in candidate_label and partial_match is None:
                partial_match = candidate

        return exact_match or partial_match

    def get_interactable_objects(self, entity: Entity, range_ft: int = 30) -> List[Dict[str, Any]]:
        battle_map = self.current_game.get_map_for_entity(entity)
        if battle_map is None:
            return []

        objects = []
        for obj in list(battle_map.interactable_objects.keys()):
            try:
                distance_ft = battle_map.distance(entity, obj) * battle_map.feet_per_grid
            except Exception:
                continue

            if distance_ft > range_ft:
                continue

            try:
                visible = battle_map.can_see(entity, obj)
            except Exception:
                visible = True

            if not visible:
                continue

            try:
                interactions = obj.available_interactions(entity, battle=None) or {}
            except Exception:
                interactions = {}

            enabled_actions = [
                action_name for action_name, details in interactions.items()
                if not (details or {}).get('disabled')
            ]
            if not enabled_actions:
                continue

            objects.append({
                'id': getattr(obj, 'entity_uid', None),
                'name': entity_label(obj),
                'distance_ft': distance_ft,
                'position': battle_map.entity_or_object_pos(obj),
                'mention_handle': mention_handle_for(obj),
                'actions': enabled_actions,
            })

        return objects

    def build_approach_action(self, actor: Entity, target, distance_ft: int = 5):
        if actor is None or target is None:
            return None

        battle_map = self.current_game.get_map_for_entity(actor)
        if battle_map is None:
            return None

        feet_per_grid = getattr(battle_map, 'feet_per_grid', 5) or 5
        target_pos = battle_map.entity_or_object_pos(target)
        if target_pos is None:
            return None

        current_distance_ft = battle_map.distance(actor, target) * feet_per_grid
        if current_distance_ft <= distance_ft:
            return None

        candidate_positions = []
        for pos_x in range(battle_map.size[0]):
            for pos_y in range(battle_map.size[1]):
                if not battle_map.placeable(actor, pos_x, pos_y, squeeze=False):
                    continue
                try:
                    candidate_distance_ft = battle_map.distance(
                        actor,
                        target,
                        entity_1_pos=(pos_x, pos_y),
                        entity_2_pos=target_pos,
                    ) * feet_per_grid
                except Exception:
                    continue
                if candidate_distance_ft <= distance_ft:
                    candidate_positions.append((pos_x, pos_y))

        if not candidate_positions:
            return None

        source_x, source_y = battle_map.position_of(actor)
        path_compute = PathCompute(None, battle_map, actor, ignore_opposing=True)
        paths = path_compute.compute_paths_to_multiple_destinations(source_x, source_y, candidate_positions)

        best_destination = None
        best_path = None
        for destination, path in paths.items():
            if not path or len(path) < 2:
                continue
            if best_path is None or len(path) < len(best_path):
                best_destination = destination
                best_path = path

        if best_destination is None or best_path is None:
            return None

        trimmed_path = path_compute.compute_path(
            source_x,
            source_y,
            best_destination[0],
            best_destination[1],
            available_movement_cost=actor.available_movement(None),
        )
        if not trimmed_path or len(trimmed_path) < 2:
            return None

        action = MoveAction(self.game_session, actor, 'move')
        action.move_path = [list(step) for step in trimmed_path]
        return action

    def build_interact_action(self, actor: Entity, target, action_name: Optional[str] = None):
        if actor is None or target is None or not hasattr(target, 'available_interactions'):
            return None

        try:
            interactions = target.available_interactions(actor, battle=None) or {}
        except Exception:
            interactions = {}

        enabled_actions = [
            interaction_name for interaction_name, details in interactions.items()
            if not (details or {}).get('disabled')
        ]
        if not enabled_actions:
            return None

        selected_action = action_name
        if selected_action and selected_action not in enabled_actions:
            return None
        if not selected_action:
            selected_action = enabled_actions[0]

        interact = InteractAction(self.game_session, actor, 'interact')
        interact.target = target
        interact.object_action = selected_action
        built_action = interact.build_custom_action(selected_action, target)
        if isinstance(built_action, InteractAction):
            return built_action
        if isinstance(built_action, Action):
            return built_action
        return None

    def apply_response_plan_directives(self, plan: Dict[str, Any], actor: Entity, speaker: Entity = None, advance_time: bool = False) -> Dict[str, Any]:
        result = {
            'scheduled_goal': None,
            'executed_actions': [],
            'goal_status': None,
        }
        if actor is None or not plan:
            return result

        if plan.get('set_goal'):
            result['scheduled_goal'] = self.current_game.schedule_short_term_goal(actor, plan['set_goal'], speaker=speaker)

        if plan.get('goal_complete'):
            result['goal_status'] = 'completed'
            self.current_game.complete_short_term_goal(actor, status='completed', reason='Marked complete by LLM')
        elif plan.get('goal_give_up'):
            result['goal_status'] = 'abandoned'
            self.current_game.complete_short_term_goal(actor, status='abandoned', reason='Abandoned by LLM')

        if self.current_game.get_current_battle() is None:
            execution_username = self._execution_username_for(actor)
            pov_entities = [actor]

            request_check = plan.get('request_check')
            if request_check and request_check.get('target') is not None:
                self._log_requested_check(
                    actor,
                    request_check['target'],
                    request_check['skill'],
                    dc=request_check.get('dc'),
                )
                result['executed_actions'].append('request_check')

            approach_directive = plan.get('approach')
            if approach_directive and approach_directive.get('target') is not None:
                move_action = self.build_approach_action(
                    actor,
                    approach_directive['target'],
                    distance_ft=approach_directive.get('distance_ft', 5),
                )
                if move_action is not None:
                    self.current_game.commit_and_update(execution_username, move_action, pov_entities)
                    result['executed_actions'].append('approach')

            interact_directive = plan.get('interact')
            if interact_directive and interact_directive.get('target') is not None:
                interact_action = self.build_interact_action(
                    actor,
                    interact_directive['target'],
                    action_name=interact_directive.get('action'),
                )
                if interact_action is not None:
                    self.current_game.commit_and_update(execution_username, interact_action, pov_entities)
                    result['executed_actions'].append('interact')

        if advance_time and self.current_game.get_current_battle() is None:
            self.current_game.advance_world_time(
                seconds=6,
                trigger_environment=not result['executed_actions'],
            )

        return result

    def execute_scheduled_goal(self, entity_uid: str, llm_conversation_handler) -> Optional[Dict[str, Any]]:
        entity = self.current_game.get_entity_by_uid(entity_uid)
        if entity is None:
            return None

        goal_state = self.current_game.get_short_term_goal(entity)
        if goal_state is None or goal_state.get('status') != 'active':
            return None

        requester = None
        requester_uid = goal_state.get('requester_uid')
        if requester_uid:
            try:
                requester = self.game_session.entity_by_uid(requester_uid)
            except Exception:
                requester = None

        if not getattr(entity, 'dialog', False):
            self.current_game.complete_short_term_goal(entity, status='abandoned', reason='Entity cannot use dialog goals')
            return {'goal_status': 'abandoned'}

        conversation_id = f"{entity.entity_uid}:goal"
        system_prompt = self.goal_execution_prompt(entity, goal_state, requester=requester)
        llm_conversation_handler.create_conversation(conversation_id, system_prompt)
        try:
            llm_conversation_handler.conversations[conversation_id]['system_prompt'] = system_prompt
        except Exception:
            pass

        llm_conversation_handler.add_message(conversation_id, 'user', self.goal_turn_snapshot(entity, goal_state, requester=requester))
        response = llm_conversation_handler.generate_response(conversation_id)
        plan = self.build_conversation_response_plan(
            response,
            entity,
            speaker=requester,
            llm_conversation_handler=llm_conversation_handler,
        )
        directive_result = self.apply_response_plan_directives(plan, entity, speaker=requester, advance_time=True)
        self.current_game.record_short_term_goal_history(entity, {
            'time': self.game_session.game_time,
            'response': response,
            'executed_actions': list(directive_result['executed_actions']),
            'goal_status': directive_result.get('goal_status') or 'active',
        })
        return directive_result

    def goal_execution_prompt(self, entity: Entity, goal_state: Dict[str, Any], requester: Entity = None) -> str:
        requester_label = entity_label(requester) if requester is not None else 'nobody in particular'
        return (
            f"You are {entity_label(entity)} acting autonomously in a D&D world.\n"
            f"Your active short-term goal is: {goal_state.get('goal', '')}\n"
            f"This goal was last requested or influenced by: {requester_label}.\n"
            "Take one 6-second out-of-combat turn. Return only optional control tags plus an optional spoken line.\n"
            "Available control tags:\n"
            "- [APPROACH: target=@handle, distance=5] to move up to full movement speed until you are within the requested distance.\n"
            "- [INTERACT: target=<name or @handle>, action=<interaction>] to use an interactable object.\n"
            "- [INSIGHT: target=speaker] or [INSIGHT: target=@handle] to privately assess whether someone seems truthful before responding.\n"
            "- [REQUEST_CHECK: skill=persuasion, target=speaker] or [REQUEST_CHECK: skill=intimidation, target=@handle] to ask for a social check.\n"
            "- [SET_GOAL: new short goal] to replace your current short-term goal.\n"
            "- [GOAL_COMPLETE] when the current goal is done.\n"
            "- [GOAL_GIVE_UP] when the current goal cannot be completed or is no longer worth pursuing.\n"
            "- [OBSERVE] or [INVENTORY] if you need refreshed world state before deciding.\n"
            "- [NO_RESPONSE] if you do not say anything aloud this turn.\n"
        )

    def goal_turn_snapshot(self, entity: Entity, goal_state: Dict[str, Any], requester: Entity = None) -> str:
        context = self.get_entity_context(entity)
        nearby_entities = self.get_nearby_entities(entity, range_ft=60, include_extended=True)
        interactable_objects = self.get_interactable_objects(entity, range_ft=60)
        history_entries = goal_state.get('history', [])[-3:]

        lines = [
            f"Goal: {goal_state.get('goal', '')}",
            f"Game time: {self.game_session.game_time}",
            f"Your position: {context.get('position')}",
            f"Requester: {entity_label(requester) if requester is not None else 'none'}",
            f"Attempts so far: {goal_state.get('attempts', 0)}",
            "Nearby entities:",
        ]

        if nearby_entities:
            for nearby in nearby_entities[:8]:
                lines.append(
                    f"- {nearby['name']} (@{nearby['mention_handle']}) at {nearby['distance']}ft; reachable_now={nearby['reachable_now']}"
                )
        else:
            lines.append("- none")

        lines.append("Visible interactable objects:")
        if interactable_objects:
            for obj in interactable_objects[:8]:
                actions = ', '.join(obj['actions'])
                lines.append(
                    f"- {obj['name']} (@{obj['mention_handle']}) at {obj['distance_ft']}ft; actions={actions}"
                )
        else:
            lines.append("- none")

        lines.append("Recent goal history:")
        if history_entries:
            for entry in history_entries:
                lines.append(f"- t={entry.get('time')}: {entry}")
        else:
            lines.append("- none")

        lines.append("Choose your next turn.")
        return '\n'.join(lines)

    def _execution_username_for(self, entity: Entity) -> str:
        owners = self.current_game.entity_owners(entity)
        return owners[0] if owners else 'dm'
    
    def parse_language_from_response(self, response: str) -> Tuple[str, str]:
        """
        Parse language specification from AI response.
        
        Args:
            response: The raw response from the AI
            
        Returns:
            Tuple of (language, response_text)
        """
        if not response or "[in" not in response:
            return "common", response
        
        try:
            # Find the start of [in
            start_idx = response.find("[in")
            if start_idx != -1:
                # Find the closing bracket after [in
                end_bracket_idx = response.find("]", start_idx)
                if end_bracket_idx != -1:
                    # Extract language (everything between [in and ])
                    language = response[start_idx + 3:end_bracket_idx].strip()
                    # Extract the rest of the response after the closing bracket
                    response_text = response[end_bracket_idx + 1:].strip()
                    return language, response_text
                else:
                    # No closing bracket found, treat as common
                    return "common", response
            else:
                return "common", response
        except (IndexError, ValueError):
            # Fallback to common if parsing fails
            return "common", response

    def _process_rag_commands(self, response: str, speaker: Entity, receiver: Entity, llm_conversation_handler) -> str:
        """
        Process RAG commands in the response and generate appropriate responses.

        Args:
            response: The response containing RAG commands
            receiver: The entity processing the response
            llm_conversation_handler: The LLM conversation handler

        Returns:
            The processed response
        """
        # Handle hostile state change
        if "[GO_HOSTILE]" in response:
            return self._handle_hostile_state_change(receiver)

        if "[GO_FRIENDLY]" in response:
            return self._handle_friendly_state_change(receiver)

        # Handle inventory queries
        if "[INVENTORY" in response or "[LIST_INVENTORY" in response:
            return self._handle_inventory_query(receiver, llm_conversation_handler)

        # Handle observation requests
        if "[OBSERVE" in response:
            return self._handle_observation_request(receiver, llm_conversation_handler)

        # Handle insight requests
        if "[INSIGHT" in response:
            return self._handle_insight_request(response, receiver, speaker, llm_conversation_handler)

        try:
            keyword_entries = receiver.conversation_keywords()
        except Exception:
            keyword_entries = []

        if not isinstance(keyword_entries, (list, tuple)):
            keyword_entries = []

        for keywords in keyword_entries:
            if keywords['keyword'] in response:
                logger.info(f"Processing event for keyword '{keywords['keyword']}': {keywords}")
                generic_handler = GenericEventHandler(self.game_session, receiver, keywords)
                generic_handler.handle(self, opts={'speaker': speaker})
                # Remove the keyword from the response
                response = response.replace(keywords['keyword'], '')

        return response

    def _handle_insight_request(self, response: str, receiver: Entity, speaker: Entity, llm_conversation_handler) -> str:
        if llm_conversation_handler is None:
            return ""

        match = INSIGHT_DIRECTIVE_PATTERN.search(response or '')
        params = self._parse_named_params(match.group(1) if match else '', positional_keys=('target',))
        target_spec = params.get('target') or 'speaker'
        target = self.resolve_named_target(receiver, target_spec, speaker=speaker, include_objects=False)
        if target is None:
            return re.sub(INSIGHT_DIRECTIVE_PATTERN, '', response or '').strip()

        try:
            roll = receiver.insight_check(description=f"insight check on {entity_label(target)}")
        except Exception as e:
            logger.error(f"Error rolling insight check for {entity_label(receiver)}: {e}")
            return ""

        statement = self._latest_statement_from_source(receiver, speaker or target)
        assessment = self._evaluate_insight_assessment(receiver, target, statement, roll, llm_conversation_handler)
        system_response = (
            f"[INSIGHT] You rolled {roll} = {roll.result()} while reading {entity_label(target)}. "
            f"DM assessment: {assessment['assessment']}. {assessment['reason']}"
        )
        self._log_social_check(
            f"{entity_label(receiver)} makes an insight check on {entity_label(target)} and rolls {roll} = {roll.result()}. "
            f"Assessment: {assessment['assessment']}. {assessment['reason']}",
            entities=[receiver, target],
        )
        llm_conversation_handler.add_message(receiver.entity_uid, 'system', system_response)
        regenerated_response = llm_conversation_handler.generate_response(receiver.entity_uid)
        if regenerated_response:
            _language, regenerated_response = self.parse_language_from_response(regenerated_response)
            return regenerated_response
        return ""

    def _latest_statement_from_source(self, receiver: Entity, source: Entity) -> str:
        if receiver is None or source is None:
            return ''

        for message in reversed(getattr(receiver, 'memory_buffer', []) or []):
            if message.get('source') == source:
                return message.get('message', '') or ''
        return ''

    def _evaluate_insight_assessment(self, observer: Entity, target: Entity, statement: str, roll, llm_conversation_handler) -> Dict[str, str]:
        default_assessment = {
            'assessment': 'uncertain',
            'reason': 'There is not enough reliable evidence to determine whether the statement is true or deceptive.',
        }

        llm_handler = getattr(llm_conversation_handler, 'llm_hander', None)
        if llm_handler is None:
            return default_assessment

        messages = [
            {
                'role': 'system',
                'content': (
                    'You are the Dungeon Master adjudicating an NPC insight check. '
                    'Use the insight roll as a confidence gate. '
                    'If the roll is low, the evidence is mixed, or the context is insufficient, return uncertain. '
                    'Return JSON only with keys assessment and reason. '
                    'assessment must be one of truthful, lie, or uncertain. '
                    'IMPORTANT: the "reason" field is shown verbatim to the player\'s character. '
                    'Write it strictly in-character and only describe cues the observer could plausibly notice '
                    '(tone of voice, body language, hesitations, eye contact, inconsistencies with what was said earlier). '
                    'NEVER reveal DM-only knowledge such as the target\'s true nature, alignment, stat block, '
                    'hidden identity, illusion/undead/construct status, secret motives, backstory facts the observer '
                    'has not learned in play, or any meta-game information. '
                    'If the roll is too low to learn anything, say so vaguely without referencing hidden truths.'
                ),
            },
            {
                'role': 'user',
                'content': json.dumps({
                    'statement': statement,
                    'insight_roll_total': roll.result(),
                    'observer': entity_label(observer),
                    'target': entity_label(target),
                    'dm_context': self._build_dm_insight_context(observer, target, statement),
                }, default=str),
            },
        ]

        try:
            raw_response = llm_handler.send_message(messages)
        except Exception as e:
            logger.error(f"Error adjudicating insight check for {entity_label(observer)}: {e}")
            return default_assessment

        return self._parse_insight_assessment_response(raw_response, default_assessment)

    def _parse_insight_assessment_response(self, raw_response: str, default_assessment: Dict[str, str]) -> Dict[str, str]:
        if not raw_response:
            return default_assessment

        text = str(raw_response).strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        try:
            payload = json.loads(text)
            assessment = str(payload.get('assessment', 'uncertain')).strip().lower()
            reason = str(payload.get('reason', '')).strip()
        except Exception:
            lowered = text.lower()
            if 'truthful' in lowered or 'honest' in lowered or re.search(r'\btrue\b', lowered):
                assessment = 'truthful'
            elif 'lying' in lowered or 'decept' in lowered or re.search(r'\blie\b', lowered):
                assessment = 'lie'
            else:
                assessment = 'uncertain'
            reason = text

        if assessment not in {'truthful', 'lie', 'uncertain'}:
            assessment = 'uncertain'
        if not reason:
            reason = default_assessment['reason']
        reason = self._sanitize_insight_reason(reason, default_assessment['reason'])
        return {'assessment': assessment, 'reason': reason}

    # Sentences containing any of these terms reveal DM-only knowledge that
    # the observing character could not perceive from cues alone. They are
    # dropped from the player-facing reason text. If everything would be
    # dropped, we fall back to a vague default.
    _DM_LEAK_TERMS = (
        'illusion', 'illusory', 'illusionary', 'phantasm',
        'construct', 'undead', 'ghost', 'spectre', 'specter', 'apparition',
        'incorporeal', 'shapechanger', 'doppelganger', 'simulacrum',
        'true form', 'true nature', 'actually a', 'in reality',
        'stat block', 'alignment', 'backstory', 'hit point', 'hp ',
        'meta', 'dm note', 'dungeon master', 'behind the scenes',
        'created by the house', 'manifestation of', 'spirit of',
    )

    def _sanitize_insight_reason(self, reason: str, fallback: str) -> str:
        text = str(reason or '').strip()
        if not text:
            return fallback
        # Split on sentence boundaries while keeping it lightweight; drop any
        # sentence that name-drops DM-only metadata.
        sentences = re.split(r'(?<=[\.\!\?])\s+', text)
        kept = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(term in lowered for term in self._DM_LEAK_TERMS):
                continue
            kept.append(sentence.strip())
        cleaned = ' '.join(part for part in kept if part).strip()
        return cleaned or fallback

    def _build_dm_insight_context(self, observer: Entity, target: Entity, statement: str) -> Dict[str, Any]:
        battle_map = self.current_game.get_map_for_entity(observer)
        player_characters = []
        if battle_map is not None:
            for entity in getattr(battle_map, 'entities', []):
                if isinstance(entity, PlayerCharacter):
                    player_characters.append(entity)

        return {
            'statement': statement,
            'observer': self.get_entity_context(observer),
            'target': self._dm_pc_context(target) if isinstance(target, PlayerCharacter) else self._dm_entity_context(target),
            'all_player_characters': [self._dm_pc_context(entity) for entity in player_characters],
        }

    def _dm_entity_context(self, entity: Entity) -> Dict[str, Any]:
        context = self.get_entity_context(entity)
        context['background'] = entity.backstory() if hasattr(entity, 'backstory') else ''
        context['statuses'] = list(getattr(entity, 'statuses', []) or [])
        if hasattr(entity, 'current_effects') and callable(getattr(entity, 'current_effects')):
            try:
                context['effects'] = [str(effect['effect']) for effect in entity.current_effects()]
            except Exception:
                context['effects'] = []
        else:
            context['effects'] = []
        context['recent_memory'] = [
            {
                'source': entity_label(message.get('source')),
                'message': message.get('message'),
                'time': message.get('time'),
            }
            for message in (getattr(entity, 'memory_buffer', []) or [])[-8:]
        ]
        output_logger = getattr(self.current_game, 'output_logger', None)
        if output_logger is not None and hasattr(output_logger, 'get_logs_for_entity'):
            try:
                context['recent_logs'] = output_logger.get_logs_for_entity(entity)[-12:]
            except Exception:
                context['recent_logs'] = []
        else:
            context['recent_logs'] = []
        try:
            from webapp import app as app_module
            details = app_module.game_context_provider.get_entity_details(entity_label(entity))
            if isinstance(details, dict):
                context['dm_details'] = details
        except Exception:
            pass
        return context

    def _dm_pc_context(self, entity: Entity) -> Dict[str, Any]:
        context = self._dm_entity_context(entity)
        context['is_player_character'] = isinstance(entity, PlayerCharacter)
        return context

    def _log_social_check(self, message: str, entities: List[Entity]):
        output_logger = getattr(self.current_game, 'output_logger', None)
        if output_logger is None or not hasattr(output_logger, 'log'):
            return

        entity_uids = [getattr(entity, 'entity_uid', None) for entity in (entities or []) if entity is not None]
        output_logger.log(message, visibility={'kind': 'entities', 'entity_uids': entity_uids})

    def _log_requested_check(self, actor: Entity, target: Entity, skill: str, dc: Optional[int] = None):
        dc_suffix = f" (DC {dc})" if dc is not None else ''
        self._log_social_check(
            f"{entity_label(actor)} requests a {skill} check from {entity_label(target)}{dc_suffix}.",
            entities=[actor, target],
        )

    def _handle_friendly_state_change(self, receiver: Entity) -> str:
        """
        Handle friendly state change command.

        Args:
            receiver: The entity changing to friendly state

        Returns:
            Empty string (response will be handled by caller)
        """
        try:
            receiver.update_state('active')
            self.current_game.update_group(receiver, 'a')
            logger.info(f"Entity {receiver.label()} is now in the friendly group")
            return ""
        except Exception as e:
            logger.error(f"Error changing entity to friendly state: {e}")
            return ""

    def _handle_hostile_state_change(self, receiver: Entity) -> str:
        """
        Handle hostile state change command.
        
        Args:
            receiver: The entity changing to hostile state
            
        Returns:
            Empty string (response will be handled by caller)
        """
        try:
            receiver.update_state('active')
            self.current_game.update_group(receiver, 'b')
            logger.info(f"Entity {receiver.label()} is now in the hostile group")
            return ""
        except Exception as e:
            logger.error(f"Error changing entity to hostile state: {e}")
            return ""
    
    def _handle_inventory_query(self, receiver: Entity, llm_conversation_handler) -> str:
        """
        Handle inventory query command.
        
        Args:
            receiver: The entity whose inventory is being queried
            llm_conversation_handler: The LLM conversation handler
            
        Returns:
            The response after inventory processing
        """
        try:
            # Get inventory items
            inventory_items = [item['label'] for item in receiver.inventory_items(self.game_session)]
            system_response = f'[INVENTORY] {", ".join(inventory_items)}'
            
            # Add system message and regenerate response
            llm_conversation_handler.add_message(receiver.entity_uid, 'system', system_response)
            response = llm_conversation_handler.generate_response(receiver.entity_uid)
            
            # Re-parse language for the new response
            if response:
                language, response = self.parse_language_from_response(response)
                return response
            
            return ""
        except Exception as e:
            logger.error(f"Error handling inventory query: {e}")
            return ""
    
    def _handle_observation_request(self, receiver: Entity, llm_conversation_handler) -> str:
        """
        Handle observation request command.
        
        Args:
            receiver: The entity making the observation
            llm_conversation_handler: The LLM conversation handler
            
        Returns:
            The response after observation processing
        """
        try:
            # Get nearby entities
            battle_map = self.current_game.get_map_for_entity(receiver)
            nearby = receiver.observe(battle_map)
            
            # Build observation response
            observation_text = ""
            for entity, distance in nearby:
                observation_text += f"{entity.label()} is {distance}ft away\n"
            
            system_response = f'[OBSERVE] {observation_text}'
            
            # Add system message and regenerate response
            llm_conversation_handler.add_message(receiver.entity_uid, 'system', system_response)
            response = llm_conversation_handler.generate_response(receiver.entity_uid)
            
            # Re-parse language for the new response
            if response:
                language, response = self.parse_language_from_response(response)
                return response
            
            return ""
        except Exception as e:
            logger.error(f"Error handling observation request: {e}")
            return ""
    
    def get_entity_context(self, entity: Entity) -> Dict[str, Any]:
        """
        Get comprehensive context information for an entity.
        
        Args:
            entity: The entity to get context for
            
        Returns:
            Dictionary containing entity context information
        """
        context = {
            'name': entity.label() if hasattr(entity, 'label') else str(entity),
            'entity_uid': getattr(entity, 'entity_uid', None),
            'description': entity.description() if hasattr(entity, 'description') else 'No description available.'
        }
        
        # Add combat stats
        if hasattr(entity, 'hp') and callable(getattr(entity, 'hp')):
            context['hp'] = entity.hp()
        elif hasattr(entity, 'hp'):
            context['hp'] = entity.hp
        
        if hasattr(entity, 'max_hp') and callable(getattr(entity, 'max_hp')):
            context['max_hp'] = entity.max_hp()
        elif hasattr(entity, 'max_hp'):
            context['max_hp'] = entity.max_hp
        
        if hasattr(entity, 'armor_class') and callable(getattr(entity, 'armor_class')):
            context['ac'] = entity.armor_class()
        elif hasattr(entity, 'ac'):
            context['ac'] = entity.ac
        
        # Add level information
        if hasattr(entity, 'level') and callable(getattr(entity, 'level')):
            context['level'] = entity.level()
        elif hasattr(entity, 'level'):
            context['level'] = entity.level
        
        # Add race information
        if hasattr(entity, 'race') and callable(getattr(entity, 'race')):
            context['race'] = entity.race()
        elif hasattr(entity, 'race'):
            context['race'] = entity.race
        
        # Add class information
        class_value = None
        if hasattr(entity, 'class_descriptor') and callable(getattr(entity, 'class_descriptor')):
            class_value = entity.class_descriptor()
        if class_value:
            context['class'] = class_value
        elif hasattr(entity, 'class_and_level') and callable(getattr(entity, 'class_and_level')):
            class_info = entity.class_and_level()
            if class_info:
                context['class'] = ', '.join([f"{cls} {lvl}" for cls, lvl in class_info])
        
        # Add inventory information
        try:
            inventory_items = entity.inventory_items(self.game_session)
            context['inventory'] = [item['label'] for item in inventory_items] if inventory_items else []
        except:
            context['inventory'] = []
        
        # Add position information
        try:
            battle_map = self.current_game.get_map_for_entity(entity)
            if battle_map and hasattr(battle_map, 'entity_or_object_pos'):
                context['position'] = battle_map.entity_or_object_pos(entity)
        except:
            context['position'] = None
        
        return context
    
    def get_nearby_entities(self, entity: Entity, range_ft: int = 30, volume: Optional[str] = None, include_extended: bool = False) -> List[Dict[str, Any]]:
        """
        Get nearby entities for an entity.
        
        Args:
            entity: The entity to get nearby entities for
            range_ft: The range in feet to search
            
        Returns:
            List of nearby entity information
        """
        try:
            battle_map = self.current_game.get_map_for_entity(entity)
            try:
                if include_extended:
                    nearby = conversation_reachability(entity, battle_map, distance_ft=range_ft, mode=volume)
                else:
                    nearby = audible_entities(entity, battle_map, distance_ft=range_ft, mode=volume)
            except Exception:
                nearby = None

            if not isinstance(nearby, list):
                nearby = []

            if nearby and isinstance(nearby[0], dict):
                audience_entries = nearby
            else:
                if battle_map is None:
                    observed = []
                else:
                    observed = entity.observe(battle_map)
                audience_entries = []
                for observed_entity, distance in observed or []:
                    audience_entries.append({
                        'entity': observed_entity,
                        'distance_ft': distance,
                        'adjusted_distance_ft': distance,
                        'effective_distance_ft': distance,
                        'passive_perception': None,
                        'hearing_modifier_ft': 0,
                        'reachable_now': distance <= range_ft,
                        'reachable_with_shout': distance <= range_ft,
                        'minimum_volume': volume or 'normal',
                        'status': 'reachable' if distance <= range_ft else 'too_far',
                        'acoustic_penalty_ft': 0,
                        'acoustic_summary': '',
                        'closed_doors': 0,
                        'walls': 0,
                        'opaque_objects': 0,
                    })
            
            response = []
            # Short-lived cache for can_see results to avoid repeated LoS ray traces
            # within a single get_nearby_entities call (same speaker, same map state).
            _visibility_cache: Dict[Tuple[str, str], bool] = {}

            for audience_entry in audience_entries:
                nearby_entity = audience_entry['entity']
                # Hide entities the speaker cannot see; otherwise listing them in the
                # UI would reveal hidden/invisible/unseen creatures even though they
                # may still be able to hear the speaker.
                try:
                    if battle_map is not None and hasattr(battle_map, 'can_see'):
                        vis_key = (entity.entity_uid, nearby_entity.entity_uid)
                        if vis_key in _visibility_cache:
                            visible = _visibility_cache[vis_key]
                        else:
                            visible = battle_map.can_see(entity, nearby_entity)
                            _visibility_cache[vis_key] = visible
                        if not visible:
                            continue
                except Exception:
                    pass
                response.append({
                    'id': nearby_entity.entity_uid,
                    'name': entity_label(nearby_entity),
                    'distance': audience_entry['distance_ft'],
                    'adjusted_distance_ft': audience_entry.get('adjusted_distance_ft', audience_entry['distance_ft']),
                    'effective_distance_ft': audience_entry['effective_distance_ft'],
                    'passive_perception': audience_entry['passive_perception'],
                    'hearing_modifier_ft': audience_entry['hearing_modifier_ft'],
                    'reachable_now': audience_entry.get('reachable_now', True),
                    'reachable_with_shout': audience_entry.get('reachable_with_shout', True),
                    'minimum_volume': audience_entry.get('minimum_volume'),
                    'status': audience_entry.get('status', 'reachable'),
                    'acoustic_penalty_ft': audience_entry.get('acoustic_penalty_ft', 0),
                    'acoustic_summary': audience_entry.get('acoustic_summary', ''),
                    'closed_doors': audience_entry.get('closed_doors', 0),
                    'walls': audience_entry.get('walls', 0),
                    'opaque_objects': audience_entry.get('opaque_objects', 0),
                    'mention_handle': mention_handle_for(nearby_entity),
                    'conversable': nearby_entity.conversable()
                })
            
            return response
        except Exception as e:
            logger.error(f"Error getting nearby entities: {e}")
            return []
    
    def validate_language_for_entity(self, language: str, entity: Entity) -> str:
        """
        Validate that an entity can speak the specified language.
        
        Args:
            language: The language to validate
            entity: The entity to check
            
        Returns:
            The validated language (falls back to first available if invalid)
        """
        if language not in entity.languages():
            return entity.languages()[0] if entity.languages() else "common"
        return language 
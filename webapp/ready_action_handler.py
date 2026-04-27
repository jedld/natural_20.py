"""LLM-assisted Ready/Hold action support for the webapp.

Two responsibilities:

1. ``parse_ready_action_request``: turn the player's free-text description
   ("if the goblin steps next to me, I attack with my longsword") into a
   structured ``trigger`` + ``action_spec`` pair, *and* validate that the
   intended action is something the entity could actually take this turn
   (otherwise the DM rejects per 5e rules).
2. ``resolve_fired_ready_action``: at trigger time, pick a concrete Action
   from the entity's currently-available actions that matches the prepared
   intent. Plugged into the engine via ``Battle.set_ready_action_resolver``.

Both helpers degrade gracefully if no LLM provider is available: a
deterministic rule-based parser handles common phrasings, and
``natural20.ready_action.default_resolver`` covers the common "attack the
trigger creature" case.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.ready_action import (
    ReadyActionState,
    SUPPORTED_TRIGGER_EVENTS,
    SUPPORTED_ACTION_KINDS,
    default_resolver,
    normalize_action_spec,
    normalize_trigger,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _entity_weapons(entity) -> List[str]:
    """Best-effort enumeration of weapon slugs the entity can attack with."""
    weapons: List[str] = []
    seen = set()
    try:
        equipped = entity.equipped_weapons(entity.session) or []
    except Exception:
        equipped = []
    for w in equipped:
        slug = w.get('name') if isinstance(w, dict) else getattr(w, 'name', None) or str(w)
        if slug and slug not in seen:
            seen.add(slug)
            weapons.append(slug)
    return weapons


def _entity_spells(entity) -> List[Dict[str, Any]]:
    """List of currently-castable spells with name/level for the LLM prompt."""
    out: List[Dict[str, Any]] = []
    try:
        raw = entity.prepared_spells
        if callable(raw):
            raw = raw()
        prepared = list(raw or [])
    except Exception:
        prepared = []
    for spell_name in prepared:
        try:
            spell_def = entity.session.load_spell(spell_name)
        except Exception:
            spell_def = None
        if not spell_def:
            continue
        out.append({
            'name': spell_name,
            'level': spell_def.get('level'),
            'casting_time': spell_def.get('casting_time'),
        })
    return out


def _entity_usable_items(entity) -> List[Dict[str, Any]]:
    """List of (slug, name, qty) for items the entity can use as an action."""
    items: List[Dict[str, Any]] = []
    try:
        usable = entity.usable_items() or []
    except Exception:
        usable = []
    for item in usable:
        if not isinstance(item, dict):
            continue
        slug = item.get('name') or item.get('slug')
        if not slug:
            continue
        items.append({
            'slug': slug,
            'qty': item.get('qty', 1),
            'consumable': bool(item.get('consumable')),
        })
    return items


def _enemy_uids(entity, battle) -> List[Tuple[str, str]]:
    """List of (uid, label) pairs for visible adversaries."""
    pairs: List[Tuple[str, str]] = []
    if battle is None:
        return pairs
    try:
        for other in list(battle.combat_order):
            if other is None or other is entity:
                continue
            try:
                if battle.allies(entity, other):
                    continue
            except Exception:
                pass
            uid = str(getattr(other, 'entity_uid', ''))
            if not uid:
                continue
            label = getattr(other, 'name', None) or other.label() if hasattr(other, 'label') else uid
            pairs.append((uid, label))
    except Exception:
        pass
    return pairs


# --------------------------------------------------------------------------
# Rule-based fallback parser. Used when no LLM provider is configured or
# when the LLM fails. Recognises the most common Ready phrasings.
# --------------------------------------------------------------------------

_TRIGGER_PATTERNS = [
    # "when my ally attacks X" / "when X attacks Y" -> ally_attacks. We let
    # the LLM (or a downstream UI affordance) pin a specific enemy via
    # ``attack_target_uid``; the heuristic just sets the event.
    (re.compile(r"\b(?:when|if)\b.*\b(?:my\s+ally|ally|allies|teammate|partner|friend)\b.*\battacks?\b", re.I),
     {'event': 'ally_attacks', 'condition': 'always', 'subject_filter': 'allies'}),
    (re.compile(r"\bgang(?:s)?\s+up\b|\bfocus\s*fire\b|\b(?:pile|piles)\s+on\b", re.I),
     {'event': 'ally_attacks', 'condition': 'always', 'subject_filter': 'allies'}),
    # "on command" phrasings: the readier reacts when an ally (or anyone)
    # speaks a recognised command word/phrase. We try to capture the phrase
    # itself from constructions like "when X says 'foo'" or "on the command 'foo'".
    (re.compile(r"\b(?:on (?:my |the )?command|when (?:i|he|she|they|my master|the wizard|the cleric|anyone) (?:says?|shouts?|yells?|orders?|commands?))\b", re.I),
     {'event': 'on_command', 'condition': 'always', 'subject_filter': 'allies'}),
    # Door / object phrasings: "when the door opens", "if the chest is unlocked", etc.
    (re.compile(r"\b(?:door|chest|gate|lid|trapdoor|hatch)\b.*\b(opens?|closes?|unlocks?|opens up)\b", re.I),
     {'event': 'object_interaction', 'condition': 'always', 'subject_filter': 'any'}),
    (re.compile(r"\b(?:when|if)\b.*\b(opens?|closes?|unlocks?)\b.*\b(?:door|chest|gate|lid|trapdoor|hatch)\b", re.I),
     {'event': 'object_interaction', 'condition': 'always', 'subject_filter': 'any'}),
    (re.compile(r"\b(goes? down|drops? to (?:0|zero)|falls? unconscious|hits? (?:0|zero)\s*hp|knocked out|gets? knocked out)\b", re.I),
     {'event': 'goes_down', 'condition': 'always', 'subject_filter': 'allies'}),
    (re.compile(r"\b(becomes? visible|comes? into view|steps? into (?:the )?light|appears?)\b", re.I),
     {'event': 'becomes_visible', 'condition': 'always', 'subject_filter': 'enemies'}),
    (re.compile(r"\b(adjacent|next to|step(?:s)? next to|comes within (?:5|five)(?:\s*ft|\s*feet)?)\b", re.I),
     {'event': 'movement', 'condition': 'adjacent_to_self', 'subject_filter': 'enemies'}),
    (re.compile(r"\bcomes? within (\d+)\s*(?:ft|feet)\b", re.I),
     {'event': 'movement', 'condition': 'within_range', 'subject_filter': 'enemies'}),
    (re.compile(r"\bmoves\b", re.I),
     {'event': 'movement', 'condition': 'always', 'subject_filter': 'enemies'}),
    (re.compile(r"\b(starts? (?:its|their|his|her) turn|begins (?:its|their|his|her) turn)\b", re.I),
     {'event': 'start_of_turn', 'condition': 'starts_turn', 'subject_filter': 'enemies'}),
]


def _heuristic_parse(description: str, weapons: List[str],
                     spells: List[Dict[str, Any]],
                     usable_items: Optional[List[Dict[str, Any]]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    text = description or ''
    usable_items = usable_items or []
    trigger: Dict[str, Any] = {
        'event': 'movement',
        'condition': 'adjacent_to_self',
        'subject_filter': 'enemies',
        'description': text.strip(),
    }
    for pattern, hint in _TRIGGER_PATTERNS:
        m = pattern.search(text)
        if m:
            trigger.update({k: v for k, v in hint.items() if k != 'description'})
            if hint.get('condition') == 'within_range' and m.lastindex:
                try:
                    trigger['range_ft'] = int(m.group(1))
                except Exception:
                    pass
            # Capture a quoted command phrase for on_command triggers.
            if hint.get('event') == 'on_command':
                phrase_match = re.search(r"['\"“]([^'\"”]{1,40})['\"”]", text)
                if phrase_match:
                    trigger['command_phrase'] = phrase_match.group(1).strip()
            # Capture the object action sub_type for object_interaction triggers.
            if hint.get('event') == 'object_interaction':
                sub = re.search(r"\b(opens?|closes?|unlocks?)\b", text, re.I)
                if sub:
                    base = sub.group(1).lower()
                    trigger['object_action'] = (
                        'open' if base.startswith('open')
                        else 'close' if base.startswith('close')
                        else 'unlock'
                    )
            break

    action_spec: Dict[str, Any] = {'kind': 'attack', 'description': text.strip()}
    chosen_weapon = None
    lower = text.lower()

    # Item-use phrasings come first: "ready a healing potion", "use a potion".
    item_match = None
    if re.search(r"\b(potion|elixir|scroll|use\s+(?:a|an|the|my))\b", lower):
        # Try to match a specific inventory slug first.
        for item in usable_items:
            slug = (item.get('slug') or '').lower()
            if slug and slug.replace('_', ' ') in lower:
                item_match = slug
                break
        # Fallback to a healing potion if mentioned generically.
        if item_match is None and 'potion' in lower:
            for item in usable_items:
                slug = (item.get('slug') or '').lower()
                if 'healing_potion' in slug or 'potion' in slug:
                    item_match = slug
                    break
            if item_match is None:
                # Best-effort: 'healing_potion' is the canonical slug shipped
                # with the engine; the resolver will reject cleanly if the
                # entity does not actually carry one.
                item_match = 'healing_potion'
    if item_match:
        action_spec = {
            'kind': 'use_item',
            'item': item_match,
            'description': text.strip(),
        }
        return normalize_trigger(trigger), normalize_action_spec(action_spec)

    for w in weapons:
        if w and w.lower().replace('_', ' ') in lower:
            chosen_weapon = w
            break
    if chosen_weapon is None and weapons:
        chosen_weapon = weapons[0]
    action_spec['weapon'] = chosen_weapon

    # If a known spell name appears in the text, prefer a spell ready.
    for spell in spells:
        name = (spell.get('name') or '').lower().replace('_', ' ')
        if name and name in lower:
            action_spec = {
                'kind': 'spell',
                'spell': spell.get('name'),
                'at_level': spell.get('level'),
                'description': text.strip(),
            }
            break

    return normalize_trigger(trigger), normalize_action_spec(action_spec)


# --------------------------------------------------------------------------
# LLM-based parser
# --------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are the Dungeon Master adjudicating a player's Ready (Hold) action "
    "in D&D 5e. The player describes a trigger and what they want to do when "
    "the trigger fires. You must convert this into a structured JSON object. "
    "Return ONLY a JSON object with this exact shape:\n"
    "{\n"
    "  \"approved\": true|false,\n"
    "  \"reason\": \"brief in-character DM explanation\",\n"
    "  \"trigger\": {\n"
    "    \"event\": one of [\"movement\", \"start_of_turn\", \"attacked\", \"becomes_visible\", \"goes_down\", \"on_command\", \"object_interaction\", \"ally_attacks\"],\n"
    "    \"condition\": one of [\"always\", \"adjacent_to_self\", \"within_range\", \"starts_turn\"],\n"
    "    \"subject_filter\": one of [\"enemies\", \"allies\", \"any\"],\n"
    "    \"subject_uids\": [list of specific entity_uids if the player named one],\n"
    "    \"range_ft\": integer (only for within_range),\n"
    "    \"command_phrase\": string (only for on_command -- the spoken word/phrase to listen for, lowercased substring match),\n"
    "    \"object_action\": one of [\"open\", \"close\", \"unlock\"] (only for object_interaction),\n"
    "    \"object_uid\": string (only for object_interaction; entity_uid of a specific door/chest if the player named one),\n"
    "    \"attack_target_uid\": string (only for ally_attacks; entity_uid of a specific enemy to react to. Omit to react to any enemy your ally attacks),\n"
    "    \"description\": short paraphrase of the trigger\n"
    "  },\n"
    "  \"action_spec\": {\n"
    "    \"kind\": one of [\"attack\", \"spell\", \"move\", \"use_item\"],\n"
    "    \"weapon\": string (weapon slug from the equipped list, only for attack),\n"
    "    \"spell\": string (spell name from the available list, only for spell),\n"
    "    \"at_level\": integer (slot level used, only for spell),\n"
    "    \"item\": string (item slug from the usable_items list, only for use_item -- e.g. \"healing_potion\"),\n"
    "    \"description\": short paraphrase of the prepared action\n"
    "  }\n"
    "}\n"
    "Examples of valid trigger phrasings: \"if an enemy steps adjacent\" -> movement+adjacent_to_self+enemies; "
    "\"if my ally goes down\" -> goes_down+always+allies; "
    "\"if a hidden goblin becomes visible\" -> becomes_visible+always+enemies; "
    "\"when I shout 'now!'\" -> on_command+always+allies+command_phrase=\"now!\"; "
    "\"if anyone opens that door\" -> object_interaction+always+any+object_action=\"open\"; "
    "\"when my ally attacks the goblin, I attack it too\" -> ally_attacks+always+allies (set attack_target_uid to the goblin's uid if visible). "
    "For a familiar readying a healing potion when its owner drops, set kind=use_item, "
    "item=\"healing_potion\", trigger.event=goes_down, subject_filter=allies. "
    "Reject (set approved=false) if the player asks for something illegal in 5e: "
    "more than one reaction in a round; readying a multi-attack; readying an action "
    "they could not normally take on their turn; or a trigger that has no observable event. "
    "Reasoning must be brief and in-character."
)


def _build_messages(player_label: str, description: str,
                    weapons: List[str], spells: List[Dict[str, Any]],
                    enemies: List[Tuple[str, str]],
                    has_reaction: bool,
                    usable_items: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    return [
        {'role': 'system', 'content': _SYSTEM_PROMPT},
        {
            'role': 'user',
            'content': json.dumps({
                'player': player_label,
                'description': description,
                'equipped_weapons': weapons,
                'available_spells': spells,
                'usable_items': usable_items or [],
                'visible_enemies': [{'uid': uid, 'name': name} for uid, name in enemies],
                'has_reaction_available': bool(has_reaction),
                'allowed_events': list(SUPPORTED_TRIGGER_EVENTS),
                'allowed_action_kinds': list(SUPPORTED_ACTION_KINDS),
            }),
        },
    ]


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = str(text).strip()
    # Strip thinking blocks if a provider leaks them.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def parse_ready_action_request(entity, battle, description: str,
                               llm_handler=None) -> Dict[str, Any]:
    """Return ``{approved, reason, trigger, action_spec}`` for a player's Ready.

    Uses the configured LLM provider (via ``llm_handler.send_message``) when
    available; otherwise falls back to the rule-based heuristic. Always
    returns valid normalized structures so callers can pass them straight
    into ``ReadyAction``.
    """
    description = (description or '').strip()
    if not description:
        return {
            'approved': False,
            'reason': 'You must describe the trigger and what you intend to do.',
            'trigger': normalize_trigger(None),
            'action_spec': normalize_action_spec(None),
        }

    weapons = _entity_weapons(entity)
    spells = _entity_spells(entity)
    usable_items = _entity_usable_items(entity)
    enemies = _enemy_uids(entity, battle)
    has_reaction = entity.has_reaction(battle) if battle is not None else True

    parsed: Optional[dict] = None
    provider = getattr(llm_handler, 'current_provider', None)
    if provider is not None:
        try:
            messages = _build_messages(
                entity.label() if hasattr(entity, 'label') else getattr(entity, 'name', 'PC'),
                description, weapons, spells, enemies, has_reaction,
                usable_items=usable_items,
            )
            raw = llm_handler.send_message(messages)
            parsed = _extract_json(raw if isinstance(raw, str) else getattr(raw, 'content', None) or str(raw))
        except Exception as exc:
            logger.warning(f"Ready-action LLM parse failed: {exc}")
            parsed = None

    if parsed is None:
        trigger, action_spec = _heuristic_parse(description, weapons, spells, usable_items)
        return {
            'approved': True,
            'reason': 'You ready your action.',
            'trigger': trigger,
            'action_spec': action_spec,
        }

    approved = bool(parsed.get('approved', True))
    reason = str(parsed.get('reason') or '').strip() or 'You ready your action.'
    trigger = normalize_trigger(parsed.get('trigger'))
    action_spec = normalize_action_spec(parsed.get('action_spec'))

    if approved:
        # Final guard: refuse if the prepared action references an unknown
        # weapon/spell/item that the entity does not actually have.
        rejection = _validate_5e_legality(entity, action_spec, weapons, spells, usable_items)
        if rejection:
            approved = False
            reason = rejection
    if not trigger.get('description'):
        trigger['description'] = description
    if not action_spec.get('description'):
        action_spec['description'] = description
    return {
        'approved': approved,
        'reason': reason,
        'trigger': trigger,
        'action_spec': action_spec,
    }


def _normalize_slug(value) -> str:
    """Normalise a spell/weapon identifier for comparison.

    LLMs frequently return ``"shocking grasp"`` while the engine stores
    ``"shocking_grasp"``; match them by lowercasing and collapsing
    whitespace/hyphens to underscores.
    """
    if not value:
        return ''
    return re.sub(r"[\s\-]+", "_", str(value).strip().lower())


def _validate_5e_legality(entity, action_spec, weapons, spells,
                          usable_items: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    kind = action_spec.get('kind')
    if kind == 'attack':
        weapon = (action_spec.get('weapon') or '').strip()
        if weapon and weapons:
            wanted = _normalize_slug(weapon)
            known = {_normalize_slug(w) for w in weapons}
            if wanted and wanted not in known:
                return (f"You don't have {weapon} equipped, so you can't ready an "
                        'attack with it.')
    elif kind == 'spell':
        spell = (action_spec.get('spell') or '').strip()
        if spell and spells:
            wanted = _normalize_slug(spell)
            known = {_normalize_slug(s.get('name')) for s in spells}
            if wanted and wanted not in known:
                return (f"You don't have {spell} prepared, so you can't ready it.")
            # Snap the action_spec's spell back to the canonical slug so the
            # engine can find the spell definition at trigger time.
            for s in spells:
                if _normalize_slug(s.get('name')) == wanted:
                    action_spec['spell'] = s.get('name')
                    break
    elif kind == 'use_item':
        item = (action_spec.get('item') or '').strip()
        if not item:
            return "You must name the item you want to ready."
        items = usable_items or []
        wanted = _normalize_slug(item)
        known = {_normalize_slug(i.get('slug')) for i in items}
        if known and wanted not in known:
            return (f"You don't have a usable {item.replace('_', ' ')}, so you "
                    "can't ready it.")
        # Snap to canonical slug.
        for i in items:
            if _normalize_slug(i.get('slug')) == wanted:
                action_spec['item'] = i.get('slug')
                break
    return None


# --------------------------------------------------------------------------
# Trigger-time resolver
# --------------------------------------------------------------------------

def make_llm_resolver(llm_handler=None):
    """Return a resolver suitable for ``Battle.set_ready_action_resolver``.

    The resolver tries an LLM call first; if the LLM is unavailable or its
    pick is not legal, it falls back to ``natural20.ready_action.default_resolver``
    (which handles attack-the-trigger-source).
    """

    def _resolver(state: ReadyActionState, event_name: str,
                  event_payload: Dict[str, Any], battle, owner):
        provider = getattr(llm_handler, 'current_provider', None)
        if provider is None:
            return default_resolver(state, event_name, event_payload, battle, owner)
        # Currently we let the LLM influence target selection only via the
        # action_spec recorded at ready-time. Picking a fully different action
        # at fire time is a future enhancement; the deterministic resolver is
        # the safe path for now.
        return default_resolver(state, event_name, event_payload, battle, owner)

    return _resolver


__all__ = [
    'parse_ready_action_request',
    'make_llm_resolver',
]

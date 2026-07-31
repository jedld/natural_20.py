"""Campaign-configurable conversation item offer rules (no adventure-specific logic)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from natural20.utils.animal_communication import has_animal_communication
from natural20.utils.conversation import entity_label

OFFER_STATE_KEY = 'conversation_item_offers'

KNOWN_BLOCK_REASONS = frozenset({
    'target_has_item',
    'offer_completed',
    'target_effect_animal_communication',
    'actor_lacks_item',
    'listener_has_not_chosen',
    'guest_has_not_chosen_room',  # legacy alias
})

KNOWN_EFFECTS = frozenset({'animal_communication'})

_GENERIC_CHOICE_TOKENS = frozenset({'key', 'item', 'the', 'a', 'an', 'of', 'for'})

_BROWSE_INQUIRY = re.compile(
    r'\b(?:'
    r'do you have|have you got|would you have|got any|any\b.*\b(?:available|spare)|'
    r'what(?:\s+\w+){0,4}\s+(?:options|choices|rooms|kinds)|'
    r'(?:rooms?|options?)\s+(?:available|to spare|for rent)'
    r')\b',
    re.IGNORECASE,
)


def is_browse_inquiry(text: str) -> bool:
    """True when the listener is asking what is available, not choosing one item."""
    return bool(_BROWSE_INQUIRY.search(str(text or '')))


def _load_item_definition(session, item_slug: str) -> Dict[str, Any]:
    if session is None or not item_slug:
        return {}
    try:
        raw = session.load_equipment(item_slug) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _item_conversation_offer_cfg(
    item_slug: str,
    *,
    session=None,
    game_properties=None,
    actor=None,
) -> Dict[str, Any]:
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    offer = cfg.get('conversation_offer')
    if isinstance(offer, dict):
        return offer
    return _load_item_definition(session, item_slug).get('conversation_offer') or {}


def _sibling_numbered_offer_slugs(actor, item_slug: str) -> List[str]:
    """Inventory slugs sharing the same ``prefix_N`` pattern (e.g. room_key_1..4)."""
    slug = str(item_slug or '').strip().lower()
    match = re.match(r'(.+)_(\d+)$', slug)
    if not match or actor is None:
        return []
    base = match.group(1)
    siblings: List[str] = []
    for carried in (getattr(actor, 'inventory', None) or {}):
        carried = str(carried).strip().lower()
        if re.fullmatch(rf'{re.escape(base)}_\d+', carried) and _inventory_qty(actor, carried) > 0:
            siblings.append(carried)
    return sorted(set(siblings))


def requires_listener_disambiguation(
    session,
    actor,
    item_slug: str,
    *,
    game_properties=None,
) -> bool:
    """True when the listener must pick among similar carried items before an offer."""
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    offer = _item_conversation_offer_cfg(
        item_slug,
        session=session,
        game_properties=game_properties,
        actor=actor,
    )
    if offer.get('require_listener_choice') is False or cfg.get('require_listener_choice') is False:
        return False
    if (
        offer.get('require_listener_choice')
        or cfg.get('require_listener_choice')
        or cfg.get('require_room_selection')  # legacy campaign key
    ):
        return True
    return len(_sibling_numbered_offer_slugs(actor, item_slug)) > 1


def listener_chose_item(
    session,
    item_slug: str,
    player_message: str,
    *,
    actor=None,
    game_properties=None,
) -> bool:
    """True when the listener's latest message clearly requests this specific item."""
    text = str(player_message or '').strip()
    if not text:
        return False
    lowered = text.lower()
    slug = str(item_slug or '').strip().lower()
    if not slug:
        return False
    if slug in lowered or slug.replace('_', ' ') in lowered:
        return True

    cfg = offer_config_for_item(slug, game_properties=game_properties, actor=actor)
    item_def = _load_item_definition(session, slug)
    name = str(item_def.get('name') or cfg.get('item_label') or '').strip().lower()
    if name and name in lowered:
        return True

    offer = _item_conversation_offer_cfg(
        slug,
        session=session,
        game_properties=game_properties,
        actor=actor,
    )
    for raw in offer.get('choice_patterns') or []:
        try:
            if re.search(str(raw), text, re.IGNORECASE):
                return True
        except re.error:
            continue

    suffix_match = re.search(r'_(\d+)$', slug)
    if suffix_match and re.search(rf'\b{re.escape(suffix_match.group(1))}\b', lowered):
        return True

    for token in slug.split('_'):
        if len(token) < 4 or token in _GENERIC_CHOICE_TOKENS:
            continue
        if re.search(rf'\b{re.escape(token)}\b', lowered):
            return True
    return False


def is_player_character(entity) -> bool:
    if entity is None:
        return False
    try:
        from natural20.player_character import PlayerCharacter

        return isinstance(entity, PlayerCharacter)
    except Exception:
        return False


def prefer_player_character_for_item(
    item_slug: str,
    *,
    game_properties=None,
    actor=None,
) -> bool:
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    return bool(cfg.get('prefer_player_character'))


def adjust_item_offer_target(
    resolved_target,
    *,
    target_spec: str,
    speaker=None,
    player_speaker=None,
    item_slug: str,
    game_properties=None,
    actor=None,
):
    """When configured, route ``target=speaker`` offers to the engaging PC, not an NPC relay."""
    if not prefer_player_character_for_item(
        item_slug,
        game_properties=game_properties,
        actor=actor,
    ):
        return resolved_target
    if player_speaker is None or not is_player_character(player_speaker):
        return resolved_target
    if resolved_target is not None and is_player_character(resolved_target):
        return resolved_target

    spec = str(target_spec or '').strip().lower().lstrip('@')
    if spec not in ('', 'speaker', 'you'):
        return resolved_target

    return player_speaker


def _entity_properties(entity) -> Dict[str, Any]:
    props = getattr(entity, 'properties', None)
    return props if isinstance(props, dict) else {}


def _campaign_offer_config(game_properties: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(game_properties, dict):
        return {}
    raw = game_properties.get('conversation_item_offers')
    return raw if isinstance(raw, dict) else {}


def _entity_offer_config(entity) -> Dict[str, Any]:
    raw = _entity_properties(entity).get('conversation_item_offers')
    return raw if isinstance(raw, dict) else {}


def merged_offer_configs(game_properties=None, actor=None) -> Dict[str, Dict[str, Any]]:
    """Campaign rules merged with optional per-NPC overrides (NPC wins on conflict)."""
    merged = dict(_campaign_offer_config(game_properties))
    merged.update(_entity_offer_config(actor))
    return merged


def canonical_item_slug(item_raw: str, offer_configs: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    slug = str(item_raw or '').strip().lower().replace(' ', '_')
    if not slug:
        return ''
    configs = offer_configs or {}
    for canonical, cfg in configs.items():
        if not isinstance(cfg, dict):
            continue
        aliases = cfg.get('aliases') if isinstance(cfg.get('aliases'), list) else []
        alias_set = {str(a).strip().lower().replace(' ', '_') for a in aliases if a}
        alias_set.add(str(canonical).strip().lower())
        if slug in alias_set:
            return str(canonical).strip().lower()
    return slug


def offer_config_for_item(
    item_slug: str,
    *,
    game_properties=None,
    actor=None,
) -> Dict[str, Any]:
    slug = str(item_slug or '').strip().lower()
    if not slug:
        return {}
    configs = merged_offer_configs(game_properties, actor)
    cfg = configs.get(slug)
    return cfg if isinstance(cfg, dict) else {}


def _inventory_qty(entity, item_slug: str) -> int:
    try:
        inventory = getattr(entity, 'inventory', {}) or {}
        return int((inventory.get(item_slug) or {}).get('qty') or 0)
    except (TypeError, ValueError):
        return 0


def _offer_record_key(actor, target, item_slug: str) -> str:
    actor_uid = str(getattr(actor, 'entity_uid', '') or '')
    target_uid = str(getattr(target, 'entity_uid', '') or '')
    return f"{actor_uid}:{target_uid}:{item_slug}"


def has_completed_item_offer(session, actor, target, item_slug: str) -> bool:
    try:
        state = session.load_state(OFFER_STATE_KEY) or {}
    except Exception:
        state = {}
    completed = state.get('completed') if isinstance(state.get('completed'), dict) else {}
    return bool(completed.get(_offer_record_key(actor, target, item_slug)))


def record_completed_item_offer(session, actor, target, item_slug: str) -> None:
    try:
        state = session.load_state(OFFER_STATE_KEY) or {}
    except Exception:
        state = {}
    if not isinstance(state, dict):
        state = {}
    completed = state.get('completed') if isinstance(state.get('completed'), dict) else {}
    completed[_offer_record_key(actor, target, item_slug)] = int(
        getattr(session, 'game_time', 0) or 0
    )
    state['completed'] = completed
    try:
        session.save_state(OFFER_STATE_KEY, state)
    except Exception:
        pass


def evaluate_offer_block(
    session,
    actor,
    target,
    item_slug: str,
    *,
    game_properties=None,
    actor_has_map_item: bool = False,
    player_message: str = '',
) -> Tuple[bool, str]:
    """Return (allowed, reason). reason is 'ok' when allowed."""
    if actor is None or target is None or not item_slug:
        return False, 'missing_entities'

    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    block_when = cfg.get('block_when') if isinstance(cfg.get('block_when'), list) else []
    if not block_when:
        block_when = ['offer_completed', 'target_has_item']

    if requires_listener_disambiguation(session, actor, item_slug, game_properties=game_properties):
        if not listener_chose_item(
            session,
            item_slug,
            player_message,
            actor=actor,
            game_properties=game_properties,
        ):
            return False, 'listener_has_not_chosen'

    if (
        player_message
        and is_browse_inquiry(player_message)
        and not listener_chose_item(
            session,
            item_slug,
            player_message,
            actor=actor,
            game_properties=game_properties,
        )
    ):
        return False, 'listener_has_not_chosen'

    if 'offer_completed' in block_when and has_completed_item_offer(session, actor, target, item_slug):
        return False, 'offer_completed'

    if 'target_has_item' in block_when and _inventory_qty(target, item_slug) > 0:
        return False, 'target_has_item'

    actor_qty = _inventory_qty(actor, item_slug)
    if actor_qty <= 0 and not actor_has_map_item:
        return False, 'actor_lacks_item'

    if 'target_effect_animal_communication' in block_when and has_animal_communication(
        session,
        entity=target,
    ):
        return False, 'target_effect_animal_communication'

    return True, 'ok'


def _format_guidance(
    template: str,
    *,
    actor,
    target,
    item_slug: str,
    cfg: Dict[str, Any],
    available_items: str = '',
) -> str:
    item_label = str(cfg.get('item_label') or item_slug.replace('_', ' '))
    return (
        template.replace('{target}', entity_label(target) if target is not None else 'the listener')
        .replace('{actor}', entity_label(actor) if actor is not None else 'You')
        .replace('{item}', item_slug)
        .replace('{item_label}', item_label)
        .replace('{available_items}', available_items or 'none on your person or within reach')
    )


def enumerate_actor_offerable_items(
    actor,
    *,
    game_properties=None,
    actor_has_map_item_fn=None,
) -> List[str]:
    """Return item slugs the actor can currently hand over."""
    found: List[str] = []
    seen = set()
    configs = merged_offer_configs(game_properties, actor)

    for slug in (getattr(actor, 'inventory', None) or {}):
        if _inventory_qty(actor, slug) > 0 and slug not in seen:
            found.append(str(slug))
            seen.add(str(slug))

    if actor_has_map_item_fn:
        for slug in configs:
            slug = str(slug)
            if slug in seen:
                continue
            if _inventory_qty(actor, slug) > 0:
                found.append(slug)
                seen.add(slug)
                continue
            if actor_has_map_item_fn(actor, slug):
                found.append(slug)
                seen.add(slug)

    return sorted(found)


def format_available_offer_items(
    actor,
    *,
    game_properties=None,
    actor_has_map_item_fn=None,
) -> str:
    """Human-readable list of items the actor can offer right now."""
    slugs = enumerate_actor_offerable_items(
        actor,
        game_properties=game_properties,
        actor_has_map_item_fn=actor_has_map_item_fn,
    )
    if not slugs:
        return 'none on your person or within reach'

    parts: List[str] = []
    for slug in slugs:
        qty = _inventory_qty(actor, slug)
        cfg = offer_config_for_item(slug, game_properties=game_properties, actor=actor)
        label = str(cfg.get('item_label') or slug.replace('_', ' '))
        if qty > 1:
            parts.append(f'{label} ({slug}, x{qty})')
        else:
            parts.append(f'{label} ({slug})')
    return '; '.join(parts)


def item_offer_suppression_note(
    actor,
    target,
    item_slug: str,
    block_reason: str,
    *,
    game_properties=None,
    actor_has_map_item_fn=None,
) -> Optional[str]:
    """System note for the offering NPC when an [OFFER_ITEM] directive was blocked."""
    if not block_reason or block_reason == 'ok':
        return None

    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    item_label = str(cfg.get('item_label') or item_slug.replace('_', ' '))
    target_name = entity_label(target) if target is not None else 'the listener'
    available_items = format_available_offer_items(
        actor,
        game_properties=game_properties,
        actor_has_map_item_fn=actor_has_map_item_fn,
    )

    guidance_map: Dict[str, Any] = {}
    if isinstance(game_properties, dict):
        raw = game_properties.get('conversation_offer_guidance')
        if isinstance(raw, dict):
            guidance_map.update(raw)
    per_item = cfg.get('guidance_when_blocked')
    if isinstance(per_item, dict):
        for key, template in per_item.items():
            guidance_map.setdefault(str(key), template)

    if block_reason == 'actor_lacks_item':
        return (
            f'Your offer of {item_label} to {target_name} could not be completed — '
            f'you are not carrying {item_slug} and cannot reach it. '
            f'Items you can hand over instead: {available_items}. '
            'Use [OFFER_ITEM: item=<correct_slug>, target=speaker] with one of those; '
            'do not tell the guest you handed something over unless the offer succeeds.'
        )

    if block_reason in ('listener_has_not_chosen', 'guest_has_not_chosen_room'):
        return (
            f'Your offer of {item_label} to {target_name} was blocked — they have not '
            f'clearly chosen that specific item yet. Describe the options and wait for '
            f'their next message to name which one they want (and take payment if needed), '
            f'then use [OFFER_ITEM: item={item_slug}, target=speaker]. Do not use '
            '[OFFER_ITEM] while you are only answering what is available.'
        )

    template = guidance_map.get(block_reason) or guidance_map.get(f'{block_reason}:{item_slug}')
    if template:
        return _format_guidance(
            str(template),
            actor=actor,
            target=target,
            item_slug=item_slug,
            cfg=cfg,
            available_items=available_items,
        )

    return (
        f'Your offer of {item_label} to {target_name} was blocked ({block_reason}). '
        f'Items you can hand over instead: {available_items}.'
    )


def _offer_evaluation_target(speaker, player_speaker, cfg: Dict[str, Any]):
    if cfg.get('prefer_player_character') and player_speaker is not None:
        return player_speaker
    return speaker


def offer_guidance_lines(
    session,
    actor,
    speaker=None,
    *,
    player_speaker=None,
    game_properties=None,
    actor_has_map_item_fn=None,
    player_message: str = '',
) -> List[str]:
    """Prompt lines for the LLM based on campaign/entity offer config."""
    lines = [
        "- Use [OFFER_ITEM] only when you can hand the item over: it is in your inventory, in an open container within reach, or you will [RETRIEVE] it first in the same reply.",
        "- When an item is stocked behind a counter or shelf, use [RETRIEVE: item=<slug>, target=@container, qty=1] before [OFFER_ITEM] if you are not already carrying it.",
        "- Never repeat an item offer after the listener has accepted it.",
        "- Never use [OFFER_ITEM] in the same reply where you list multiple options and ask which they want — wait for their next message to name the specific item.",
        "- Only use [OFFER_ITEM] after the listener clearly requests that item (by name, number, or distinguishing detail in their latest message).",
    ]
    available_items = format_available_offer_items(
        actor,
        game_properties=game_properties,
        actor_has_map_item_fn=actor_has_map_item_fn,
    )
    if available_items != 'none on your person or within reach':
        lines.append(f"- Items you can hand over right now: {available_items}.")
    configs = merged_offer_configs(game_properties, actor)
    guidance_map = {}
    if isinstance(game_properties, dict):
        raw = game_properties.get('conversation_offer_guidance')
        if isinstance(raw, dict):
            guidance_map.update(raw)

    disambiguation_slugs = set()
    for carried in (getattr(actor, 'inventory', None) or {}):
        carried = str(carried).strip().lower()
        if requires_listener_disambiguation(session, actor, carried, game_properties=game_properties):
            disambiguation_slugs.add(carried)
    for item_slug in sorted(disambiguation_slugs):
        cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
        item_label = str(cfg.get('item_label') or item_slug.replace('_', ' '))
        if listener_chose_item(
            session,
            item_slug,
            player_message,
            actor=actor,
            game_properties=game_properties,
        ):
            lines.append(
                f"- Listener chose {item_label}; you may use "
                f"[OFFER_ITEM: item={item_slug}, target=speaker] once terms are settled."
            )
        else:
            lines.append(
                f"- Do not use [OFFER_ITEM: item={item_slug}, ...] yet — the listener has not "
                f'named {item_label} in their latest message. Present options and wait.'
            )

    for item_slug, cfg in configs.items():
        if not isinstance(cfg, dict):
            continue
        per_item = cfg.get('guidance_when_blocked')
        if isinstance(per_item, dict):
            for key, template in per_item.items():
                guidance_map.setdefault(key, template)

        has_map_item = bool(actor_has_map_item_fn(actor, item_slug)) if actor_has_map_item_fn else False
        if _inventory_qty(actor, item_slug) <= 0 and not has_map_item:
            template = guidance_map.get('actor_lacks_item') or guidance_map.get(f"actor_lacks_item:{item_slug}")
            if template:
                lines.append(
                    _format_guidance(
                        str(template),
                        actor=actor,
                        target=speaker,
                        item_slug=item_slug,
                        cfg=cfg,
                        available_items=available_items,
                    )
                )
            continue

        evaluation_target = _offer_evaluation_target(speaker, player_speaker, cfg)
        if evaluation_target is None:
            continue

        allowed, reason = evaluate_offer_block(
            session,
            actor,
            evaluation_target,
            item_slug,
            game_properties=game_properties,
            actor_has_map_item=has_map_item,
            player_message=player_message,
        )
        if allowed:
            if cfg.get('prefer_player_character') and is_player_character(player_speaker):
                try:
                    from natural20.utils.conversation import mention_handle_for

                    handle = mention_handle_for(player_speaker)
                except Exception:
                    handle = getattr(player_speaker, 'entity_uid', 'adventurer')
                item_label = str(cfg.get('item_label') or item_slug.replace('_', ' '))
                lines.append(
                    f"- For {item_label}, use [OFFER_ITEM: item={item_slug}, target=@{handle}] "
                    "for the adventurer who came to help — not tavern staff or other NPCs "
                    "who are only relaying speech."
                )
            continue
        template = guidance_map.get(reason) or guidance_map.get(f"{reason}:{item_slug}")
        if template:
            lines.append(
                _format_guidance(
                    str(template),
                    actor=actor,
                    target=evaluation_target,
                    item_slug=item_slug,
                    cfg=cfg,
                    available_items=available_items,
                )
            )

    return lines


def accept_effect_for_item(item_slug: str, *, game_properties=None, actor=None) -> Optional[str]:
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    effect = str(cfg.get('accept_effect') or '').strip()
    return effect or None


def on_accept_auto_use(item_slug: str, *, game_properties=None, actor=None) -> bool:
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    return bool(cfg.get('on_accept_auto_use'))


def item_offer_resolution_note(
    actor,
    target,
    item_slug: str,
    *,
    accepted: bool,
    effect_message: Optional[str] = None,
    game_properties=None,
) -> str:
    """System note for the offering NPC after a player accepts or declines."""
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    item_label = str(cfg.get('item_label') or item_slug.replace('_', ' '))
    target_name = entity_label(target) if target is not None else 'the listener'

    if not accepted:
        return (
            f"{target_name} declined your offered {item_label}. "
            "React in character if appropriate; do not offer the same item again unless they ask."
        )

    if effect_message:
        return (
            f"{effect_message} They can understand your beast/sheep speech now. "
            f"Do not offer the {item_label} again or repeat how to use it. "
            "Continue in [in sheep] with clear dialogue they can understand."
        )

    return (
        f"{target_name} accepted your offered {item_label}. "
        f"Do not use [OFFER_ITEM: item={item_slug}, ...] again for them. "
        "If they still need to use it, urge them to do so from their inventory."
    )

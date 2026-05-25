"""Campaign-configurable conversation item offer rules (no adventure-specific logic)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from natural20.utils.animal_communication import has_animal_communication
from natural20.utils.conversation import entity_label

OFFER_STATE_KEY = 'conversation_item_offers'

KNOWN_BLOCK_REASONS = frozenset({
    'target_has_item',
    'offer_completed',
    'target_effect_animal_communication',
    'actor_lacks_item',
})

KNOWN_EFFECTS = frozenset({'animal_communication'})


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
) -> Tuple[bool, str]:
    """Return (allowed, reason). reason is 'ok' when allowed."""
    if actor is None or target is None or not item_slug:
        return False, 'missing_entities'

    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    block_when = cfg.get('block_when') if isinstance(cfg.get('block_when'), list) else []
    if not block_when:
        block_when = ['offer_completed', 'target_has_item']

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


def _format_guidance(template: str, *, actor, target, item_slug: str, cfg: Dict[str, Any]) -> str:
    item_label = str(cfg.get('item_label') or item_slug.replace('_', ' '))
    return (
        template.replace('{target}', entity_label(target) if target is not None else 'the listener')
        .replace('{actor}', entity_label(actor) if actor is not None else 'You')
        .replace('{item}', item_slug)
        .replace('{item_label}', item_label)
    )


def offer_guidance_lines(
    session,
    actor,
    speaker=None,
    *,
    game_properties=None,
    actor_has_map_item_fn=None,
) -> List[str]:
    """Prompt lines for the LLM based on campaign/entity offer config."""
    lines = [
        "- Only use [OFFER_ITEM] when you physically have the item to give and the listener does not already have it.",
        "- Never repeat an item offer after the listener has accepted it.",
    ]
    configs = merged_offer_configs(game_properties, actor)
    guidance_map = {}
    if isinstance(game_properties, dict):
        raw = game_properties.get('conversation_offer_guidance')
        if isinstance(raw, dict):
            guidance_map.update(raw)

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
                lines.append(_format_guidance(str(template), actor=actor, target=speaker, item_slug=item_slug, cfg=cfg))
            continue

        if speaker is None:
            continue

        allowed, reason = evaluate_offer_block(
            session,
            actor,
            speaker,
            item_slug,
            game_properties=game_properties,
            actor_has_map_item=has_map_item,
        )
        if allowed:
            continue
        template = guidance_map.get(reason) or guidance_map.get(f"{reason}:{item_slug}")
        if template:
            lines.append(_format_guidance(str(template), actor=actor, target=speaker, item_slug=item_slug, cfg=cfg))

    return lines


def accept_effect_for_item(item_slug: str, *, game_properties=None, actor=None) -> Optional[str]:
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    effect = str(cfg.get('accept_effect') or '').strip()
    return effect or None


def on_accept_auto_use(item_slug: str, *, game_properties=None, actor=None) -> bool:
    cfg = offer_config_for_item(item_slug, game_properties=game_properties, actor=actor)
    return bool(cfg.get('on_accept_auto_use'))

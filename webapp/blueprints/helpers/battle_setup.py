"""Helpers for battle setup (initiative / combatant lists)."""

from __future__ import annotations

def augment_turn_order_with_party_pcs(current_game, battle_map, turn_order):
    """Ensure every party PC on the active map is in the manual turn-order payload."""
    present = set()
    augmented = []
    for item in turn_order or []:
        if not isinstance(item, dict):
            continue
        uid = str(item.get('id') or '')
        if not uid:
            continue
        normalized = dict(item)
        normalized['id'] = uid
        augmented.append(normalized)
        present.add(uid)

    for entity, group in current_game.party_player_characters_on_map(battle_map):
        uid = str(entity.entity_uid)
        if uid in present:
            continue
        augmented.append({'id': uid, 'group': group})
        present.add(uid)

    return augmented

"""Build a display payload for the character-sheet item card modal."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from natural20.utils.merchant import parse_item_cost
from natural20.weapon_mastery import MASTERY_BLURBS, MASTERY_LABELS

TYPE_LABELS = {
    'melee_attack': 'Melee Weapon',
    'ranged_attack': 'Ranged Weapon',
    'armor': 'Armor',
    'shield': 'Shield',
    'potion': 'Potion',
    'scroll': 'Scroll',
    'tool': 'Tool',
    'ammunition': 'Ammunition',
    'letter': 'Letter',
    'currency': 'Currency',
    'provisions': 'Provisions',
    'gear': 'Adventuring Gear',
    'arcane_focus': 'Arcane Focus',
    'spellbook': 'Spellbook',
    'accessory': 'Wondrous Item',
    'container': 'Container',
    'parchment': 'Parchment',
}

RARITY_LABELS = {
    'common': 'Common',
    'uncommon': 'Uncommon',
    'rare': 'Rare',
    'very_rare': 'Very Rare',
    'legendary': 'Legendary',
    'artifact': 'Artifact',
}

WEAPON_TYPES = frozenset({'melee_attack', 'ranged_attack'})
ARMOR_TYPES = frozenset({'armor', 'shield'})


def _title_token(value) -> str:
    text = str(value or '').replace('_', ' ').strip()
    return text.title() if text else ''


def _as_list(value) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def format_item_cost(cost) -> Optional[str]:
    """Pretty-print YAML ``cost`` as gp/sp/cp."""
    if cost is None or cost == '':
        return None
    original = str(cost).strip() if isinstance(cost, str) else None
    try:
        gp = parse_item_cost(cost)
    except (TypeError, ValueError):
        return original or str(cost)
    if gp <= 0:
        return None
    if gp >= 1:
        return f"{int(gp)} gp" if gp == int(gp) else f"{gp:g} gp"
    sp = gp * 10
    if abs(sp - round(sp)) < 1e-9 and round(sp) >= 1:
        return f"{int(round(sp))} sp"
    cp = gp * 100
    if abs(cp - round(cp)) < 1e-9:
        return f"{int(round(cp))} cp"
    return f"{gp:g} gp"


def item_icon_url(item: Dict[str, Any], item_name: str) -> str:
    if item.get('icon'):
        return str(item['icon'])
    image = item.get('image') or item_name
    return f"/assets/items/{image}.png"


def _flavor_text(item: Dict[str, Any]) -> Optional[str]:
    for key in ('flavor_text', 'flavor', 'lore', 'quote'):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _stealth_disadvantage(item: Dict[str, Any]) -> bool:
    if item.get('stealth_disadvantage'):
        return True
    disadvantage = _as_list(item.get('disadvantage'))
    return 'stealth' in [str(entry).lower() for entry in disadvantage]


def _range_label(normal, maximum=None) -> Optional[str]:
    if normal is None and maximum is None:
        return None
    if maximum:
        return f"{normal}/{maximum} ft"
    if normal is None:
        return None
    return f"{normal} ft"


def _effect_list(item: Dict[str, Any]) -> List[str]:
    effect = item.get('effect')
    if not effect:
        return []
    if isinstance(effect, str):
        return [effect]
    if isinstance(effect, (list, tuple)):
        return [str(entry) for entry in effect if entry]
    return [str(effect)]


def _weapon_masteries(entity, item: Dict[str, Any]) -> List[Dict[str, Any]]:
    session = getattr(entity, 'session', None)
    ruleset = getattr(session, 'ruleset', None) if session is not None else None
    if ruleset is None or not hasattr(ruleset, 'weapon_mastery_enabled'):
        return []
    try:
        if not ruleset.weapon_mastery_enabled():
            return []
    except TypeError:
        return []

    raw = item.get('weapon_mastery') or item.get('mastery') or []
    names = [str(name).lower() for name in _as_list(raw) if name]
    if not names:
        return []

    known = entity.properties.get('known_weapon_masteries') if getattr(entity, 'properties', None) else None
    has_feature = False
    if hasattr(entity, 'class_feature'):
        try:
            has_feature = bool(entity.class_feature('weapon_mastery'))
        except Exception:
            has_feature = False

    rows = []
    for name in names:
        trained = (known is None and has_feature) or (known and name in known)
        rows.append({
            'id': name,
            'label': MASTERY_LABELS.get(name, _title_token(name)),
            'blurb': MASTERY_BLURBS.get(name, ''),
            'trained': bool(trained),
        })
    return rows


def _to_hit_label(entity, item: Dict[str, Any], item_name: str) -> Optional[str]:
    if item.get('type') not in WEAPON_TYPES:
        return None
    if not hasattr(entity, 'attack_roll_mod'):
        return None
    weapon = dict(item)
    weapon['name'] = item_name
    try:
        modifier = entity.attack_roll_mod(weapon)
    except Exception:
        return None
    if modifier is None:
        return None
    return f"+{modifier}" if modifier >= 0 else str(modifier)


def _stat_rows(entity, item: Dict[str, Any], item_name: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    item_type = item.get('type')

    if item_type in WEAPON_TYPES:
        damage = item.get('damage')
        damage_type = item.get('damage_type')
        magic_bonus = item.get('magic_bonus') or 0
        damage_label = str(damage) if damage is not None else None
        if damage_label and magic_bonus:
            damage_label = f"{damage_label} +{magic_bonus}"
        if damage_label and damage_type:
            damage_label = f"{damage_label} {damage_type}"
        elif damage_type and not damage_label:
            damage_label = str(damage_type)
        if damage_label:
            rows.append({'label': 'Damage', 'value': damage_label})
        if item.get('damage_2'):
            rows.append({'label': 'Versatile', 'value': str(item['damage_2'])})
        to_hit = _to_hit_label(entity, item, item_name)
        if to_hit:
            rows.append({'label': 'To Hit', 'value': to_hit})
        reach = _range_label(item.get('range'), item.get('range_max'))
        if reach:
            label = 'Range' if item_type == 'ranged_attack' or item.get('range_max') else 'Reach'
            rows.append({'label': label, 'value': reach})
        thrown = item.get('thrown') if isinstance(item.get('thrown'), dict) else None
        if thrown:
            thrown_range = _range_label(thrown.get('range'), thrown.get('range_max'))
            if thrown_range:
                rows.append({'label': 'Thrown', 'value': thrown_range})
        if item.get('ammo'):
            rows.append({'label': 'Ammunition', 'value': _title_token(item['ammo'])})

    if item_type in ARMOR_TYPES or item.get('ac') is not None or item.get('bonus_ac') is not None:
        ac = item.get('ac') if item.get('ac') is not None else item.get('bonus_ac')
        magic_bonus = item.get('magic_bonus') or 0
        ac_label = str(ac) if ac is not None else None
        if ac_label and magic_bonus:
            ac_label = f"{ac_label} (+{magic_bonus})"
        if ac_label:
            rows.append({'label': 'AC', 'value': ac_label})
        if item.get('subtype') and item_type == 'armor':
            rows.append({'label': 'Armor Type', 'value': _title_token(item['subtype'])})
        if _stealth_disadvantage(item):
            rows.append({'label': 'Stealth', 'value': 'Disadvantage'})

    if item.get('hp_regained'):
        rows.append({'label': 'Healing', 'value': str(item['hp_regained'])})

    light = item.get('light')
    if isinstance(light, dict):
        bright = light.get('bright')
        dim = light.get('dim')
        parts = []
        if bright:
            parts.append(f"{bright} ft bright")
        if dim:
            parts.append(f"{dim} ft dim")
        if parts:
            rows.append({'label': 'Light', 'value': ', '.join(parts)})

    return rows


def _container_contents_for_card(entity, item_name: str) -> Optional[List[Dict[str, Any]]]:
    if entity is None or not hasattr(entity, 'is_container'):
        return None
    session = getattr(entity, 'session', None)
    try:
        if not entity.is_container(item_name, session):
            return None
    except Exception:
        return None
    contents = []
    raw_contents = []
    if hasattr(entity, 'get_container_contents'):
        try:
            raw_contents = entity.get_container_contents(item_name) or []
        except Exception:
            raw_contents = []
    for content in raw_contents:
        content_type = content.get('type') or content.get('item')
        if not content_type or content.get('is_creature'):
            continue
        try:
            nested_qty = int(content.get('qty', 0) or 0)
        except (TypeError, ValueError):
            nested_qty = 0
        if nested_qty <= 0:
            continue
        definition = {}
        if session is not None and hasattr(session, 'load_thing'):
            try:
                definition = session.load_thing(content_type) or {}
            except Exception:
                definition = {}
        can_equip = False
        if hasattr(entity, 'check_equip'):
            try:
                can_equip = entity.check_equip(content_type) == 'ok'
            except Exception:
                can_equip = False
        contents.append({
            'name': content_type,
            'label': content.get('label') or definition.get('label') or definition.get('name') or _title_token(content_type),
            'icon': item_icon_url(definition, content_type),
            'qty': nested_qty,
            'weight': content.get('weight', definition.get('weight')),
            'usable': bool(definition.get('usable')),
            'consumable': bool(definition.get('consumable')),
            'equippable': can_equip,
            'type': definition.get('type'),
            'container': item_name,
        })
    return contents


def _owned_qty(entity, item_name: str, container_name: Optional[str] = None) -> int:
    if entity is None:
        return 0
    if container_name and hasattr(entity, 'get_container_contents'):
        total = 0
        try:
            for content in entity.get_container_contents(container_name) or []:
                content_type = content.get('type') or content.get('item')
                if content_type != item_name:
                    continue
                try:
                    total += int(content.get('qty', 0) or 0)
                except (TypeError, ValueError):
                    continue
        except Exception:
            return 0
        return total
    if hasattr(entity, 'item_count'):
        try:
            return int(entity.item_count(item_name) or 0)
        except Exception:
            return 0
    inventory = getattr(entity, 'inventory', None) or {}
    try:
        return int((inventory.get(item_name) or {}).get('qty', 0) or 0)
    except (TypeError, ValueError):
        return 0


def build_item_card(entity, item_name: str, container_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return a template-ready dict for ``item_name``, or ``None`` if unknown."""
    if not item_name or entity is None:
        return None
    session = getattr(entity, 'session', None)
    if session is None or not hasattr(session, 'load_thing'):
        return None
    try:
        item = session.load_thing(item_name)
    except Exception:
        item = None
    if not item:
        return None

    item_type = item.get('type')
    rarity = item.get('rarity')
    proficiency = _as_list(item.get('proficiency_type'))
    properties = [_title_token(prop) for prop in _as_list(item.get('properties')) if prop]
    inventory = getattr(entity, 'inventory', None) or {}
    qty = _owned_qty(entity, item_name, container_name)
    container_label = None
    if container_name:
        container_def = {}
        try:
            container_def = session.load_thing(container_name) or {}
        except Exception:
            container_def = {}
        container_entry = inventory.get(container_name) or {}
        container_label = (
            container_entry.get('label')
            or container_def.get('label')
            or container_def.get('name')
            or _title_token(container_name)
        )

    equipped_names = set()
    if hasattr(entity, 'equipped_items'):
        try:
            equipped_names = {row.get('name') for row in (entity.equipped_items() or [])}
        except Exception:
            equipped_names = set()

    charges = None
    if hasattr(entity, 'item_charge_summary'):
        try:
            charges = entity.item_charge_summary(item_name)
        except Exception:
            charges = None

    attunement_bits = []
    if item.get('attunement_class'):
        attunement_bits.append(_title_token(item['attunement_class']))
    if item.get('attunement_race'):
        attunement_bits.append(_title_token(item['attunement_race']))
    attunement_note = None
    if item.get('requires_attunement'):
        attunement_note = 'Requires attunement'
        if attunement_bits:
            attunement_note = f"Requires attunement by a {' or '.join(attunement_bits)}"

    category = 'gear'
    if item_type in WEAPON_TYPES:
        category = 'weapon'
    elif item_type in ARMOR_TYPES:
        category = 'armor'
    elif item_type in ('potion', 'scroll'):
        category = item_type
    elif item.get('magical'):
        category = 'magic'

    can_equip = bool(item.get('equippable'))
    if hasattr(entity, 'check_equip'):
        try:
            can_equip = entity.check_equip(item_name) == 'ok'
        except Exception:
            can_equip = False

    contents = _container_contents_for_card(entity, item_name)

    return {
        'name': item_name,
        'label': item.get('label') or item.get('name') or _title_token(item_name),
        'icon': item_icon_url(item, item_name),
        'type': item_type,
        'type_label': TYPE_LABELS.get(item_type, _title_token(item_type) or 'Item'),
        'subtype': item.get('subtype'),
        'subtype_label': _title_token(item.get('subtype')),
        'category': category,
        'proficiency_label': ', '.join(_title_token(entry) for entry in proficiency if entry),
        'rarity': rarity,
        'rarity_label': RARITY_LABELS.get(str(rarity).lower(), _title_token(rarity)) if rarity else None,
        'magical': bool(item.get('magical') or (item.get('magic_bonus') or 0)),
        'magic_bonus': item.get('magic_bonus') or 0,
        'requires_attunement': bool(item.get('requires_attunement')),
        'attunement_note': attunement_note,
        'flavor': _flavor_text(item),
        'description': (item.get('description') or '').strip() or None,
        'content': (item.get('content') or '').strip() or None,
        'effect': _effect_list(item),
        'stats': _stat_rows(entity, item, item_name),
        'properties': properties,
        'masteries': _weapon_masteries(entity, item),
        'weight': item.get('weight'),
        'cost_label': format_item_cost(item.get('cost')),
        'qty': qty if qty > 0 else 1,
        'charges': charges,
        'equipped': item_name in equipped_names,
        'usable': bool(item.get('usable')),
        'consumable': bool(item.get('consumable')),
        'equippable': can_equip,
        'hp_regained': item.get('hp_regained'),
        'is_container': contents is not None,
        'contents': contents,
        'container': container_name,
        'container_label': container_label,
    }

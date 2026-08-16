"""Party sidekicks: NPC membership, owners, and optional class overlays.

Runtime records live in ``session.session_state['sidekicks']`` so mid-game
join/leave is save/loadable without rewriting campaign YAML.

Campaign definitions (optional) live in ``game.yml``::

    sidekicks:
      - entity_uid: npc_squire
        selectable: true
        spawn_with_party: true
        owners: []
      - entity_uid: npc_guide
        owners: [gomerin]
        require_session:
          quest_accepted: true
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

STATUS_IN_PARTY = 'in_party'
STATUS_LEFT = 'left'
STATUS_HOSTILE = 'hostile'
PARTY_GROUP = 'a'
NEUTRAL_GROUP = 'c'
HOSTILE_GROUP = 'b'
_STATE_KEY = 'sidekicks'


def _uid_of(entity_or_uid) -> str:
    if entity_or_uid is None:
        return ''
    if isinstance(entity_or_uid, str):
        return str(entity_or_uid).strip()
    return str(getattr(entity_or_uid, 'entity_uid', '') or '').strip()


def _entity_of(session, entity_or_uid):
    if entity_or_uid is None:
        return None
    if not isinstance(entity_or_uid, str):
        return entity_or_uid
    getter = getattr(session, 'entity_by_uid', None)
    if callable(getter):
        return getter(entity_or_uid)
    return None


def sidekick_records(session) -> dict[str, dict[str, Any]]:
    if session is None:
        return {}
    state = getattr(session, 'session_state', None)
    if not isinstance(state, dict):
        session.session_state = {}
        state = session.session_state
    raw = state.get(_STATE_KEY)
    if not isinstance(raw, dict):
        raw = {}
        state[_STATE_KEY] = raw
    return raw


def campaign_sidekick_defs(session) -> list[dict[str, Any]]:
    props = getattr(session, 'game_properties', None) or {}
    raw = props.get('sidekicks') or []
    return list(raw) if isinstance(raw, list) else []


def _campaign_def_for(session, entity_or_uid) -> dict[str, Any]:
    uid = _uid_of(entity_or_uid)
    if not uid:
        return {}
    for cfg in campaign_sidekick_defs(session):
        if str(cfg.get('entity_uid') or '').strip() == uid:
            return cfg
    return {}


def quest_allows_sidekick(session, cfg: dict[str, Any]) -> bool:
    from natural20.companion import quest_allows_companion
    return quest_allows_companion(session, cfg)


def sidekick_record(session, entity_or_uid) -> Optional[dict[str, Any]]:
    uid = _uid_of(entity_or_uid)
    if not uid:
        return None
    return sidekick_records(session).get(uid)


def is_in_party_sidekick(session, entity_or_uid) -> bool:
    rec = sidekick_record(session, entity_or_uid)
    return bool(rec and rec.get('status') == STATUS_IN_PARTY)


def is_sidekick(session, entity_or_uid) -> bool:
    """True when the entity has any sidekick record (in party or recently left)."""
    return sidekick_record(session, entity_or_uid) is not None


def sidekick_owners(session, entity_or_uid) -> list[str]:
    rec = sidekick_record(session, entity_or_uid)
    if not rec or rec.get('status') != STATUS_IN_PARTY:
        return []
    owners = rec.get('owners') or []
    return [str(name).strip().lower() for name in owners if str(name).strip()]


def iter_in_party_sidekicks(session) -> list:
    result = []
    seen = set()
    for uid, rec in list(sidekick_records(session).items()):
        if rec.get('status') != STATUS_IN_PARTY:
            continue
        entity = _entity_of(session, uid)
        if entity is None:
            continue
        if uid in seen:
            continue
        seen.add(uid)
        result.append(entity)
    return result


def iter_party_members(session) -> list:
    """Player characters plus in-party sidekicks (unique by UID)."""
    from natural20.map_set import iter_player_characters
    from natural20.player_character import PlayerCharacter

    seen: set[str] = set()
    members = []
    for entity in iter_player_characters(session):
        uid = _uid_of(entity)
        if not uid or uid in seen:
            continue
        seen.add(uid)
        members.append(entity)
    for entity in iter_in_party_sidekicks(session):
        uid = _uid_of(entity)
        if not uid or uid in seen:
            continue
        if isinstance(entity, PlayerCharacter):
            continue
        seen.add(uid)
        members.append(entity)
    return members


def average_party_level(session) -> int:
    from natural20.player_character import PlayerCharacter

    levels = []
    for entity in iter_party_members(session):
        if isinstance(entity, PlayerCharacter):
            try:
                levels.append(int(entity.level() or 1))
            except Exception:
                levels.append(1)
        else:
            rec = sidekick_record(session, entity) or {}
            try:
                levels.append(int(rec.get('sidekick_level') or 1))
            except Exception:
                levels.append(1)
    if not levels:
        return 1
    return max(1, int(round(sum(levels) / len(levels))))


def _set_group(entity, group: str) -> None:
    if entity is None:
        return
    entity.group = group
    props = getattr(entity, 'properties', None)
    if isinstance(props, dict):
        props['group'] = group


def join_party(session, entity, owners: Optional[Iterable[str]] = None, *,
               sidekick_class: Optional[str] = None,
               sidekick_level: Optional[int] = None,
               role: Optional[str] = None) -> dict[str, Any]:
    """Convert ``entity`` into an in-party sidekick.

    ``owners`` are player usernames (not entity UIDs). Empty owners means the
    sidekick is in the party but unassigned (DM / jointly claimed later).
    """
    if entity is None:
        raise ValueError('entity is required')
    uid = _uid_of(entity)
    if not uid:
        raise ValueError('entity has no entity_uid')

    owner_list = []
    seen_owners = set()
    for name in owners or []:
        normalized = str(name or '').strip().lower()
        if not normalized or normalized in seen_owners:
            continue
        seen_owners.add(normalized)
        owner_list.append(normalized)

    rec = sidekick_record(session, uid) or {}
    cfg = _campaign_def_for(session, uid)
    if sidekick_class is None:
        sidekick_class = rec.get('sidekick_class') or cfg.get('sidekick_class') or cfg.get('class')
    if sidekick_level is None:
        sidekick_level = rec.get('sidekick_level')
    if sidekick_level is None:
        sidekick_level = cfg.get('sidekick_level') or cfg.get('level')
    if sidekick_level is None:
        sidekick_level = average_party_level(session)
    if role is None:
        role = rec.get('role') or cfg.get('role')

    record = {
        'owners': owner_list,
        'status': STATUS_IN_PARTY,
        'sidekick_class': sidekick_class,
        'sidekick_level': int(sidekick_level or 1),
        'role': role,
        'pending_asi': rec.get('pending_asi') or 0,
    }
    sidekick_records(session)[uid] = record
    _set_group(entity, PARTY_GROUP)
    if hasattr(entity, 'update_state'):
        try:
            entity.update_state('active')
        except Exception:
            pass

    if sidekick_class:
        apply_sidekick_class(
            session,
            entity,
            sidekick_class,
            level=int(record['sidekick_level']),
            role=role,
        )
    return record


def leave_party(session, entity, *, hostile: bool = False) -> dict[str, Any]:
    """Drop an in-party sidekick back to a regular (or hostile) NPC."""
    if entity is None:
        raise ValueError('entity is required')
    uid = _uid_of(entity)
    rec = sidekick_record(session, uid) or {}
    rec['status'] = STATUS_HOSTILE if hostile else STATUS_LEFT
    rec['owners'] = []
    sidekick_records(session)[uid] = rec
    _set_group(entity, HOSTILE_GROUP if hostile else NEUTRAL_GROUP)
    return rec


def assign_owners(session, entity, owners: Iterable[str]) -> dict[str, Any]:
    rec = sidekick_record(session, entity)
    if rec is None or rec.get('status') != STATUS_IN_PARTY:
        rec = join_party(session, entity, owners)
        return rec
    owner_list = []
    seen = set()
    for name in owners or []:
        normalized = str(name or '').strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        owner_list.append(normalized)
    rec['owners'] = owner_list
    return rec


def sync_campaign_sidekicks(session) -> list[dict[str, Any]]:
    """Join campaign-defined sidekicks that already have owners (quest-gated)."""
    applied = []
    for cfg in campaign_sidekick_defs(session):
        if not quest_allows_sidekick(session, cfg):
            continue
        uid = cfg.get('entity_uid')
        if not uid:
            continue
        existing = sidekick_record(session, uid)
        if existing and existing.get('status') == STATUS_IN_PARTY:
            continue
        owners = cfg.get('owners') or []
        if not owners:
            continue
        entity = _entity_of(session, uid)
        if entity is None:
            continue
        applied.append(join_party(
            session,
            entity,
            owners,
            sidekick_class=cfg.get('sidekick_class') or cfg.get('class'),
            sidekick_level=cfg.get('sidekick_level') or cfg.get('level'),
            role=cfg.get('role'),
        ))
    return applied


def selectable_sidekick_entries(session) -> list[dict[str, Any]]:
    """Character-selection shaped dicts for ``selectable: true`` campaign sidekicks."""
    entries = []
    for cfg in campaign_sidekick_defs(session):
        if not cfg.get('selectable'):
            continue
        if not quest_allows_sidekick(session, cfg):
            continue
        uid = str(cfg.get('entity_uid') or '').strip()
        if not uid:
            continue
        entity = _entity_of(session, uid)
        display = cfg.get('display_name')
        if not display and entity is not None:
            try:
                display = entity.label()
            except Exception:
                display = uid
        sheet = cfg.get('sheet') or cfg.get('npc') or cfg.get('npc_type')
        if not sheet and entity is not None:
            sheet = getattr(entity, 'npc_type', None)
        token = cfg.get('file')
        if not token and entity is not None:
            try:
                token = entity.token_image()
            except Exception:
                token = None
        entries.append({
            'name': uid,
            'display_name': display or uid,
            'description': cfg.get('description') or '',
            'file': token or 'goblin_ambush_login.png',
            'sheet': f'npcs/{sheet}' if sheet and not str(sheet).startswith('npcs/') else sheet,
            'kind': 'npc',
            'role_label': 'Sidekick',
            'overrides': {'entity_uid': uid},
            'sidekick_class': cfg.get('sidekick_class') or cfg.get('class'),
            'sidekick_level': cfg.get('sidekick_level') or cfg.get('level'),
            'role': cfg.get('role'),
            'spawn_with_party': bool(cfg.get('spawn_with_party', True)),
        })
    return entries


def extra_attack_count(entity) -> int:
    """Total attacks granted by Extra Attack (1 = no extra)."""
    if entity is None or not getattr(entity, 'class_feature', None):
        return 1
    if entity.class_feature('extra_attack_3'):
        return 4
    if entity.class_feature('extra_attack_2'):
        return 3
    if entity.class_feature('extra_attack'):
        return 2
    return 1


def consume_inspiring_help(entity, roll, battle=None):
    """Add pending Inspiring Help dice to a d20 roll, then clear them."""
    if entity is None or roll is None:
        return roll
    dice = int(getattr(entity, '_inspiring_help_dice', 0) or 0)
    if dice <= 0:
        return roll
    entity._inspiring_help_dice = 0
    from natural20.die_roll import DieRoll
    extra = DieRoll.roll(
        f"{dice}d6",
        description='dice_roll.inspiring_help',
        entity=entity,
        battle=battle,
    )
    return roll + extra


def spellcasting_ability_mod(entity) -> int:
    if entity is None:
        return 0
    ability = (getattr(entity, 'properties', None) or {}).get('spellcasting_ability') or 'int'
    try:
        return int(entity.ability_mod(ability) or 0)
    except Exception:
        return 0


def extra_spell_damage_bonus(entity, spell_props=None) -> int:
    """Potent Cantrips / Empowered Spells numeric bonus (0 if none)."""
    if entity is None or not getattr(entity, 'class_feature', None):
        return 0
    props = spell_props if isinstance(spell_props, dict) else {}
    try:
        level = int(props.get('level') or 0)
    except (TypeError, ValueError):
        level = 0
    school = str(props.get('school') or '').lower()
    bonus = 0
    if level == 0 and entity.class_feature('potent_cantrips'):
        bonus += spellcasting_ability_mod(entity)
    if level > 0 and entity.class_feature('empowered_spells'):
        chosen = str((getattr(entity, 'properties', None) or {}).get('empowered_school') or '').lower()
        if chosen and chosen == school:
            bonus += spellcasting_ability_mod(entity)
    return bonus


def extra_attacks_remaining(entity, battle) -> int:
    if battle is None or entity is None:
        return 0
    state = battle.entity_state_for(entity)
    if not state:
        return 0
    try:
        return int(state.get('extra_attacks_remaining') or 0)
    except (TypeError, ValueError):
        return 0


def bump_stat_block_proficiency(npc, delta: int) -> None:
    """When PB increases, add ``delta`` to stat-block attack bonuses and DCs."""
    if npc is None or not delta:
        return
    actions = None
    props = getattr(npc, 'properties', None)
    if isinstance(props, dict):
        actions = props.get('actions')
    if not isinstance(actions, list):
        actions = getattr(npc, 'npc_actions', None)
    if not isinstance(actions, list):
        return
    for action in actions:
        if not isinstance(action, dict):
            continue
        if action.get('attack') is not None:
            try:
                action['attack'] = int(action['attack']) + int(delta)
            except (TypeError, ValueError):
                pass
        if action.get('dc') is not None:
            try:
                action['dc'] = int(action['dc']) + int(delta)
            except (TypeError, ValueError):
                pass
    if isinstance(props, dict):
        npc.npc_actions = props.get('actions', actions)


def grant_sidekick_hit_points(npc, levels: int = 1) -> int:
    """Roll hit die + CON (min 1) per level into max HP. Returns HP gained."""
    if npc is None or levels <= 0:
        return 0
    from natural20.die_roll import DieRoll

    hp_die = '1d8'
    props = getattr(npc, 'properties', None) or {}
    raw_die = props.get('hp_die') or '1d8'
    try:
        parsed = DieRoll.parse(str(raw_die))
        die_type = parsed.die_type or '8'
        hp_die = f"1d{die_type}"
    except Exception:
        hp_die = '1d8'
    try:
        con_mod = int(npc.ability_mod('con') or npc.ability_mod('constitution') or 0)
    except Exception:
        con_mod = 0
    gained_total = 0
    for _ in range(int(levels)):
        try:
            roll = DieRoll.roll(f"{hp_die}+{con_mod}", description='dice_roll.hit_points', entity=npc)
            gained = max(1, int(roll.result()))
        except Exception:
            gained = max(1, 1 + con_mod)
        gained_total += gained
        current_max = int(getattr(npc, '_max_hp', None) or props.get('max_hp') or npc.max_hp() or 0)
        new_max = current_max + gained
        npc._max_hp = new_max
        if isinstance(props, dict):
            props['max_hp'] = new_max
        try:
            npc.attributes['hp'] = int(npc.hp() or 0) + gained
        except Exception:
            pass
    return gained_total


def apply_sidekick_class(session, npc, class_id: str, level: int = 1,
                         role: Optional[str] = None, *, force: bool = False) -> Optional[dict[str, Any]]:
    """Apply a data-driven sidekick class overlay from ``char_classes`` YAML.

    No-ops (returns None) when the class YAML is not available — campaigns
    without the Tasha pack still get party membership and player control.
    """
    if session is None or npc is None or not class_id:
        return None
    try:
        class_yaml = session.load_class(str(class_id))
    except Exception:
        return None
    if not isinstance(class_yaml, dict):
        return None

    cr_limit = class_yaml.get('max_cr')
    if cr_limit is not None and not force:
        try:
            cr = float(npc.properties.get('cr', 0) or 0)
            if cr > float(cr_limit):
                return {
                    'applied': False,
                    'warning': f'CR {cr} exceeds pack max_cr {cr_limit}',
                    'class_id': class_id,
                }
        except (TypeError, ValueError):
            pass

    level = max(1, min(20, int(level or 1)))
    old_pb = int(npc.properties.get('proficiency_bonus') or npc.proficiency_bonus() or 2)
    pb_table = class_yaml.get('proficiency_bonuses') or []
    new_pb = old_pb
    if isinstance(pb_table, list) and len(pb_table) >= level:
        try:
            new_pb = int(pb_table[level - 1])
        except (TypeError, ValueError):
            new_pb = old_pb
    npc.properties['proficiency_bonus'] = new_pb
    if new_pb > old_pb:
        bump_stat_block_proficiency(npc, new_pb - old_pb)

    features = _features_up_to_level(class_yaml, level, role=role)
    attrs = list(npc.properties.get('attributes') or [])
    class_features = list(npc.properties.get('class_features') or [])
    for feature in features:
        if feature not in attrs:
            attrs.append(feature)
        if feature not in class_features:
            class_features.append(feature)
    npc.properties['attributes'] = attrs
    npc.properties['class_features'] = class_features

    if 'second_wind' in features:
        uses = 2 if level >= 20 else 1
        npc.second_wind_count = uses
        npc.properties['second_wind_count'] = uses

    if 'indomitable' in features:
        uses = 2 if level >= 18 else 1
        npc.indomitable_uses = uses
        npc.properties['indomitable_uses'] = uses

    slots = _spell_slots_for_level(class_yaml, level)
    if slots:
        npc.properties['spell_slots'] = dict(slots)
        npc.properties['max_spell_slots'] = dict(slots)
        if hasattr(npc, '_ensure_max_spell_slots_snapshot'):
            try:
                npc._ensure_max_spell_slots_snapshot()
            except Exception:
                pass

    roles = class_yaml.get('roles') or {}
    chosen_role = role or npc.properties.get('sidekick_role')
    if not chosen_role and roles:
        if 'attacker' in roles:
            chosen_role = 'attacker'
        elif 'mage' in roles:
            chosen_role = 'mage'
        else:
            chosen_role = next(iter(roles))
    if chosen_role and chosen_role in roles:
        npc.properties['sidekick_role'] = chosen_role
        role_cfg = roles.get(chosen_role) or {}
        if role_cfg.get('spellcasting_ability'):
            npc.properties['spellcasting_ability'] = role_cfg['spellcasting_ability']
        if role_cfg.get('features'):
            for feature in role_cfg['features']:
                if feature not in attrs:
                    attrs.append(feature)
                if feature not in class_features:
                    class_features.append(feature)
            npc.properties['attributes'] = attrs
            npc.properties['class_features'] = class_features

    _apply_known_spells(npc, class_yaml, level, role=chosen_role)

    rec = sidekick_record(session, npc) or {}
    rec['sidekick_class'] = class_id
    rec['sidekick_level'] = level
    rec['role'] = chosen_role
    asi_levels = class_yaml.get('asi_levels') or []
    pending = 0
    for asi_level in asi_levels:
        try:
            if int(asi_level) <= level:
                pending += 1
        except (TypeError, ValueError):
            continue
    already = int(npc.properties.get('sidekick_asi_applied') or 0)
    rec['pending_asi'] = max(0, pending - already)
    sidekick_records(session)[_uid_of(npc)] = rec
    npc.properties['sidekick_class'] = class_id
    npc.properties['sidekick_level'] = level
    return {'applied': True, 'class_id': class_id, 'level': level, 'features': features}


def sync_sidekick_levels(session) -> list[dict[str, Any]]:
    """Bump in-party sidekick levels to the party's average PC level."""
    target = average_party_level(session)
    updates = []
    for entity in iter_in_party_sidekicks(session):
        rec = sidekick_record(session, entity) or {}
        current = int(rec.get('sidekick_level') or 1)
        if current >= target:
            continue
        gained = target - current
        grant_sidekick_hit_points(entity, gained)
        class_id = rec.get('sidekick_class')
        if class_id:
            apply_sidekick_class(
                session,
                entity,
                class_id,
                level=target,
                role=rec.get('role'),
            )
        else:
            rec['sidekick_level'] = target
            sidekick_records(session)[_uid_of(entity)] = rec
        updates.append({'entity_uid': _uid_of(entity), 'old_level': current, 'new_level': target})
    return updates


def _features_up_to_level(class_yaml: dict[str, Any], level: int, role: Optional[str] = None) -> list[str]:
    features: list[str] = []
    for feat in class_yaml.get('class_features') or []:
        if feat not in features:
            features.append(feat)
    progression = class_yaml.get('progression') or {}
    for lvl in range(1, level + 1):
        row = progression.get(f'level_{lvl}') or {}
        for feat in row.get('class_features') or []:
            if feat not in features:
                features.append(feat)
    if role:
        role_cfg = (class_yaml.get('roles') or {}).get(role) or {}
        for feat in role_cfg.get('features') or []:
            if feat not in features:
                features.append(feat)
    return features


def _spell_slots_for_level(class_yaml: dict[str, Any], level: int) -> dict[str, int]:
    table = class_yaml.get('spell_slots')
    if not isinstance(table, list) or len(table) < level:
        return {}
    row = table[level - 1]
    if not isinstance(row, (list, tuple)):
        return {}
    slots = {}
    for idx, count in enumerate(row):
        spell_level = idx + 1
        try:
            qty = int(count or 0)
        except (TypeError, ValueError):
            qty = 0
        if qty > 0:
            slots[str(spell_level)] = qty
    return slots


def _table_value_at(table, level: int, default=0):
    if not isinstance(table, list) or level < 1 or len(table) < level:
        return default
    try:
        return int(table[level - 1] or 0)
    except (TypeError, ValueError):
        return default


def _apply_known_spells(npc, class_yaml: dict[str, Any], level: int, role: Optional[str] = None) -> None:
    """Fill ``prepared_spells`` from role lists sliced by known-spell tables."""
    if npc is None or not isinstance(class_yaml, dict):
        return
    chosen = role or (npc.properties or {}).get('sidekick_role')
    role_cfg = (class_yaml.get('roles') or {}).get(chosen) or {}
    cantrips = [str(s) for s in (role_cfg.get('cantrips') or []) if s]
    spells = [str(s) for s in (role_cfg.get('spells') or []) if s]
    if not cantrips and not spells:
        return
    cantrip_n = _table_value_at(class_yaml.get('cantrips_known'), level, default=len(cantrips))
    spell_n = _table_value_at(class_yaml.get('spells_known'), level, default=len(spells))
    prepared = cantrips[:max(0, cantrip_n)] + spells[:max(0, spell_n)]
    existing = list(npc.properties.get('prepared_spells') or [])
    for slug in prepared:
        if slug not in existing:
            existing.append(slug)
    npc.properties['prepared_spells'] = existing

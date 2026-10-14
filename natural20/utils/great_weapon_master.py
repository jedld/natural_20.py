"""Great Weapon Master feat.

Two parts are automated:

* **Heavy Weapon Mastery** (2024 feat): hitting with a Heavy weapon as part of
  an attack on your own turn deals extra damage equal to your proficiency
  bonus (``gwm_hit_riders``).
* **Hew** (2024) / the 2014 bonus attack: right after a melee weapon critical
  hit or reducing a creature to 0 HP on your turn, you can make one melee
  attack with the same weapon as a bonus action (``note_hew_trigger`` sets
  ``hew_pending`` and ``HewAttackAction`` offers the attack).

The edition comes from the campaign ruleset; a character built with the other
edition's feat can set ``feat_editions: {great_weapon_master: 5e-2024}``.
The 2014 -5/+10 power attack option is not modelled.
"""

from __future__ import annotations

FEAT = 'great_weapon_master'


def has_gwm(entity):
    check = getattr(entity, 'class_feature', None)
    try:
        return bool(callable(check) and check(FEAT))
    except Exception:
        return False


def gwm_edition(entity):
    props = getattr(entity, 'properties', None) or {}
    override = (props.get('feat_editions') or {}).get(FEAT)
    if override:
        return str(override)
    ruleset = getattr(getattr(entity, 'session', None), 'ruleset', None)
    return getattr(ruleset, 'name', None) or '5e-2014'


def _own_turn(battle, entity):
    if battle is None:
        return False
    try:
        return battle.current_turn() is entity
    except Exception:
        return False


def gwm_hit_riders(entity, weapon, battle=None, as_reaction=False):
    if not isinstance(weapon, dict) or as_reaction or not has_gwm(entity):
        return []
    if gwm_edition(entity) != '5e-2024':
        return []
    if 'heavy' not in (weapon.get('properties') or []):
        return []
    if battle is not None and not _own_turn(battle, entity):
        return []
    bonus = int(entity.proficiency_bonus() or 0)
    if bonus <= 0:
        return []
    return [{'damage_die': str(bonus), 'damage_type': weapon.get('damage_type') or 'bludgeoning'}]


def note_hew_trigger(battle, item, crit=False):
    """Mark a pending Hew attack after a melee crit or a kill on the attacker's turn."""
    if battle is None:
        return
    source, target = item.get('source'), item.get('target')
    weapon_key = item.get('weapon')
    if source is None or target is None or not weapon_key or item.get('thrown'):
        return
    if item.get('_hew') or not has_gwm(source) or not _own_turn(battle, source):
        return
    weapon = source.session.load_weapon(weapon_key) if isinstance(weapon_key, str) else weapon_key
    if not isinstance(weapon, dict) or weapon.get('type') != 'melee_attack':
        return
    dropped = False
    try:
        dropped = target.hp() <= 0 or target.dead() or target.unconscious()
    except Exception:
        dropped = False
    if not (crit or dropped):
        return
    state = battle.entity_state_for(source)
    if state is not None:
        state['hew_pending'] = weapon_key
        source._hew_pending_weapon = weapon_key

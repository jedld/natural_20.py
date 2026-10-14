"""Luck points (2024 Lucky-style feats) and the halfling-style reroll trait.

A feat (or creature YAML) grants luck with a ``luck`` block and a pool::

    resource_pools:
      luck_points: {max: proficiency_bonus, restore_on: long_rest}
    luck:
      pool: luck_points            # default
      self_advantage: true         # spend on your own attack roll / save / ability check
      impose_disadvantage: true    # spend when a creature's attack roll hits you
      ai_min_chance: 0.25          # offered only when the extra d20 has this chance to matter

The rules let a creature spend a point *before* rolling. The engine asks only
after the d20 is rolled:

- **Own roll:** after a failed roll, roll a second d20 and keep the higher. A
  roll that already succeeded is kept, so the success chance equals advantage
  (``1 - (1 - p)^2``), and the point is spent only when it can help. With
  disadvantage, the point cancels it: the first die of the pair stands
  (again the same overall odds as cancelling up front). Not offered with
  advantage.
- **Attack against you:** after a hit, the attacker rolls another d20 and
  keeps the lower. With advantage, the point cancels it (first die stands).
  Not offered when the attacker already has disadvantage.

Luck is offered only in combat (the creature is a battle combatant) and only
for rolls with a known target number: attack rolls (weapon and spell), saves
made with ``opts['dc']``, death saves, and ability checks whose caller passes
``dc``.

The controller is asked through the usual reaction prompt
(``giant_ancestry._ask_controller``). The point is offered only when the
extra die has at least ``ai_min_chance`` of changing the outcome, so AI
controllers (which accept any offer) spend it sensibly.

``has_reroll_ones_trait`` is the separate halfling Lucky trait (reroll
natural 1s). It comes from race/subrace features, NPC ``attributes`` or
``class_features``, never from the ``feats`` list.
"""

from __future__ import annotations

from natural20.action import Action
from natural20.die_roll import DieRoll, DieRolls

DEFAULT_POOL = 'luck_points'
DEFAULT_MIN_CHANCE = 0.25
REROLL_ONES_TRAIT = 'lucky'


# ---------------------------------------------------------------------------
# Halfling-style trait
# ---------------------------------------------------------------------------

def has_reroll_ones_trait(entity):
    """True for the "reroll natural 1s" trait (not a feat of the same name)."""
    if entity is None or not callable(getattr(entity, 'class_feature', None)):
        return False
    try:
        if not entity.class_feature(REROLL_ONES_TRAIT):
            return False
    except Exception:
        return False
    props = getattr(entity, 'properties', None) or {}
    if REROLL_ONES_TRAIT not in (props.get('feats') or []):
        return True
    if REROLL_ONES_TRAIT in (props.get('attributes') or []) or REROLL_ONES_TRAIT in (props.get('class_features') or []):
        return True
    race = getattr(entity, 'race_properties', None) or {}
    features = list(race.get('race_features') or [])
    subrace = entity.subrace() if callable(getattr(entity, 'subrace', None)) else None
    if subrace:
        features += ((race.get('subrace') or {}).get(subrace) or {}).get('race_features') or []
    return REROLL_ONES_TRAIT in features


# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------

def luck_spec(entity):
    """Merged ``luck`` block from the creature's feats / own YAML, or None."""
    if entity is None:
        return None
    from natural20.utils.feat_mechanics import feat_definitions
    spec = None
    blocks = [definition.get('luck') for _feat, definition in feat_definitions(entity)]
    blocks.append((getattr(entity, 'properties', None) or {}).get('luck'))
    for block in blocks:
        if not block:
            continue
        spec = dict(spec or {})
        spec.update(block if isinstance(block, dict) else {})
    return spec


def luck_pool(entity, spec=None):
    spec = spec if spec is not None else luck_spec(entity)
    if not spec or not hasattr(entity, 'register_resource'):
        return None
    from natural20.utils.feat_mechanics import ensure_feat_pools
    ensure_feat_pools(entity)
    name = spec.get('pool') or DEFAULT_POOL
    pool = entity.get_resource(name)
    if pool is None:
        pool = entity.register_resource(name, max(1, int(entity.proficiency_bonus() or 0)),
                                        restore_on='long_rest')
    return pool


def luck_points(entity):
    pool = luck_pool(entity)
    return pool.current if pool is not None else 0


def _min_chance(spec):
    try:
        return float(spec.get('ai_min_chance', DEFAULT_MIN_CHANCE))
    except (TypeError, ValueError):
        return DEFAULT_MIN_CHANCE


# ---------------------------------------------------------------------------
# Roll helpers
# ---------------------------------------------------------------------------

def _d20_part(roll):
    """``(d20 DieRoll, index in DieRolls or None)``."""
    if isinstance(roll, DieRoll):
        return (roll, None) if roll.die_sides == 20 and roll.rolls else (None, None)
    if isinstance(roll, DieRolls):
        for index, part in enumerate(roll.rolls):
            if isinstance(part, DieRoll) and part.die_sides == 20 and part.rolls:
                return part, index
    return None, None


def _with_part(roll, index, new_part):
    if index is None:
        return new_part
    parts = list(roll.rolls)
    parts[index] = new_part
    return DieRolls(parts)


def _face(part):
    return part.natural_d20()


def _fresh(part, rolls, advantage=False, disadvantage=False):
    new = part.clone()
    new.rolls = rolls
    new.advantage = advantage
    new.disadvantage = disadvantage
    new.prev_roll = None
    for key in ('last_result', 'guidance_base'):
        new.metadata.pop(key, None)
    return new


def _first_die(part):
    first = part.rolls[0]
    return first[0] if isinstance(first, (tuple, list)) else first


def _succeeds(face, offset, dc, crit_rules):
    if crit_rules:
        if face == 20:
            return True
        if face == 1:
            return False
    return face + offset >= dc


def _roll_total(roll):
    return int(roll.result())


def _extra_d20(entity, battle):
    extra = DieRoll.roll('1d20', description='dice_roll.luck_point', entity=entity, battle=battle)
    return extra.rolls[0]


class LuckPointOption(Action):
    """Yes option for spending a luck point."""

    def __init__(self, session, source, mode):
        super().__init__(session, source, 'luck_point')
        self.mode = mode

    def label(self):
        verb = 'Roll again with advantage' if self.mode == 'advantage' else 'Impose disadvantage'
        return f"Luck point: {verb} ({luck_points(self.source)} left)"

    def button_label(self):
        return self.label()

    def __str__(self):
        return self.label()

    __repr__ = __str__

    def build_map(self):
        return self

    def resolve(self, session, map, opts=None):
        return self


def _decide(entity, battle, mode, event):
    from natural20.utils.giant_ancestry import _ask_controller
    if battle is None or battle.entity_state_for(entity) is None:
        return False
    option = LuckPointOption(entity.session, entity, mode)
    return _ask_controller(entity, battle, [option], event) is not None


def _spend(entity, pool, event_data):
    pool.consume(1)
    event = dict(event_data, event='luck_point', remaining=pool.current)
    manager = getattr(getattr(entity, 'session', None), 'event_manager', None)
    if manager is not None:
        manager.received_event(event)


# ---------------------------------------------------------------------------
# Public hooks
# ---------------------------------------------------------------------------

def luck_on_own_roll(entity, roll, dc, battle=None, roll_kind='attack_roll', target=None,
                     crit_rules=None):
    """Offer a luck point after ``roll`` failed to reach ``dc``; returns the roll to use."""
    if roll is None or dc is None or entity is None:
        return roll
    spec = luck_spec(entity)
    if not spec or not spec.get('self_advantage', True):
        return roll
    part, index = _d20_part(roll)
    if part is None or part.advantage:
        return roll
    if crit_rules is None:
        crit_rules = roll_kind == 'attack_roll'
    try:
        dc = int(dc)
        total = _roll_total(roll)
        face = _face(part)
    except Exception:
        return roll
    if face is None or _succeeds(face, total - face, dc, crit_rules):
        return roll
    pool = luck_pool(entity, spec)
    if pool is None or not pool.available(1):
        return roll
    offset = total - face
    if part.disadvantage:
        kept = _first_die(part)
        chance = 1.0 if _succeeds(kept, offset, dc, crit_rules) else 0.0
    else:
        chance = sum(1 for f in range(1, 21) if _succeeds(f, offset, dc, crit_rules)) / 20.0
    if chance < _min_chance(spec) or chance <= 0:
        return roll
    event = {
        'type': 'luck_point', 'trigger': roll_kind, 'mode': 'advantage',
        'source': entity, 'target': target, 'roll': total, 'dc': dc, 'chance': chance,
    }
    if not _decide(entity, battle, 'advantage', event):
        return roll
    if part.disadvantage:
        new_part = _fresh(part, [kept] + list(part.rolls[1:]))
    else:
        new_part = _fresh(part, [(part.rolls[0], _extra_d20(entity, battle))] + list(part.rolls[1:]),
                          advantage=True)
    new_roll = _with_part(roll, index, new_part)
    _spend(entity, pool, {
        'source': entity, 'target': target, 'mode': 'advantage', 'roll_kind': roll_kind,
        'old_roll': roll, 'roll': new_roll, 'dc': dc,
    })
    return new_roll


def luck_against_attack(defender, attacker, roll, target_ac, battle=None):
    """Offer the defender a luck point after ``roll`` hit; returns the roll to use."""
    if roll is None or target_ac is None or defender is None or defender is attacker:
        return roll
    spec = luck_spec(defender)
    if not spec or not spec.get('impose_disadvantage', True):
        return roll
    part, index = _d20_part(roll)
    if part is None or part.disadvantage:
        return roll
    try:
        target_ac = int(target_ac)
        total = _roll_total(roll)
        face = _face(part)
    except Exception:
        return roll
    if face is None or not _succeeds(face, total - face, target_ac, True):
        return roll
    pool = luck_pool(defender, spec)
    if pool is None or not pool.available(1):
        return roll
    offset = total - face
    crit = face == 20

    def worse(f):
        return not _succeeds(f, offset, target_ac, True) or (crit and f != 20)

    if part.advantage:
        kept = _first_die(part)
        chance = 1.0 if worse(kept) else 0.0
    else:
        chance = sum(1 for f in range(1, 21) if worse(f)) / 20.0
    if chance < _min_chance(spec) or chance <= 0:
        return roll
    event = {
        'type': 'luck_point', 'trigger': 'attack_roll_against', 'mode': 'disadvantage',
        'source': defender, 'target': attacker, 'roll': total, 'dc': target_ac, 'chance': chance,
    }
    if not _decide(defender, battle, 'disadvantage', event):
        return roll
    if part.advantage:
        new_part = _fresh(part, [kept] + list(part.rolls[1:]))
    else:
        new_part = _fresh(part, [(part.rolls[0], _extra_d20(defender, battle))] + list(part.rolls[1:]),
                          disadvantage=True)
    new_roll = _with_part(roll, index, new_part)
    _spend(defender, pool, {
        'source': defender, 'target': attacker, 'mode': 'disadvantage',
        'roll_kind': 'attack_roll', 'old_roll': roll, 'roll': new_roll, 'dc': target_ac,
    })
    return new_roll

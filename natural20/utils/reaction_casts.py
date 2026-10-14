"""Reactions a creature can take when an attack roll hits it (class / feat YAML).

    reaction_casts:                 # cast a spell as the reaction
      - feature: misty_escape
        spell: misty_step
        trigger: damage_taken       # offered when an attack hits (damage incoming)

    hit_reactions:                  # Uncanny-Dodge style riders
      - feature: beguiling_defenses
        id: beguiling_defenses
        name: Beguiling Defenses
        pool: beguiling_defenses    # one use, restored on a long rest
        restore_with_slot: true     # or spend a spell slot when the pool is empty
        halve_damage: true
        retaliate:                  # attacker saves vs the creature's spell DC
          save: wisdom
          damage_type: psychic      # takes damage equal to the damage dealt

A reaction spell is cast with the creature's reaction instead of its normal
casting time, paying with a free cast (``free_casts`` pool) or a slot.
Teleport spells pick a destination away from foes automatically.
``hit_reaction_window`` is called from ``after_attack_roll_hook`` (weapon and
spell attacks); interactive controllers are prompted through
``AsyncReactionHandler`` (reaction type ``hit_reaction``). The halving marker
is read by ``attack_util.damage_event`` (``consume_hit_marker``).
"""

from __future__ import annotations

from natural20.action import Action, AsyncReactionHandler

REACTION_TYPE = 'hit_reaction'
MARKER_KEY = 'hit_reaction_marker'


def reaction_cast_specs(entity, trigger):
    from natural20.utils.class_mechanics import class_specs
    from natural20.utils.feat_mechanics import feat_specs
    out = []
    for _owner, spec in list(class_specs(entity, 'reaction_casts')) + list(feat_specs(entity, 'reaction_casts')):
        if spec.get('trigger', 'damage_taken') == trigger and spec.get('spell'):
            out.append(spec)
    return out


def _escape_square(entity, attacker, battle, battle_map, range_ft):
    try:
        cur_x, cur_y = battle_map.position_of(entity)
    except Exception:
        return None
    feet = getattr(battle_map, 'feet_per_grid', 5) or 5
    reach = max(1, int(range_ft) // feet)
    try:
        ax, ay = battle_map.position_of(attacker) if attacker is not None else (cur_x, cur_y)
    except Exception:
        ax, ay = cur_x, cur_y
    foes = [attacker] if attacker is not None else []
    if battle is not None:
        foes = [e for e in battle.opponents_of(entity) if e.conscious()] or foes
    foe_positions = []
    for foe in foes:
        try:
            foe_positions.append(battle_map.position_of(foe))
        except Exception:
            continue
    if not foe_positions:
        foe_positions = [(ax, ay)]
    best, best_score = None, None
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            if dx == 0 and dy == 0:
                continue
            x, y = cur_x + dx, cur_y + dy
            if x < 0 or y < 0 or x >= battle_map.size[0] or y >= battle_map.size[1]:
                continue
            if battle_map.distance_to_square(entity, x, y) > reach:
                continue
            if not battle_map.placeable(entity, x, y, battle, squeeze=False):
                continue
            if not battle_map.can_see_square(entity, (x, y)):
                continue
            score = min(max(abs(x - fx), abs(y - fy)) for fx, fy in foe_positions)
            if best_score is None or score > best_score:
                best, best_score = [x, y], score
    return best


def inline_spell_action(entity, spell_slug, battle, casting_time='1:reaction'):
    """A ready-to-target ``SpellAction`` for ``spell_slug`` cast with
    ``casting_time`` (a reaction by default), paid with a free cast or the
    lowest usable slot. ``None`` when it can't be cast."""
    from natural20.actions.spell_action import SpellAction
    from natural20.utils.spell_loader import load_spell_class
    from natural20.utils.attack_util import _spell_class_key
    session = entity.session
    try:
        details = session.load_spell(spell_slug)
    except Exception:
        details = None
    if not details:
        return None
    details = dict(details, casting_time=casting_time)
    class_key = _spell_class_key(details)
    try:
        spell_class = load_spell_class(class_key)
    except Exception:
        return None
    from natural20.utils.action_restrictions import is_restricted
    from natural20.utils.spell_requirements import environment_issue
    if is_restricted(entity, 'spell') or environment_issue(entity, details, battle):
        return None
    action = SpellAction(session, entity, 'spell')
    action.spell = details
    action.level = details.get('level', 1)
    action.at_level = action.level
    action.spell_class = spell_class
    if action.level > 0:
        from natural20.utils.class_mechanics import free_cast_pool_for
        action.free_cast_pool = free_cast_pool_for(entity, spell_slug)
        if not action.free_cast_pool and hasattr(entity, 'next_spell_slot_level'):
            for slot_class in entity.spell_list_classes_for(details):
                slot_level = entity.next_spell_slot_level(slot_class, action.at_level)
                if slot_level is not None:
                    action.at_level = slot_level
                    action.spellcasting_class = slot_class
                    break
            if not action.spellcasting_class:
                return None
    instance = spell_class(session, entity, class_key, details)
    instance.action = action
    action.spell_action = instance
    action.as_reaction = casting_time.endswith(':reaction')
    return action


def _build_cast(entity, spell_slug, battle, battle_map, attacker):
    action = inline_spell_action(entity, spell_slug, battle)
    if action is None:
        return None
    details = action.spell
    if details.get('range') is not None and battle_map is not None:
        square = _escape_square(entity, attacker, battle, battle_map, details.get('range', 30))
        if square is None:
            return None
        action.target = square
    else:
        action.target = entity
    from natural20.utils.spell_riders import riders_for, _priority
    riders = sorted(riders_for(entity, spell_slug), key=_priority)
    if riders:
        action.spell_rider = riders[0].get('id')
    return action


def hit_reaction_specs(entity):
    from natural20.utils.class_mechanics import class_specs
    from natural20.utils.feat_mechanics import feat_specs
    return [spec for _owner, spec in list(class_specs(entity, 'hit_reactions')) + list(feat_specs(entity, 'hit_reactions'))]


def _slot_to_restore(entity):
    """Lowest spell slot the creature could spend (class key, level), or None."""
    slots = getattr(entity, 'spell_slots', None) or {}
    for klass, table in slots.items():
        for level in sorted(int(l) for l in (table or {}).keys()):
            if level > 0 and int(table.get(level, 0) or 0) > 0:
                return klass, level
    return None


def _hit_reaction_usable(entity, spec):
    pool = spec.get('pool')
    if not pool:
        return True
    res = entity.get_resource(pool) if hasattr(entity, 'get_resource') else None
    if res is not None and res.current > 0:
        return True
    return bool(spec.get('restore_with_slot')) and _slot_to_restore(entity) is not None


class HitReactionAction(Action):
    """A ``hit_reactions`` entry chosen as a reaction to being hit."""

    def __init__(self, session, source, spec, attacker=None):
        super().__init__(session, source, spec.get('id') or 'hit_reaction')
        self.spec = spec
        self.attacker = attacker
        self.as_reaction = True

    def label(self):
        return self.spec.get('name') or str(self.spec.get('id')).replace('_', ' ').title()

    button_label = label
    name = label

    def __str__(self):
        return self.label()

    __repr__ = __str__

    def build_map(self):
        return self

    def use(self, battle):
        entity = self.source
        spec = self.spec
        pool = spec.get('pool')
        paid_with_slot = None
        if pool:
            res = entity.get_resource(pool)
            if res is not None and res.current > 0:
                entity.consume_resource(pool)
            elif spec.get('restore_with_slot'):
                slot = _slot_to_restore(entity)
                if slot is None:
                    return []
                entity.consume_spell_slot(slot[1], character_class=slot[0])
                paid_with_slot = slot[1]
        battle.consume(entity, 'reaction')
        marker = {'by': spec.get('id'), 'label': self.label(),
                  'attacker': getattr(self.attacker, 'entity_uid', None),
                  'halve_damage': bool(spec.get('halve_damage'))}
        if spec.get('retaliate'):
            from natural20.spell.hold_person_spell import HoldPersonSpell
            marker['retaliate'] = dict(spec['retaliate'])
            marker['dc'] = entity.spell_save_dc(HoldPersonSpell._caster_spell_ability(entity, None))
        entity.attributes[MARKER_KEY] = marker
        entity.session.event_manager.received_event({
            'event': 'hit_reaction', 'source': entity, 'target': self.attacker,
            'label': self.label(), 'slot_level': paid_with_slot,
        })
        return []


def consume_hit_marker(target, attacker):
    """Pop the marker a hit reaction left for the incoming damage from ``attacker``."""
    attrs = getattr(target, 'attributes', None)
    if not isinstance(attrs, dict):
        return None
    marker = attrs.get(MARKER_KEY)
    if not marker:
        return None
    if marker.get('attacker') and marker['attacker'] != getattr(attacker, 'entity_uid', None):
        return None
    attrs.pop(MARKER_KEY, None)
    return marker


def retaliate(marker, target, attacker, damage_taken, battle):
    """Attacker saves or takes ``damage_taken`` (Beguiling Defenses)."""
    spec = (marker or {}).get('retaliate')
    if not spec or attacker is None or damage_taken <= 0 or attacker.dead():
        return
    dc = int(marker.get('dc') or 10)
    roll = attacker.save_throw(spec.get('save', 'wisdom'), battle, {'dc': dc, 'is_magical': True})
    session = target.session
    session.event_manager.received_event({
        'event': 'spell_rider', 'source': target, 'target': attacker, 'rider': marker.get('label'),
        'roll': roll, 'dc': dc, 'success': roll.result() >= dc,
        'message': 'resists' if roll.result() >= dc else f"takes {damage_taken} {spec.get('damage_type', 'psychic')} damage",
    })
    if roll.result() < dc:
        from natural20.utils.attack_util import damage_event
        damage_event({
            'source': target, 'target': attacker, 'damage': int(damage_taken),
            'damage_type': spec.get('damage_type', 'psychic'),
            'attack_name': marker.get('label'), 'spell_save': roll, 'dc': dc,
            'hit_reaction_retaliation': True,
        }, battle)


def hit_reaction_window(battle, target, attacker, attack_roll, effective_ac, original_action=None):
    """Offer reactions to an attack roll that hits ``target``; returns event dicts."""
    events = []
    if battle is None or target is None or attacker is None or attacker is target:
        return events
    if attack_roll is None or effective_ac is None:
        return events
    if attack_roll.nat_1() or (not attack_roll.nat_20() and attack_roll.result() < effective_ac):
        return events
    if battle.entity_state_for(target) is None or not hit_reaction_specs(target):
        return events
    if not hasattr(target, 'conscious') or not target.conscious() or not target.has_reaction(battle):
        return events
    try:
        if target.incapacitated():
            return events
    except Exception:
        pass
    battle_map = battle.map_for(target)
    options = []
    for spec in hit_reaction_specs(target):
        if _hit_reaction_usable(target, spec):
            if spec.get('requires_sight', True) and battle_map is not None:
                try:
                    if not battle_map.can_see(target, attacker):
                        continue
                except Exception:
                    pass
            options.append(HitReactionAction(target.session, target, spec, attacker))
    for spec in reaction_cast_specs(target, 'damage_taken'):
        action = _build_cast(target, spec['spell'], battle, battle_map, attacker)
        if action is not None:
            options.append(action)
    if not options:
        return events

    controller = battle.controller_for(target)
    chosen = None
    stored = False
    if original_action is not None and hasattr(original_action, 'has_async_reaction_for_source'):
        stored = original_action.has_async_reaction_for_source(target, REACTION_TYPE)
    if stored is not False:
        chosen = stored
    elif controller is None or not hasattr(controller, 'select_reaction'):
        chosen = None
    else:
        try:
            chosen = controller.select_reaction(target, battle, battle_map, options, {
                'type': REACTION_TYPE, 'trigger': 'on_hit_target',
                'source': target, 'target': target, 'attacker': attacker,
            })
        except Exception:
            chosen = options[0]
        if hasattr(chosen, 'send'):
            if original_action is None:
                try:
                    chosen.close()
                except Exception:
                    pass
                return events
            raise AsyncReactionHandler(target, chosen, original_action, REACTION_TYPE)
    if isinstance(chosen, int):
        chosen = options[chosen] if 0 <= chosen < len(options) else None
    if isinstance(chosen, list):
        chosen = chosen[0] if chosen else None
    if chosen is None:
        return events
    match = next((o for o in options if o is chosen or (
        type(o) is type(chosen) and getattr(o, 'action_type', None) == getattr(chosen, 'action_type', None))), None)
    if match is None:
        return events
    if isinstance(match, HitReactionAction):
        match.use(battle)
        return events
    instance = match.spell_action
    results = instance.resolve(target, battle, match, battle_map) or []
    instance.consume(battle)
    target.session.event_manager.received_event({
        'event': 'reaction_cast', 'source': target, 'spell': match.spell.get('name'),
    })
    events.extend(results)
    return events

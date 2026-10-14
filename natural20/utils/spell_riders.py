"""Optional riders a feature adds to a spell (class / subclass / feat YAML).

    spell_riders:
      - feature: steps_of_the_fey
        spells: [misty_step]
        id: refreshing_step
        name: Refreshing Step
        temp_hp: 1d10                 # to the caster after the spell
      - feature: steps_of_the_fey
        spells: [misty_step]
        id: taunting_step
        name: Taunting Step
        origin: departure             # departure | arrival | best
        radius: 5
        save: wisdom                  # vs the caster's spell save DC
        on_fail: taunt                # creatures are taunted (natural20/utils/taunt.py)
      - feature: misty_escape
        spells: [misty_step]
        id: disappearing_step
        name: Disappearing Step
        invisible_until_next_turn: true
      - feature: misty_escape
        spells: [misty_step]
        id: dreadful_step
        name: Dreadful Step
        origin: best                  # whichever end has more foes
        radius: 5
        save: wisdom
        damage: 2d4
        damage_type: psychic

A spell that supports riders offers them as a ``select_choice`` step (listed
best-first, so AI controllers take the first) and calls ``apply_rider`` after
its own effect, passing the departure and arrival squares.
"""

from __future__ import annotations

NO_RIDER = 'none'


def riders_for(entity, spell_slug):
    from natural20.utils.class_mechanics import class_specs
    from natural20.utils.feat_mechanics import feat_specs
    out = []
    specs = list(class_specs(entity, 'spell_riders'))
    try:
        specs.extend(feat_specs(entity, 'spell_riders'))
    except Exception:
        pass
    for _owner, spec in specs:
        if spell_slug not in (spec.get('spells') or []):
            continue
        if any(r.get('id') == spec.get('id') for r in out):
            continue
        out.append(spec)
    return out


def rider_by_id(entity, spell_slug, rider_id):
    for spec in riders_for(entity, spell_slug):
        if spec.get('id') == rider_id:
            return spec
    return None


def _priority(spec):
    if spec.get('invisible_until_next_turn'):
        return 0
    if spec.get('damage'):
        return 1
    if spec.get('on_fail'):
        return 2
    return 3


def choice_param(entity, spell_slug):
    """``select_choice`` param for the riders ``entity`` can add, or ``None``."""
    riders = sorted(riders_for(entity, spell_slug), key=_priority)
    if not riders:
        return None
    choices = [[r.get('name') or str(r.get('id')).replace('_', ' ').title(), r.get('id')] for r in riders]
    choices.append(['No additional effect', NO_RIDER])
    return {'type': 'select_choice', 'num': 1, 'choices': choices,
            'label': 'Additional effect', 'ai_first_only': True}


def _creatures_near(battle, battle_map, square, radius_ft, exclude):
    out = []
    if battle_map is None or square is None:
        return out
    feet = getattr(battle_map, 'feet_per_grid', 5) or 5
    reach = max(1, int(radius_ft) // feet)
    sx, sy = int(square[0]), int(square[1])
    candidates = list(battle.entities.keys()) if battle is not None else list(getattr(battle_map, 'entities', {}).keys())
    for creature in candidates:
        if creature is exclude or not hasattr(creature, 'dead') or creature.dead():
            continue
        try:
            pos = battle_map.entity_or_object_pos(creature)
        except Exception:
            continue
        if pos is None:
            continue
        size = 1
        try:
            size = max(1, int(creature.token_size()))
        except Exception:
            pass
        dx = max(0, pos[0] - sx, sx - (pos[0] + size - 1))
        dy = max(0, pos[1] - sy, sy - (pos[1] + size - 1))
        if max(dx, dy) <= reach:
            out.append(creature)
    return out


def _pick_origin(spec, caster, battle, battle_map, departure, arrival):
    origin = spec.get('origin', 'departure')
    if origin == 'arrival':
        return arrival
    if origin != 'best' or battle is None:
        return departure

    def score(square):
        total = 0
        for c in _creatures_near(battle, battle_map, square, spec.get('radius', 5), caster):
            total += 1 if battle.opposing(caster, c) else -1
        return total
    return departure if score(departure) >= score(arrival) else arrival


def apply_rider(spec, caster, battle, battle_map, departure, arrival, dc):
    """Resolve a rider immediately; returns event dicts for the log."""
    from natural20.die_roll import DieRoll
    session = caster.session
    events = []
    rider_name = spec.get('name') or spec.get('id')
    if spec.get('temp_hp'):
        roll = DieRoll.roll(str(spec['temp_hp']), description=rider_name, entity=caster, battle=battle)
        amount = roll.result()
        caster.grant_temp_hp(amount, source=caster)
        session.event_manager.received_event({
            'event': 'spell_rider', 'source': caster, 'rider': rider_name,
            'message': f"gains {amount} temporary hit points",
        })
    if spec.get('invisible_until_next_turn'):
        from natural20.effects.fleeting_invisibility_effect import FleetingInvisibilityEffect
        FleetingInvisibilityEffect(caster, label=rider_name).start()
        session.event_manager.received_event({
            'event': 'spell_rider', 'source': caster, 'rider': rider_name,
            'message': 'becomes invisible until the start of their next turn',
        })
    if spec.get('save'):
        square = _pick_origin(spec, caster, battle, battle_map, departure, arrival)
        ability = spec['save']
        for creature in _creatures_near(battle, battle_map, square, spec.get('radius', 5), caster):
            roll = creature.save_throw(ability, battle, {'dc': dc, 'is_magical': True})
            success = roll.result() >= dc
            outcome = 'resists'
            if not success:
                if spec.get('on_fail') == 'taunt':
                    from natural20.utils.taunt import apply_taunt
                    apply_taunt(creature, caster, label=spec.get('id'))
                    outcome = 'is taunted'
            session.event_manager.received_event({
                'event': 'spell_rider', 'source': caster, 'target': creature, 'rider': rider_name,
                'roll': roll, 'dc': dc, 'success': success, 'message': outcome,
            })
            if not success and spec.get('damage'):
                from natural20.utils.attack_util import damage_event
                dmg = DieRoll.roll(str(spec['damage']), description=rider_name, entity=caster, battle=battle)
                damage_event({
                    'source': caster, 'target': creature, 'damage': dmg,
                    'damage_type': spec.get('damage_type', 'force'),
                    'attack_name': rider_name, 'spell_save': roll, 'dc': dc,
                }, battle)
    return events

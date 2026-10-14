"""Area saving-throw hazards fired from map objects and YAML events.

An ``area_save`` block (object ``events`` entry, see ``GenericEventHandler``)
makes every creature in an area roll a save against damage, like a trap or an
animated statue breathing fire::

    area_save:
      label: Statue Fire Breath
      annotation: s12_sanctuary   # creatures inside this map annotation
      radius: 30                  # ...or within N feet of the source object
      line_of_effect: true        # default: needs an unblocked line from the source
      save: dexterity
      dc: 16
      damage_die: 10d6
      damage_type: fire
      half_on_success: true
      on_fail_condition: prone    # optional, until the end of the target's next turn

Without ``annotation`` or ``radius`` every creature on the map is affected.
"""

from natural20.die_roll import DieRoll


def _source_position(battle_map, source):
    try:
        pos = battle_map.position_of(source)
    except Exception:
        return None
    return tuple(pos) if pos is not None else None


def area_save_targets(source, battle_map, config):
    """Living creatures (not objects) caught by ``config``'s area."""
    if battle_map is None:
        return []
    annotation = None
    if config.get('annotation'):
        annotation = battle_map.map_annotation_by_id(config['annotation'])
        if annotation is None:
            return []
    origin = _source_position(battle_map, source)
    radius = config.get('radius')
    feet = getattr(battle_map, 'feet_per_grid', 5) or 5
    line_of_effect = config.get('line_of_effect', True) and origin is not None

    from natural20.map_annotations import annotation_contains_point
    targets = []
    for creature, pos in list(battle_map.entities.items()):
        if creature is source or creature.object() or creature.dead():
            continue
        if not getattr(creature, 'allow_targeting', lambda: True)():
            continue
        squares = battle_map.entity_squares(creature) or [tuple(pos)]
        if annotation is not None and not any(
                annotation_contains_point(annotation, sx, sy) for sx, sy in squares):
            continue
        if radius is not None and origin is not None:
            nearest = min(max(abs(sx - origin[0]), abs(sy - origin[1])) for sx, sy in squares)
            if nearest * feet > int(radius):
                continue
        if line_of_effect and not any(
                battle_map.line_of_sight(origin[0], origin[1], sx, sy, inclusive=False) is not None
                for sx, sy in squares):
            continue
        targets.append(creature)
    return targets


def resolve_area_save(source, config, battle=None, battle_map=None, session=None):
    """Roll damage once, then each target saves for half (or none). Returns the creatures hit."""
    from natural20.spell.extensions.save_check import SaveCheck
    session = session or getattr(source, 'session', None)
    if battle_map is None and session is not None:
        battle_map = session.map_for(source)
    targets = area_save_targets(source, battle_map, config)
    if not targets:
        return []
    label = config.get('label') or config.get('name') or 'hazard'
    dc = int(config.get('dc', 10))
    save_type = config.get('save', 'dexterity')
    damage_type = config.get('damage_type', 'fire')
    roll = DieRoll.roll(str(config.get('damage_die', '1d6')), battle=battle,
                        description='dice_roll.area_hazard')
    condition = config.get('on_fail_condition')
    hit = []
    for creature in targets:
        save = SaveCheck.make(creature, save_type, dc, battle=battle,
                              opts={'is_magical': bool(config.get('magical', True)), 'dc': dc})
        if save.passed and config.get('half_on_success', True) is False:
            amount = 0
        else:
            amount = roll.result() // 2 if save.passed else roll.result()
        if session is not None:
            session.event_manager.received_event({
                'event': 'hazard_save', 'source': source, 'target': creature,
                'label': label, 'save': save_type, 'dc': dc, 'save_roll': save.roll,
                'saved': save.passed, 'damage': amount, 'damage_type': damage_type,
            })
        if amount > 0:
            creature.take_damage(amount, battle=battle, damage_type=damage_type,
                                 session=session, roll_info=roll)
        if condition and not save.passed and not creature.dead():
            from natural20.effects.timed_condition_effect import TimedConditionEffect
            TimedConditionEffect.apply_to(creature, str(condition), source=source, battle=battle)
        hit.append(creature)
    return hit

"""Counterspell reaction window.

When a creature casts a spell during combat, each hostile creature that has
Counterspell prepared, a reaction, a usable slot, and can see the caster
within range is offered the chance to interrupt it. The window runs from
``SpellAction.resolve`` before the spell takes effect.

Resolution itself lives on ``CounterspellSpell`` (2014: auto-success when the
counter slot >= the target spell level, else an ability check; 2024: the
caster makes a CON save). This module only finds candidates, asks their
controllers, and reports whether the spell was countered.
"""

from natural20.action import AsyncReactionHandler

COUNTERSPELL_SPELL = 'counterspell'
REACTION_TYPE = 'counterspell'


def _target_spell_level(spell_action):
    for value in (getattr(spell_action, 'at_level', None), getattr(spell_action, 'level', None)):
        if value:
            return int(value)
    props = getattr(getattr(spell_action, 'spell_action', None), 'properties', None) or {}
    return int(props.get('level', 0) or 0)


def _slot_levels_for(entity, spell_details):
    """Slot levels (>= the spell's level) the entity can still spend, with class key."""
    base = int(spell_details.get('level', 3) or 3)
    slot_owner = entity.owner if entity.familiar() else entity
    options = []
    for level in range(base, 10):
        for klass in spell_details.get('spell_list_classes', []):
            class_key = klass.lower()
            try:
                count = slot_owner.spell_slots_count(level, class_key)
            except Exception:
                count = 0
            if count and count > 0:
                options.append((level, class_key))
                break
    return options


def _in_range_and_visible(battle_map, entity, caster, spell_range):
    try:
        distance_ft = battle_map.distance(entity, caster) * getattr(battle_map, 'feet_per_grid', 5)
    except Exception:
        return False
    if distance_ft > spell_range:
        return False
    try:
        return bool(battle_map.can_see(entity, caster))
    except Exception:
        return False


def counterspell_candidates(battle, caster):
    """Hostile creatures able to counter a spell ``caster`` is casting right now."""
    if battle is None or caster is None or not battle.ongoing():
        return []
    battle_map = battle.map_for(caster)
    if battle_map is None:
        return []
    session = battle.session
    spell_details = session.load_spell(COUNTERSPELL_SPELL)
    if not spell_details:
        return []
    spell_range = spell_details.get('range', 60)

    from natural20.actions.spell_action import SpellAction

    candidates = []
    for entity in list(battle.entities.keys()):
        if entity is caster or not hasattr(entity, 'prepared_spells'):
            continue
        if COUNTERSPELL_SPELL not in (entity.prepared_spells() or []):
            continue
        if not entity.conscious() or not battle.opposing(entity, caster):
            continue
        if battle.map_for(entity) is not battle_map:
            continue
        if not SpellAction.can_cast(entity, battle, COUNTERSPELL_SPELL):
            continue
        if not _in_range_and_visible(battle_map, entity, caster, spell_range):
            continue
        candidates.append(entity)
    return candidates


def build_counterspell_actions(battle, entity, caster, target_spell_level):
    """One Counterspell ``SpellAction`` per slot level the entity can spend."""
    from natural20.actions.spell_action import SpellAction
    from natural20.utils.spell_loader import load_spell_class

    session = battle.session
    spell_details = session.load_spell(COUNTERSPELL_SPELL)
    spell_class = load_spell_class('CounterspellSpell')
    actions = []
    for slot_level, class_key in _slot_levels_for(entity, spell_details):
        action = SpellAction(session, entity, 'spell')
        action.spell = spell_details
        action.level = spell_details.get('level', 3)
        action.at_level = slot_level
        action.spellcasting_class = class_key
        action.spell_class = spell_class
        action.target = caster
        action.as_reaction = True
        action.opts = {'target_spell_level': target_spell_level}
        instance = spell_class(session, entity, 'CounterspellSpell', spell_details)
        instance.action = action
        action.spell_action = instance
        actions.append(action)
    return actions


def choose_counterspell(entity, battle, valid_actions, event):
    """Heuristic pick for AI controllers; ``None`` declines."""
    if not valid_actions:
        return None
    target_level = int((event or {}).get('target_spell_level', 0) or 0)
    if target_level <= 0:
        return None
    ordered = sorted(valid_actions, key=lambda a: a.at_level)
    ruleset = getattr(battle.session, 'ruleset', None) if battle is not None else None
    if ruleset is not None and ruleset.counterspell_resolution() == 'caster_con_save':
        return ordered[0]
    for action in ordered:
        if action.at_level >= target_level:
            return action
    return ordered[0]


def _countered_resolution(events):
    for item in events:
        if item.get('type') == 'abjuration_check':
            return item.get('resolution')
    return None


def run_counterspell_window(battle, spell_action):
    """Offer Counterspell to eligible enemies of the caster.

    Returns ``(countered, events)``. Progress is cached on ``spell_action`` so
    re-resolving it after an async (player) reaction prompt does not re-ask
    or re-charge creatures that already reacted.
    """
    state = getattr(spell_action, '_counterspell_state', None)
    if state is None:
        state = {'resolved': set(), 'events': [], 'countered': False, 'resolution': None}
        spell_action._counterspell_state = state
    if state['countered']:
        return True, list(state['events'])

    caster = spell_action.source
    target_spell_level = _target_spell_level(spell_action)
    spell_props = getattr(spell_action.spell_action, 'properties', None) or {}

    for entity in counterspell_candidates(battle, caster):
        if entity.entity_uid in state['resolved']:
            continue
        actions = build_counterspell_actions(battle, entity, caster, target_spell_level)
        if not actions:
            state['resolved'].add(entity.entity_uid)
            continue
        controller = battle.controller_for(entity)
        if controller is None or not hasattr(controller, 'select_reaction'):
            state['resolved'].add(entity.entity_uid)
            continue

        event = {
            'type': REACTION_TYPE,
            'trigger': REACTION_TYPE,
            'source': entity,
            'target': caster,
            'caster': caster,
            'spell': spell_props,
            'target_spell_level': target_spell_level,
        }
        stored = spell_action.has_async_reaction_for_source(entity, REACTION_TYPE)
        chosen = stored if stored is not False else controller.select_reaction(
            entity, battle, battle.map_for(entity), actions, event,
        )
        if hasattr(chosen, 'send'):
            raise AsyncReactionHandler(entity, chosen, spell_action, REACTION_TYPE)

        state['resolved'].add(entity.entity_uid)
        if not chosen:
            continue

        counter = chosen.spell_action
        results = counter.resolve(entity, battle, chosen, battle.map_for(entity)) or []
        counter.consume(battle)
        state['events'].extend(results)
        if any(item.get('type') == 'abjuration_check' and item.get('success') for item in results):
            state['countered'] = True
            state['resolution'] = _countered_resolution(results)
            state['events'].append({
                'type': 'spell_countered',
                'source': entity,
                'target': caster,
                'spell': spell_props,
                'effect': counter,
            })
            break

    return state['countered'], list(state['events'])

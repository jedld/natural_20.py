"""Fear: 30-ft cone, WIS save or frightened and forced to flee; repeat save only out of sight."""
from natural20.actions.dash import DashAction
from natural20.spell.fear_spell import FearSpell
from natural20.utils.fear import flee_choice, flee_source, is_frightened_of
from tests.ranger_spell_helpers import Arena, forced_save


def _arena(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', caster='wizard', spells=['fear'])
    arena.map.move_to(arena.ally, 2, 8, arena.battle)  # out of the cone
    return arena


def _cast(arena, goblin_save=1, goblin2_save=1):
    with forced_save(arena.goblin, goblin_save), forced_save(arena.goblin2, goblin2_save):
        return arena.cast('fear', 3, [6, 2])


def test_yaml_definition(tmp_path):
    arena = _arena(tmp_path)
    details = arena.spell('fear')
    assert details['spell_class'] == 'Natural20::Fear'
    assert details['range_cone'] == 30 and details['concentration']
    assert 'wizard' in [c.lower() for c in details['spell_list_classes']]


def test_failed_saves_frighten_and_force_flight(tmp_path):
    arena = _arena(tmp_path)
    _cast(arena, goblin_save=1, goblin2_save=30)
    assert is_frightened_of(arena.goblin, arena.caster)
    assert not is_frightened_of(arena.goblin2, arena.caster)
    assert flee_source(arena.goblin) is arena.caster
    assert isinstance(arena.caster.concentration, FearSpell)
    assert not is_frightened_of(arena.ally, arena.caster)


def test_everyone_saves_no_concentration(tmp_path):
    arena = _arena(tmp_path)
    _cast(arena, goblin_save=30, goblin2_save=30)
    assert arena.caster.concentration is None
    assert arena.caster.spell_slots['wizard'][3] == 2


def test_flee_choice_dashes_first(tmp_path):
    arena = _arena(tmp_path)
    _cast(arena)
    arena.goblin.reset_turn(arena.battle)
    dash = DashAction(arena.session, arena.goblin, 'dash')
    assert flee_choice(arena.goblin, arena.battle, [dash]) is dash


def test_repeat_save_only_when_caster_unseen(tmp_path):
    arena = _arena(tmp_path)
    _cast(arena)
    with forced_save(arena.goblin, 30):
        arena.goblin.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert is_frightened_of(arena.goblin, arena.caster)  # still sees the caster

    arena.map.can_see = lambda *args, **kwargs: False
    with forced_save(arena.goblin, 30):
        arena.goblin.resolve_trigger('end_of_turn', {'battle': arena.battle})
    assert not is_frightened_of(arena.goblin, arena.caster)
    assert is_frightened_of(arena.goblin2, arena.caster)
    assert isinstance(arena.caster.concentration, FearSpell)


def test_dropping_concentration_ends_fear(tmp_path):
    arena = _arena(tmp_path)
    _cast(arena)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert not is_frightened_of(arena.goblin, arena.caster)
    assert not is_frightened_of(arena.goblin2, arena.caster)
    assert not arena.goblin.entity_event_hooks.get('end_of_turn')


def test_save_load_round_trip(tmp_path):
    arena = _arena(tmp_path)
    _cast(arena)
    session2, battle2, _maps2 = arena.round_trip()
    goblin2 = session2.entity_by_uid(arena.goblin.entity_uid)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert is_frightened_of(goblin2, caster2)
    assert flee_source(goblin2) is caster2
    assert goblin2.entity_event_hooks.get('end_of_turn')
    caster2.dismiss_effect(caster2.concentration)
    assert not is_frightened_of(goblin2, caster2)

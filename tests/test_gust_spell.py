"""Gust (Xanathar's pack): STR save or a Medium-or-smaller creature is pushed 5 ft away."""
from natural20.spell.push_creature_spell import PushCreatureSpell
from tests.ranger_spell_helpers import Arena, forced_save

PACK = 'xanathars_guide'


def _arena(tmp_path):
    return Arena(tmp_path, ruleset='5e-2024', packs=[PACK], caster='wizard', spells=['gust'])


def test_pack_definition(tmp_path):
    arena = _arena(tmp_path)
    details = arena.spell('gust')
    assert details['spell_class'] == 'Natural20::PushCreature'
    assert details['level'] == 0 and details['max_size'] == 'medium'


def test_failed_save_pushes_away(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin2, 1):
        action = arena.cast('gust', 0, arena.goblin2)
    assert arena.map.position_of(arena.goblin2) == [8, 2]
    assert action.result[0]['success'] is False


def test_successful_save_resists(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin2, 30):
        arena.cast('gust', 0, arena.goblin2)
    assert arena.map.position_of(arena.goblin2) == [7, 2]


def test_too_large_creature_is_unaffected(tmp_path):
    arena = _arena(tmp_path)
    arena.goblin2.size_identifier = lambda: 'large'
    spell = PushCreatureSpell(arena.session, arena.caster, 'PushCreatureSpell', arena.spell('gust'))
    spell.validate(arena.map, arena.goblin2, arena.battle)
    assert 'spell.push_creature.too_large' in repr(spell.validation_issues)
    with forced_save(arena.goblin2, 1):
        action = arena.cast('gust', 0, arena.goblin2)
    assert action.result[0].get('too_large')
    assert arena.map.position_of(arena.goblin2) == [7, 2]
    del arena.goblin2.size_identifier


def test_hit_probability_with_multi_die_save(tmp_path):
    from natural20.die_roll import DieRoll, DieRolls
    arena = _arena(tmp_path)
    arena.goblin2.save_throw = lambda *a, **k: DieRolls([DieRoll([10], 0, 20), DieRoll([2], 0, 4)])
    spell = PushCreatureSpell(arena.session, arena.caster, 'PushCreatureSpell', arena.spell('gust'))
    spell.action = type('A', (), {'target': arena.goblin2})()
    prob = spell.compute_hit_probability(arena.battle)
    del arena.goblin2.save_throw
    assert 0.0 <= prob <= 1.0


def test_cantrip_spends_no_slot(tmp_path):
    arena = _arena(tmp_path)
    slots = dict(arena.caster.spell_slots['wizard'])
    with forced_save(arena.goblin2, 30):
        arena.cast('gust', 0, arena.goblin2)
    assert arena.caster.spell_slots['wizard'] == slots


def test_save_load_round_trip(tmp_path):
    arena = _arena(tmp_path)
    with forced_save(arena.goblin2, 1):
        arena.cast('gust', 0, arena.goblin2)
    session2, _battle2, maps2 = arena.round_trip()
    goblin2 = session2.entity_by_uid(arena.goblin2.entity_uid)
    assert maps2['field'].position_of(goblin2) == [8, 2]
    assert session2.load_spell('gust')['push_distance'] == 5

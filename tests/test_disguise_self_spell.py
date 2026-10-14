"""Disguise Self: cosmetic disguise that observers can see through with Investigation."""
from natural20.die_roll import DieRoll
from natural20.spell.disguise_self_spell import disguise_of, is_disguised, see_through_disguise
from tests.ranger_spell_helpers import Arena


def _cast(tmp_path, with_battle=False):
    arena = Arena(tmp_path, caster='wizard', with_battle=with_battle, spells=['disguise_self'])
    arena.cast('disguise_self', 1)
    return arena


def test_yaml_definition(tmp_path):
    arena = Arena(tmp_path, caster='wizard', spells=['disguise_self'])
    details = arena.spell('disguise_self')
    assert details['spell_class'] == 'Natural20::DisguiseSelf'
    assert details['ai_in_combat'] is False
    assert 'wizard' in [c.lower() for c in details['spell_list_classes']]


def test_cast_sets_disguise_with_save_dc(tmp_path):
    arena = _cast(tmp_path)
    assert is_disguised(arena.caster)
    disguise = disguise_of(arena.caster)
    assert disguise['description']
    assert disguise['dc'] == arena.caster.spell_save_dc('intelligence')
    assert arena.caster.spell_slots['wizard'][1] == 2


def test_cast_works_in_combat_too(tmp_path):
    arena = _cast(tmp_path, with_battle=True)
    assert is_disguised(arena.caster)


def test_investigation_check_sees_through(tmp_path):
    arena = _cast(tmp_path)
    DieRoll.fudge(1)
    try:
        failed, _roll = see_through_disguise(arena.goblin, arena.caster)
    finally:
        DieRoll.unfudge()
    assert not failed
    DieRoll.fudge(20)
    try:
        success, roll = see_through_disguise(arena.goblin, arena.caster)
    finally:
        DieRoll.unfudge()
    assert success and roll is not None
    assert arena.goblin.entity_uid in disguise_of(arena.caster)['seen_through_by']


def test_undisguised_target_is_seen_as_is(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['disguise_self'])
    assert see_through_disguise(arena.goblin, arena.caster) == (True, None)


def test_ending_the_spell_removes_disguise(tmp_path):
    arena = _cast(tmp_path)
    effect = arena.caster.effects['disguise_self'][0]['effect']
    arena.caster.dismiss_effect(effect)
    assert not is_disguised(arena.caster)
    assert disguise_of(arena.caster) is None


def test_save_load_round_trip(tmp_path):
    arena = _cast(tmp_path, with_battle=True)
    session2, _battle2, _maps2 = arena.round_trip()
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert is_disguised(caster2)
    assert disguise_of(caster2)['dc'] == disguise_of(arena.caster)['dc']

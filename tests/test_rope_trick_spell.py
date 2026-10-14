"""Rope Trick: out-of-combat hideout; members are untargetable and can't attack or cast."""
from natural20.actions.spell_action import SpellAction
from natural20.spell.rope_trick_spell import RopeTrickSpell
from natural20.utils.action_restrictions import is_restricted
from tests.ranger_spell_helpers import Arena


def _cast(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    arena.cast('rope_trick', 2)
    effect = arena.caster.effects['rope_trick'][0]['effect']
    return arena, effect


def test_yaml_definition(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    details = arena.spell('rope_trick')
    assert details['spell_class'] == 'Natural20::RopeTrick'
    assert 'out_of_combat' in details['requires']
    assert details['max_creatures'] == 8


def test_cannot_cast_during_combat(tmp_path):
    arena = Arena(tmp_path, caster='wizard', spells=['rope_trick'])
    assert not SpellAction.can_cast(arena.caster, arena.battle, 'rope_trick')


def test_can_cast_out_of_combat(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    assert SpellAction.can_cast(arena.caster, None, 'rope_trick')


def test_members_hidden_and_restricted(tmp_path):
    arena, effect = _cast(tmp_path)
    assert isinstance(effect, RopeTrickSpell)
    for member in (arena.caster, arena.ally):
        assert not member.allow_targeting()
        assert is_restricted(member, 'attack') and is_restricted(member, 'spell')
    assert arena.goblin.allow_targeting()
    assert not arena.goblin.has_effect('rope_trick')


def test_member_cap(tmp_path):
    arena = Arena(tmp_path, caster='wizard', with_battle=False, spells=['rope_trick'])
    spell = RopeTrickSpell(arena.session, arena.caster, 'RopeTrickSpell',
                           dict(arena.spell('rope_trick'), max_creatures=1))
    assert spell.members_for(arena.caster) == [arena.caster]


def test_ending_the_spell_restores_members(tmp_path):
    arena, effect = _cast(tmp_path)
    arena.caster.dismiss_effect(effect)
    for member in (arena.caster, arena.ally):
        assert member.allow_targeting()
        assert not is_restricted(member, 'attack')
        assert not member.has_effect('rope_trick')


def test_save_load_round_trip(tmp_path):
    arena, _effect = _cast(tmp_path)
    session2, _battle2, _maps2 = arena.round_trip()
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    ally2 = session2.entity_by_uid(arena.ally.entity_uid)
    assert not ally2.allow_targeting() and not caster2.allow_targeting()
    assert is_restricted(ally2, 'spell')
    caster2.dismiss_effect(caster2.effects['rope_trick'][0]['effect'])
    assert ally2.allow_targeting() and caster2.allow_targeting()

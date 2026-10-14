"""Feather Fall: up to five creatures get the feather_fall status (no fall damage) for a minute."""
from natural20.spell.utility_spells import FeatherFallEffect
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('feather_fall')
    assert spell_is_implemented('feather_fall', meta)
    assert meta['casting_time'] == '1:reaction'


def test_grants_status_until_it_expires():
    arena = SpellArena()
    arena.learn(arena.wizard, 'feather_fall', 1)
    action = arena.cast(arena.wizard, 'feather_fall', 1, [arena.wizard, arena.cleric])
    assert 'feather_fall' in arena.wizard.statuses
    assert 'feather_fall' in arena.cleric.statuses
    effect = next(d['effect'] for d in arena.cleric.effects['feather_fall'])
    assert isinstance(effect, FeatherFallEffect)
    assert any(i['type'] == 'feather_fall' for i in action.result)
    arena.session.game_time += 61
    arena.cleric._cleanup_effects()
    assert 'feather_fall' not in arena.cleric.statuses


def test_existing_status_is_left_alone():
    arena = SpellArena()
    arena.cleric.statuses.append('feather_fall')
    arena.learn(arena.wizard, 'feather_fall', 1)
    arena.cast(arena.wizard, 'feather_fall', 1, [arena.cleric])
    arena.session.game_time += 61
    arena.cleric._cleanup_effects()
    assert 'feather_fall' in arena.cleric.statuses

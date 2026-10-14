"""Mending: repairs a small break in an object; out of combat only (1-minute casting time)."""
from natural20.actions.spell_action import SpellAction
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('mending')
    assert spell_is_implemented('mending', meta)
    assert meta['casting_time'] == '1:minute'


def test_logs_repair():
    arena = SpellArena(with_battle=False)
    arena.learn(arena.wizard, 'mending', 0)
    events = []
    arena.session.event_manager.register_event_listener('mending', events.append)
    arena.cast(arena.wizard, 'mending', 0, [1, 5])
    assert events and events[0]['source'] is arena.wizard
    assert events[0]['target'] == [1, 5]


def test_not_castable_mid_battle():
    arena = SpellArena()
    arena.learn(arena.wizard, 'mending', 0)
    assert not SpellAction.can_cast(arena.wizard, arena.battle, 'mending')

"""Prestidigitation: a harmless trick at a point, logged as an event."""
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('prestidigitation')
    assert spell_is_implemented('prestidigitation', meta)
    assert meta['ai_in_combat'] is False


def test_logs_the_chosen_trick():
    arena = SpellArena(with_battle=False)
    arena.learn(arena.wizard, 'prestidigitation', 0)
    events = []
    arena.session.event_manager.register_event_listener('prestidigitation', events.append)
    arena.cast(arena.wizard, 'prestidigitation', 0, [1, 5], opts={'trick': 'light'})
    assert events and events[0]['trick'] == 'light'
    assert events[0]['target'] == [1, 5]


def test_unknown_trick_falls_back_to_sensory():
    arena = SpellArena(with_battle=False)
    arena.learn(arena.wizard, 'prestidigitation', 0)
    action = arena.cast(arena.wizard, 'prestidigitation', 0, [1, 5], opts={'trick': 'fireball'})
    assert action.result[0]['trick'] == 'sensory'

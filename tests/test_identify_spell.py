"""Identify: reports a touched creature's magic items and the spells affecting it."""
from natural20.spell.utility_spells import magic_items_of
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('identify')
    assert spell_is_implemented('identify', meta)
    assert meta['spell_list_classes'] == ['Bard', 'Wizard']


def test_reports_active_spells():
    arena = SpellArena(with_battle=False)
    arena.learn(arena.wizard, 'identify', 1)
    arena.learn(arena.wizard, 'mage_armor', 1)
    arena.cast(arena.wizard, 'mage_armor', 1, arena.wizard)
    action = arena.cast(arena.wizard, 'identify', 1, arena.wizard)
    item = next(i for i in action.result if i['type'] == 'identify')
    assert any('Mage Armor' in str(s) for s in item['spells'])


def test_lists_magic_items():
    arena = SpellArena(with_battle=False)
    original = arena.session.load_thing

    def load_thing(name):
        thing = original(name)
        if name == 'dagger' and isinstance(thing, dict):
            thing = dict(thing, magical=True, label='Glowing Dagger')
        return thing

    arena.session.load_thing = load_thing
    arena.wizard.properties['equipped'] = ['dagger']
    assert 'Glowing Dagger' in magic_items_of(arena.wizard)

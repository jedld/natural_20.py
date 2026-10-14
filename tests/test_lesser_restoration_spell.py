"""Lesser Restoration: ends one of paralyzed/blinded/poisoned/deafened or a disease."""
from natural20.spell.lesser_restoration_spell import end_condition
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def _arena():
    arena = SpellArena()
    arena.learn(arena.cleric, 'lesser_restoration', 2)
    return arena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('lesser_restoration')
    assert spell_is_implemented('lesser_restoration', meta)
    assert meta['spell_list_classes'] == ['Bard', 'Cleric', 'Druid', 'Paladin', 'Ranger']


def test_auto_picks_most_debilitating_condition():
    arena = _arena()
    arena.wizard.statuses.extend(['poisoned', 'paralyzed', 'deafened'])
    action = arena.cast(arena.cleric, 'lesser_restoration', 2, arena.wizard)
    assert 'paralyzed' not in arena.wizard.statuses
    assert 'poisoned' in arena.wizard.statuses
    assert any(i.get('ended') == 'paralyzed' for i in action.result)
    assert arena.cleric.spell_slots['cleric'][2] == 3


def test_explicit_condition_choice():
    arena = _arena()
    arena.wizard.statuses.extend(['poisoned', 'blinded'])
    arena.cast(arena.cleric, 'lesser_restoration', 2, arena.wizard, opts={'condition': 'poisoned'})
    assert 'poisoned' not in arena.wizard.statuses
    assert 'blinded' in arena.wizard.statuses


def test_cures_a_disease():
    arena = _arena()
    arena.wizard.statuses.append('disease_sewer_plague')
    arena.cast(arena.cleric, 'lesser_restoration', 2, arena.wizard)
    assert 'disease_sewer_plague' not in arena.wizard.statuses


class _Hold:
    id = 'hold_test'

    def __init__(self, source):
        self.source = source
        self.dismissed = False

    def dismiss(self, entity, _descriptor=None, opts=None):
        self.dismissed = True


def test_ends_effect_that_imposes_paralysis():
    arena = _arena()
    hold = _Hold(arena.ogre)
    arena.wizard.statuses.append('paralyzed')
    arena.wizard.register_effect('hold_person', _Hold, effect=hold, source=arena.ogre)
    arena.cast(arena.cleric, 'lesser_restoration', 2, arena.wizard)
    assert 'paralyzed' not in arena.wizard.statuses
    assert not arena.wizard.has_effect('hold_person')
    assert hold.dismissed


def test_end_condition_helper_ignores_absent_conditions():
    arena = _arena()
    assert end_condition(arena.wizard, 'disease') is None


def test_nothing_to_cure_still_logs():
    arena = _arena()
    action = arena.cast(arena.cleric, 'lesser_restoration', 2, arena.wizard)
    item = next(i for i in action.result if i['type'] == 'lesser_restoration')
    assert item['condition'] is None

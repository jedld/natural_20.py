"""Faerie Fire: DEX save or be outlined (advantage for attackers, no invisibility)."""
from natural20.utils.serialization import Serialization
from natural20.utils.spell_loader import spell_is_implemented
from natural20.spell.faerie_fire_spell import FaerieFireEffect
from tests.spell_cast_helpers import SpellArena


def _outlined(arena):
    arena.learn(arena.wizard, 'faerie_fire', 1)
    arena.cast(arena.wizard, 'faerie_fire', 1, [3, 4], d20=1)
    return arena


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('faerie_fire')
    assert spell_is_implemented('faerie_fire', meta)
    assert meta['spell_list_classes'] == ['Bard', 'Druid']


def test_failed_save_outlines_creature_and_grants_advantage():
    arena = _outlined(SpellArena())
    ogre = arena.ogre
    assert ogre.has_effect('targeted_advantage_override')
    assert ogre.has_effect('invisibility_suppressed')
    adv, _dis = ogre.eval_effect('targeted_advantage_override', {'target': ogre, 'source': arena.cleric,
                                                                  'value': [[], []]}) or ([], [])
    assert 'faerie_fire' in adv
    assert isinstance(arena.wizard.concentration, FaerieFireEffect)


def test_successful_save_avoids_outline():
    arena = SpellArena()
    arena.learn(arena.wizard, 'faerie_fire', 1)
    arena.cast(arena.wizard, 'faerie_fire', 1, [3, 4], d20=20)
    assert not arena.ogre.has_effect('targeted_advantage_override')


def test_invisible_outlined_creature_is_seen():
    arena = _outlined(SpellArena())
    arena.ogre.statuses.append('invisible')
    assert not arena.ogre.invisible()


def test_dropping_concentration_ends_outline():
    arena = _outlined(SpellArena())
    arena.wizard.dismiss_effect(arena.wizard.concentration)
    assert not arena.ogre.has_effect('targeted_advantage_override')
    assert arena.wizard.concentration is None


def test_save_and_load_keeps_outline():
    arena = _outlined(SpellArena())
    serializer = Serialization()
    _session, battle, _maps = serializer.deserialize(
        serializer.serialize(arena.session, arena.battle, [arena.map]))
    ogre = next(e for e in battle.entities if e.entity_uid == arena.ogre.entity_uid)
    wizard = next(e for e in battle.entities if e.entity_uid == arena.wizard.entity_uid)
    assert ogre.has_effect('targeted_advantage_override')
    wizard.dismiss_effect(wizard.concentration)
    assert not ogre.has_effect('targeted_advantage_override')

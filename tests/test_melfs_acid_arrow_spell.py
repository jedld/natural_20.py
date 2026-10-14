"""Melf's Acid Arrow: 4d4 on hit plus 2d4 at the end of the target's next turn; half and no burn on a miss."""
from natural20.spell.melfs_acid_arrow_spell import AcidArrowBurn
from natural20.utils.serialization import Serialization
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena


def _cast(arena, d20, level=2):
    arena.learn(arena.wizard, 'melfs_acid_arrow', level)
    return arena.cast(arena.wizard, 'melfs_acid_arrow', level, arena.ogre, d20=d20)


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('melfs_acid_arrow')
    assert spell_is_implemented('melfs_acid_arrow', meta)


def test_hit_applies_burn_that_fires_at_end_of_targets_turn():
    arena = SpellArena()
    action = _cast(arena, d20=15)
    assert any(i['type'] == 'spell_damage' for i in action.result)
    assert arena.ogre.has_effect('acid_arrow')
    hp = arena.ogre.hp()
    arena.end_turn(arena.ogre)
    assert arena.ogre.hp() < hp
    assert not arena.ogre.has_effect('acid_arrow')
    hp = arena.ogre.hp()
    arena.end_turn(arena.ogre)
    assert arena.ogre.hp() == hp


def test_miss_deals_half_and_no_burn():
    arena = SpellArena()
    hp = arena.ogre.hp()
    action = _cast(arena, d20=2)
    assert any(i['type'] == 'spell_miss' for i in action.result)
    half = [i for i in action.result if i['type'] == 'spell_damage']
    assert half and half[0].get('half_damage')
    assert arena.ogre.hp() <= hp
    assert not arena.ogre.has_effect('acid_arrow')


def test_upcast_adds_to_both_parts():
    arena = SpellArena()
    action = _cast(arena, d20=15, level=4)
    burn = next(i for i in action.result if i['type'] == 'melfs_acid_arrow')
    assert burn['burn_dice'] == '4d4'


def test_burn_survives_save_and_load():
    arena = SpellArena()
    _cast(arena, d20=15)
    serializer = Serialization()
    _session, battle, _maps = serializer.deserialize(
        serializer.serialize(arena.session, arena.battle, [arena.map]))
    ogre = next(e for e in battle.entities if e.entity_uid == arena.ogre.entity_uid)
    effect = next(d['effect'] for d in ogre.effects['acid_arrow'])
    assert isinstance(effect, AcidArrowBurn)
    hp = ogre.hp()
    ogre.resolve_trigger('end_of_turn', {'battle': battle})
    assert ogre.hp() < hp

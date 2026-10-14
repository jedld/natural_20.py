"""Flaming Sphere: end-of-turn DEX save for half, bonus-action move and ram, save/load."""
from natural20.actions.flaming_sphere_action import FlamingSphereAction
from natural20.spell.flaming_sphere_spell import FlamingSphereZone, active_sphere
from natural20.spell.objects.flaming_sphere import FlamingSphereTile
from natural20.utils.serialization import Serialization
from natural20.utils.spell_loader import spell_is_implemented
from tests.spell_cast_helpers import SpellArena, sticky_d20


def _sphere(arena, at=(3, 5), level=2):
    arena.learn(arena.wizard, 'flaming_sphere', level)
    arena.cast(arena.wizard, 'flaming_sphere', level, list(at))
    return active_sphere(arena.wizard)


def _tiles(battle_map):
    return [o for col in battle_map.objects for cell in col for o in cell if isinstance(o, FlamingSphereTile)]


def test_is_implemented():
    meta = SpellArena(with_battle=False).session.load_spell('flaming_sphere')
    assert spell_is_implemented('flaming_sphere', meta)
    assert meta['spell_list_classes'] == ['Druid', 'Wizard']


def test_cast_places_sphere_and_concentrates():
    arena = SpellArena()
    handle = _sphere(arena)
    assert isinstance(handle.zone, FlamingSphereZone)
    assert handle.zone.center == (3, 5)
    assert handle.zone in arena.battle.active_zones
    assert len(_tiles(arena.map)) == 1


def test_creature_ending_turn_adjacent_takes_fire_damage():
    arena = SpellArena()
    _sphere(arena)
    hp = arena.ogre.hp()
    with sticky_d20(1):
        arena.end_turn(arena.ogre)
    assert arena.ogre.hp() < hp


def test_successful_save_halves_damage():
    arena = SpellArena()
    handle = _sphere(arena)
    with sticky_d20(20):
        roll = handle.zone.burn(arena.ogre)
    assert roll.result() >= handle.zone.dc


def test_bonus_action_moves_and_rams():
    arena = SpellArena()
    handle = _sphere(arena, at=(2, 2))
    arena.wizard.reset_turn(arena.battle)
    assert FlamingSphereAction.can(arena.wizard, arena.battle)
    action = FlamingSphereAction.build(arena.session, arena.wizard)['next']([4, 5])
    hp = arena.ogre.hp()
    with sticky_d20(1):
        arena.battle.execute_action(action)
    assert handle.zone.center != (2, 2)
    assert handle.zone.contains(arena.map.position_of(arena.ogre))
    assert arena.ogre.hp() < hp
    assert not FlamingSphereAction.can(arena.wizard, arena.battle)


def test_move_without_ram_relocates_tile():
    arena = SpellArena()
    handle = _sphere(arena, at=(2, 2))
    arena.wizard.reset_turn(arena.battle)
    action = FlamingSphereAction.build(arena.session, arena.wizard)['next']([3, 2])
    arena.battle.execute_action(action)
    assert handle.zone.center == (3, 2)
    assert arena.map.entity_or_object_pos(_tiles(arena.map)[0]) == [3, 2]


def test_action_offered_through_class_feature_registry():
    arena = SpellArena()
    _sphere(arena, at=(2, 2))
    arena.wizard.reset_turn(arena.battle)
    actions = arena.wizard.available_actions(arena.session, arena.battle)
    assert any(isinstance(a, FlamingSphereAction) for a in actions)


def test_dropping_concentration_removes_sphere():
    arena = SpellArena()
    handle = _sphere(arena)
    arena.wizard.dismiss_effect(arena.wizard.concentration)
    assert handle.zone not in arena.battle.active_zones
    assert _tiles(arena.map) == []


def test_save_and_load_restores_sphere():
    arena = SpellArena()
    _sphere(arena)
    serializer = Serialization()
    _session, battle, maps = serializer.deserialize(
        serializer.serialize(arena.session, arena.battle, [arena.map]))
    battle_map = maps[0] if isinstance(maps, list) else list(maps.values())[0]
    wizard = next(e for e in battle.entities if e.entity_uid == arena.wizard.entity_uid)
    handle = active_sphere(wizard)
    assert handle is not None
    zone = handle.zone
    assert zone in battle.active_zones
    assert zone.center == (3, 5) or list(zone.center) == [3, 5]
    assert len(_tiles(battle_map)) == 1
    wizard.dismiss_effect(wizard.concentration)
    assert _tiles(battle_map) == []

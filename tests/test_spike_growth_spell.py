"""Spike Growth: difficult-terrain thorns that deal 2d4 per 5 ft moved inside."""
from natural20.actions.move_action import MoveAction
from natural20.spell.objects.spike_growth_tile import SpikeGrowthTile
from natural20.spell.spike_growth_spell import SpikeGrowthEffect, SpikeGrowthZone
from tests.ranger_spell_helpers import Arena

CENTER = [11, 2]  # radius 4 squares: x 7..15, so goblin2 (7, 2) is inside and goblin (6, 2) is not


def _cast(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['spike_growth'])
    arena.cast('spike_growth', 2, CENTER)
    zone = next(z for z in arena.battle.active_zones if isinstance(z, SpikeGrowthZone))
    return arena, zone


def _damage_events(arena):
    events = []
    arena.session.event_manager.register_event_listener(
        'spike_growth_damage', lambda event: events.append(event))
    return events


def _walk(arena, entity, path):
    entity.reset_turn(arena.battle)
    arena.battle.current_turn_index = arena.battle.combat_order.index(entity)
    move = MoveAction(arena.session, entity, 'move')
    move.target = path[-1]
    move.move_path = path
    arena.battle.action(move)
    arena.battle.commit(move)


def test_cast_creates_zone_tiles_and_concentration(tmp_path):
    arena, zone = _cast(tmp_path)
    assert isinstance(arena.caster.concentration, SpikeGrowthEffect)
    assert zone.contains((7, 2)) and not zone.contains((6, 2))
    tiles = [o for o in arena.map.interactable_objects if isinstance(o, SpikeGrowthTile)]
    assert len(tiles) == len(zone.squares)
    assert arena.caster.spell_slots['ranger'][2] == 2


def test_area_is_difficult_terrain(tmp_path):
    arena = Arena(tmp_path, ruleset='5e-2024', spells=['spike_growth'])
    path = [(6, 4), (7, 4), (8, 4)]
    before = arena.map.movement_cost(arena.goblin, path, arena.battle)
    arena.cast('spike_growth', 2, CENTER)
    after = arena.map.movement_cost(arena.goblin, path, arena.battle)
    assert after.budget < before.budget, (before, after)


def test_each_step_inside_deals_damage(tmp_path):
    arena, zone = _cast(tmp_path)
    events = _damage_events(arena)
    hp = arena.goblin.hp()
    _walk(arena, arena.goblin, [(6, 2), (6, 3), (7, 3), (8, 3)])
    assert [tuple(e['position']) for e in events] == [(7, 3), (8, 3)]
    assert arena.goblin.hp() < hp or arena.goblin.dead()


def test_moving_outside_is_harmless(tmp_path):
    arena, _zone = _cast(tmp_path)
    events = _damage_events(arena)
    _walk(arena, arena.goblin, [(6, 2), (6, 3), (5, 3)])
    assert events == []


def test_dismiss_removes_thorns(tmp_path):
    arena, zone = _cast(tmp_path)
    arena.caster.dismiss_effect(arena.caster.concentration)
    assert not [o for o in arena.map.interactable_objects if isinstance(o, SpikeGrowthTile)]
    assert zone not in arena.battle.active_zones or zone.expired()


def test_save_load_round_trip(tmp_path):
    arena, zone = _cast(tmp_path)
    session2, battle2, maps2 = arena.round_trip()
    zone2 = next(z for z in battle2.active_zones if isinstance(z, SpikeGrowthZone))
    assert zone2.contains((7, 2)) and zone2.damage_dice == zone.damage_dice
    tiles2 = [o for o in maps2['field'].interactable_objects if isinstance(o, SpikeGrowthTile)]
    assert len(tiles2) == len(zone.squares)
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    goblin2 = session2.entity_by_uid(arena.goblin.entity_uid)
    events = []
    session2.event_manager.register_event_listener('spike_growth_damage', lambda e: events.append(e))
    goblin2.reset_turn(battle2)
    battle2.current_turn_index = battle2.combat_order.index(goblin2)
    move = MoveAction(session2, goblin2, 'move')
    move.target = (7, 3)
    move.move_path = [(6, 2), (6, 3), (7, 3)]
    battle2.action(move)
    battle2.commit(move)
    assert len(events) == 1
    caster2.dismiss_effect(caster2.concentration)
    assert not [o for o in maps2['field'].interactable_objects if isinstance(o, SpikeGrowthTile)]

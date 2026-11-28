"""Wall of Thorns (SRD): line-of-sight blocking, 4x movement cost, shape
targeting (60 ft wall / 20 ft circle), upcast scaling and 3D fixtures."""
from natural20.spell.wall_of_thorns_spell import (
    WallOfThornsSpell,
    wall_of_thorns_squares,
)
from natural20.web.map_state import classify_object_kind, objects_from_tiles

from tests.ranger_spell_helpers import Arena, forced_save


def test_wall_shape_is_12_squares_centered(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    squares = wall_of_thorns_squares(arena.map, (8, 8), 'wall', wall_length_ft=60)
    assert len(squares) == 12
    assert {s for s in squares} == {(x, 8) for x in range(2, 14)}


def test_circle_shape_is_ring(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    squares = wall_of_thorns_squares(arena.map, (8, 8), 'circle',
                                     circle_diameter_ft=20)
    assert len(squares) == 12
    assert (8, 8) not in squares  # the ring has a hole
    assert (6, 6) in squares and (9, 9) in squares


def test_build_chain_carries_shape_through_clones(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    action = arena.build('wall_of_thorns', 6, 'circle', [8, 8])
    assert action.spell_action.shape == 'circle'


def test_upcast_dice_scale(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    arena.cast('wall_of_thorns', 8, 'wall', [8, 8])
    zone = next(z for z in arena.battle.active_zones if z.name == 'wall_of_thorns')
    # Two slots above 6th: +2d8 on both damage types.
    assert zone.appearance_dice == '9d8'
    assert zone.enter_dice == '9d8'


def test_wall_blocks_los_and_costs_movement(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    caster = arena.caster
    path = [(7, 8), (8, 8)]
    open_cost = arena.map.movement_cost(caster, path, arena.battle)
    arena.cast('wall_of_thorns', 6, 'wall_ns', [8, 8])
    zone = next(z for z in arena.battle.active_zones if z.name == 'wall_of_thorns')
    assert len(zone._square_set) == 12
    # Opaque squares: line of sight along the crossing axis is blocked.
    assert not arena.map.line_of_sight(4, 8, 12, 8)
    assert arena.map.opaque(8, 8, origin=(4, 8))
    # 5 ft through the wall costs 4 squares of movement (3 more than an
    # open square). Movement.budget is the remaining budget after the path.
    wall_cost = arena.map.movement_cost(caster, path, arena.battle)
    assert open_cost.budget - wall_cost.budget == 3


def test_wall_itself_is_visible_through_fog(tmp_path):
    """see_own_square: players see the thorn wall itself; squares behind
    it stay fogged, and so do far wall squares seen through other thorns."""
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    caster = arena.caster
    arena.map.move_to(caster, 8, 6, arena.battle)
    arena.cast('wall_of_thorns', 6, 'wall', [8, 8])
    tiles = [o for o in arena.map.interactable_objects
             if o.properties.get('wall_of_thorns')]
    front = next(o for o in tiles if tuple(arena.map.interactable_objects[o]) == (8, 8))
    far = next(o for o in tiles if tuple(arena.map.interactable_objects[o]) == (2, 8))
    # The wall square in front of the caster is visible (fog + object render).
    assert arena.map.can_see_square(caster, (8, 8))
    assert arena.map.can_see(caster, front)
    # Squares behind the wall stay hidden; so does a distant wall square
    # whose straight path crosses other thorn squares.
    assert not arena.map.can_see_square(caster, (8, 10))
    assert not arena.map.can_see(caster, far)
    # And the fogged-out square does not leak the tile objects: the 2D
    # renderer carries the marker only on visible squares.
    from natural20.web.json_renderer import JsonRenderer
    from natural20.web.map_state import flatten_tiles
    rows = JsonRenderer(arena.map, arena.battle).render(entity_pov=[caster])
    by_pos = {(t['x'], t['y']): t for t in flatten_tiles(rows)}
    assert any(o.get('wall_of_thorns_marker') for o in by_pos[(8, 8)]['objects'])
    assert not by_pos[(8, 10)].get('line_of_sight')
    assert not by_pos[(8, 10)].get('objects')


def test_appearance_damage_hits_occupants(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    goblin = arena.goblin
    arena.map.move_to(goblin, 8, 8, arena.battle)
    with forced_save(goblin, 1):
        arena.cast('wall_of_thorns', 6, 'wall', [8, 8])
    assert goblin.hp() < 7  # 7d8 piercing on a failed save is lethal for a goblin


def test_wall_tile_classifies_as_thorns_for_3d():
    assert classify_object_kind({'type': 'wall_of_thorns_tile',
                                 'name': 'Wall of Thorns'}) == 'thorns'
    objects = objects_from_tiles([{
        'x': 4, 'y': 5,
        'objects': [{
            'id': 'wall_of_thorns_tile:abc',
            'name': 'Wall of Thorns',
            'type': 'wall_of_thorns_tile',
            'image': None,
        }],
    }])
    assert len(objects) == 1 and objects[0]['kind'] == 'thorns'


def test_spell_class_registration():
    from natural20.utils.spell_loader import load_spell_class
    assert load_spell_class('WallOfThornsSpell') is WallOfThornsSpell


def test_save_load_round_trip(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=['wall_of_thorns'])
    arena.cast('wall_of_thorns', 6, 'wall', [8, 8])
    session2, battle2, maps2 = arena.round_trip()
    zone2 = next(z for z in battle2.active_zones if z.name == 'wall_of_thorns')
    assert len(zone2._square_set) == 12
    assert zone2.enter_dice == '7d8'
    tiles2 = [o for o in (maps2['field'].interactable_objects if 'field' in maps2
                          else maps2[list(maps2)[0]].interactable_objects)
              if o.properties.get('wall_of_thorns')]
    assert len(tiles2) == 12

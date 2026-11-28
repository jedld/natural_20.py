"""Create Bonfire zone squares must reach both VTTs: the 3D map state serves
them as lit campfire fixtures, and the 2D renderer carries a bonfire marker."""
from natural20.spell.create_bonfire_spell import BonfireTile
from natural20.web.json_renderer import JsonRenderer
from natural20.web.map_state import classify_object_kind, flatten_tiles, objects_from_tiles

from tests.ranger_spell_helpers import Arena


def test_bonfire_tile_classifies_as_campfire():
    assert classify_object_kind({'type': 'bonfire_tile', 'name': 'Bonfire'}) == 'campfire'
    assert classify_object_kind({'type': 'bonfire', 'name': 'Magical Flame'}) == 'campfire'


def test_bonfire_tile_reaches_3d_objects():
    tiles = [{
        'x': 2,
        'y': 3,
        'objects': [{
            'id': 'bonfire_tile:abc',
            'name': 'Bonfire',
            'type': 'bonfire_tile',
            'image': None,
        }],
    }]
    objects = objects_from_tiles(tiles)
    assert len(objects) == 1
    entry = objects[0]
    assert entry['kind'] == 'campfire'
    assert entry['x'] == 2 and entry['y'] == 3


def test_bonfire_marker_on_2d_tiles(tmp_path):
    arena = Arena(tmp_path, caster='ranger', spells=[])
    tile = BonfireTile(arena.session, arena.map, arena.caster, None)
    arena.map.place_object(tile, 4, 4)
    rows = JsonRenderer(arena.map, arena.battle).render(entity_pov=[arena.caster])
    by_pos = {(t['x'], t['y']): t for t in flatten_tiles(rows)}
    objects = by_pos[(4, 4)].get('objects') or []
    assert any(o.get('bonfire_marker') for o in objects)


# --- Healing Spirit / Plant Growth zone squares (same rendering gap) ---


def test_healing_spirit_and_overgrowth_classify_for_3d():
    from natural20.web.map_state import classify_object_kind
    assert classify_object_kind(
        {'type': 'healing_spirit_tile', 'name': 'Healing Spirit'}) == 'lamp'
    assert classify_object_kind(
        {'type': 'overgrowth_tile', 'name': 'Overgrowth'}) == 'briar'


def test_healing_spirit_and_overgrowth_2d_markers(tmp_path):
    from natural20.spell.healing_spirit_spell import HealingSpiritTile
    from natural20.spell.plant_growth_spell import OvergrowthTile
    arena = Arena(tmp_path, caster='ranger', spells=[])
    arena.map.place_object(
        HealingSpiritTile(arena.session, arena.map, arena.caster, None), 5, 5)
    arena.map.place_object(
        OvergrowthTile(arena.session, arena.map, arena.caster), 6, 6)
    rows = JsonRenderer(arena.map, arena.battle).render(entity_pov=[arena.caster])
    by_pos = {(t['x'], t['y']): t for t in flatten_tiles(rows)}
    assert any(o.get('healing_spirit_marker') for o in by_pos[(5, 5)].get('objects') or [])
    assert any(o.get('overgrowth_marker') for o in by_pos[(6, 6)].get('objects') or [])

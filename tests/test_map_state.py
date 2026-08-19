"""Tests for the JSON map-state payload used by the 3D VTT client."""
from pathlib import Path

import pytest

from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.web.json_renderer import JsonRenderer
from natural20.web.map_state import (
    build_map_geometry,
    build_map_state,
    classify_object_kind,
    entities_from_tiles,
    flatten_tiles,
    nearest_wall_edge,
    objects_from_tiles,
    visual_lights_from_map,
    map_visual_effects,
)
from natural20.web.vtt3d_catalog import infer_door_kind, infer_hatch_kind, resolve_vtt3d_model, resolve_vtt3d_walls


@pytest.fixture
def session():
    s = Session(root_path='tests/fixtures')
    s.render_for_text = False
    return s


def test_solid_hash_walls_from_ascii(session):
    battle_map = Map(
        session,
        'box',
        name='box',
        properties={
            'map': {
                'illumination': 0.4,
                'base': [
                    '###',
                    '#.#',
                    '###',
                ],
            },
        },
    )
    geom = build_map_geometry(battle_map)
    solid = {tuple(cell) for cell in geom['solid_walls']}
    assert (0, 0) in solid
    assert (1, 0) in solid
    assert (2, 2) in solid
    assert (1, 1) not in solid
    assert geom['edge_walls'] == []
    assert geom['doors'] == []


def test_thin_walls_and_full_cell_stone(session):
    battle_map = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
    geom = build_map_geometry(battle_map)
    solid = {tuple(cell) for cell in geom['solid_walls']}
    # H tokens are type stone_wall (full cell), not base '#'
    assert (1, 1) in solid
    assert (4, 6) in solid
    edge_keys = {(w['x'], w['y']): set(w['edges']) for w in geom['edge_walls']}
    assert edge_keys[(1, 2)] == {'n', 'w'}  # ┌ stone_wall_tl
    assert 'n' in edge_keys[(2, 2)]  # ┬ stone_wall_t
    assert geom['doors'] == []


def test_windowed_barrier_edges_are_not_extruded(session):
    """Stair wells use type barrier with window flags — collision only, no 3D wall."""
    battle_map = Map(
        session,
        'stairs',
        name='stairs',
        properties={
            'map': {
                'base': [
                    '....',
                    '.┬b.',
                    '....',
                ],
            },
            'legend': {
                '┬': {'name': 'wall', 'type': 'stone_wall_t'},
                'b': {
                    'name': 'stair opening',
                    'type': 'barrier',
                    'border': [1, 0, 0, 0],
                },
            },
        },
    )
    geom = build_map_geometry(battle_map)
    by_pos = {(w['x'], w['y']): set(w['edges']) for w in geom['edge_walls']}
    assert by_pos.get((1, 1)) == {'n'}
    assert (2, 1) not in by_pos


def test_doors_export_edges_and_open_state(session):
    battle_map = Map(session, 'tests/fixtures/maps/thinwall_map_doors.yml')
    geom = build_map_geometry(battle_map)
    assert geom['doors'], 'expected door objects on thinwall_map_doors'
    by_pos = {(d['x'], d['y']): d for d in geom['doors']}
    # '=' horizontal door with door_pos: 2 (south)
    south = by_pos.get((2, 5)) or next(
        (d for d in geom['doors'] if 's' in d['edges']),
        None,
    )
    assert south is not None
    assert south['open'] is False
    assert 's' in south['edges'] or 'n' in south['edges'] or 'e' in south['edges'] or 'w' in south['edges']


def test_corner_door_exports_attached_wall_edges(session):
    """DoorObjectWall combo: door on one edge, opaque wall on the other."""
    battle_map = Map(
        session,
        'corner',
        name='corner',
        properties={
            'map': {
                'base': [
                    '...',
                    '.╒.',
                    '...',
                ],
            },
            'legend': {
                '╒': {'name': 'corner', 'type': 'corner_door_tl'},
            },
        },
    )
    geom = build_map_geometry(battle_map)
    doors = {(d['x'], d['y']): d for d in geom['doors']}
    walls = {(w['x'], w['y']): set(w['edges']) for w in geom['edge_walls']}
    assert doors[(1, 1)]['edges'] == ['n']
    assert walls.get((1, 1)) == {'w'}
    assert 'n' not in walls.get((1, 1), set())


def test_map_wall_style_overrides_campaign_default(session):
    dungeon = Map(
        session,
        'box',
        name='box',
        properties={'map': {'base': ['...']}},
    )
    assert resolve_vtt3d_walls(dungeon)['style'] == 'dungeon'
    manor = Map(
        session,
        'manor',
        name='manor',
        properties={
            'map': {'base': ['...']},
            'vtt3d': {'walls': {'style': 'mansion'}},
        },
    )
    assert resolve_vtt3d_walls(manor)['style'] == 'mansion'
    haunted = Map(
        session,
        'haunted',
        name='haunted',
        properties={
            'map': {'base': ['...']},
            'vtt3d': {'walls': {'style': 'gothic'}},
        },
    )
    assert resolve_vtt3d_walls(haunted)['style'] == 'gothic'
    alias = Map(
        session,
        'alias',
        name='alias',
        properties={
            'map': {'base': ['...']},
            'vtt3d': {'walls': {'style': 'haunted'}},
        },
    )
    assert resolve_vtt3d_walls(alias)['style'] == 'gothic'
    office = Map(
        session,
        'office',
        name='office',
        properties={
            'map': {'base': ['...']},
            'vtt3d': {'walls': {'style': 'modern'}},
        },
    )
    assert resolve_vtt3d_walls(office)['style'] == 'office'
    cave = Map(
        session,
        'cavern',
        name='cavern',
        properties={
            'map': {'base': ['...']},
            'vtt3d': {'walls': {'style': 'cave'}},
        },
    )
    assert resolve_vtt3d_walls(cave)['style'] == 'cave'
    cavern_alias = Map(
        session,
        'grotto',
        name='grotto',
        properties={
            'map': {'base': ['...']},
            'vtt3d': {'walls': {'style': 'grotto'}},
        },
    )
    assert resolve_vtt3d_walls(cavern_alias)['style'] == 'cave'
    from_cave_palette = Map(
        session,
        'cavern_palette',
        name='cavern_palette',
        properties={
            'map': {'base': ['...']},
            'render': {'palette': 'cave'},
        },
    )
    assert resolve_vtt3d_walls(from_cave_palette)['style'] == 'cave'
    from_palette = Map(
        session,
        'inn',
        name='inn',
        properties={
            'map': {'base': ['...']},
            'render': {'palette': 'interior'},
        },
    )
    assert resolve_vtt3d_walls(from_palette)['style'] == 'mansion'
    assert build_map_state(manor, []).get('map', {}).get('walls', {}).get('style') == 'mansion'


def test_map_state_exports_default_fog_effect(session):
    battle_map = Map(
        session,
        'foggy',
        name='foggy',
        properties={
            'map': {'base': ['....', '....']},
            'default_effect': {
                'effect': 'fog',
                'action': 'start',
                'config': {
                    'color': '#aab4c8',
                    'density': 0.1,
                    'opacity': 0.5,
                    'mask': True,
                    'mask_layers': [{'type': 'polygon', 'points': [[0, 0], [4, 0], [4, 2], [0, 2]]}],
                },
            },
        },
    )
    payloads = map_visual_effects(battle_map)
    assert payloads[0]['effect'] == 'fog'
    assert payloads[0]['exclusive'] is False
    assert payloads[0]['config']['mask'] is True
    state = build_map_state(battle_map, [])
    assert state['effects'][0]['effect'] == 'fog'
    assert state['effects'][0]['config']['opacity'] == pytest.approx(0.5)


def test_map_state_entities_and_fog_parity(session):
    battle_map = Map(
        session,
        'box',
        name='box',
        properties={
            'map': {
                'illumination': 1.0,
                'base': [
                    '....',
                    '....',
                    '....',
                ],
            },
        },
    )
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle_map.place((1, 1), fighter, 'G')
    tiles = JsonRenderer(battle_map, padding=[0, 0]).render(entity_pov=[fighter])
    state = build_map_state(battle_map, tiles, background='maps/demo.webp')
    assert state['map']['size'] == [4, 3]
    assert state['map']['illumination'] == pytest.approx(1.0)
    assert state['map']['illumination_default'] == pytest.approx(1.0)
    assert state['map']['illumination_overridden'] is False
    assert state['map']['background'] == '/assets/maps/demo.webp'
    assert state['map']['feet_per_grid'] == 5
    uids = {e['uid'] for e in state['entities']}
    assert fighter.entity_uid in uids
    entity = next(e for e in state['entities'] if e['uid'] == fighter.entity_uid)
    assert entity['x'] == 1
    assert entity['y'] == 1
    assert entity['token']
    assert entity['size'] == 1
    assert 'prone' in entity
    assert 'flying' in entity
    flat = flatten_tiles(tiles)
    assert any(t.get('id') == fighter.entity_uid for t in flat)
    rendered_ids = {
        t.get('id') for t in flat if t.get('entity')
    }
    assert rendered_ids == uids
    assert entities_from_tiles(flat, battle_map) == state['entities']


def test_map_state_tiles_are_jsonable(session):
    battle_map = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
    tiles = JsonRenderer(battle_map, padding=[0, 0]).render()
    state = build_map_state(battle_map, tiles)
    import json
    dumped = json.dumps(state)
    assert '"solid_walls"' in dumped or '"geometry"' in dumped
    assert state['geometry']['solid_walls']
    assert state['geometry']['edge_walls']


def test_classify_object_kind_chests_barrels_cover_and_skips():
    assert classify_object_kind({'type': 'chest', 'opened': False, 'locked': True}) == 'chest'
    assert classify_object_kind({'name': 'Treasure Chest'}) == 'chest'
    assert classify_object_kind({'type': 'barrel', 'cover': 'half'}) == 'barrel'
    assert classify_object_kind({'type': 'tree'}) == 'tree'
    assert classify_object_kind({'cover': 'half', 'type': 'rubble'}) == 'cover'
    assert classify_object_kind({'teleporter_marker': True}) == 'teleporter'
    assert classify_object_kind({'type': 'wooden_door'}) is None
    assert classify_object_kind({'type': 'stone_wall_t'}) is None
    assert classify_object_kind({'door_highlight': True, 'type': 'chest'}) is None
    assert classify_object_kind({'hide_map_token': True, 'type': 'chest'}) is None


def test_classify_object_kind_light_fixtures():
    assert classify_object_kind({'type': 'campfire'}) == 'campfire'
    assert classify_object_kind({'name': 'fire'}) == 'campfire'
    assert classify_object_kind({'type': 'brazier'}) == 'brazier'
    assert classify_object_kind({'type': 'fireplace'}) == 'fireplace'
    assert classify_object_kind({'type': 'torch'}) == 'torch'
    assert classify_object_kind({'type': 'fireplace', 'hide_map_token': True}) == 'fireplace'
    assert classify_object_kind({'type': 'campfire', 'hide_map_token': True}) == 'campfire'
    assert classify_object_kind({'type': 'candle', 'light': {'bright': 5, 'dim': 5}}) == 'lamp'
    assert classify_object_kind({'light': {'bright': 10, 'dim': 5}, 'type': 'altar'}) == 'lamp'
    assert classify_object_kind({'type': 'altar'}, {'altar': {'kind': 'lamp'}}) == 'lamp'
    assert classify_object_kind({'type': 'note', 'vtt3d': {'kind': 'barrel'}}) == 'barrel'
    assert classify_object_kind({'type': 'trap_door'}) == 'trap_door'
    assert classify_object_kind({'type': 'church_trapdoor'}) == 'trap_door'
    assert classify_object_kind({'type': 'trap_door', 'secret': True}) == 'secret_trapdoor'
    assert classify_object_kind({'type': 'trap_door', 'door_highlight': True}) == 'trap_door'
    assert classify_object_kind({'type': 'pit_trap'}) == 'pit_trap'
    assert classify_object_kind({'type': 'chasm'}) == 'chasm'
    assert classify_object_kind({'type': 'bottomless_pit'}) == 'chasm'


def test_classify_object_kind_stairs_despite_hide_map_token():
    assert classify_object_kind({'type': 'stairs', 'hide_map_token': True}) == 'stairs'
    assert classify_object_kind({'type': 'stair', 'hide_map_token': True}) == 'stairs'
    assert classify_object_kind({'name': 'Stairs Up', 'type': 'teleporter'}) == 'teleporter'
    assert classify_object_kind({'type': 'custom_ramp'}, {'custom_ramp': {'kind': 'stairs'}}) == 'stairs'


def test_objects_from_tiles_exports_stair_run():
    tiles = [
        {
            'x': 3,
            'y': 4,
            'objects': [{
                'id': 'stairs-1',
                'name': 'Stairs',
                'type': 'stairs',
                'hide_map_token': True,
                'squares': [[3, 4], [3, 5], [3, 6]],
                'height': -8,
                'style': 'wood',
                'solid': False,
            }],
        },
        {
            'x': 0,
            'y': 0,
            'objects': [{
                'id': 'chest-1',
                'name': 'Chest',
                'type': 'chest',
            }],
        },
    ]
    objs = objects_from_tiles(tiles)
    stairs = next(item for item in objs if item['kind'] == 'stairs')
    chest = next(item for item in objs if item['kind'] == 'chest')
    assert stairs['squares'] == [[3, 4], [3, 5], [3, 6]]
    assert stairs['height'] == -8.0
    assert stairs['style'] == 'wood'
    assert stairs['solid'] is False
    assert chest['id'] == 'chest-1'


def test_objects_from_tiles_stair_well_flags_from_object_and_catalog():
    tiles = [{
        'x': 1, 'y': 1,
        'objects': [{
            'id': 'stairs-open',
            'type': 'stairs',
            'hide_map_token': True,
            'squares': [[1, 1], [2, 1], [2, 2], [1, 2]],
            'open_well': True,
            'wall_attached': True,
        }],
    }]
    stairs = objects_from_tiles(tiles)[0]
    assert stairs['open_well'] is True
    assert stairs['wall_attached'] is True
    catalog = {'stairs': {'kind': 'stairs', 'open_well': True, 'wall_attached': True}}
    inherited = objects_from_tiles([{
        'x': 0, 'y': 0,
        'objects': [{
            'id': 'stairs-cat',
            'type': 'stairs',
            'hide_map_token': True,
            'squares': [[0, 0], [1, 0], [1, 1], [0, 1]],
        }],
    }], catalog)[0]
    assert inherited['open_well'] is True
    assert inherited['wall_attached'] is True


def test_objects_from_tiles_exports_chasm_as_sunken_pit():
    tiles = [{
        'x': 2, 'y': 3,
        'objects': [{
            'id': 'chasm-1',
            'type': 'chasm',
            'name': 'Chasm',
            'fall_distance': 20,
        }],
    }]
    chasm = objects_from_tiles(tiles)[0]
    assert chasm['kind'] == 'chasm'
    assert chasm['fall_distance'] == 20.0


def test_entities_and_objects_export_pose_notes_and_quick_interact():
    tiles = [{
        'x': 1, 'y': 2, 'id': 'pc1', 'entity': 'fighter.png',
        'prone': True, 'is_flying': False, 'hp': 8, 'max_hp': 12,
    }]
    ents = entities_from_tiles(tiles)
    assert ents[0]['prone'] is True
    assert ents[0]['flying'] is False
    tiles[0]['prone'] = False
    tiles[0]['is_flying'] = True
    assert entities_from_tiles(tiles)[0]['flying'] is True
    objs = objects_from_tiles([{
        'x': 3, 'y': 4,
        'objects': [{
            'id': 'door-1',
            'name': 'Oak Door',
            'type': 'wooden_door',
            'door_highlight': True,
            'notes': [{'note': 'Scratched initials.'}],
            'quick_interact': [{'action': 'open', 'label': 'Open', 'image': 'open'}],
        }],
    }])
    assert objs
    assert objs[0]['kind'] is None
    assert objs[0]['notes'][0]['note'] == 'Scratched initials.'
    assert objs[0]['quick_interact'][0]['action'] == 'open'


def test_vtt3d_infers_secret_door_and_portcullis():
    assert infer_door_kind({'type': 'portcullis_b', 'name': 'portcullis'}) == 'portcullis'
    assert infer_door_kind({'type': 'dungeon_secret_door1'}) == 'secret_door'
    assert infer_door_kind({'type': 'door_l', 'secret': True}) == 'secret_door'
    assert infer_door_kind({'type': 'wooden_door'}) == 'door'
    spec = resolve_vtt3d_model(
        {'type': 'custom_gate', 'vtt3d': {'kind': 'portcullis', 'src': 'models/gate.glb'}},
        {},
        role='door',
    )
    assert spec['kind'] == 'portcullis'
    assert spec['src'] == 'models/gate.glb'
    catalog = {'ornate_door': {'kind': 'secret_door'}}
    assert resolve_vtt3d_model({'type': 'ornate_door'}, catalog, role='door')['kind'] == 'secret_door'
    spec = resolve_vtt3d_model(
        {'type': 'stairs'},
        {'stairs': {'kind': 'stairs', 'open_well': True, 'wall_attached': True}},
        role='object',
    )
    assert spec['kind'] == 'stairs'
    assert spec['open_well'] is True
    assert spec['wall_attached'] is True
    opt_out = resolve_vtt3d_model(
        {'type': 'wooden_door', 'vtt3d': {'double': False}},
        {},
        role='door',
    )
    assert opt_out['kind'] == 'door'
    assert opt_out['double'] is False


def test_adjacent_east_doors_export_same_opening_edge(session):
    battle_map = Map(
        session,
        'pair',
        name='pair',
        properties={
            'map': {
                'base': [
                    '...',
                    '.╗.',
                    '.╗.',
                ],
            },
            'legend': {
                '╗': {'name': 'east_leaf', 'type': 'corner_door_rt'},
            },
        },
    )
    geom = build_map_geometry(battle_map)
    leaves = [d for d in geom['doors'] if (d['x'], d['y']) in {(1, 1), (1, 2)}]
    assert len(leaves) == 2
    assert all(d['edges'] == ['e'] for d in leaves)
    assert all(d.get('kind', 'door') == 'door' for d in leaves)


def test_vtt3d_infers_hatches_and_skips_wall_doors():
    assert infer_hatch_kind({'type': 'trap_door'}) == 'trap_door'
    assert infer_hatch_kind({'type': 'church_trapdoor'}) == 'trap_door'
    assert infer_hatch_kind({'type': 'trap_door', 'secret': True}) == 'secret_trapdoor'
    assert infer_hatch_kind({'type': 'pit_trap'}) == 'pit_trap'
    assert infer_door_kind({'type': 'trap_door'}) == 'skip'
    assert infer_door_kind({'type': 'church_trapdoor'}) == 'skip'
    assert infer_door_kind({'type': 'pit_trap'}) == 'skip'
    catalog = {'trap_door': {'kind': 'trap_door'}}
    assert resolve_vtt3d_model(
        {'type': 'trap_door', 'secret': True}, catalog, role='object',
    )['kind'] == 'secret_trapdoor'


def test_geometry_doors_use_barrier_kinds(session):
    battle_map = Map(
        session,
        'gates',
        name='gates',
        properties={
            'map': {
                'base': [
                    '.....',
                    '.=~.s',
                    '.....',
                ],
            },
            'legend': {
                '=': {'name': 'oak', 'type': 'wooden_door'},
                '~': {'name': 'gate', 'type': 'portcullis_b'},
                's': {'name': 'panel', 'type': 'attic_secret_door'},
            },
        },
    )
    geom = build_map_geometry(battle_map)
    kinds = {door['kind'] for door in geom['doors']}
    assert 'door' in kinds
    assert 'portcullis' in kinds
    assert 'secret_door' in kinds
    assert all('kind' in door for door in geom['doors'])


def test_visual_lights_from_yaml_overlay_hangs_on_nearest_wall(session):
    battle_map = Map(
        session,
        'box',
        name='box',
        properties={
            'map': {
                'illumination': 0.0,
                'base': [
                    '###',
                    '#.#',
                    '###',
                ],
                'light': [
                    '...',
                    '.A.',
                    '...',
                ],
            },
            'lights': {'A': {'bright': 10, 'dim': 5}},
        },
    )
    geom = build_map_geometry(battle_map)
    lamps = visual_lights_from_map(battle_map, geom, set())
    assert lamps == [{
        'x': 1,
        'y': 1,
        'kind': 'torch',
        'lit': True,
        'bright': 10.0,
        'dim': 5.0,
        'edge': 'n',
    }]
    assert nearest_wall_edge(1, 1, geom) == 'n'


def test_visual_lights_skip_solid_walls_and_occupied_fixtures(session):
    battle_map = Map(
        session,
        'box',
        name='box',
        properties={
            'map': {
                'base': [
                    '###',
                    '#.#',
                    '###',
                ],
                'light': [
                    'A..',
                    '.A.',
                    '...',
                ],
            },
            'lights': {'A': {'bright': 20, 'dim': 10}},
        },
    )
    geom = build_map_geometry(battle_map)
    lamps = visual_lights_from_map(battle_map, geom, {(1, 1)})
    assert lamps == []


def test_map_state_visual_lights_do_not_mutate_game_light(session):
    battle_map = Map(
        session,
        'box',
        name='box',
        properties={
            'map': {
                'illumination': 0.0,
                'base': [
                    '###',
                    '#.#',
                    '###',
                ],
                'light': [
                    '...',
                    '.A.',
                    '...',
                ],
            },
            'lights': {'A': {'bright': 10, 'dim': 5}},
        },
    )
    before = battle_map.light_at(1, 1)
    tiles = JsonRenderer(battle_map, padding=[0, 0]).render()
    state = build_map_state(battle_map, tiles)
    assert battle_map.light_at(1, 1) == before
    assert state['lights']
    assert state['lights'][0]['kind'] == 'torch'
    assert state['map']['illumination'] == pytest.approx(0.0)


def test_map_state_exports_campfire_light_fixture(session):
    battle_map = Map(session, 'battle_sim_objects')
    tiles = JsonRenderer(battle_map, padding=None).render()
    state = build_map_state(battle_map, tiles)
    camp = next((obj for obj in state['objects'] if obj.get('kind') == 'campfire'), None)
    assert camp is not None, state['objects']
    assert camp['type'] == 'campfire'
    assert camp.get('light', {}).get('bright')
    assert camp['lit'] is True
    occupied = {(camp['x'], camp['y'])}
    for lamp in state.get('lights') or []:
        assert (lamp['x'], lamp['y']) not in occupied


def test_map_state_exports_chest_and_barrel_fixture_state(session):
    battle_map = Map(session, 'battle_sim_objects')
    tiles = JsonRenderer(battle_map, padding=None).render()
    state = build_map_state(battle_map, tiles)
    by_kind = {}
    for obj in state['objects']:
        by_kind.setdefault(obj.get('kind'), []).append(obj)
    assert by_kind.get('chest'), state['objects']
    assert by_kind.get('barrel'), state['objects']
    chest = by_kind['chest'][0]
    assert chest['opened'] is False
    assert 'locked' in chest
    assert chest['type'] == 'chest'
    barrel = by_kind['barrel'][0]
    assert barrel['cover'] == 'half'
    assert all(obj.get('kind') != 'wooden_door' for obj in state['objects'])


def test_hatches_are_objects_not_wall_doors(session):
    battle_map = Map(
        session,
        'hatches',
        name='hatches',
        properties={
            'map': {
                'base': [
                    '.....',
                    '.q.p.',
                    '.....',
                ],
            },
            'legend': {
                'q': {
                    'name': 'Trapdoor',
                    'type': 'trap_door',
                    'secret': True,
                    'locked': True,
                    'lockable': True,
                    'target_map': 'hatches',
                    'target_position': [0, 0],
                },
                'p': {
                    'name': 'pit trap',
                    'type': 'pit_trap',
                },
            },
        },
    )
    geom = build_map_geometry(battle_map)
    assert geom['doors'] == []
    tiles = JsonRenderer(battle_map, padding=None).render()
    state = build_map_state(battle_map, tiles)
    by_kind = {obj.get('kind'): obj for obj in state['objects']}
    assert by_kind.get('secret_trapdoor'), state['objects']
    assert by_kind['secret_trapdoor'].get('secret') is True
    assert by_kind['secret_trapdoor'].get('locked') is True
    assert 'opened' in by_kind['secret_trapdoor']
    assert by_kind.get('pit_trap'), state['objects']
    assert by_kind['pit_trap']['activated'] is False
    assert by_kind['pit_trap']['concealed'] is True


def test_pit_trap_exports_activated_state(session):
    battle_map = Map(session, 'traps')
    tiles = JsonRenderer(battle_map, padding=None).render()
    state = build_map_state(battle_map, tiles)
    pits = [obj for obj in state['objects'] if obj.get('kind') == 'pit_trap']
    assert pits, state['objects']
    pit = pits[0]
    assert pit['activated'] is False
    assert pit['disarmed'] is False
    assert pit['concealed'] is True


def test_map_state_exports_carried_torch_on_entity(session):
    battle_map = Map(
        session,
        'box',
        name='box',
        properties={'map': {'illumination': 0.0, 'base': ['....', '....']}},
    )
    rogue = PlayerCharacter.load(session, 'halfling_rogue.yml')
    battle_map.place((1, 1), rogue, 'R')
    tiles = JsonRenderer(battle_map, padding=[0, 0]).render(entity_pov=[rogue])
    state = build_map_state(battle_map, tiles)
    entity = next(e for e in state['entities'] if e['uid'] == rogue.entity_uid)
    assert entity['light']['bright'] >= 20
    assert entity['light']['dim'] >= 20
    assert entity['light']['origin'] == 'item'


def test_map_state_exports_light_spell_aura(session):
    from natural20.spell.light_spell import LightEffect, LightSpell

    battle_map = Map(
        session,
        'box',
        name='box',
        properties={'map': {'illumination': 0.0, 'base': ['....', '....']}},
    )
    wizard = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle_map.place((0, 0), wizard, 'W')
    LightSpell.apply(None, {
        'type': 'light',
        'source': wizard,
        'target': wizard,
        'color': 'blue',
        'effect': LightEffect(wizard, wizard, color='blue'),
        'spell': session.load_spell('light') or {},
        'saving_throw': None,
        'save_success': False,
    }, session=session)
    tiles = JsonRenderer(battle_map, padding=[0, 0]).render(entity_pov=[wizard])
    state = build_map_state(battle_map, tiles)
    entity = next(e for e in state['entities'] if e['uid'] == wizard.entity_uid)
    assert entity['light']['origin'] == 'effect'
    assert entity['light']['bright'] >= 20
    assert entity['light']['color'] == 'blue'


def test_water_cells_exported_for_3d_basins(session):
    battle_map = Map(session, 'battle_sim_objects')
    geom = build_map_geometry(battle_map)
    water = {tuple(cell) for cell in geom['water']}
    assert water, 'expected water terrain cells on battle_sim_objects'
    solid = {tuple(cell) for cell in geom['solid_walls']}
    assert water.isdisjoint(solid)


def test_visual_lights_skip_water_cells(session):
    battle_map = Map(
        session,
        'pool',
        name='pool',
        properties={
            'map': {
                'base': [
                    'www',
                    'w.w',
                    '###',
                ],
                'light': [
                    '.A.',
                    '.A.',
                    '...',
                ],
            },
            'legend': {
                'w': {'name': 'Pool', 'type': 'water'},
            },
            'lights': {'A': {'bright': 5, 'dim': 5}},
        },
    )
    geom = build_map_geometry(battle_map)
    water = {tuple(cell) for cell in geom['water']}
    assert (1, 0) in water
    assert (1, 1) not in water
    lamps = visual_lights_from_map(battle_map, geom, set())
    positions = {(lamp['x'], lamp['y']) for lamp in lamps}
    assert (1, 0) not in positions
    assert (1, 1) in positions


def test_template_map_water_has_no_yaml_torch(session):
    path = Path(__file__).resolve().parents[1] / 'templates/maps/goblin_cave.yml'
    battle_map = Map(session, str(path), name='goblin_cave')
    geom = build_map_geometry(battle_map)
    water = {tuple(cell) for cell in geom['water']}
    for x in range(4, 7):
        for y in range(0, 2):
            assert (x, y) in water
    lamps = visual_lights_from_map(battle_map, geom, set())
    assert all((lamp['x'], lamp['y']) not in water for lamp in lamps)
    assert any(lamp['x'] == 3 and lamp['y'] == 4 for lamp in lamps)

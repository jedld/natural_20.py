"""Wall-embedded windows: glass/shutters, bars, cover, and difficult terrain."""
from natural20.item_library.window_object import WindowObjectWall
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.ac_utils import calculate_cover_ac
from natural20.web.map_state import build_map_geometry
from natural20.web.vtt3d_catalog import infer_door_kind

WX, WY = 2, 2
OUTSIDE_FAR = (2, 0)
OUTSIDE_NEAR = (2, 1)
INSIDE = (2, 2)
INSIDE_SOUTH = (2, 3)


def _window_map(session, **legend_overrides):
    legend = {
        'name': 'window',
        'type': 'window_top',
    }
    legend.update(legend_overrides)
    return Map(
        session,
        'win',
        name='win',
        properties={
            'map': {
                'base': [
                    '.....',
                    '.....',
                    '..▭..',
                    '.....',
                    '.....',
                ],
            },
            'legend': {
                '▭': legend,
            },
        },
    )


def test_window_loads_as_window_object_wall():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session)
    obj = battle_map.object_at(WX, WY)
    assert isinstance(obj, WindowObjectWall)
    assert obj.closed()
    assert obj.cover_pane == 'glass'
    assert obj.inside_cover == 'half'
    assert infer_door_kind(obj) == 'window'


def test_glass_closed_is_see_through_but_total_cover():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session)
    window = battle_map.object_at(WX, WY)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle_map.place(OUTSIDE_FAR, goblin, 'g')
    battle_map.place(INSIDE, fighter, 'G')

    assert window.opaque(OUTSIDE_NEAR) is False
    assert battle_map.can_see(goblin, fighter)
    assert battle_map.has_total_cover_between(goblin, fighter)
    assert battle_map.cover_at(WX, WY, origin=OUTSIDE_NEAR, occupant=fighter) == 'total'


def test_opaque_shutter_blocks_vision_when_closed():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, cover_pane='opaque')
    window = battle_map.object_at(WX, WY)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle_map.place(OUTSIDE_FAR, goblin, 'g')
    battle_map.place(INSIDE, fighter, 'G')

    assert window.cover_pane == 'opaque'
    assert window.opaque(OUTSIDE_NEAR) is True
    assert not battle_map.can_see(goblin, fighter)


def test_open_window_grants_inside_half_cover():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session)
    window = battle_map.object_at(WX, WY)
    window.open()
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle_map.place(OUTSIDE_FAR, goblin, 'g')
    battle_map.place(INSIDE, fighter, 'G')

    assert battle_map.can_see(goblin, fighter)
    assert not battle_map.has_total_cover_between(goblin, fighter)
    assert battle_map.cover_at(WX, WY, origin=OUTSIDE_NEAR, occupant=fighter) == 'half'
    assert calculate_cover_ac(battle_map, goblin, fighter) == 2


def test_open_window_three_quarter_cover_option():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, inside_cover='three_quarter')
    window = battle_map.object_at(WX, WY)
    window.open()
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle_map.place(OUTSIDE_FAR, goblin, 'g')
    battle_map.place(INSIDE, fighter, 'G')

    assert battle_map.cover_at(WX, WY, origin=OUTSIDE_NEAR, occupant=fighter) == 'three_quarter'
    assert calculate_cover_ac(battle_map, goblin, fighter) == 5


def test_prone_creature_has_total_cover_at_open_window():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session)
    window = battle_map.object_at(WX, WY)
    window.open()
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle_map.place(OUTSIDE_FAR, goblin, 'g')
    battle_map.place(INSIDE, fighter, 'G')
    fighter.do_prone()

    assert battle_map.cover_at(WX, WY, origin=OUTSIDE_NEAR, occupant=fighter) == 'total'
    assert battle_map.has_total_cover_between(goblin, fighter)
    assert not battle_map.can_see(goblin, fighter)


def test_barred_window_opens_from_inside_only():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, barred=True)
    window = battle_map.object_at(WX, WY)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')
    battle_map.place(OUTSIDE_NEAR, goblin, 'g')
    battle_map.place(INSIDE, fighter, 'G')

    outside = window.available_interactions(goblin)
    assert outside['open']['disabled'] is True
    inside = window.available_interactions(fighter)
    assert 'open' in inside
    assert not inside['open'].get('disabled')
    assert 'unbar' in inside

    window.use(fighter, {'action': 'open'}, session)
    assert window.opened()
    assert window.barred is False


def test_open_window_is_difficult_terrain_when_crossing():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session)
    window = battle_map.object_at(WX, WY)
    window.open()
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle_map.place(OUTSIDE_NEAR, fighter, 'G')

    assert battle_map.difficult_terrain(fighter, WX, WY, from_pos=OUTSIDE_NEAR)
    assert not battle_map.difficult_terrain(fighter, *INSIDE_SOUTH, from_pos=INSIDE)


def test_closed_window_blocks_passage():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session)
    window = battle_map.object_at(WX, WY)
    assert window.passable(OUTSIDE_NEAR) is False
    window.open()
    assert window.passable(OUTSIDE_NEAR) is True


def test_window_geometry_exports_3d_kind_and_pane():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, barred=True)
    geom = build_map_geometry(battle_map)
    by_pos = {(d['x'], d['y']): d for d in geom['doors']}
    entry = by_pos[(WX, WY)]
    assert entry['kind'] == 'window'
    assert entry['cover_pane'] == 'glass'
    assert entry['barred'] is True
    assert entry['window_material'] == 'wood'
    assert 'n' in entry['edges']


def test_window_round_trip_serialization():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, barred=True, cover_pane='opaque')
    window = battle_map.object_at(WX, WY)
    data = window.to_dict()
    data['session'] = session
    restored = WindowObjectWall.from_dict(data)
    assert restored.barred is True
    assert restored.cover_pane == 'opaque'
    assert restored.inside_cover == 'half'
    assert restored.max_pass_size == 'any'
    assert restored.door_pos == 0


def test_layer_placement_overrides_window_properties():
    session = Session(root_path='tests/fixtures')
    battle_map = Map(
        session,
        'win',
        name='win',
        properties={
            'map': {
                'base': [
                    '.....',
                    '.....',
                    '..▭..',
                    '.....',
                    '.....',
                ],
                'layer_placements': [
                    {
                        'id': 'lp_base_window_top_2_2',
                        'layer': 'base',
                        'token': '▭',
                        'pos': [2, 2],
                        'cover_pane': 'opaque',
                        'barred': True,
                        'inside_cover': 'three_quarter',
                        'window_material': 'iron',
                    },
                ],
            },
            'legend': {
                '▭': {
                    'name': 'window',
                    'type': 'window_top',
                    'cover_pane': 'glass',
                    'barred': False,
                },
            },
        },
    )
    window = battle_map.object_at(WX, WY)
    assert isinstance(window, WindowObjectWall)
    assert window.cover_pane == 'opaque'
    assert window.barred is True
    assert window.inside_cover == 'three_quarter'
    assert window.window_material == 'iron'


def test_max_pass_size_blocks_larger_creatures():
    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, max_pass_size='small')
    window = battle_map.object_at(WX, WY)
    window.open()
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin')

    assert window.max_pass_size == 'small'
    assert fighter.size_identifier() == 2
    assert goblin.size_identifier() == 1
    assert window.passable_for(goblin, OUTSIDE_NEAR) is True
    assert window.passable_for(fighter, OUTSIDE_NEAR) is False
    assert battle_map.passable(goblin, WX, WY, origin=OUTSIDE_NEAR)
    assert not battle_map.passable(fighter, WX, WY, origin=OUTSIDE_NEAR)
    # Walking along the interior of the cell does not cross the opening.
    assert battle_map.passable(fighter, *INSIDE_SOUTH, origin=INSIDE)


def test_window_pass_size_appears_in_tile_tooltip():
    from natural20.web.terrain_tooltip import build_terrain_tooltip

    session = Session(root_path='tests/fixtures')
    battle_map = _window_map(session, max_pass_size='small')
    window = battle_map.object_at(WX, WY)
    assert window.pass_size_tooltip() == 'Fits Small or smaller'
    html = build_terrain_tooltip(
        {'x': WX, 'y': WY, 'difficult': False},
        battle_map,
        map_objects=[window],
    )
    assert 'Fits Small or smaller' in html
    unrestricted = _window_map(session).object_at(WX, WY)
    assert unrestricted.pass_size_tooltip() is None
    html_any = build_terrain_tooltip(
        {'x': WX, 'y': WY, 'difficult': False},
        battle_map,
        map_objects=[unrestricted],
    )
    assert 'Fits' not in html_any

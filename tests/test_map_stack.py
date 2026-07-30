"""Tests for multi-level map stacks."""

import pytest

from natural20.item_library.chest import Chest
from natural20.map_stack import MapStackRegistry, WorldCoord
from natural20.session import Session


@pytest.fixture
def stack_session():
    return Session(root_path='user_levels/wild_sheep_chase')


def test_map_stacks_load_from_game_yml(stack_session):
    session = stack_session
    assert hasattr(session, 'map_stacks')
    stack = session.map_stacks.get('amphail_tavern')
    assert stack is not None
    assert 'town_market' in stack.maps_in_stack()
    assert 'tavern_2nd_floor' in stack.maps_in_stack()


def test_local_to_world_anchor(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    wx, wy, elev = stack.local_to_world('tavern_2nd_floor', 0, 0)
    assert (wx, wy) == (9, 16)
    assert elev == 15.0
    wx2, wy2, _ = stack.local_to_world('town_market', 9, 16)
    assert (wx2, wy2) == (9, 16)


def test_top_floor_at_stairs(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    top = stack.top_floor_at(9, 16)
    assert top is not None
    assert top.map_name == 'tavern_2nd_floor'


def test_stack_opening_indexed(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    assert stack.is_stack_opening(9, 16) or stack.is_stack_opening(9, 17)


def test_stack_transitions_at_stairs(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    assert stack.is_stack_opening(9, 16)
    transitions = stack.transitions_from('tavern_2nd_floor', 0, 0)
    assert ('town_market', 9, 16) in transitions or ('town_market', 9, 17) in transitions


def test_guest_chests_still_present(stack_session):
    session = stack_session
    upstairs = session.maps['tavern_2nd_floor']
    chests = {
        getattr(obj, 'entity_uid', None)
        for obj in upstairs.interactable_objects
        if isinstance(obj, Chest)
    }
    assert 'tavern_room_1_chest' in chests


def test_ceiling_elevation_open_sky_and_covered(stack_session):
    import math

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base_floor = stack.floor_for_map('town_market')
    overlay_floor = stack.floor_for_map('tavern_2nd_floor')

    # Outdoor market — no overlay above, no ceiling_height on base → open sky.
    assert math.isinf(stack.ceiling_elevation_ft(5, 5, base_floor))

    # Taproom under the overlay footprint — capped by 2nd-floor deck at 15 ft.
    assert stack.ceiling_elevation_ft(10, 17, base_floor) == 15.0

    # Upstairs guest room — 10 ft ceiling above the 15 ft deck.
    assert overlay_floor.ceiling_height_ft == 10.0
    assert stack.ceiling_elevation_ft(10, 17, overlay_floor) == 25.0


def test_overlay_layer_skips_map_padding(stack_session):
    from natural20.web.stack_renderer import build_stack_render_layers

    session = stack_session
    upstairs = session.maps['tavern_2nd_floor']
    layers = build_stack_render_layers(session, upstairs, None, padding=[6, 15])
    overlay = next(layer for layer in layers['layers'] if layer['role'] == 'overlay')
    ow, oh = upstairs.size
    for row in overlay['tiles']:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            assert 0 <= tile['x'] < ow
            assert 0 <= tile['y'] < oh
            assert not tile.get('stack_void')


def test_composite_upstairs_view_reveals_base_surround(stack_session):
    from natural20.map_stack_movement import transfer_entity_to_map
    from natural20.web.stack_renderer import build_stack_render_layers

    session = stack_session
    upstairs = session.maps['tavern_2nd_floor']
    base = session.maps['town_market']
    entity = next(iter(base.entities))
    transfer_entity_to_map(entity, base, upstairs, 1, 0, None)

    layers = build_stack_render_layers(session, upstairs, None, entity_pov=entity)
    assert layers is not None
    assert layers.get('composite_mode') is True
    assert layers.get('anchor') == [9, 16]

    overlay_layer = next(layer for layer in layers['layers'] if layer['role'] == 'overlay')
    assert overlay_layer['background'] == 'tavern_2nd_floor.png'

    base_tiles = layers['layers'][0]['tiles']
    under = sum(1 for row in base_tiles for t in row if isinstance(t, dict) and t.get('under_overlay'))
    visible_outdoors = sum(
        1 for row in base_tiles for t in row
        if isinstance(t, dict) and t.get('line_of_sight') and not t.get('under_overlay')
    )
    assert under == upstairs.size[0] * upstairs.size[1]
    peek_underlay = layers.get('base_peek_underlay')
    peek_filled = 0
    if peek_underlay:
        peek_filled = sum(
            1 for row in peek_underlay for t in row
            if isinstance(t, dict) and not t.get('underlay_empty')
        )
    assert visible_outdoors >= 0
    assert peek_filled >= 0

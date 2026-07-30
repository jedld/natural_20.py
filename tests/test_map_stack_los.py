"""3D line-of-sight tests for map stacks."""

import pytest

from natural20.map_stack_los import stack_can_see, _column_blocks_sight
from natural20.session import Session


@pytest.fixture
def stack_session():
    return Session(root_path='user_levels/wild_sheep_chase')


class _StubEntity:
    def __init__(
        self,
        uid: str,
        map_name: str,
        lx: int,
        ly: int,
        stack,
        session,
        *,
        altitude_ft: float = 0.0,
        size: str = 'medium',
        prone: bool = False,
        eye_height_ft: float | None = None,
    ):
        self.entity_uid = uid
        self._map_name = map_name
        self._lx = lx
        self._ly = ly
        self._stack = stack
        self._session = session
        self.altitude_ft = altitude_ft
        self.properties = {'size': size}
        self._prone = prone
        self._eye_height_ft = eye_height_ft

    def size(self):
        return self.properties.get('size', 'medium')

    def prone(self):
        return self._prone

    def eye_height_ft(self):
        if self._eye_height_ft is not None:
            return float(self._eye_height_ft)
        from natural20.utils.entity_height import eye_height_ft as _eye_height_ft
        return _eye_height_ft(self)

    def world_position(self, battle_map):
        wx, wy, elev = self._stack.local_to_world(self._map_name, self._lx, self._ly)
        from natural20.map_stack import WorldCoord
        return WorldCoord(wx, wy, elev + float(self.altitude_ft or 0.0))

    def sight_world_position(self, battle_map):
        wp = self.world_position(battle_map)
        from natural20.map_stack import WorldCoord
        return WorldCoord(wp.x, wp.y, wp.elevation_ft + self.eye_height_ft())

    def entity_or_object_pos(self, battle_map):
        if battle_map.name == self._map_name:
            return (self._lx, self._ly)
        wx, wy, _ = self._stack.local_to_world(self._map_name, self._lx, self._ly)
        return self._stack.world_to_local(wx, wy, battle_map.name)

    def darkvision(self, _distance_ft):
        return False


def test_opaque_floor_deck_blocks_ground_to_upstairs(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    viewer = _StubEntity('ground', 'town_market', 5, 5, stack, session)
    target = _StubEntity('upstairs', 'tavern_2nd_floor', 1, 1, stack, session)

    # Under the overlay footprint but not on the stair shaft or target column.
    assert _column_blocks_sight(
        stack, 10, 16,
        0.0, 15.0,
        'town_market',
        (5, 5),
        (10, 17),
    ) is True

    assert stack_can_see(stack, viewer, target, base, upstairs) is False


def test_stack_opening_pierces_floor_deck(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    assert stack.is_stack_opening(9, 16)
    viewer = _StubEntity('ground', 'town_market', 9, 16, stack, session)
    target = _StubEntity('upstairs', 'tavern_2nd_floor', 0, 0, stack, session)

    assert stack_can_see(stack, viewer, target, base, upstairs) is True


def test_window_pierces_floor_deck(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']

    # Window object at local (0,6) → world (9, 22)
    assert stack.is_window_at(9, 22, 'tavern_2nd_floor')

    from natural20.utils.entity_height import eye_height_ft

    ground_eye = eye_height_ft(_StubEntity('g', 'town_market', 0, 0, stack, session, size='medium'))
    upstairs_eye = 15.0 + ground_eye

    assert _column_blocks_sight(
        stack, 9, 22,
        ground_eye, upstairs_eye,
        'town_market',
        (9, 21),
        (9, 22),
    ) is False


def test_ground_walls_block_cross_floor_ray(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    upstairs = session.maps['tavern_2nd_floor']
    base = session.maps['town_market']

    viewer = _StubEntity('up', 'tavern_2nd_floor', 4, 4, stack, session)
    target = _StubEntity('down', 'town_market', 0, 0, stack, session)

    # Long cross-floor ray should be blocked by intervening geometry or floor deck.
    assert stack_can_see(stack, viewer, target, upstairs, base) is False


def test_room_ceiling_blocks_upward_los(stack_session):
    from natural20.map_stack_los import _vertical_ceiling_blocks

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    upstairs = session.maps['tavern_2nd_floor']

    # Interior upstairs (1,1) → world (10,17); ceiling at 25 ft.
    assert stack.ceiling_elevation_ft(10, 17, stack.floor_for_map('tavern_2nd_floor')) == 25.0
    assert _vertical_ceiling_blocks(stack, 10, 17, 16.0, 30.0) is True
    assert _vertical_ceiling_blocks(stack, 10, 17, 16.0, 24.0) is False


def test_same_floor_stack_los_unchanged(stack_session):
    from natural20.battle import Battle
    from natural20.map_stack_los import stack_can_see

    session = stack_session
    town = session.maps['town_market']
    mara = town.entity_by_uid('mara_bartender')
    pip = town.entity_by_uid('pip_barmaid')
    battle = Battle(session, town)
    stack = session.map_stacks.get('amphail_tavern')
    assert stack_can_see(stack, mara, pip, town, town, battle=battle)


def test_upstairs_outdoor_sight_beyond_building_shell(stack_session):
    from natural20.map_stack_los import stack_base_visible_from_overlay
    from natural20.map_stack_movement import transfer_entity_to_map

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']
    entity = next(iter(base.entities))
    transfer_entity_to_map(entity, base, upstairs, 0, 6, None)

    vwx, vwy, _ = stack.local_to_world('tavern_2nd_floor', 0, 6)
    visible_west = 0
    for dist in range(1, 30):
        wx, wy = vwx - dist, vwy
        if wx < 0:
            break
        if stack_base_visible_from_overlay(stack, entity, upstairs, base, wx, wy):
            visible_west = dist
    assert visible_west >= 5, 'window view should reach well beyond the building shell'


def test_perimeter_walls_do_not_edge_peek(stack_session):
    from natural20.web.stack_renderer import _edge_peek_world_target, _is_edge_peek_cell

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    floor = stack.floor_for_map('tavern_2nd_floor')
    omap = floor.map

    # North/west perimeter walls must not expose outdoor tiles through compositing.
    for lx, ly in ((0, 0), (0, 1), (0, 2), (1, 0), (8, 0), (8, 1), (8, 3)):
        assert omap.base_map[lx][ly] != '#'
        assert _edge_peek_world_target(stack, floor, lx, ly) is None
        assert _is_edge_peek_cell(stack, floor, lx, ly) is False

    # Perimeter doors are not open edge gaps.
    assert omap.base_map[0][5] == 'd'
    assert _edge_peek_world_target(stack, floor, 0, 5) is None

    # Open filler on the map edge may still peek (e.g. roof gap at local 4,0).
    assert _edge_peek_world_target(stack, floor, 4, 0) is not None


def test_eye_height_from_size_category():
    from natural20.utils.entity_height import eye_height_ft, standing_height_ft

    halfling = _StubEntity('h', 'town_market', 0, 0, None, None, size='small')
    human = _StubEntity('u', 'town_market', 0, 0, None, None, size='medium')
    assert standing_height_ft(halfling) < standing_height_ft(human)
    assert eye_height_ft(halfling) < eye_height_ft(human)

    prone_human = _StubEntity('p', 'town_market', 0, 0, None, None, size='medium', prone=True)
    assert eye_height_ft(prone_human) == 1.0


def test_sight_elevation_affects_vertical_deck_blocking(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')

    # Ground-level medium viewer eye (~5.3 ft) vs deck at 15 ft — blocked.
    assert _column_blocks_sight(
        stack, 10, 16,
        5.3, 20.5,
        'town_market',
        (9, 16),
        (10, 17),
    ) is True

    # Upstairs medium viewer eye (~20.5 ft) looking across same column — deck pierced at stair.
    assert _column_blocks_sight(
        stack, 10, 16,
        20.5, 20.5,
        'tavern_2nd_floor',
        (10, 17),
        (10, 17),
    ) is False


def test_parapet_blocks_short_viewer_outdoors(stack_session):
    from natural20.map_stack_los import _parapet_blocks_outdoor_sight, _overlay_perimeter_wall

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    floor = stack.floor_for_map('tavern_2nd_floor')
    omap = floor.map

    # West perimeter wall at local (0, 0) — world (9, 16).
    assert _overlay_perimeter_wall(omap, 0, 0)
    vwx, vwy = stack.local_to_world('tavern_2nd_floor', 4, 0)[:2]
    wall_wx, wall_wy = stack.local_to_world('tavern_2nd_floor', 0, 0)[:2]
    outdoor_wx = wall_wx - 2

    parapet_top = floor.elevation_ft + floor.parapet_height_ft
    assert _parapet_blocks_outdoor_sight(
        stack, floor, vwx, vwy, outdoor_wx, wall_wy, parapet_top - 0.5
    )
    assert not _parapet_blocks_outdoor_sight(
        stack, floor, vwx, vwy, outdoor_wx, wall_wy, parapet_top + 1.0
    )


def test_outdoor_sight_consistent_through_roof_gap(stack_session):
    """Outdoor LOS through the north roof gap must be consistent and wall cells must block."""
    from natural20.map_stack_los import stack_base_visible_from_overlay
    from natural20.map_stack_movement import transfer_entity_to_map

    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    base = session.maps['town_market']
    upstairs = session.maps['tavern_2nd_floor']
    entity = base.entity_by_uid('mara_bartender')

    def place_at(world_x: int, world_y: int) -> None:
        lx, ly = world_x - 9, world_y - 16
        for src in (upstairs, base):
            try:
                transfer_entity_to_map(entity, src, upstairs, lx, ly, None)
                return
            except Exception:
                continue
        transfer_entity_to_map(entity, base, upstairs, lx, ly, None)

    def max_outdoor_north(world_x: int, world_y: int) -> int:
        place_at(world_x, world_y)
        max_dist = 0
        for dist in range(1, 25):
            wx, wy = world_x, world_y - dist
            if wy < 0:
                break
            if stack.world_to_local(wx, wy, 'tavern_2nd_floor') is not None:
                continue
            if stack_base_visible_from_overlay(stack, entity, upstairs, base, wx, wy):
                max_dist = dist
        return max_dist

    # Open roof gap at world (13, 16); interior one row south at (13, 17).
    interior = max_outdoor_north(13, 17)
    at_gap = max_outdoor_north(13, 16)
    assert interior >= 5
    assert at_gap >= 5
    assert abs(interior - at_gap) <= 1

    # Perimeter wall at world (11, 16) must not reveal outdoors to the north.
    place_at(11, 16)
    assert not stack_base_visible_from_overlay(stack, entity, upstairs, base, 11, 15)
    assert max_outdoor_north(11, 16) == 0

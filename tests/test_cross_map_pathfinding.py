"""Cross-map / teleporter-aware pathfinding tests.

Validates that :class:`PathCompute.compute_cross_map_path` finds a route from
one map to another by stepping through teleporters, and that Chasms are *not*
used as portals (they remain hazards filtered by the single-map planner).
"""
import pytest

from natural20.session import Session
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ai.path_compute import PathCompute
from natural20.item_library.chasm import Chasm


@pytest.fixture
def session():
    s = Session(root_path='tests/fixtures')
    s.render_for_text = False
    return s


def _linked_maps(session):
    map1 = Map(session, 'tests/fixtures/maps/thinwall_map_teleport.yml')
    map2 = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
    map1.add_linked_map('map2', map2)
    return map1, map2


def test_cross_map_path_routes_through_teleporter(session):
    map1, map2 = _linked_maps(session)
    char = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
    map1.place((0, 4), char)

    pc = PathCompute(None, map1, char)
    plan = pc.compute_cross_map_path(map1, 0, 4, map2, 4, 4)

    assert plan is not None, 'expected a cross-map plan via teleporter T'
    assert len(plan) == 2, f'expected 2 segments, got {len(plan)}'

    seg1, seg2 = plan
    # First segment ends at the teleporter T at (5, 6) on map1.
    assert seg1['map'] is map1
    assert seg1['path'][0] == (0, 4)
    assert seg1['path'][-1] == (5, 6)
    assert seg1['teleporter'] is not None
    assert seg1['next_map'] is map2

    # Second segment starts at the teleporter landing tile on map2.
    assert seg2['map'] is map2
    assert seg2['path'][0] == (2, 1)
    assert seg2['path'][-1] == (4, 4)
    assert seg2['teleporter'] is None


def test_cross_map_same_map_returns_single_segment(session):
    map1, _ = _linked_maps(session)
    char = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
    map1.place((0, 4), char)

    pc = PathCompute(None, map1, char)
    plan = pc.compute_cross_map_path(map1, 0, 4, map1, 0, 0)

    assert plan is not None
    assert len(plan) == 1
    assert plan[0]['map'] is map1
    assert plan[0]['path'][0] == (0, 4)
    assert plan[0]['path'][-1] == (0, 0)
    assert plan[0]['teleporter'] is None


def test_cross_map_returns_none_when_unlinked(session):
    map1 = Map(session, 'tests/fixtures/maps/thinwall_map_teleport.yml')
    map2 = Map(session, 'tests/fixtures/maps/thinwall_map.yml')
    # Intentionally do NOT call ``add_linked_map`` — the teleporter cannot
    # resolve its destination so no cross-map plan should exist.
    char = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
    map1.place((0, 4), char)

    pc = PathCompute(None, map1, char)
    plan = pc.compute_cross_map_path(map1, 0, 4, map2, 4, 4)
    assert plan is None


def test_cross_map_skips_chasms_as_portals(session):
    """Chasms inherit from Teleporter but must not be treated as stairs."""
    map1, map2 = _linked_maps(session)
    char = PlayerCharacter.load(session, 'characters/halfling_rogue.yml')
    map1.place((0, 4), char)

    # Drop a chasm onto the source map that links to map2 — it should still
    # be ignored by the cross-map planner so the route uses the real
    # teleporter ``T`` at (5, 6) instead.
    chasm = Chasm(session, map1, {
        'name': 'Pit',
        'target_map': 'map2',
        'target_position': [0, 0],
    })
    map1.interactable_objects[chasm] = (3, 6)

    pc = PathCompute(None, map1, char)
    plan = pc.compute_cross_map_path(map1, 0, 4, map2, 4, 4)

    assert plan is not None
    # Must hop through the real teleporter at (5, 6), not the chasm at (3, 6).
    assert plan[0]['path'][-1] == (5, 6)
    assert not isinstance(plan[0]['teleporter'], Chasm)

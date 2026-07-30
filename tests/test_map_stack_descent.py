"""Tests for voluntary stack descent pathfinding."""

import pytest

from natural20.ai.path_compute import PathCompute
from natural20.map_stack_descent import (
    plan_voluntary_stack_route,
    preview_fall_damage,
    vertical_movement_cost_grids,
    voluntary_descent_edges,
)
from natural20.session import Session


@pytest.fixture
def stack_session():
    return Session(root_path='user_levels/wild_sheep_chase')


def test_preview_fall_damage_mitigations():
    class Flyer:
        flying = True
        statuses = []

        def is_flying(self):
            return True

    assert preview_fall_damage(Flyer(), '2d6')['mitigated'] is True

    class Feathered:
        flying = False
        statuses = ['feather_fall']

        def is_flying(self):
            return False

    assert preview_fall_damage(Feathered(), '2d6')['mitigated'] is True
    assert preview_fall_damage(Feathered(), '2d6')['reason'] == 'feather_fall'


def test_vertical_movement_cost_grids():
    assert vertical_movement_cost_grids(0, 5) == 0
    assert vertical_movement_cost_grids(15, 5) == 3


def test_stack_opening_is_voluntary_egress(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    upstairs = session.maps['tavern_2nd_floor']
    edges = voluntary_descent_edges(stack, 'tavern_2nd_floor', 0, 0, session=session)
    assert any(e['type'] == 'stack_opening' for e in edges)


def test_plan_descent_from_upstairs_to_market(stack_session):
    session = stack_session
    stack = session.map_stacks.get('amphail_tavern')
    upstairs = session.maps['tavern_2nd_floor']
    market = session.maps['town_market']
    entity = market.entity_by_uid('mara_bartender')
    assert entity is not None

    # Place upstairs near the stair shaft.
    upstairs.add(entity, 0, 0, group='a')
    battle = None
    pc = PathCompute(battle, upstairs, entity)
    plan = plan_voluntary_stack_route(
        pc, session, battle, entity,
        upstairs, 0, 0,
        market, 10, 20,
    )
    assert plan is not None
    assert plan.get('stack_descent')
    assert plan['stack_descent']['to_map'] == 'town_market'
    assert plan['stack_descent'].get('fall_ft', 0) > 0
    assert plan['segments'][0]['map'] == 'tavern_2nd_floor'
    assert plan['segments'][1]['map'] == 'town_market'

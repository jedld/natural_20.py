"""Integration tests for stack movement and LOS."""

import pytest

from natural20.session import Session


@pytest.fixture
def stack_session():
    return Session(root_path='user_levels/wild_sheep_chase')


def test_edge_exit_resolves_to_base(stack_session):
    stack = stack_session.map_stacks.get('amphail_tavern')
    result = stack.resolve_edge_exit('tavern_2nd_floor', -1, 0)
    assert result is not None
    map_name, lx, ly = result
    assert map_name == 'town_market'


def test_battle_registers_stack_maps(stack_session):
    from natural20.battle import Battle
    session = stack_session
    upstairs = session.maps['tavern_2nd_floor']
    battle = Battle(session, upstairs)
    names = {m.name for m in battle.maps}
    assert 'town_market' in names
    assert 'tavern_2nd_floor' in names


def test_stack_los_same_floor(stack_session):
    from natural20.battle import Battle
    from natural20.map_stack_los import stack_can_see
    session = stack_session
    town = session.maps['town_market']
    mara = town.entity_by_uid('mara_bartender')
    pip = town.entity_by_uid('pip_barmaid')
    battle = Battle(session, town)
    stack = session.map_stacks.get('amphail_tavern')
    assert stack_can_see(stack, mara, pip, town, town, battle=battle)

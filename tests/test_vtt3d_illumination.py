"""Play-time 3D ambient illumination overrides."""
import pytest

from natural20.map import Map
from natural20.session import Session
from natural20.web.map_state import build_map_state
from natural20.web.vtt3d_illumination import apply_illumination, resolve_illumination


@pytest.fixture
def session():
    s = Session(root_path='tests/fixtures')
    s.render_for_text = False
    return s


def test_resolve_uses_yaml_illumination_until_overridden(session):
    battle_map = Map(
        session,
        'cellar',
        name='cellar',
        properties={'map': {'illumination': 0.25, 'base': ['..', '..']}},
    )
    lighting = resolve_illumination(battle_map, session)
    assert lighting['illumination'] == 0.25
    assert lighting['illumination_default'] == 0.25
    assert lighting['illumination_overridden'] is False

    applied = apply_illumination(session, battle_map, 0.8)
    assert applied['illumination'] == 0.8
    assert applied['illumination_default'] == 0.25
    assert applied['illumination_overridden'] is True
    assert session.session_state['vtt3d_illumination']['cellar'] == 0.8

    state = build_map_state(battle_map, [], background='maps/demo.webp')
    assert state['map']['illumination'] == 0.8
    assert state['map']['illumination_default'] == 0.25
    assert state['map']['illumination_overridden'] is True

    reset = apply_illumination(session, battle_map, None)
    assert reset['illumination'] == 0.25
    assert reset['illumination_overridden'] is False
    assert 'cellar' not in session.session_state['vtt3d_illumination']


def test_setting_yaml_default_clears_override(session):
    battle_map = Map(
        session,
        'yard',
        name='yard',
        properties={'map': {'illumination': 1.0, 'base': ['..']}},
    )
    apply_illumination(session, battle_map, 0.2)
    snapped = apply_illumination(session, battle_map, 1.0)
    assert snapped['illumination_overridden'] is False
    assert snapped['illumination'] == 1.0


def test_percent_slider_values_map_to_unit_range(session):
    battle_map = Map(
        session,
        'yard',
        name='yard',
        properties={'map': {'illumination': 0.2, 'base': ['..']}},
    )
    applied = apply_illumination(session, battle_map, 55)
    assert applied['illumination'] == pytest.approx(0.55)
    assert applied['illumination_overridden'] is True

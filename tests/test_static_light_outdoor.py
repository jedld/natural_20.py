"""Tests for outdoor tile lighting with time of day."""

from types import SimpleNamespace

from natural20.utils.static_light_builder import StaticLightBuilder


def test_outside_grid_uses_outdoor_ambient():
    properties = {
        'map': {
            'size': [2, 2],
            'base': ['..', '..'],
            'illumination': 1.0,
            'outside': ['oo', 'o.'],
        },
    }
    battle_map = SimpleNamespace(size=(2, 2), feet_per_grid=5, properties=properties)
    battle_map.light_in_sight = lambda *args, **kwargs: (False, False)

    builder = StaticLightBuilder(battle_map)
    builder.outdoor_ambient_illumination = 0.2
    light_map = builder.build_map()

    assert builder.is_outside(0, 0) is True
    assert builder.is_outside(1, 1) is False
    assert float(light_map[0][0]) == 0.2
    assert float(light_map[1][1]) == 1.0

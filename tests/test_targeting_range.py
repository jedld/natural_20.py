from unittest.mock import MagicMock

from natural20.weapons import resolve_targeting_range_ft


def test_resolve_targeting_range_from_weapon_name():
    session = MagicMock()
    session.load_weapon.return_value = {'range': 5, 'type': 'melee_attack'}
    spec = {'type': 'select_target', 'weapon': 'unarmed_attack', 'target_types': ['enemies']}
    assert resolve_targeting_range_ft(session, spec) == 5


def test_resolve_targeting_range_defaults_for_missing_range():
    session = MagicMock()
    spec = {'type': 'select_target', 'target_types': ['enemies']}
    assert resolve_targeting_range_ft(session, spec, default=5) == 5


def test_compute_max_weapon_range_for_param_dict_without_range():
    from natural20.weapons import compute_max_weapon_range

    session = MagicMock()
    session.load_weapon.return_value = {'range': 5}
    spec = {'type': 'select_target', 'weapon': 'unarmed_attack'}
    assert compute_max_weapon_range(session, spec) == 5

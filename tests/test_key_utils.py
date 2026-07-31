"""Tests for master-key matching."""

from natural20.session import Session
from natural20.utils.key_utils import entity_has_key


def test_entity_has_key_direct_and_master_match():
    session = Session(root_path='user_levels/wild_sheep_chase')
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')
    assert entity_has_key(mara, 'tavern_skeleton_key') is True
    assert entity_has_key(mara, 'wooden_door_key') is False


def test_skeleton_key_opens_all_tavern_locks():
    session = Session(root_path='user_levels/wild_sheep_chase')
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    for key_slug in (
        'tavern_room_key_1',
        'tavern_room_key_2',
        'tavern_room_key_3',
        'tavern_room_key_4',
        'tavern_suite_key',
        'tavern_safe_key',
    ):
        assert entity_has_key(mara, key_slug), key_slug

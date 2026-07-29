"""Lockable guest-room doors and chests on tavern_2nd_floor (Wild Sheep Chase)."""

from natural20.item_library.chest import Chest
from natural20.item_library.door_object import DoorObjectWall
from natural20.session import Session


ROOM_KEYS = {
    'tavern_room_1_door': 'tavern_room_key_1',
    'tavern_room_2_door': 'tavern_room_key_2',
    'tavern_room_3_door': 'tavern_room_key_3',
    'tavern_room_4_door': 'tavern_room_key_4',
    'tavern_suite_door': 'tavern_suite_key',
}

CHEST_KEYS = {
    'tavern_room_1_chest': 'tavern_room_key_1',
    'tavern_room_2_chest': 'tavern_room_key_2',
    'tavern_room_3_chest': 'tavern_room_key_3',
    'tavern_room_4_chest': 'tavern_room_key_4',
    'tavern_suite_chest': 'tavern_suite_key',
}


def _find_interactable(upstairs, entity_uid):
    for obj, _pos in upstairs.interactable_objects.items():
        if getattr(obj, 'entity_uid', None) == entity_uid:
            return obj
    return None


def test_tavern_guest_room_doors_are_locked_with_matching_keys():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']

    found = {}
    for obj, _pos in upstairs.interactable_objects.items():
        if not isinstance(obj, DoorObjectWall):
            continue
        uid = getattr(obj, 'entity_uid', None)
        if uid in ROOM_KEYS:
            found[uid] = obj
            assert obj.lockable is True
            assert obj.locked is True
            assert obj.key_name == ROOM_KEYS[uid]

    assert set(found) == set(ROOM_KEYS)


def test_tavern_guest_room_chests_are_locked_with_matching_keys():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']

    found = {}
    for obj, _pos in upstairs.interactable_objects.items():
        if not isinstance(obj, Chest):
            continue
        uid = getattr(obj, 'entity_uid', None)
        if uid in CHEST_KEYS:
            found[uid] = obj
            assert obj.lockable is True
            assert obj.locked() is True
            assert obj.key_name == CHEST_KEYS[uid]

    assert set(found) == set(CHEST_KEYS)


def test_mara_carries_guest_room_keys():
    session = Session(root_path='user_levels/wild_sheep_chase')
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    for key_slug in (
        'tavern_room_key_1',
        'tavern_room_key_2',
        'tavern_room_key_3',
        'tavern_room_key_4',
        'tavern_suite_key',
    ):
        assert mara.item_count(key_slug) >= 1


def test_mara_can_unlock_room_door_with_key():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    door = _find_interactable(upstairs, 'tavern_room_1_door')
    assert door is not None

    unlock_action = door.available_interactions(mara).get('unlock', {})
    assert not unlock_action.get('disabled')
    result = door.resolve(mara, 'unlock', {}, {})
    door.use(mara, result, session)
    assert door.locked is False


def test_mara_can_unlock_room_chest_with_key():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    chest = _find_interactable(upstairs, 'tavern_room_1_chest')
    assert chest is not None

    unlock_action = chest.available_interactions(mara).get('unlock', {})
    assert not unlock_action.get('disabled')
    result = chest.resolve(mara, 'unlock', {}, {})
    chest.use(mara, result, session)
    assert chest.locked() is False

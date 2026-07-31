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


ROOM_DOOR_NOTES = {
    'tavern_room_1_door': 'Standard Room 1',
    'tavern_room_2_door': 'Standard Room 2',
    'tavern_room_3_door': 'Standard Room 3',
    'tavern_room_4_door': 'Standard Room 4',
    'tavern_suite_door': 'Tavern Suite',
}

HALLWAY_DOOR_SIGNS = {
    'tavern_room_1_door_sign': ('Standard Room 1', (5, 1)),
    'tavern_room_2_door_sign': ('Standard Room 2', (5, 4)),
    'tavern_room_3_door_sign': ('Standard Room 3', (5, 7)),
    'tavern_room_4_door_sign': ('Standard Room 4', (4, 3)),
    'tavern_suite_door_sign': ('Tavern Suite', (4, 7)),
}


def test_tavern_guest_room_doors_have_perception_notes():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']

    found = {}
    for obj, _pos in upstairs.interactable_objects.items():
        if not isinstance(obj, DoorObjectWall):
            continue
        uid = getattr(obj, 'entity_uid', None)
        if uid not in ROOM_DOOR_NOTES:
            continue
        found[uid] = obj
        assert not obj.has_notes(), f'{uid} notes moved to hallway sign objects'

    assert set(found) == set(ROOM_DOOR_NOTES)


def test_tavern_hallway_door_signs_are_discoverable_from_the_hall():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']

    found = {}
    for obj, pos in upstairs.interactable_objects.items():
        uid = getattr(obj, 'entity_uid', None)
        if uid not in HALLWAY_DOOR_SIGNS:
            continue
        assert obj.has_notes(), uid
        found[uid] = pos
        label, expected_pos = HALLWAY_DOOR_SIGNS[uid]
        assert pos == list(expected_pos), uid
        assert obj.properties.get('hide_map_token') is True
        notes = obj.properties.get('notes') or []
        assert len(notes) == 1
        assert label in notes[0]['note']
        assert notes[0].get('perception_dc') == 5

    assert set(found) == set(HALLWAY_DOOR_SIGNS)

    pc = session.entity_by_uid('finethir_shinebright')
    assert pc is not None
    upstairs.entities[pc] = (4, 4)
    for uid in HALLWAY_DOOR_SIGNS:
        sign = _find_interactable(upstairs, uid)
        assert sign is not None
        assert upstairs.can_see(pc, sign), uid


def test_tavern_door_room_plaque_visible_on_perception():
    from unittest.mock import MagicMock

    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    sign = _find_interactable(upstairs, 'tavern_room_1_door_sign')
    assert sign is not None

    guest = MagicMock()
    guest.passive_perception.return_value = 12
    guest.is_admin = False

    visible, _ = sign.list_notes(entity=guest, perception=12)
    assert any('Standard Room 1' in (entry.get('note') or '') for entry in visible)


def test_door_object_wall_closed_transform_is_not_none():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    door = _find_interactable(upstairs, 'tavern_room_1_door')
    assert door is not None
    assert door.closed()
    transform = door.token_image_transform()
    assert transform
    assert 'rotate' in transform


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


def test_mara_carries_tavern_keys():
    session = Session(root_path='user_levels/wild_sheep_chase')
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    assert mara.item_count('tavern_skeleton_key') >= 1
    for key_slug in (
        'tavern_room_key_1',
        'tavern_room_key_2',
        'tavern_room_key_3',
        'tavern_room_key_4',
        'tavern_suite_key',
    ):
        assert mara.item_count(key_slug) >= 1, key_slug
    assert mara.item_count('tavern_safe_key') == 0


def test_mara_can_unlock_room_door_with_skeleton_key():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    door = _find_interactable(upstairs, 'tavern_room_1_door')
    assert door is not None

    unlock_action = door.available_interactions(mara).get('unlock', {})
    assert not unlock_action.get('disabled')
    result = door.resolve(mara, 'unlock', {}, {})
    use_results = door.use(mara, result, session)
    assert door.locked is False
    sounds = [item for item in (use_results or []) if item.get('type') == 'contextual_sound']
    assert len(sounds) == 1
    assert 'unlocked' in sounds[0]['message'].lower()
    assert sounds[0]['position'] == upstairs.position_of(door)


def test_mara_can_unlock_room_chest_with_key():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    mara = session.maps['town_market'].entity_by_uid('mara_bartender')

    chest = _find_interactable(upstairs, 'tavern_room_1_chest')
    assert chest is not None

    unlock_action = chest.available_interactions(mara).get('unlock', {})
    assert not unlock_action.get('disabled')
    result = chest.resolve(mara, 'unlock', {}, {})
    use_results = chest.use(mara, result, session)
    assert chest.locked() is False
    sounds = [item for item in (use_results or []) if item.get('type') == 'contextual_sound']
    assert len(sounds) == 1
    assert 'unlocked' in sounds[0]['message'].lower()
    assert sounds[0]['position'] == upstairs.position_of(chest)


def test_mara_can_unlock_till_safe_with_skeleton_key():
    from natural20.item_library.chest import Chest

    session = Session(root_path='user_levels/wild_sheep_chase')
    market = session.maps['town_market']
    mara = market.entity_by_uid('mara_bartender')

    safe = next(
        (
            obj for obj in market.interactable_objects
            if isinstance(obj, Chest) and getattr(obj, 'key_name', None) == 'tavern_safe_key'
        ),
        None,
    )
    assert safe is not None

    unlock_action = safe.available_interactions(mara).get('unlock', {})
    assert not unlock_action.get('disabled')
    result = safe.resolve(mara, 'unlock', {}, {})
    use_results = safe.use(mara, result, session)
    assert safe.locked() is False
    sounds = [item for item in (use_results or []) if item.get('type') == 'contextual_sound']
    assert len(sounds) == 1
    assert 'unlocked' in sounds[0]['message'].lower()

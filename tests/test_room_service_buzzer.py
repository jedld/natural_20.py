"""Room service buzzers in tavern guest rooms."""

from unittest.mock import MagicMock

from natural20.actions.interact_action import InteractAction
from natural20.item_library.room_service_buzzer import RoomServiceBuzzer
from natural20.session import Session


def _find_buzzer(upstairs, entity_uid):
    for obj, _pos in upstairs.interactable_objects.items():
        if getattr(obj, 'entity_uid', None) == entity_uid:
            return obj
    return None


def test_tavern_rooms_have_service_buzzers():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']

    expected = {
        'tavern_room_1_buzzer': 'landmark_standard_room_1',
        'tavern_room_2_buzzer': 'landmark_standard_room_2',
        'tavern_room_3_buzzer': 'landmark_tavern_room_3',
        'tavern_suite_buzzer': 'tavern_suite_room',
        'tavern_room_4_buzzer': 'landmark_standard_room_4',
    }
    found = {}
    for uid, landmark in expected.items():
        buzzer = _find_buzzer(upstairs, uid)
        assert buzzer is not None, uid
        assert isinstance(buzzer, RoomServiceBuzzer)
        assert buzzer.properties.get('room_landmark') == landmark
        found[uid] = buzzer
    assert set(found) == set(expected)


def test_guest_can_buzz_and_emits_room_service_event():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    buzzer = _find_buzzer(upstairs, 'tavern_room_1_buzzer')
    assert buzzer is not None

    guest = MagicMock()
    guest.label.return_value = 'Aldric'
    guest.is_admin = False
    guest.entity_uid = 'pc-1'

    events = []
    session.event_manager.register_event_listener(
        'room_service_buzz',
        lambda event: events.append(event),
    )

    action = InteractAction(session, guest, 'interact', {'target': buzzer, 'object_action': 'buzz'})
    action.resolve(session, upstairs)
    extra = InteractAction.apply(None, action.result[0], session=session)

    assert extra and len(extra) == 1
    assert extra[0]['type'] == 'contextual_sound'
    assert 'whisper' in extra[0]['message'].lower()

    assert len(events) == 1
    assert events[0]['room_label'] == 'Standard Room 1'
    assert events[0]['room_landmark'] == 'landmark_standard_room_1'
    assert events[0]['notify_npc'] == 'pip_barmaid'
    assert 'room service' in events[0]['guest_message'].lower()

    interactions = buzzer.available_interactions(guest)
    assert 'buzz' in interactions
    assert not interactions['buzz'].get('disabled')


def test_buzzer_has_usage_note_for_guests():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    buzzer = _find_buzzer(upstairs, 'tavern_room_1_buzzer')
    assert buzzer is not None

    guest = MagicMock()
    guest.passive_perception.return_value = 10
    guest.is_admin = False

    visible, _ = buzzer.list_notes(entity_pov=[guest])
    notes_text = ' '.join(n['note'] for n in visible).lower()
    assert 'interact' in notes_text
    assert 'ring for room service' in notes_text
    assert buzzer.token_image() == 'objects/tavern_room_buzzer'

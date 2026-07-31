"""Contextual sound toast payloads."""

from unittest.mock import MagicMock

from natural20.item_library.room_service_buzzer import RoomServiceBuzzer
from natural20.session import Session
from natural20.spell.thunderwave_spell import ThunderwaveSpell
from natural20.utils.contextual_sound import build_contextual_sound


def test_build_contextual_sound_anchors_to_object_position():
    session = Session(root_path='user_levels/wild_sheep_chase')
    upstairs = session.maps['tavern_2nd_floor']
    buzzer = None
    for obj in upstairs.interactable_objects:
        if getattr(obj, 'entity_uid', None) == 'tavern_room_1_buzzer':
            buzzer = obj
            break
    assert buzzer is not None

    guest = MagicMock()
    guest.entity_uid = 'pc-1'
    payload = buzzer.contextual_sound_at('A faint ring.', source=guest, label='Message')

    assert payload['type'] == 'contextual_sound'
    assert payload['message'] == 'A faint ring.'
    assert payload['position'] == upstairs.position_of(buzzer)
    assert payload['label'] == 'Message'
    assert payload['duration_ms'] == 4000


def test_spell_contextual_sound_uses_target_anchor():
    session = Session(root_path='user_levels/wild_sheep_chase')
    caster = MagicMock()
    caster.entity_uid = 'wizard-1'
    target = MagicMock()
    target.entity_uid = 'goblin-1'
    target.map = MagicMock()
    target.map.position_of.return_value = (4, 5)
    caster.map = target.map

    spell = ThunderwaveSpell(session, caster, 'thunderwave', session.load_spell('thunderwave'))
    spell.target = target
    payload = spell.contextual_sound('A thunderous boom.', label='Thunderwave')

    assert payload['type'] == 'contextual_sound'
    assert payload['position'] == (4, 5)
    assert payload['label'] == 'Thunderwave'

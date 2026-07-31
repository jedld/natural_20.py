from typing import Any, Dict, List, Optional

from natural20.item_library.object import Object

BUZZER_ITEM_SLUG = 'tavern_room_buzzer'
BUZZER_META_KEYS = ('room_label', 'room_landmark', 'notify_npc', 'source_entity_uid')


def _entity_map_position(entity, session=None) -> Optional[List[int]]:
    if entity is None or session is None:
        return None
    maps = getattr(session, 'maps', None) or {}
    for battle_map in maps.values():
        try:
            if entity in battle_map.entities:
                pos = battle_map.entity_or_object_pos(entity)
                if pos is not None:
                    return list(pos)
        except Exception:
            continue
    return None


def apply_room_service_buzz(
    properties: Dict[str, Any],
    entity,
    session,
    *,
    source_object: Optional[Object] = None,
    position: Optional[List[int]] = None,
) -> List[Any]:
    """Ring a room-service buzzer (map fixture or carried item)."""
    room_label = (
        properties.get('room_label')
        or properties.get('label')
        or 'Guest room'
    )
    guest_name = (
        entity.label()
        if entity is not None and callable(getattr(entity, 'label', None))
        else 'A guest'
    )
    template = properties.get('buzz_message')
    if template:
        message = str(template).format(room=room_label, guest=guest_name)
    else:
        message = (
            f'You whisper into the tiny cantrip rune on the bell pull — a magical thread carries '
            f'your call down to the taproom: "{room_label} requests room service."'
        )

    staff_message = properties.get('staff_message')
    if staff_message:
        staff_message = str(staff_message).format(room=room_label, guest=guest_name)
    else:
        staff_message = (
            f'A whisper cantrip tingles in your ear — {room_label} is ringing for room service.'
        )

    if position is None and source_object is not None and getattr(source_object, 'map', None):
        try:
            position = list(source_object.position())
        except Exception:
            position = None
    if position is None:
        position = _entity_map_position(entity, session)

    if session is not None:
        session.event_manager.received_event({
            'event': 'room_service_buzz',
            'source': entity,
            'target': source_object,
            'room_label': room_label,
            'room_landmark': properties.get('room_landmark'),
            'notify_npc': properties.get('notify_npc', 'pip_barmaid'),
            'message': staff_message,
            'guest_message': message,
            'position': position,
        })
        session.event_manager.received_event({
            'source': entity,
            'target': source_object,
            'event': 'object_interaction',
            'sub_type': 'buzz',
            'result': 'success',
            'reason': message,
        })

    results: List[Any] = []
    if source_object is not None and hasattr(source_object, 'contextual_sound_at'):
        results.append(source_object.contextual_sound_at(message, source=entity, label='Message'))
    elif session is not None:
        from natural20.utils.contextual_sound import build_contextual_sound

        results.append(build_contextual_sound(
            entity,
            message,
            position=position,
            label='Message',
        ))
    return results


def buzzer_inventory_snapshot(properties: Dict[str, Any], *, entity_uid: Optional[str] = None) -> Dict[str, Any]:
    snapshot = {
        'type': BUZZER_ITEM_SLUG,
        'qty': 1,
        'room_label': (
            properties.get('room_label')
            or properties.get('label')
            or 'Guest room'
        ),
        'room_landmark': properties.get('room_landmark'),
        'notify_npc': properties.get('notify_npc', 'pip_barmaid'),
    }
    if entity_uid:
        snapshot['source_entity_uid'] = entity_uid
    return snapshot


class RoomServiceBuzzer(Object):
    """Guest-room buzzer — whispers a room-service call to bar staff (Message cantrip)."""

    def interactable(self, entity=None):
        return True

    def passable(self, origin=None):
        return True

    def _room_label(self) -> str:
        return (
            self.properties.get('room_label')
            or self.properties.get('label')
            or self.label()
            or 'Guest room'
        )

    def _buzz_message(self, entity) -> str:
        template = self.properties.get('buzz_message')
        room_label = self._room_label()
        guest_name = entity.label() if entity is not None and callable(getattr(entity, 'label', None)) else 'A guest'
        if template:
            return str(template).format(room=room_label, guest=guest_name)
        return (
            f'You whisper into the tiny cantrip rune on the bell pull — a magical thread carries '
            f'your call down to the taproom: "{room_label} requests room service."'
        )

    def _entity_already_carries_buzzer(self, entity) -> bool:
        inventory = getattr(entity, 'inventory', None) or {}
        stack = inventory.get(BUZZER_ITEM_SLUG) or {}
        try:
            return int(stack.get('qty') or 0) > 0
        except (TypeError, ValueError):
            return False

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin)
        interactions['buzz'] = {
            'prompt': self.properties.get('buzz_prompt', 'Ring for Room Service'),
        }
        if self.map is not None and hasattr(entity, 'add_item'):
            take = {'prompt': 'Take the room service buzzer'}
            if self._entity_already_carries_buzzer(entity):
                take['disabled'] = True
                take['disabled_text'] = 'You are already carrying a room service buzzer.'
            interactions['take'] = take
        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        result = super().resolve(entity, action, other_params, opts)
        if result:
            return result
        if action == 'buzz':
            return {'action': 'buzz'}
        if action == 'take':
            return {'action': 'take'}
        return None

    def _take_into_inventory(self, entity, session=None) -> bool:
        if self.map is None or not hasattr(entity, 'add_item'):
            return False
        if self._entity_already_carries_buzzer(entity):
            return False

        session = session or self.session
        source_item = buzzer_inventory_snapshot(self.properties, entity_uid=self.entity_uid)
        entity.add_item(BUZZER_ITEM_SLUG, 1, source_item=source_item)
        self.map.remove(self)
        if session is not None:
            session.event_manager.received_event({
                'event': 'object_interaction',
                'source': entity,
                'target': self,
                'sub_type': 'take',
                'result': 'success',
                'reason': f'You take the room service buzzer for {self._room_label()}.',
            })
        return True

    def use(self, entity, result, session=None):
        results = super().use(entity, result, session)
        if not result:
            return results

        action = result.get('action')
        session = session or self.session

        if action == 'take':
            if self._take_into_inventory(entity, session=session):
                return list(results or []) + [{
                    'type': 'message',
                    'message': f'You take the room service buzzer for {self._room_label()}.',
                }]
            return list(results or []) + [{
                'type': 'message',
                'message': 'You cannot take the room service buzzer right now.',
            }]

        if action != 'buzz':
            return results

        extra = apply_room_service_buzz(
            self.properties,
            entity,
            session,
            source_object=self,
        )
        return list(results or []) + extra

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'room_label': self.properties.get('room_label'),
            'room_landmark': self.properties.get('room_landmark'),
            'notify_npc': self.properties.get('notify_npc'),
        })
        return data

    @staticmethod
    def from_dict(data):
        session = data['session']
        buzzer = RoomServiceBuzzer(session, None, data['properties'])
        buzzer.entity_uid = data.get('entity_uid')
        return buzzer


class RoomServiceBuzzerItem(Object):
    """Inventory item — portable room-service buzzer."""

    def consumable(self):
        return False

    def can_use(self, entity, battle):
        return True

    def build_map(self, action):
        action.target = action.source
        return action

    def resolve(self, entity, battle, action, _battle_map):
        return {'action': 'buzz'}

    def use(self, entity, result, session=None):
        session = session or self.session
        if not result or result.get('action') != 'buzz':
            return []
        return apply_room_service_buzz(
            self.properties,
            entity,
            session,
            source_object=None,
        )

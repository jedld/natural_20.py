from natural20.item_library.object import Object


class RoomServiceBuzzer(Object):
    """Guest-room buzzer — whispers a room-service call to bar staff (Message cantrip)."""

    def interactable(self, entity=None):
        return True

    def passable(self, origin=None):
        return True

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = super().available_interactions(entity, battle, admin)
        interactions['buzz'] = {
            'prompt': self.properties.get('buzz_prompt', 'Ring for Room Service'),
        }
        return interactions

    def resolve(self, entity, action, other_params, opts=None):
        result = super().resolve(entity, action, other_params, opts)
        if result:
            return result
        if action == 'buzz':
            return {'action': 'buzz'}
        return None

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

    def use(self, entity, result, session=None):
        results = super().use(entity, result, session)
        if not result or result.get('action') != 'buzz':
            return results

        message = self._buzz_message(entity)
        staff_message = self.properties.get('staff_message')
        if staff_message:
            staff_message = str(staff_message).format(
                room=self._room_label(),
                guest=entity.label() if entity is not None and callable(getattr(entity, 'label', None)) else 'A guest',
            )
        else:
            staff_message = (
                f'A whisper cantrip tingles in your ear — {self._room_label()} is ringing for room service.'
            )

        if session is not None:
            session.event_manager.received_event({
                'event': 'room_service_buzz',
                'source': entity,
                'target': self,
                'room_label': self._room_label(),
                'room_landmark': self.properties.get('room_landmark'),
                'notify_npc': self.properties.get('notify_npc', 'pip_barmaid'),
                'message': staff_message,
                'guest_message': message,
                'position': self.position(),
            })
            session.event_manager.received_event({
                'source': entity,
                'target': self,
                'event': 'object_interaction',
                'sub_type': 'buzz',
                'result': 'success',
                'reason': message,
            })

        results = list(results or [])
        results.append(self.contextual_sound_at(message, source=entity, label='Message'))
        return results

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

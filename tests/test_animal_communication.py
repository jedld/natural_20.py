from natural20.utils.animal_communication import (
    animal_communication_expires_at,
    grant_animal_communication,
    has_animal_communication,
)
from natural20.utils.gibberish import gibberish


class _FakeSession:
    def __init__(self):
        self.game_time = 0
        self._state = {}

    def load_state(self, key):
        return self._state.get(key, {})

    def save_state(self, key, value=None):
        self._state.setdefault(key, {})
        if value is None:
            value = {}
        self._state[key].update(value)


class _FakeEntity:
    def __init__(self, uid):
        self.entity_uid = uid


def test_grant_animal_communication_is_entity_scoped_and_timed_out():
    session = _FakeSession()
    listener = _FakeEntity('pc-1')

    assert has_animal_communication(session, listener) is False

    expiration = grant_animal_communication(session, entity=listener, duration_seconds=120)
    assert expiration == 120
    assert animal_communication_expires_at(session, listener) == 120
    assert has_animal_communication(session, listener) is True

    session.game_time = 121
    assert has_animal_communication(session, listener) is False


def test_grant_animal_communication_global_applies_to_all_entities():
    session = _FakeSession()
    listener = _FakeEntity('pc-2')

    grant_animal_communication(session, entity=None, duration_seconds=60)
    assert has_animal_communication(session, listener) is True

    session.game_time = 61
    assert has_animal_communication(session, listener) is False


def test_gibberish_supports_beast_and_sheep_languages():
    text = 'Please help me, hunters are coming!'
    beast_text = gibberish(text, language='beast')
    sheep_text = gibberish(text, language='sheep')

    assert beast_text
    assert sheep_text
    assert beast_text != text
    assert sheep_text != text

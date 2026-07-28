from natural20.utils.animal_communication import (
    animal_communication_guidance_lines,
    grant_animal_communication,
)


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
    def __init__(self, uid, languages=None, label=None):
        self.entity_uid = uid
        self.properties = {}
        self._languages = list(languages or ['common'])

    def languages(self):
        return list(self._languages)

    def label(self):
        return self._label if hasattr(self, '_label') else self.entity_uid


def test_guidance_only_for_beast_speakers():
    session = _FakeSession()
    human = _FakeEntity('guard', languages=['common'])
    sheep = _FakeEntity('fin', languages=['sheep'])
    speaker = _FakeEntity('aldric', languages=['common'])

    assert animal_communication_guidance_lines(session, human, speaker=speaker) == []
    lines = animal_communication_guidance_lines(session, sheep, speaker=speaker)
    assert lines
    assert 'inactive' in '\n'.join(lines)


def test_guidance_reports_active_effect():
    session = _FakeSession()
    sheep = _FakeEntity('fin', languages=['sheep'])
    speaker = _FakeEntity('aldric', languages=['common'])
    grant_animal_communication(session, entity=speaker, duration_seconds=120)

    lines = animal_communication_guidance_lines(session, sheep, speaker=speaker)
    joined = '\n'.join(lines)
    assert 'active until game time 120' in joined
    assert 'can understand' in joined

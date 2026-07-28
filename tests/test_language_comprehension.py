from natural20.utils.language_comprehension import (
    understands_language,
    understands_language_for_languages,
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
    def __init__(self, uid, languages=None, session=None):
        self.entity_uid = uid
        self.session = session
        self._languages = list(languages or ['common'])

    def languages(self):
        return list(self._languages)


def test_sheep_dialect_requires_beast_language():
    listener = _FakeEntity('pc', languages=['common'])
    assert understands_language(listener, 'sheep') is False
    assert understands_language_for_languages(['common'], 'sheep') is False

    beast_listener = _FakeEntity('pc', languages=['common', 'beast'])
    assert understands_language(beast_listener, 'sheep') is True
    assert understands_language_for_languages(['common', 'beast'], 'sheep') is True


def test_animal_communication_grants_beast_comprehension():
    from natural20.utils.animal_communication import grant_animal_communication

    session = _FakeSession()
    listener = _FakeEntity('pc', languages=['common'], session=session)
    assert understands_language(listener, 'beast', session=session) is False
    assert understands_language(listener, 'sheep', session=session) is False

    grant_animal_communication(session, entity=listener, duration_seconds=120)
    assert understands_language(listener, 'sheep', session=session) is True
    assert understands_language(listener, 'beast', session=session) is True


def test_sheep_comprehension_without_beast_in_language_list():
    """Speak with Animals may be active before languages() is refreshed."""
    from natural20.utils.animal_communication import grant_animal_communication

    session = _FakeSession()
    listener = _FakeEntity('pc', languages=['common'], session=session)
    grant_animal_communication(session, entity=listener, duration_seconds=120)

    assert understands_language(listener, 'sheep', session=session) is True


def test_finethir_understands_common_but_only_speaks_sheep():
    from natural20.session import Session

    session = Session(root_path='user_levels/wild_sheep_chase')
    fin = session.entity_by_uid('finethir_shinebright')
    assert fin.languages() == ['sheep']
    assert 'common' in fin.languages_understood()
    assert understands_language(fin, 'common', session=session) is True


def test_speak_with_animals_lets_pc_reach_beast_in_common():
    from natural20.session import Session
    from natural20.player_character import PlayerCharacter
    from natural20.utils.animal_communication import grant_animal_communication
    from natural20.utils.conversation import delivered_conversations

    session = Session(root_path='user_levels/wild_sheep_chase')
    fin = session.entity_by_uid('finethir_shinebright')
    aldric = PlayerCharacter.load(session, 'characters/aldric_fighter.yml', override={'entity_uid': 'aldric'})
    town = session.maps['town_market']
    town.add(aldric, 10, 22, group='a')

    deliveries = delivered_conversations(
        aldric,
        'Hello Finethir',
        town,
        distance_ft=30,
        mode='normal',
        targets=[fin],
        language='common',
    )
    fin_delivery = next(item for item in deliveries if item['entity'] is fin)
    assert fin_delivery['message'] == 'Hello Finethir'

    grant_animal_communication(session, entity=aldric, duration_seconds=120)
    deliveries = delivered_conversations(
        aldric,
        'Hello again',
        town,
        distance_ft=30,
        mode='normal',
        targets=[fin],
        language='common',
    )
    fin_delivery = next(item for item in deliveries if item['entity'] is fin)
    assert fin_delivery['message'] == 'Hello again'

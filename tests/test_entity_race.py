from natural20.entity import Entity


class _Stub(Entity):
    def __init__(self, race):
        self.properties = {'race': race}


def test_race_string_is_returned_unchanged():
    assert _Stub('halfling').race() == 'halfling'


def test_race_list_is_space_joined():
    assert _Stub(['humanoid', 'goblinoid']).race() == 'humanoid goblinoid'


def test_race_missing_is_empty():
    assert _Stub(None).race() == ''

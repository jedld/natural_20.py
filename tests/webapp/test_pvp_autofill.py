import os
import sys

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp import app as app_module


class FakePlayerCharacter:
    def __init__(self, entity_uid, group):
        self.entity_uid = entity_uid
        self.group = group
        self.properties = {'group': group}


class FakeMap:
    def __init__(self):
        self.spawn_points = {
            'spawn_point_1': {'location': [1, 1]},
            'spawn_point_2': {'location': [2, 2]},
        }
        self.entities = []
        self.placed = []

    def placeable(self, entity, x, y):
        return True

    def find_empty_placeable_position(self, entity, x, y):
        return x, y

    def place(self, position, entity):
        self.placed.append((tuple(position), entity.entity_uid))


class FakeGame:
    def __init__(self, entities, deferred_players, battle_map):
        self._entities = entities
        self.deferred_players = deferred_players
        self.maps = {'index': battle_map}

    def get_entity_by_uid(self, entity_uid):
        return self._entities.get(str(entity_uid))


def test_autofill_pvp_battle_turn_order_includes_claimed_characters(monkeypatch):
    battle_map = FakeMap()
    claimed = FakePlayerCharacter('claimed', 'a')
    unclaimed = FakePlayerCharacter('unclaimed', 'b')
    current_game = FakeGame(
        entities={'claimed': claimed, 'unclaimed': unclaimed},
        deferred_players={
            'claimed': {'entity': claimed, 'map_name': 'index', 'position': [1, 1]},
            'unclaimed': {'entity': unclaimed, 'map_name': 'index', 'position': [2, 2]},
        },
        battle_map=battle_map,
    )

    monkeypatch.setattr(app_module, 'current_game', current_game)
    monkeypatch.setattr(app_module, 'PlayerCharacter', FakePlayerCharacter)
    monkeypatch.setattr(app_module, 'user_role', lambda: ['dm'])
    monkeypatch.setattr(app_module, 'pvp_team_config', lambda: {
        'enabled': True,
        'teams': {
            'a': {'capacity': 1, 'spawn_points': ['spawn_point_1'], 'map': 'index'},
            'b': {'capacity': 1, 'spawn_points': ['spawn_point_2'], 'map': 'index'},
        },
    })
    monkeypatch.setattr(app_module, 'CONTROLLERS', [{
        'entity_uid': 'claimed',
        'controllers': ['alice'],
        'team': 'a',
        'spawn_point': 'spawn_point_1',
    }])

    turn_order = app_module.autofill_pvp_battle_turn_order([])

    assert [item['id'] for item in turn_order] == ['claimed', 'unclaimed']
    assert 'controller' not in turn_order[0]
    assert turn_order[1]['controller'] == 'llm'
    assert current_game.deferred_players == {}

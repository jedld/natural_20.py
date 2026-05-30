from types import SimpleNamespace
from unittest.mock import MagicMock

from webapp.blueprints.helpers.battle_setup import augment_turn_order_with_party_pcs


def test_augment_turn_order_adds_missing_party_pcs():
    pc1 = SimpleNamespace(entity_uid='pc-1', conscious=lambda: True)
    pc2 = SimpleNamespace(entity_uid='pc-2', conscious=lambda: True)
    battle_map = SimpleNamespace(entities=[pc1, pc2])
    current_game = MagicMock()
    current_game.party_player_characters_on_map.return_value = [
        (pc1, 'a'),
        (pc2, 'a'),
    ]

    turn_order = [{'id': 'pc-1', 'group': 'a', 'controller': 'manual'}]
    augmented = augment_turn_order_with_party_pcs(current_game, battle_map, turn_order)

    ids = [item['id'] for item in augmented]
    assert ids == ['pc-1', 'pc-2']
    assert augmented[1]['group'] == 'a'

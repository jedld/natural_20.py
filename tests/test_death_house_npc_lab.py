"""Death House npc_lab map set stays isolated from adventure maps."""

from pathlib import Path

import yaml

from natural20.event_manager import EventManager
from natural20.session import Session


def test_npc_lab_map_set_is_isolated():
    campaign = Path('user_levels/death_house')
    game = yaml.safe_load((campaign / 'game.yml').read_text())
    membership = game['map_sets']
    assert 'npc_arena' in game['maps']
    assert membership['npc_lab']['maps'] == ['npc_arena']
    for set_id, spec in membership.items():
        if set_id == 'npc_lab':
            continue
        assert 'npc_arena' not in spec.get('maps', [])

    session = Session(root_path=str(campaign), event_manager=EventManager())
    assert session.map_set_for('npc_arena') == 'npc_lab'
    assert session.map_set_for('tavern') != 'npc_lab'
    assert not session.same_map_set('npc_arena', 'tavern')

    arena = session.maps['npc_arena']
    uids = {getattr(e, 'entity_uid', None) for e in arena.entities}
    assert 'lab_goblin' in uids
    assert 'lab_skeleton' in uids
    assert 'npc_arrigal' not in uids
    assert 'npc_strahd_von_zarovich' not in uids

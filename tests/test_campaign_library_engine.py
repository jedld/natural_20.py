"""Engine support for the campaign spawner library (DM panel):

- ``spawn_or_move_npc(..., duplicate=True)`` creates an independent copy of a
  unique NPC with a fresh spawn uid instead of moving the original token.
- Null tombstones in a campaign's merged item catalogue (``items/objects.yml``)
  remove bundled entries for that campaign (``_drop_tombstones``).
"""
import os
import shutil

import pytest
import yaml

from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.map_set import spawn_or_move_npc
from natural20.session import Session
from natural20.yaml_loader import load_campaign_yaml

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, 'fixtures')


def _campaign(tmp_path):
    root = tmp_path / 'campaign'
    shutil.copytree(
        FIXTURES, root,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'),
    )
    return root


@pytest.fixture
def session_and_map(tmp_path):
    root = _campaign(tmp_path)
    session = Session(root_path=str(root), event_manager=EventManager())
    battle_map = Map(session, 'battle_sim.yml')
    # spawn_or_move_npc resolves existing tokens through session.maps.
    session.maps[battle_map.name] = battle_map
    return session, battle_map


def test_duplicate_unique_npc_creates_independent_instance(session_and_map):
    session, battle_map = session_and_map

    # Unique NPC types move the existing token instead of adding a second one.
    root = session.root_path
    sheet = os.path.join(root, 'npcs', 'boar.yml')
    with open(sheet, encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}
    data['entity_uid'] = 'boar'
    data['unique'] = True
    with open(sheet, 'w', encoding='utf-8') as handle:
        yaml.safe_dump(data, handle, sort_keys=False)

    first = spawn_or_move_npc(session, 'boar', battle_map, 1, 0)
    assert first['unique'] is True
    assert first['entity_uid'] == 'boar'

    again = spawn_or_move_npc(session, 'boar', battle_map, 3, 0)
    assert again['moved'] is True
    assert again['entity_uid'] == 'boar'

    duplicate = spawn_or_move_npc(session, 'boar', battle_map, None, None,
                                  duplicate=True)
    assert duplicate['duplicate'] is True
    assert duplicate['unique'] is False
    dup_uid = duplicate['entity_uid']
    assert dup_uid != 'boar'

    # Both tokens are on the map, independently registered.
    by_uid = {str(getattr(e, 'entity_uid', '')) for e in battle_map.entities}
    assert 'boar' in by_uid and dup_uid in by_uid

    dup_entity = session.entity_by_uid(dup_uid)
    assert dup_entity is not None
    assert str(dup_entity.entity_uid) == dup_uid
    # The instance override does not touch the shared sheet.
    with open(sheet, encoding='utf-8') as handle:
        assert yaml.safe_load(handle).get('unique') is True


def test_duplicate_false_still_moves_unique(session_and_map):
    session, battle_map = session_and_map
    root = session.root_path
    sheet = os.path.join(root, 'npcs', 'owl.yml')
    with open(sheet, encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}
    data['entity_uid'] = 'owl'
    with open(sheet, 'w', encoding='utf-8') as handle:
        yaml.safe_dump(data, handle, sort_keys=False)

    first = spawn_or_move_npc(session, 'owl', battle_map, 0, 6)
    second = spawn_or_move_npc(session, 'owl', battle_map, 4, 3)
    assert first['entity_uid'] == second['entity_uid'] == 'owl'
    assert second['moved'] is True
    uids = {str(getattr(e, 'entity_uid', '')) for e in battle_map.entities}
    assert 'owl' in uids
    assert len([e for e in battle_map.entities
                if str(getattr(e, 'entity_uid', '')) == 'owl']) == 1


def test_object_catalog_tombstones(tmp_path):
    campaign = tmp_path / 'campaign'
    (campaign / 'items').mkdir(parents=True)
    (campaign / 'game.yml').write_text('name: tombstone test\n', encoding='utf-8')
    # Remove a bundled SRD object and add a campaign-only one.
    (campaign / 'items' / 'objects.yml').write_text(yaml.safe_dump({
        'barrel': None,
        'campaign_clock': {'name': 'Grandfather Clock', 'color': 'brown'},
    }), encoding='utf-8')

    merged = load_campaign_yaml(campaign, 'items', 'objects')
    assert 'barrel' not in merged, 'null tombstone should remove the bundled entry'
    assert 'campaign_clock' in merged
    # A different bundled object is untouched.
    assert 'brazier' in merged

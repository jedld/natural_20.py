"""Tests for player/campaign SQLite notebooks."""

import os

from natural20.notebook_db import CAMPAIGN_OWNER, NotebookDB, NotebookError


def _db(tmp_path):
    return NotebookDB(
        os.path.join(tmp_path, 'notebook.sqlite'),
        files_dir=os.path.join(tmp_path, 'notebook_files'),
    )


def test_player_note_crud_and_search(tmp_path):
    db = _db(tmp_path)
    folder = db.create_folder('player', 'gomerin', 'Session notes')
    note = db.create_note(
        'player',
        'gomerin',
        'Ambush',
        content='Wolves on the west road.',
        folder_id=folder['id'],
    )
    assert note['kind'] == 'note'
    fetched = db.get_item(note['id'])
    assert 'Wolves' in fetched['content']

    updated = db.update_item(note['id'], content='Wolves and a fog bank.')
    assert 'fog' in updated['content']

    hits = db.search('player', 'gomerin', 'fog')
    assert len(hits) == 1
    assert hits[0]['id'] == note['id']

    db.delete_item(note['id'])
    assert db.get_item(note['id']) is None


def test_folders_and_reorder(tmp_path):
    db = _db(tmp_path)
    a = db.create_folder('campaign', CAMPAIGN_OWNER, 'A')
    b = db.create_folder('campaign', CAMPAIGN_OWNER, 'B')
    n1 = db.create_note('campaign', CAMPAIGN_OWNER, 'One', folder_id=a['id'])
    n2 = db.create_note('campaign', CAMPAIGN_OWNER, 'Two', folder_id=a['id'])
    db.reorder(
        'campaign',
        CAMPAIGN_OWNER,
        folder_id=a['id'],
        ordered=[{'type': 'item', 'id': n2['id']}, {'type': 'item', 'id': n1['id']}],
    )
    tree = db.tree('campaign', CAMPAIGN_OWNER)
    in_a = [item for item in tree['items'] if item['folder_id'] == a['id']]
    assert [row['title'] for row in in_a] == ['Two', 'One']

    moved = db.move_node('item', n1['id'], folder_id=b['id'])
    assert moved['folder_id'] == b['id']


def test_file_upload_and_share(tmp_path):
    db = _db(tmp_path)
    item = db.create_file(
        'campaign',
        CAMPAIGN_OWNER,
        'sketch.png',
        b'\x89PNG\r\n\x1a\n' + b'\x00' * 32,
        created_by='dm',
    )
    assert item['kind'] == 'file'
    assert item['is_image'] is True
    path = db.file_path(item)
    assert path and os.path.isfile(path)

    shares = db.create_shares(item['id'], 'dm', ['gomerin'])
    view = db.shared_view(shares[0]['id'], 'gomerin')
    assert view['item']['id'] == item['id']

    try:
        db.shared_view(shares[0]['id'], 'stranger')
        assert False, 'expected NotebookError'
    except NotebookError:
        pass


def test_delete_folder_removes_nested_items(tmp_path):
    db = _db(tmp_path)
    parent = db.create_folder('player', 'alice', 'Root')
    child = db.create_folder('player', 'alice', 'Child', parent_id=parent['id'])
    note = db.create_note('player', 'alice', 'Nested', folder_id=child['id'])
    db.delete_folder(parent['id'])
    assert db.get_folder(child['id']) is None
    assert db.get_item(note['id']) is None


def test_campaign_summary_for_llm(tmp_path):
    db = _db(tmp_path)
    db.create_note('campaign', CAMPAIGN_OWNER, 'Death House', content='The mists close in.')
    summary = db.campaign_summary(query='mists')
    assert summary['item_count'] == 1
    assert summary['items'][0]['title'] == 'Death House'
    assert 'mists' in (summary['items'][0]['preview'] or '')


def test_map_link_owner_only_and_moves_on_same_map(tmp_path):
    db = _db(tmp_path)
    note = db.create_note('campaign', CAMPAIGN_OWNER, 'Handout', content='Show the party.')
    pin = db.upsert_map_link('dm', note['id'], 'tavern', 3, 4)
    assert pin['x'] == 3
    assert pin['title'] == 'Handout'
    moved = db.upsert_map_link('dm', note['id'], 'tavern', 8, 9)
    assert moved['id'] == pin['id']
    assert moved['x'] == 8
    assert db.list_map_links('gomerin', 'tavern') == []
    assert len(db.list_map_links('dm', 'tavern')) == 1
    db.delete_item(note['id'])
    assert db.list_map_links('dm', 'tavern') == []

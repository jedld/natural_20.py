import json
import os
import re
import sys
import uuid

import yaml

WEBAPP_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'webapp')
if WEBAPP_DIR not in sys.path:
    sys.path.insert(0, WEBAPP_DIR)

template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
os.environ.setdefault('TEMPLATE_DIR', template_root)

from webapp.app import app, game_session, index_data

app.config['CHARACTER_BUILDER_ONLY'] = False


def test_create_warlock_character():
    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    unique = uuid.uuid4().hex[:8]
    name = f"Warlock Tester {unique}"
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    entity_uid = safe_name.lower()

    index_path = os.path.join(game_session.root_path, 'index.json')
    with open(index_path, 'r', encoding='utf-8') as fh:
        index_original_text = fh.read()

    char_path = os.path.join(game_session.root_path, 'characters', f"{safe_name}.yml")

    payload = {
        'name': name,
        'pronoun': 'they/them',
        'race': 'human',
        'klass': 'warlock',
        'level': '2',
        'str': '10',
        'dex': '14',
        'con': '14',
        'int': '12',
        'wis': '11',
        'cha': '16',
        'skills': json.dumps(['arcana', 'deception']),
        'cantrips': json.dumps(['eldritch_blast', 'chill_touch']),
        'level1_spells': json.dumps(['burning_hands', 'expeditious_retreat', 'magic_missile']),
    }

    created_entity = None
    try:
        response = client.post('/create_character', data=payload)
        assert response.status_code == 200
        resp_json = response.get_json()
        assert resp_json is not None
        assert resp_json.get('status') == 'ok'
        assert resp_json.get('redirect') == '/'

        assert os.path.exists(char_path)
        with open(char_path, 'r', encoding='utf-8') as fh:
            pc_data = yaml.safe_load(fh)

        assert pc_data['classes'] == {'warlock': 2}
        assert pc_data['entity_uid'] == entity_uid
        assert set(pc_data.get('skills', [])) == {'arcana', 'deception'}

        spells = pc_data.get('prepared_spells', [])
        expected_spells = {'eldritch_blast', 'chill_touch', 'burning_hands', 'expeditious_retreat', 'magic_missile'}
        assert expected_spells.issubset(set(spells))
        assert len(spells) == len(set(spells))

        created_entity = game_session.entity_by_uid(entity_uid)
        assert created_entity is not None
    finally:
        if os.path.exists(char_path):
            os.remove(char_path)

        with open(index_path, 'w', encoding='utf-8') as fh:
            fh.write(index_original_text)
        index_data['selectable_characters'] = json.loads(index_original_text).get('selectable_characters', [])

        if created_entity is not None:
            for map_obj in game_session.maps.values():
                if created_entity in map_obj.entities:
                    map_obj.remove(created_entity)
                    map_obj.unaware_npcs = [entry for entry in map_obj.unaware_npcs if entry.get('entity') is not created_entity]
                    break
            game_session.entity_registry.unregister(created_entity)


def test_create_character_builder_only_mode():
    app.config['TESTING'] = True
    previous_mode = app.config.get('CHARACTER_BUILDER_ONLY', False)
    app.config['CHARACTER_BUILDER_ONLY'] = True

    client = app.test_client()
    with client.session_transaction() as sess:
        sess.clear()

    unique = uuid.uuid4().hex[:8]
    name = f"Builder Only {unique}"
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    entity_uid = safe_name.lower()

    index_path = os.path.join(game_session.root_path, 'index.json')
    with open(index_path, 'r', encoding='utf-8') as fh:
        index_original_text = fh.read()

    char_path = os.path.join(game_session.root_path, 'characters', f"{safe_name}.yml")

    payload = {
        'name': name,
        'race': 'human',
        'klass': 'warlock',
        'level': '1',
        'str': '8',
        'dex': '10',
        'con': '12',
        'int': '13',
        'wis': '14',
        'cha': '15',
        'cantrips': json.dumps(['eldritch_blast']),
        'level1_spells': json.dumps(['magic_missile']),
    }

    try:
        response = client.post('/create_character', data=payload)
        assert response.status_code == 200
        resp_json = response.get_json()
        assert resp_json is not None
        assert resp_json.get('status') == 'ok'
        assert resp_json.get('redirect') == '/character_builder'

        assert os.path.exists(char_path)
        with open(char_path, 'r', encoding='utf-8') as fh:
            pc_data = yaml.safe_load(fh)

        assert pc_data['classes'] == {'warlock': 1}
        assert pc_data['entity_uid'] == entity_uid

        assert game_session.entity_by_uid(entity_uid) is None

        with open(index_path, 'r', encoding='utf-8') as fh:
            assert fh.read() == index_original_text
    finally:
        if os.path.exists(char_path):
            os.remove(char_path)
        with open(index_path, 'w', encoding='utf-8') as fh:
            fh.write(index_original_text)
        app.config['CHARACTER_BUILDER_ONLY'] = previous_mode
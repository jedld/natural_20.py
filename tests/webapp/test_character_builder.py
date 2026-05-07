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


def test_create_kender_character_with_racial_options():
    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    unique = uuid.uuid4().hex[:8]
    name = f"Brash Kender {unique}"
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    entity_uid = safe_name.lower()

    index_path = os.path.join(game_session.root_path, 'index.json')
    with open(index_path, 'r', encoding='utf-8') as fh:
        index_original_text = fh.read()

    char_path = os.path.join(game_session.root_path, 'characters', f"{safe_name}.yml")

    payload = {
        'name': name,
        'race': 'kender',
        'klass': 'fighter',
        'level': '1',
        'str': '10',
        'dex': '14',
        'con': '13',
        'int': '10',
        'wis': '12',
        'cha': '11',
        'skills': json.dumps(['athletics', 'perception']),
        'race_ability_bonuses': json.dumps({'dex': 2, 'wis': 1}),
        'race_skills': json.dumps(['stealth']),
        'race_languages': json.dumps(['elvish']),
    }

    created_entity = None
    try:
        response = client.post('/create_character', data=payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data and data.get('status') == 'ok'

        assert os.path.exists(char_path)
        with open(char_path, 'r', encoding='utf-8') as fh:
            pc_data = yaml.safe_load(fh)

        abilities = pc_data['ability']
        assert abilities['dex'] == 16
        assert abilities['wis'] == 13

        languages = pc_data.get('languages', [])
        assert set(languages) == {'common', 'kenderspeak', 'elvish'}

        skills = set(pc_data.get('skills', []))
        assert {'athletics', 'perception', 'stealth'}.issubset(skills)

        created_entity = game_session.entity_by_uid(entity_uid)
        assert created_entity is not None
        assert created_entity.class_feature('fearless')

        save_roll = created_entity.save_throw('wisdom', opts={'conditions': ['frightened']})
        assert getattr(save_roll, 'advantage', False)
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


def test_kender_missing_racial_bonuses_returns_error():
    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    payload = {
        'name': 'Incomplete Kender',
        'race': 'kender',
        'klass': 'fighter',
        'level': '1',
        'str': '10',
        'dex': '10',
        'con': '10',
        'int': '10',
        'wis': '10',
        'cha': '10',
    }

    response = client.post('/create_character', data=payload)
    assert response.status_code == 400
    data = response.get_json()
    assert data is not None
    assert data.get('error') == 'Select all racial ability bonuses.'


def test_create_druid_character_with_spell_choices():
    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    unique = uuid.uuid4().hex[:8]
    name = f"Druid Tester {unique}"
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    char_path = os.path.join(game_session.root_path, 'characters', f"{safe_name}.yml")
    index_path = os.path.join(game_session.root_path, 'index.json')
    with open(index_path, 'r', encoding='utf-8') as fh:
        index_original_text = fh.read()

    payload = {
        'name': name,
        'race': 'human',
        'klass': 'druid',
        'level': '2',
        'str': '10',
        'dex': '12',
        'con': '14',
        'int': '10',
        'wis': '16',
        'cha': '10',
        'skills': json.dumps(['nature', 'survival']),
        'cantrips': json.dumps(['guidance', 'shillelagh']),
        'level1_spells': json.dumps(['cure_wounds', 'healing_word', 'thunderwave']),
    }

    created_entity = None
    try:
        response = client.post('/create_character', data=payload)
        assert response.status_code == 200
        resp = response.get_json()
        assert resp and resp.get('status') == 'ok'

        assert os.path.exists(char_path)
        with open(char_path, 'r', encoding='utf-8') as fh:
            pc_data = yaml.safe_load(fh)

        spells = set(pc_data.get('prepared_spells', []))
        assert {'guidance', 'shillelagh', 'cure_wounds', 'healing_word', 'thunderwave'}.issubset(spells)

        entity_uid = re.sub(r'[^a-zA-Z0-9_\-]', '_', name).lower()
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


def test_update_character_editor_saves_spells_and_feats():
    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['username'] = 'dm'

    unique = uuid.uuid4().hex[:8]
    name = f"Editor Target {unique}"
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', name)
    entity_uid = safe_name.lower()
    char_path = os.path.join(game_session.root_path, 'characters', f"{safe_name}.yml")

    seed_character = {
        'name': name,
        'race': 'human',
        'classes': {'warlock': 2},
        'level': 2,
        'hit_die': 'inherit',
        'ability': {'str': 8, 'dex': 12, 'con': 14, 'int': 10, 'wis': 10, 'cha': 16},
        'skills': ['arcana', 'deception'],
        'prepared_spells': ['eldritch_blast', 'magic_missile'],
        'entity_uid': entity_uid,
        'token': ['E'],
        'equipped': [],
        'inventory': [],
    }

    with open(char_path, 'w', encoding='utf-8') as fh:
        yaml.safe_dump(seed_character, fh, sort_keys=False)

    try:
        editor_page = client.get(f'/character_editor/{entity_uid}?next=/character_selection')
        assert editor_page.status_code == 200

        payload = {
            'pronoun': 'they/them',
            'skills': json.dumps(['arcana', 'investigation']),
            'cantrips': json.dumps(['eldritch_blast', 'chill_touch']),
            'level1_spells': json.dumps(['burning_hands', 'expeditious_retreat', 'magic_missile']),
            'feats': json.dumps(['alert']),
            'next': '/character_selection',
        }
        response = client.post(f'/update_character/{entity_uid}', data=payload)
        assert response.status_code == 200
        resp = response.get_json()
        assert resp and resp.get('status') == 'ok'
        assert resp.get('redirect') == '/character_selection'

        with open(char_path, 'r', encoding='utf-8') as fh:
            updated = yaml.safe_load(fh)

        assert updated.get('pronoun') == 'they/them'
        assert set(updated.get('skills', [])) == {'arcana', 'investigation'}
        spells = set(updated.get('prepared_spells', []))
        assert {'eldritch_blast', 'chill_touch', 'burning_hands', 'expeditious_retreat', 'magic_missile'}.issubset(spells)
        assert updated.get('feats') == ['alert']
    finally:
        if os.path.exists(char_path):
            os.remove(char_path)
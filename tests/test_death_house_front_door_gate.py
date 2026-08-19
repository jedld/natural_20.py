"""Death House front doors stay sealed until the basement_2 boss dies."""

from pathlib import Path

import yaml

from natural20.item_library.teleporter import Teleporter
from natural20.map import Map


CAMPAIGN = Path('user_levels/death_house')


def _load_map_yaml(name):
    return yaml.safe_load((CAMPAIGN / 'maps' / f'{name}.yml').read_text())


def test_entryway_front_doors_require_cleared_flag():
    legend = _load_map_yaml('entryway')['legend']
    for token in ('SD', 'S2'):
        req = legend[token]['requires_session']
        assert 'death_house_cleared' in req['all_of']
        assert legend[token].get('deny_message')


def test_basement_boss_died_sets_cleared_flag():
    legend = _load_map_yaml('basement_2')['legend']
    events = legend['L']['overrides']['events']
    died = next(item for item in events if item.get('event') == 'died')
    assert died['set_session']['death_house_cleared'] is True
    assert died['campaign_event'] == 'death_house_cleared'


def test_game_yml_battle_end_hook_sets_same_flag():
    game = yaml.safe_load((CAMPAIGN / 'game.yml').read_text())
    hook = next(
        item for item in game['battle_end_hooks']
        if item.get('id') == 'death_house_boss_defeated'
    )
    assert hook['map'] == 'basement_2'
    assert hook['session_flags']['death_house_cleared'] is True
    assert hook['once_session_key'] == 'death_house_cleared'
    assert 'b' in hook['require_groups_defeated']


def test_death_house_uses_milestone_progression():
    game = yaml.safe_load((CAMPAIGN / 'game.yml').read_text())
    progression = game['progression']
    assert progression['mode'] == 'milestone'
    stairs = progression['events']['secret_stairs_revealed']
    escaped = progression['events']['death_house_escaped']
    assert stairs['target_level'] == 2
    assert escaped['target_level'] == 3


def test_attic_and_front_door_fire_milestone_events():
    attic = _load_map_yaml('attic')
    dollhouse = attic['legend']['D']['events'][0]
    assert dollhouse['campaign_event'] == 'secret_stairs_revealed'
    stairs = attic['legend']['q']
    assert stairs['events'][0]['campaign_event'] == 'secret_stairs_revealed'

    entryway = _load_map_yaml('entryway')
    for token in ('SD', 'S2'):
        events = entryway['legend'][token]['events']
        assert events[0]['campaign_event'] == 'death_house_escaped'


def test_npc_spawn_overrides_merges_legend_events():
    merged = Map._npc_spawn_overrides({
        'events': [{'event': 'died', 'set_session': 'from_legend'}],
        'overrides': {
            'entity_uid': 'boss',
            'events': [{'event': 'died', 'set_session': 'from_overrides'}],
        },
    })
    assert merged['entity_uid'] == 'boss'
    assert [item['set_session'] for item in merged['events']] == [
        'from_legend',
        'from_overrides',
    ]


def test_front_door_teleporter_opens_after_flag():
    props = _load_map_yaml('entryway')['legend']['SD']
    session = type('S', (), {'session_state': {}, 'event_manager': None})()
    tp = Teleporter(session, None, props)
    entity = type('E', (), {'name': 'hero', 'inventory': {}})()
    source_map = type('M', (), {'session': session})()
    assert tp._session_gate_allows(entity, source_map) is False
    session.session_state['death_house_cleared'] = True
    assert tp._session_gate_allows(entity, source_map) is True

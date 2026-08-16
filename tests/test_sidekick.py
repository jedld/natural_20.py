"""Party sidekick membership, death saves, Extra Attack, and Tasha overlay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from natural20.actions.attack_action import AttackAction
from natural20.actions.help_action import HelpAction, HelpBonusAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session
from natural20.sidekick import (
    apply_sidekick_class,
    extra_attack_count,
    is_in_party_sidekick,
    iter_party_members,
    join_party,
    leave_party,
    selectable_sidekick_entries,
    STATUS_HOSTILE,
    STATUS_IN_PARTY,
    STATUS_LEFT,
)
from natural20.companion import companion_defs


PACK = Path('expansion_packs/tashas_sidekicks')


def _session():
    em = EventManager()
    em.standard_cli()
    return Session(root_path='tests/fixtures', event_manager=em)


def test_join_and_leave_party():
    session = _session()
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_squire'}})
    session.register_entity(npc)
    rec = join_party(session, npc, ['alice'])
    assert rec['status'] == STATUS_IN_PARTY
    assert rec['owners'] == ['alice']
    assert npc.group == 'a'
    assert is_in_party_sidekick(session, npc)
    members = iter_party_members(session)
    assert npc in members
    defs = companion_defs(session.game_properties, session=session)
    assert any(d.get('entity_uid') == 'npc_squire' for d in defs)

    left = leave_party(session, npc)
    assert left['status'] == STATUS_LEFT
    assert npc.group == 'c'
    assert not is_in_party_sidekick(session, npc)

    join_party(session, npc, ['alice'])
    hostile = leave_party(session, npc, hostile=True)
    assert hostile['status'] == STATUS_HOSTILE
    assert npc.group == 'b'


def test_death_saves_for_in_party_sidekick():
    session = _session()
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_squire'}})
    session.register_entity(npc)
    assert not npc.makes_death_saves()
    join_party(session, npc, ['alice'])
    assert npc.makes_death_saves()
    npc.attributes['hp'] = 1
    npc.take_damage(5, session=session)
    assert npc.unconscious()
    assert not npc.dead()


def test_selectable_sidekick_entries_from_game_yml(tmp_path):
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'npcs').mkdir()
    game = {
        'name': 'Sidekick Fixture',
        'starting_map': 'maps/town',
        'maps': {'town': 'maps/town'},
        'sidekicks': [
            {'entity_uid': 'npc_squire', 'selectable': True, 'sheet': 'goblin'},
        ],
    }
    (tmp_path / 'game.yml').write_text(yaml.safe_dump(game), encoding='utf-8')
    (tmp_path / 'index.json').write_text('{"tile_size": 70, "title": "t", "logins": [], "default_controllers": []}', encoding='utf-8')
    (tmp_path / 'maps' / 'town.yml').write_text(
        'name: town\nmap:\n  illumination: 1.0\n  base: ["..",".."]\nlegend: {}\nplayer: []\nnpc: []\n',
        encoding='utf-8',
    )
    goblin_src = Path('tests/fixtures/npcs/goblin.yml').read_text(encoding='utf-8')
    (tmp_path / 'npcs' / 'goblin.yml').write_text(goblin_src, encoding='utf-8')
    session = Session(root_path=str(tmp_path), event_manager=EventManager())
    entries = selectable_sidekick_entries(session)
    assert len(entries) == 1
    assert entries[0]['kind'] == 'npc'
    assert entries[0]['role_label'] == 'Sidekick'


def test_help_bonus_action_requires_helpful():
    session = _session()
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_squire'}})
    battle = Battle(session, Map(session, 'tests/fixtures/battle_sim.yml'))
    battle.add(npc, 'a')
    state = battle.entity_state_for(npc)
    state['bonus_action'] = 1
    state['action'] = 1
    assert not HelpBonusAction.can(npc, battle)
    npc.properties.setdefault('class_features', []).append('helpful')
    assert HelpBonusAction.can(npc, battle)
    assert HelpAction.can(npc, battle)


def test_extra_attack_count_and_follow_up():
    session = _session()
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_squire'}})
    assert extra_attack_count(npc) == 1
    npc.properties.setdefault('class_features', []).append('extra_attack')
    assert extra_attack_count(npc) == 2
    battle = Battle(session, Map(session, 'tests/fixtures/battle_sim.yml'))
    battle.add(npc, 'a')
    state = battle.entity_state_for(npc)
    state['action'] = 0
    state['extra_attacks_remaining'] = 1
    assert AttackAction.can(npc, battle)


@pytest.mark.skipif(not PACK.is_dir(), reason='tashas_sidekicks pack not present')
def test_tasha_warrior_overlay(tmp_path):
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'npcs').mkdir()
    game = {
        'name': 'Pack Fixture',
        'starting_map': 'maps/town',
        'maps': {'town': 'maps/town'},
    }
    (tmp_path / 'game.yml').write_text(yaml.safe_dump(game), encoding='utf-8')
    index = {
        'tile_size': 70,
        'title': 't',
        'logins': [],
        'default_controllers': [],
        'expansion_packs': {'tashas_sidekicks': 'tashas_sidekicks'},
    }
    (tmp_path / 'index.json').write_text(json.dumps(index), encoding='utf-8')
    (tmp_path / 'maps' / 'town.yml').write_text(
        'name: town\nmap:\n  illumination: 1.0\n  base: ["..",".."]\nlegend: {}\nplayer: []\nnpc: []\n',
        encoding='utf-8',
    )
    goblin_src = Path('tests/fixtures/npcs/goblin.yml').read_text(encoding='utf-8')
    (tmp_path / 'npcs' / 'goblin.yml').write_text(goblin_src, encoding='utf-8')
    session = Session(root_path=str(tmp_path), event_manager=EventManager())
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_squire'}})
    session.register_entity(npc)
    join_party(session, npc, ['alice'])
    result = apply_sidekick_class(session, npc, 'sidekick_warrior', level=6, role='attacker')
    assert result and result.get('applied')
    assert npc.class_feature('extra_attack')
    assert npc.class_feature('martial_role_attacker')
    assert extra_attack_count(npc) == 2
    assert int(npc.properties.get('proficiency_bonus') or 0) == 3


def _pack_session(tmp_path, *, game_extra=None):
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'npcs').mkdir()
    game = {
        'name': 'Pack Fixture',
        'starting_map': 'maps/town',
        'maps': {'town': 'maps/town'},
    }
    if game_extra:
        game.update(game_extra)
    (tmp_path / 'game.yml').write_text(yaml.safe_dump(game), encoding='utf-8')
    index = {
        'tile_size': 70,
        'title': 't',
        'logins': [],
        'default_controllers': [],
        'expansion_packs': {'tashas_sidekicks': 'tashas_sidekicks'},
    }
    (tmp_path / 'index.json').write_text(json.dumps(index), encoding='utf-8')
    (tmp_path / 'maps' / 'town.yml').write_text(
        'name: town\nmap:\n  illumination: 1.0\n  base: ["..",".."]\nlegend: {}\nplayer: []\nnpc: []\n',
        encoding='utf-8',
    )
    goblin_src = Path('tests/fixtures/npcs/goblin.yml').read_text(encoding='utf-8')
    (tmp_path / 'npcs' / 'goblin.yml').write_text(goblin_src, encoding='utf-8')
    return Session(root_path=str(tmp_path), event_manager=EventManager())


@pytest.mark.skipif(not PACK.is_dir(), reason='tashas_sidekicks pack not present')
def test_tasha_healer_overlay_grants_cure_wounds(tmp_path):
    session = _pack_session(tmp_path)
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_healer'}})
    session.register_entity(npc)
    result = apply_sidekick_class(session, npc, 'sidekick_spellcaster', level=1, role='healer')
    assert result and result.get('applied')
    prepared = npc.prepared_spells()
    assert 'cure_wounds' in prepared
    assert 'spare_the_dying' in prepared
    assert npc.spell_slots_count(1) == 2
    assert npc.has_spells()


@pytest.mark.skipif(not PACK.is_dir(), reason='tashas_sidekicks pack not present')
def test_join_party_applies_campaign_healer_class(tmp_path):
    session = _pack_session(tmp_path, game_extra={
        'sidekicks': [{
            'entity_uid': 'npc_healer',
            'sidekick_class': 'sidekick_spellcaster',
            'sidekick_level': 1,
            'role': 'healer',
        }],
    })
    npc = session.npc('goblin', {'overrides': {'entity_uid': 'npc_healer'}})
    session.register_entity(npc)
    join_party(session, npc, ['alice'])
    assert 'cure_wounds' in npc.prepared_spells()
    assert npc.properties.get('sidekick_role') == 'healer'

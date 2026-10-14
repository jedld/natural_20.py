"""SRD 5.2 Ranger overlay + Gloom Stalker (players_handbook_2024 pack)."""
import json
import random
import shutil
from pathlib import Path

import pytest
import yaml

from natural20.actions.attack_option_action import AttackOptionHitAction, AttackOptionHitOffer
from natural20.actions.class_feature_action import ClassFeatureAction
from natural20.actions.granted_attack_action import GrantedAttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import attack_options as ao
from natural20.utils.class_feature_registry import collect_class_feature_actions
from natural20.utils.class_mechanics import evades_darkvision, extra_prepared_spells, free_cast_pool_for
from natural20.utils.serialization import Serialization

PACK = Path('expansion_packs/players_handbook_2024')
pytestmark = pytest.mark.skipif(not PACK.is_dir(), reason='players_handbook_2024 pack not present')


def _campaign(tmp_path):
    (tmp_path / 'maps').mkdir()
    shutil.copy('tests/fixtures/maps/empty_map.yml', tmp_path / 'maps' / 'empty_map.yml')
    dark = yaml.safe_load(open('tests/fixtures/maps/empty_map.yml'))
    dark['map']['illumination'] = 0.0
    (tmp_path / 'maps' / 'dark_map.yml').write_text(yaml.safe_dump(dark))
    (tmp_path / 'game.yml').write_text(yaml.safe_dump({'name': 'Ranger Fixture', 'ruleset': '5e-2024',
                                                       'starting_map': 'maps/empty_map'}))
    (tmp_path / 'index.json').write_text(json.dumps({
        'tile_size': 70, 'title': 't', 'logins': [], 'default_controllers': [],
        'expansion_packs': {'players_handbook_2024': 'players_handbook_2024'},
    }))
    return Session(root_path=str(tmp_path), event_manager=EventManager())


def _ranger_props(**extra):
    props = {
        'name': 'Stalker', 'entity_uid': 'stalker', 'race': 'human',
        'classes': {'ranger': 11}, 'level': 11, 'ranger_archetype': 'gloom_stalker',
        'max_hp': 81, 'hp': 81, 'hit_die': 'inherit',
        'ability': {'str': 13, 'dex': 18, 'con': 12, 'int': 8, 'wis': 19, 'cha': 8},
        'saving_throw_proficiencies': ['str', 'dex', 'wis'],
        'prepared_spells': ['hunters_mark', 'cure_wounds'],
        'equipped': ['studded_leather', 'longbow', 'arrows'],
        'inventory': [{'type': 'studded_leather', 'qty': 1}, {'type': 'longbow', 'qty': 1},
                      {'type': 'arrows', 'qty': 20}],
        'token': ['S'], 'group': 'a',
    }
    props.update(extra)
    return props


@pytest.fixture
def setup(tmp_path):
    random.seed(7)
    session = _campaign(tmp_path)
    battle_map = Map(session, 'maps/empty_map')
    battle = Battle(session, battle_map)
    pc = PlayerCharacter(session, _ranger_props())
    goblin = Npc(session, 'goblin', {'name': 'g1'})
    goblin2 = Npc(session, 'goblin', {'name': 'g2'})
    for entity in (pc, goblin, goblin2):
        session.register_entity(entity)
    battle_map.add(pc, 0, 0)
    battle_map.add(goblin, 3, 3)
    battle_map.add(goblin2, 4, 3)
    battle.add(pc, 'a', add_to_initiative=True)
    battle.add(goblin, 'b', add_to_initiative=True)
    battle.add(goblin2, 'b', add_to_initiative=True)
    battle.start(combat_order=[pc, goblin, goblin2])
    yield session, battle, battle_map, pc, goblin, goblin2
    DieRoll.unfudge(20)


def _hit_result(pc, target, battle):
    return {'hit?': True, 'battle': battle, 'target': target, 'weapon': 'longbow',
            'damage_type': 'piercing', 'source': pc}


def test_slots_pools_and_free_hunters_mark(setup):
    _session, _battle, _map, pc, _g, _g2 = setup
    assert dict(pc.spell_slots['ranger']) == {0: 0, 1: 4, 2: 3, 3: 3}
    assert pc.get_resource('favored_enemy').max_value == 4
    assert pc.get_resource('tireless').max_value == 4
    assert pc.get_resource('dreadful_strike').max_value == 4
    assert free_cast_pool_for(pc, 'hunters_mark') == 'favored_enemy'
    assert 'disguise_self' in extra_prepared_spells(pc)
    assert 'hunters_mark' in extra_prepared_spells(pc)


def test_features(setup):
    _session, _battle, _map, pc, _g, _g2 = setup
    for feature in ('favored_enemy', 'deft_explorer', 'roving', 'tireless', 'expertise',
                    'dread_ambusher', 'umbral_sight', 'iron_mind', 'stalkers_flurry'):
        assert pc.class_feature(feature), feature
    assert not pc.class_feature('shadowy_dodge')


def test_initiative_speed_and_first_turn_movement(setup):
    _session, battle, _map, pc, _g, _g2 = setup
    assert pc.initiative_bonus() == pc.dex_mod() + pc.wis_mod()
    assert pc.speed() == 40
    pc.reset_turn(battle)
    assert battle.entity_state_for(pc)['movement'] == 50
    pc.reset_turn(battle)
    assert battle.entity_state_for(pc)['movement'] == 40


def test_umbral_sight(setup):
    session, _battle, _map, pc, _g, _g2 = setup
    assert pc.darkvision(60)
    assert evades_darkvision(pc)
    dark_map = Map(session, 'maps/dark_map')
    watcher = Npc(session, 'goblin', {'name': 'watcher'})
    dark_map.add(pc, 0, 0)
    dark_map.add(watcher, 3, 0)
    assert dark_map.can_see(pc, watcher)
    assert not dark_map.can_see(watcher, pc)


def test_tireless_temp_hp(setup):
    session, battle, battle_map, pc, _g, _g2 = setup
    pc.reset_turn(battle)
    actions = [a for a in collect_class_feature_actions(session, pc, battle) if isinstance(a, ClassFeatureAction)]
    assert len(actions) == 1
    action = actions[0].resolve(session, battle_map, {'battle': battle})
    battle.commit(action)
    assert pc.temp_hp() >= 1 + pc.wis_mod()
    assert pc.get_resource('tireless').current == 3


def test_tireless_short_rest_reduces_exhaustion(setup):
    _session, _battle, _map, pc, _g, _g2 = setup
    pc.set_exhaustion_level(2)
    pc.short_rest(None, force=True)
    assert pc.exhaustion_level() == 1


def _dreadful(pc):
    return next(o for o in ao.attack_options_for(pc) if o['id'] == 'dreadful_strike')


def test_dreadful_strike_variants_and_damage(setup):
    _session, battle, _map, pc, goblin, _g2 = setup
    option = _dreadful(pc)
    assert ao.option_extra_damage(pc, option) == '2d8'
    assert [v['id'] for v in ao.option_variants(pc, option)] == ['sudden_strike', 'mass_fear']
    pc.reset_turn(battle)
    hit = _hit_result(pc, goblin, battle)
    action = AttackOptionHitAction(pc.session, pc, option, goblin, hit)
    action.resolve(pc.session, battle.map_for(pc), {'battle': battle})
    damage = next(i for i in action.result if i['type'] == 'additional_damage')
    assert damage['damage_type'] == 'psychic'
    battle.commit(action)
    assert pc.get_resource('dreadful_strike').current == 3
    assert not ao.option_available(pc, battle, option)


def test_mass_fear_frightens_target_and_neighbour(setup):
    _session, battle, _map, pc, goblin, goblin2 = setup
    pc.reset_turn(battle)
    variant = next(v for v in ao.option_variants(pc, _dreadful(pc)) if v['id'] == 'mass_fear')
    DieRoll.fudge(1)
    action = AttackOptionHitAction(pc.session, pc, variant, goblin, _hit_result(pc, goblin, battle))
    action.resolve(pc.session, battle.map_for(pc), {'battle': battle})
    DieRoll.unfudge(20)
    battle.commit(action)
    assert pc.entity_uid in goblin.attributes.get('frightened_by', {})
    assert pc.entity_uid in goblin2.attributes.get('frightened_by', {})
    assert pc.get_resource('dreadful_strike').current == 3


def test_sudden_strike_grants_free_attack_on_neighbour(setup):
    session, battle, battle_map, pc, goblin, goblin2 = setup
    pc.reset_turn(battle)
    variant = next(v for v in ao.option_variants(pc, _dreadful(pc)) if v['id'] == 'sudden_strike')
    action = AttackOptionHitAction(session, pc, variant, goblin, _hit_result(pc, goblin, battle))
    action.resolve(session, battle_map, {'battle': battle})
    battle.commit(action)
    granted = [a for a in collect_class_feature_actions(session, pc, battle) if isinstance(a, GrantedAttackAction)]
    assert len(granted) == 1
    attack = granted[0].clone()
    attack.target = goblin
    attack.resolve(session, battle_map, {'battle': battle})
    assert attack.result == []
    attack = granted[0].clone()
    attack.target = goblin2
    actions_before = battle.entity_state_for(pc)['action']
    attack.resolve(session, battle_map, {'battle': battle})
    assert attack.result
    battle.commit(attack)
    assert battle.entity_state_for(pc)['action'] == actions_before
    assert battle.entity_state_for(pc)['granted_attack'] is None


def test_hit_offer_lists_variants(setup):
    _session, battle, _map, pc, goblin, _g2 = setup
    pc.reset_turn(battle)
    seen = {}

    class Picker:
        def select_reaction(self, entity, battle, map, actions, event):
            seen['ids'] = [a.option['id'] for a in actions]
            return actions[2]

    battle.entities[pc]['controller'] = Picker()
    offer = AttackOptionHitOffer(pc, _dreadful(pc))
    results = offer.on_attack_hit(pc, {'result': _hit_result(pc, goblin, battle)})
    assert seen['ids'] == ['dreadful_strike', 'sudden_strike', 'mass_fear']
    assert any(r.get('type') == 'attack_option_hit' and r['option']['id'] == 'mass_fear' for r in results)


def test_serialization_round_trip(setup):
    session, battle, battle_map, pc, goblin, _g2 = setup
    pc.reset_turn(battle)
    pc.get_resource('dreadful_strike').consume(1)
    from natural20.actions.granted_attack_action import grant_attack
    grant_attack(battle, pc, 'longbow', [goblin], label='Sudden Strike')
    dump = Serialization().serialize(session, battle, {'empty_map': battle_map})
    session2, battle2, _maps2 = Serialization().deserialize(dump)
    pc2 = session2.entity_by_uid('stalker')
    assert pc2.resource_value('dreadful_strike') == 3
    assert pc2.speed() == 40
    assert battle2.entity_state_for(pc2)['granted_attack']['candidates'] == [goblin.entity_uid]

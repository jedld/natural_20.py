"""YAML-only classes (data-driven) using the Tasha's Cauldron artificer pack."""
import json
import random
import shutil
from pathlib import Path

import pytest
import yaml

from natural20.actions.craft_item_action import CraftItemAction
from natural20.actions.spell_action import SpellAction
from natural20.actions.use_item_action import UseItemAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.class_feature_registry import collect_class_feature_actions
from natural20.utils.class_mechanics import apply_spell_roll_bonuses, free_cast_pool_for
from natural20.utils.serialization import Serialization

PACK = Path('expansion_packs/tashas_cauldron')
pytestmark = pytest.mark.skipif(not PACK.is_dir(), reason='tashas_cauldron pack not present')


def _campaign(tmp_path):
    (tmp_path / 'maps').mkdir()
    shutil.copy('tests/fixtures/maps/empty_map.yml', tmp_path / 'maps' / 'empty_map.yml')
    (tmp_path / 'game.yml').write_text(yaml.safe_dump({'name': 'Artificer Fixture', 'ruleset': '5e-2014',
                                                       'starting_map': 'maps/empty_map'}))
    (tmp_path / 'index.json').write_text(json.dumps({
        'tile_size': 70, 'title': 't', 'logins': [], 'default_controllers': [],
        'expansion_packs': {'tashas_cauldron': 'tashas_cauldron'},
    }))
    return Session(root_path=str(tmp_path), event_manager=EventManager())


def _artificer_props(**extra):
    props = {
        'name': 'Tinker', 'entity_uid': 'tinker', 'race': 'gnome', 'subrace': 'rock_gnome',
        'race_edition': '5e-2024', 'classes': {'artificer': 11}, 'level': 11,
        'artificer_specialist': 'alchemist', 'max_hp': 80, 'hp': 80, 'hit_die': 'inherit',
        'ability': {'str': 9, 'dex': 12, 'con': 14, 'int': 20, 'wis': 11, 'cha': 10},
        'saving_throw_proficiencies': ['con', 'int'],
        'tool_proficiencies': ['thieves_tools', 'tinkers_tools', 'alchemists_supplies'],
        'cantrips': ['firebolt'], 'prepared_spells': ['cure_wounds'],
        'spell_abilities': {'mending': 'intelligence'},
        'equipped': ['shield'],
        'inventory': [{'type': 'alchemists_supplies', 'qty': 1}, {'type': 'shield', 'qty': 1}],
        'token': ['T'], 'group': 'a',
    }
    props.update(extra)
    return props


@pytest.fixture
def setup(tmp_path):
    random.seed(11)
    session = _campaign(tmp_path)
    battle_map = Map(session, 'maps/empty_map')
    battle = Battle(session, battle_map)
    pc = PlayerCharacter(session, _artificer_props())
    ally = PlayerCharacter(session, _artificer_props(name='Ally', entity_uid='ally', classes={'artificer': 3},
                                                     level=3, artificer_specialist=None))
    session.register_entity(pc)
    session.register_entity(ally)
    battle_map.add(pc, 1, 1)
    battle_map.add(ally, 2, 1)
    battle.add(pc, 'a', add_to_initiative=True)
    battle.add(ally, 'a', add_to_initiative=True)
    battle.start(combat_order=[pc, ally])
    pc.reset_turn(battle)
    ally.reset_turn(battle)
    yield session, battle, battle_map, pc, ally
    DieRoll.unfudge(20)


def test_spellcasting_rounds_half_caster_up(setup):
    _session, _battle, _map, pc, ally = setup
    assert dict(pc.spell_slots['artificer']) == {0: 0, 1: 4, 2: 3, 3: 3}
    assert pc.max_spell_slots(3, 'artificer') == 3
    assert dict(ally.spell_slots['artificer']) == {0: 0, 1: 3}


def test_features_pools_and_prepared_spells(setup):
    session, _battle, _map, pc, _ally = setup
    for feature in ('flash_of_genius', 'experimental_elixir', 'alchemical_savant',
                    'restorative_reagents', 'spell_storing_item', 'tool_expertise'):
        assert pc.class_feature(feature), feature
    assert not pc.class_feature('chemical_mastery')
    pools = {name: pool.max_value for name, pool in pc.resources.items()}
    assert pools == {'flash_of_genius': 5, 'spell_storing_item': 10, 'restorative_reagents': 5}
    prepared = pc.prepared_spells()
    assert 'healing_word' in prepared and 'mass_healing_word' in prepared
    assert 'mending' in prepared and 'prestidigitation' in prepared  # rock gnome lineage
    assert 'blight' not in prepared  # 13th-level alchemist spell
    assert 'artificer' in pc.spell_list_classes_for(session.load_spell('healing_word'))
    assert pc.spell_attack_modifier_for(session.load_spell('firebolt')) == 9
    assert pc.expertise('thieves_tools')


def test_gnomish_cunning_2024_gives_mental_save_advantage(setup):
    _session, battle, _map, pc, _ally = setup
    assert pc.race_properties.get('base_speed') == 30
    captured = {}
    original = DieRoll.roll

    def spy(roll_str, **kwargs):
        if 'saving_throw' in str(kwargs.get('description', '')):
            captured.update(kwargs)
        return original(roll_str, **kwargs)

    DieRoll.roll = staticmethod(spy)
    try:
        pc.save_throw('wisdom', battle)
    finally:
        DieRoll.roll = staticmethod(original)
    assert captured.get('advantage')


def test_long_rest_grants_elixirs_and_expires_old_ones(setup):
    _session, _battle, _map, pc, _ally = setup
    pc.long_rest(force=True)
    granted = list(pc.properties['rest_granted_items']['experimental_elixir'])
    assert len(granted) == 2
    for item in granted:
        assert pc.inventory[item]['crafted_by'] == 'tinker'
    pc.long_rest(force=True)
    assert sum(pc.item_count(item) for item in set(granted)) <= len(pc.properties['rest_granted_items']['experimental_elixir'])
    assert len(pc.properties['rest_granted_items']['experimental_elixir']) == 2


def test_craft_elixir_spends_lowest_slot(setup):
    session, battle, battle_map, pc, _ally = setup
    actions = [a for a in collect_class_feature_actions(session, pc, battle) if isinstance(a, CraftItemAction)]
    assert len(actions) == 6
    flight = next(a for a in actions if a.item == 'elixir_of_flight')
    flight.resolve(session, battle_map, {'battle': battle})
    battle.commit(flight)
    assert pc.spell_slots['artificer'][1] == 3
    assert pc.item_count('elixir_of_flight') == 1
    assert 'elixir_of_flight' in pc.properties['rest_granted_items']['experimental_elixir']


def test_craft_requires_alchemist_supplies(setup):
    session, battle, _map, pc, _ally = setup
    pc.inventory.pop('alchemists_supplies')
    assert not [a for a in collect_class_feature_actions(session, pc, battle) if isinstance(a, CraftItemAction)]


def _drink(session, battle, battle_map, user, item, target):
    action = UseItemAction.build_self_use(session, user, item, target=target)
    action.resolve(session, battle_map, {'battle': battle})
    battle.commit(action)
    return action


def test_elixirs_use_makers_intelligence_and_restorative_reagents(setup):
    session, battle, battle_map, pc, ally = setup
    from natural20.utils.class_mechanics import give_crafted_item
    give_crafted_item(pc, 'elixir_of_healing')
    ally.take_damage(30, battle=battle)
    before = ally.hp()
    action = _drink(session, battle, battle_map, pc, 'elixir_of_healing', ally)
    result = action.result[0]
    assert result['hp_gain_roll'].result() >= 2 + 5
    assert ally.hp() == min(ally.max_hp(), before + result['hp_gain_roll'].result())
    assert result['temp_hp_roll'].result() >= 2 + 5
    assert ally.temp_hp() == result['temp_hp_roll'].result()
    assert pc.item_count('elixir_of_healing') == 0


def test_boldness_and_flight_buffs(setup):
    session, battle, battle_map, pc, _ally = setup
    from natural20.effects.consumable_buff_effect import attack_roll_dice
    from natural20.utils.class_mechanics import give_crafted_item
    give_crafted_item(pc, 'elixir_of_boldness')
    give_crafted_item(pc, 'elixir_of_flight')
    _drink(session, battle, battle_map, pc, 'elixir_of_boldness', pc)
    assert len(attack_roll_dice(pc, battle)) == 1
    assert pc.has_effect('save_modifier')
    pc.reset_turn(battle)
    _drink(session, battle, battle_map, pc, 'elixir_of_flight', pc)
    assert pc.fly_speed() == 10 and pc.is_flying()
    session.game_time += 601
    assert pc.fly_speed() == 0
    assert not pc.is_flying()


def test_alchemical_savant_needs_supplies(setup):
    session, battle, _map, pc, ally = setup
    spell = session.load_spell('firebolt')

    def items():
        return [{'type': 'spell_damage', 'source': pc, 'target': ally, 'damage_type': 'fire',
                 'damage': DieRoll.roll('2d10'), 'damage_roll': None, 'spell': spell}]

    boosted = apply_spell_roll_bonuses(pc, spell, items(), battle)
    assert boosted[0]['roll_bonuses'] == ['alchemical_savant']
    pc.inventory.pop('alchemists_supplies')
    plain = apply_spell_roll_bonuses(pc, spell, items(), battle)
    assert 'roll_bonuses' not in plain[0]


def test_spell_storing_item_casts_without_a_slot(setup):
    session, battle, battle_map, pc, ally = setup
    pc.properties['spell_storing_item'] = {'spell': 'cure_wounds', 'item': 'rod'}
    assert free_cast_pool_for(pc, 'cure_wounds') == 'spell_storing_item'
    ally.take_damage(10, battle=battle)
    action = SpellAction.build(session, pc)['next'](['cure_wounds', 1])['next'](ally)
    assert action.free_cast_pool == 'spell_storing_item'
    action.resolve(session, battle_map, {'battle': battle})
    battle.commit(action)
    assert pc.spell_slots['artificer'][1] == 4
    assert pc.resource_value('spell_storing_item') == 9


def test_flash_of_genius_turns_a_failed_save(setup):
    _session, battle, _map, pc, ally = setup
    DieRoll.fudge(8)
    try:
        roll = ally.save_throw('dexterity', battle, {'dc': 14, 'is_magical': True})
    finally:
        DieRoll.unfudge(20)
    assert roll.result() >= 14
    assert pc.resource_value('flash_of_genius') == 4
    assert pc.total_reactions(battle) == 0


def test_flash_of_genius_skips_hopeless_saves(setup):
    _session, battle, _map, pc, ally = setup
    DieRoll.fudge(1)
    try:
        ally.save_throw('dexterity', battle, {'dc': 25})
    finally:
        DieRoll.unfudge(20)
    assert pc.resource_value('flash_of_genius') == 5


def test_infusion_raises_item_bonus(setup):
    session, _battle, _map, pc, _ally = setup
    base = pc.armor_class()
    pc.properties['infusions'] = [{'infusion': 'enhanced_defense', 'item': 'shield'}]
    assert pc.armor_class() == base + 2


def test_save_load_round_trip_keeps_pools_and_buffs(setup):
    session, battle, battle_map, pc, _ally = setup
    from natural20.utils.class_mechanics import give_crafted_item
    give_crafted_item(pc, 'elixir_of_resilience', 'experimental_elixir')
    _drink(session, battle, battle_map, pc, 'elixir_of_resilience', pc)
    pc.consume_resource('flash_of_genius')
    ac = pc.armor_class()
    dump = Serialization().serialize(session, battle, {'empty_map': battle_map})
    session2, _battle2, _maps2 = Serialization().deserialize(dump)
    pc2 = session2.entity_by_uid('tinker')
    assert pc2.resource_value('flash_of_genius') == 4
    assert pc2.armor_class() == ac
    assert pc2.properties['rest_granted_items']['experimental_elixir'] == ['elixir_of_resilience']

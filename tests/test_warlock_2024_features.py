"""SRD 5.2 warlock overlay, Archfey patron (PHB 2024 pack), item mechanics,
weapon alternate modes, attack penalties, the D&D Beyond feature-choice
import and generic autobuild choice handling."""
import json
import sys
from pathlib import Path

import pytest
import yaml

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.attack_penalties import apply_targeted_penalties, subtract_dice
from natural20.utils.class_mechanics import (
    AT_WILL_POOL,
    cantrip_rider_specs,
    devils_sight_range,
    free_cast_pool_for,
)
from natural20.utils.action_builder import autobuild
from tests.ranger_spell_helpers import make_campaign

ROOT = Path(__file__).resolve().parent.parent


def warlock_props(**extra):
    props = {
        'name': 'Warlock', 'entity_uid': 'warlock', 'race': 'human',
        'classes': {'warlock': 11}, 'level': 11, 'otherworldly_patron': 'archfey_patron',
        'max_hp': 70, 'hp': 70, 'hit_die': 'inherit',
        'ability': {'str': 8, 'dex': 14, 'con': 14, 'int': 10, 'wis': 10, 'cha': 20},
        'saving_throw_proficiencies': ['wis', 'cha'],
        'eldritch_invocations': ['agonizing_blast', 'repelling_blast', 'devils_sight', 'eldritch_mind',
                                 'fiendish_vigor', 'pact_of_the_chain'],
        'mystic_arcanum': {6: 'summon_fiend'},
        'cantrips': ['eldritch_blast'],
        'prepared_spells': ['misty_step', 'hex', 'false_life', 'find_familiar', 'contact_other_plane',
                            'summon_fiend'],
        'spell_slots': {'warlock': {5: 3}},
        'equipped': ['dagger', 'wand_of_the_war_mage_plus_one', 'periapt_of_proof_against_poison'],
        'inventory': [{'type': 'dagger', 'qty': 1}, {'type': 'wand_of_the_war_mage_plus_one', 'qty': 1},
                      {'type': 'periapt_of_proof_against_poison', 'qty': 1}],
        'token': ['W'], 'group': 'a',
    }
    props.update(extra)
    return props


@pytest.fixture
def campaign(tmp_path):
    return make_campaign(tmp_path, ruleset='5e-2024', packs=['players_handbook_2024', 'xanathars_guide'])


@pytest.fixture
def warlock(campaign):
    pc = PlayerCharacter(campaign, warlock_props())
    campaign.register_entity(pc)
    return pc


def test_2024_overlay_resources_and_free_casts(warlock):
    for pool in ('magical_cunning', 'contact_patron', 'mystic_arcanum_6', 'steps_of_the_fey'):
        assert warlock.has_resource(pool), pool
    assert free_cast_pool_for(warlock, 'summon_fiend') == 'mystic_arcanum_6'
    assert free_cast_pool_for(warlock, 'contact_other_plane') == 'contact_patron'
    assert free_cast_pool_for(warlock, 'misty_step') == 'steps_of_the_fey'
    assert free_cast_pool_for(warlock, 'false_life') == AT_WILL_POOL
    assert free_cast_pool_for(warlock, 'find_familiar') == AT_WILL_POOL
    assert free_cast_pool_for(warlock, 'mage_armor') is None


def test_mystic_arcanum_castable_without_level_six_slot(warlock):
    assert SpellAction.can_cast(warlock, None, 'summon_fiend')


def test_invocations_devils_sight_and_cantrip_riders(warlock):
    assert devils_sight_range(warlock) == 120
    rider_ids = {spec.get('feature') or spec.get('id') for _klass, spec in cantrip_rider_specs(warlock, 'eldritch_blast')}
    assert {'agonizing_blast', 'repelling_blast'} <= rider_ids


def test_archfey_beguiling_defenses_charm_immunity_at_level_ten(warlock):
    assert warlock.immune_to_condition('charmed')


def test_item_mechanics_wand_and_periapt(warlock):
    assert warlock.item_spell_attack_bonus() == 1
    assert warlock.immune_to_condition('poisoned')
    hp = warlock.hp()
    warlock.take_damage(7, damage_type='poison')
    assert warlock.hp() == hp


def test_subtract_dice_lowers_roll(campaign):
    roll = DieRoll.roll('10')
    lowered = subtract_dice(roll, ['1d4'])
    assert 6 <= lowered.result() <= 9


def test_targeted_penalty_from_blade_ward_effect(campaign, warlock):
    goblin = Npc(campaign, 'goblin', {'name': 'g'})

    class Ward:
        @staticmethod
        def targeted_attack_penalty(entity, opts=None):
            return '1d4'

    warlock.register_effect('targeted_attack_penalty', Ward, effect=Ward())
    roll = apply_targeted_penalties(DieRoll.roll('15'), goblin, warlock)
    assert 11 <= roll.result() <= 14


def test_autobuild_select_choice_passes_values(campaign, warlock):
    battle_map = Map(campaign, 'maps/field')
    battle = Battle(campaign, battle_map)
    goblin = Npc(campaign, 'goblin', {'name': 'g'})
    for entity, x, group in ((warlock, 2, 'a'), (goblin, 5, 'b')):
        battle_map.add(entity, x, 2, group)
        battle.add(entity, group, add_to_initiative=True)
    battle.start(combat_order=[warlock, goblin])
    warlock.reset_turn(battle)
    built = autobuild(campaign, SpellAction, warlock, battle, map=battle_map,
                      match={'select_spell': 'hex', 'select_choice': 'wis', 'select_target': goblin})
    built = [b for b in built or [] if b]
    assert built and built[0].spell_action.hexed_ability == 'wis'


def test_dragonlance_hoopak_alternate_mode_needs_ammo():
    root = ROOT / 'user_levels' / 'dragonlance'
    if not (root / 'items' / 'weapons.yml').is_file():
        pytest.skip('dragonlance campaign submodule not checked out')
    data = yaml.safe_load((root / 'items' / 'weapons.yml').read_text())
    assert data['hoopak']['alternate_modes'] == ['hoopak_sling']
    assert data['hoopak_sling']['type'] == 'ranged_attack'


def test_importer_extracts_invocations_and_mystic_arcanum(tmp_path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import beyond_importer as bi
    make_campaign(tmp_path, ruleset='5e-2024', packs=['players_handbook_2024'])
    importer = bi.BeyondImporter(campaign_root=str(tmp_path))
    payload = {
        'classes': [{
            'definition': {'name': 'Warlock'},
            'classFeatures': [
                {'definition': {'id': 1, 'name': 'Eldritch Invocations'}},
                {'definition': {'id': 2, 'name': 'Mystic Arcanum (Level 6 Spell)'}},
            ],
        }],
        'options': {'class': [
            {'componentId': 1, 'definition': {'id': 11, 'name': 'Agonizing Blast (Eldritch Blast)'}},
            {'componentId': 1, 'definition': {'id': 12, 'name': 'Pact of the Tome'}},
        ]},
        'spells': {'class': [
            {'componentId': 12, 'definition': {'name': 'Vicious Mockery'}},
            {'componentId': 2, 'definition': {'name': 'Summon Fiend'}},
        ]},
    }
    out = importer._extract_feature_choices(payload)
    assert out['eldritch_invocations'] == ['agonizing_blast', 'pact_of_the_tome']
    assert out['invocation_spells'] == {'agonizing_blast': 'eldritch_blast'}
    assert out['class_spells'] == {'warlock': ['vicious_mockery']}
    assert out['mystic_arcanum'] == {6: 'summon_fiend'}


def test_imported_dragonlance_warlock_loads():
    root = ROOT / 'user_levels' / 'dragonlance'
    sheet = root / 'characters' / 'chestnut_latchlifter.yml'
    if not sheet.is_file():
        pytest.skip('dragonlance campaign submodule not checked out')
    session = Session(root_path=str(root), event_manager=EventManager())
    pc = PlayerCharacter.load(session, 'characters/chestnut_latchlifter.yml')
    assert pc.level() == 11
    assert pc.armor_class() == 15
    assert pc.spell_attack_modifier_for(session.load_spell('eldritch_blast')) == 10
    assert pc.immune_to_condition('poisoned') and pc.immune_to_condition('charmed')
    assert free_cast_pool_for(pc, 'summon_fiend') == 'mystic_arcanum_6'
    assert free_cast_pool_for(pc, 'detect_evil_and_good') == 'high_sorcery_spell_1'
    assert free_cast_pool_for(pc, 'comprehend_languages') == 'high_sorcery_spell_2'
    assert pc.has_resource('taunt')
    for spell in json.loads(json.dumps(pc.properties['prepared_spells'])):
        session.load_spell(spell)

"""Zephyr Strike (Xanathar's pack): no opportunity attacks plus one empowered surge."""
from natural20.actions.attack_action import AttackAction
from natural20.actions.attack_surge_action import AttackSurgeAction
from natural20.die_roll import DieRoll
from natural20.spell.strike_surge_spell import StrikeSurgeSpell, ready_surge_spell
from natural20.utils.class_feature_registry import collect_class_feature_actions
from natural20.utils.movement import retrieve_opportunity_attacks
from tests.ranger_spell_helpers import Arena

PACK = 'xanathars_guide'


def _arena(tmp_path):
    return Arena(tmp_path, ruleset='5e-2024', packs=[PACK], spells=['zephyr_strike'])


def _surge(arena):
    action = AttackSurgeAction(arena.session, arena.caster)
    action.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(action)
    return action


def _shoot(arena, roll):
    attack = AttackAction(arena.session, arena.caster, 'attack')
    attack.target = arena.goblin
    attack.using = 'longbow'
    DieRoll.fudge(roll)
    try:
        arena.battle.execute_action(attack)
    finally:
        DieRoll.unfudge()
    return attack


def test_pack_definition(tmp_path):
    arena = _arena(tmp_path)
    details = arena.spell('zephyr_strike')
    assert details['spell_class'] == 'Natural20::StrikeSurge'
    assert details['no_opportunity_attacks'] is True
    assert details['attack_surge']['speed_bonus'] == 30


def test_movement_provokes_no_opportunity_attacks(tmp_path):
    arena = _arena(tmp_path)
    arena.map.move_to(arena.caster, 5, 3, arena.battle)
    path = [(5, 3), (4, 3), (3, 4)]
    assert retrieve_opportunity_attacks(arena.caster, path, arena.battle)
    arena.cast('zephyr_strike', 1)
    assert isinstance(arena.caster.concentration, StrikeSurgeSpell)
    assert retrieve_opportunity_attacks(arena.caster, path, arena.battle) == []


def test_surge_offered_once_per_casting(tmp_path):
    arena = _arena(tmp_path)
    assert not AttackSurgeAction.can(arena.caster, arena.battle)
    arena.cast('zephyr_strike', 1)
    arena.caster.reset_turn(arena.battle)
    offered = [a for a in collect_class_feature_actions(arena.session, arena.caster, arena.battle)
               if isinstance(a, AttackSurgeAction)]
    assert len(offered) == 1
    _surge(arena)
    assert ready_surge_spell(arena.caster) is None
    assert not AttackSurgeAction.can(arena.caster, arena.battle)


def test_surge_hit_adds_force_damage_and_speed(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('zephyr_strike', 1)
    arena.caster.reset_turn(arena.battle)
    movement_before = arena.battle.entity_state_for(arena.caster)['movement']
    _surge(arena)
    attack = _shoot(arena, roll=19)
    assert attack.result[0].get('advantage_mod', 0) >= 0
    force = [i for i in attack.result if i.get('damage_type') == 'force']
    assert force, 'surge hit should add extra force damage'
    assert arena.battle.entity_state_for(arena.caster)['movement'] == movement_before + 30


def test_surge_miss_still_grants_speed(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('zephyr_strike', 1)
    arena.caster.reset_turn(arena.battle)
    movement_before = arena.battle.entity_state_for(arena.caster)['movement']
    _surge(arena)
    attack = _shoot(arena, roll=1)
    assert not [i for i in attack.result if i.get('damage_type') == 'force']
    assert arena.battle.entity_state_for(arena.caster)['movement'] == movement_before + 30


def test_save_load_round_trip(tmp_path):
    arena = _arena(tmp_path)
    arena.cast('zephyr_strike', 1)
    session2, battle2, _maps2 = arena.round_trip()
    caster2 = session2.entity_by_uid(arena.caster.entity_uid)
    assert caster2.has_effect('no_opportunity_attacks')
    assert ready_surge_spell(caster2) is not None
    caster2.dismiss_effect(caster2.concentration)
    assert not caster2.has_effect('no_opportunity_attacks')

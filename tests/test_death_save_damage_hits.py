"""Death-save failures from damage hits on a downed (0 HP) PC (PHB 2014/2024).

* A melee hit on a creature at 0 HP within 5 ft is an automatic critical hit.
* A critical hit that doesn't kill the creature inflicts TWO death save failures.
* Any other hit while at 0 HP inflicts one failure; misses none.
* Damage >= the creature's hit point maximum kills instantly.
"""

import random

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.session import Session


def _setup(seed, foe_dx=1):
    random.seed(seed)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'entryway')
    battle = Battle(session, battle_map)
    pc = battle_map.entity_by_uid('gomerin')
    px, py = list(battle_map.entities[pc])
    battle.add(pc, 'a')
    goblin = session.npc('goblin')
    battle.add(goblin, 'b', position=[px + foe_dx, py])
    battle.start()
    pc.reset_turn(battle)
    goblin.reset_turn(battle)

    # Toughen the PC so a goblin crit stays under the massive-damage threshold.
    pc.properties['max_hp'] = 60
    pc.attributes['hp'] = 60
    pc.take_damage(60, battle=battle, session=session, damage_type='slashing',
                   item={'source': goblin})
    pc.armor_class = lambda: 1
    return session, battle_map, battle, pc, goblin


def _melee_action(session, goblin, pc):
    attack = AttackAction(session, goblin, 'attack')
    attack.target = pc
    attack.npc_action = next(a for a in goblin.npc_actions
                             if a.get('type') == 'melee_attack')
    return attack


def _hit(battle, session, goblin, pc, nat):
    attack = _melee_action(session, goblin, pc)
    DieRoll.fudge(nat)
    battle.execute_action(attack)
    DieRoll.unfudge()
    return attack


def test_drop_to_zero_itself_costs_no_failure():
    _session, _map, _battle, pc, _goblin = _setup(11)
    assert pc.hp() == 0 and pc.unconscious()
    assert pc.death_fails == 0 and not pc.dead()


def test_melee_hit_within_five_feet_auto_crits_and_costs_two_failures():
    session, _map, battle, pc, goblin = _setup(21)
    attack = _hit(battle, session, goblin, pc, 19)
    assert attack.hit_result.get('critical') is True
    assert pc.death_fails == 2
    assert not pc.dead()


def test_second_melee_hit_reaches_three_failures_and_kills():
    session, _map, battle, pc, goblin = _setup(21)
    _hit(battle, session, goblin, pc, 19)
    # nat 3 still auto-crits within 5 ft; 2+2 failures reaches three.
    _hit(battle, session, goblin, pc, 3)
    assert pc.dead()
    assert (pc.attributes.get('death_info') or {}).get('cause') == 'damage_while_dying'


def test_miss_on_downed_creature_costs_no_failure():
    session, _map, battle, pc, goblin = _setup(12)
    pc.armor_class = lambda: 999
    _hit(battle, session, goblin, pc, 0)
    assert pc.death_fails == 0 and not pc.dead()


def test_ranged_hit_beyond_five_feet_costs_only_one_failure():
    session, battle_map, battle, pc, goblin = _setup(13, foe_dx=3)
    assert battle_map.distance(goblin, pc) * battle_map.feet_per_grid > 5
    attack = AttackAction(session, goblin, 'attack')
    attack.target = pc
    attack.npc_action = next(a for a in goblin.npc_actions if a.get('type') == 'ranged_attack')
    DieRoll.fudge(19)
    battle.execute_action(attack)
    DieRoll.unfudge()
    assert attack.hit_result.get('critical') is False
    assert pc.death_fails == 1
    assert not pc.dead()


def test_massive_damage_kills_instantly():
    session, _map, battle, pc, goblin = _setup(11)
    # A stock 10 HP PC crit-struck by a goblin takes damage >= its max HP.
    pc.properties['max_hp'] = 10
    pc.armor_class = lambda: 1
    _hit(battle, session, goblin, pc, 19)
    assert pc.dead()
    assert (pc.attributes.get('death_info') or {}).get('cause') == 'massive_damage'

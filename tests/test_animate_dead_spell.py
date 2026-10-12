import random
from types import SimpleNamespace

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.animate_dead_spell import AnimateDeadSpell
from natural20.utils.corpses import corpses_at
from natural20.utils.spell_loader import load_spell_class


def _setup():
    random.seed(4242)
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'battle_sim')
    caster = PlayerCharacter.load(session, 'high_elf_mage.yml')
    guard = session.npc('human_guard', {'name': 'Guard'})
    battle_map.add(caster, 2, 2, group='a')
    battle_map.add(guard, 3, 2, group='b')
    return session, battle_map, caster, guard


def _spell(session, caster):
    spell = AnimateDeadSpell(session, caster, 'animate_dead', session.load_spell('animate_dead'))
    return spell


def test_loader_resolves_dedicated_class():
    assert load_spell_class('AnimateDeadSpell') is AnimateDeadSpell


def test_requires_a_corpse_in_the_square():
    session, battle_map, caster, guard = _setup()
    spell = _spell(session, caster)
    assert not spell.validate(battle_map, [3, 2])
    guard.make_dead()
    assert corpses_at(battle_map, 3, 2, humanoid=True, sizes=('small', 'medium')) == [guard]
    assert spell.validate(battle_map, [3, 2])
    assert not spell.validate(battle_map, [2, 2])


def _raise(item, session):
    assert AnimateDeadSpell.apply(None, item, session) is None
    return item['raised']


def test_raises_zombie_under_casters_control():
    session, battle_map, caster, guard = _setup()
    guard.make_dead()
    spell = _spell(session, caster)
    items = spell.resolve(caster, None, SimpleNamespace(target=[3, 2], at_level=3), battle_map)
    raised = _raise(items[0], session)

    assert len(raised) == 1
    zombie = raised[0]
    assert zombie.npc_type == 'zombie'
    assert zombie.owner is caster
    assert zombie.properties['summoner_uid'] == caster.entity_uid
    assert guard not in battle_map.entities
    assert battle_map.entity_at(3, 2) is zombie
    assert zombie.group == caster.group


def test_commit_keeps_action_result_as_dicts():
    session, battle_map, caster, guard = _setup()
    guard.make_dead()
    battle = Battle(session, battle_map)
    battle.add(caster, 'a')
    action = SpellAction(session, caster, 'spell')
    action.result = _spell(session, caster).resolve(
        caster, battle, SimpleNamespace(target=[3, 2], at_level=3), battle_map)
    battle.commit(action)

    assert all(isinstance(item, dict) for item in action.result)
    assert battle_map.entity_at(3, 2).npc_type == 'zombie'


def test_bones_become_skeleton():
    session, battle_map, caster, guard = _setup()
    guard.properties['remains'] = 'bones'
    guard.make_dead()
    items = _spell(session, caster).resolve(caster, None, SimpleNamespace(target=[3, 2], at_level=3), battle_map)
    raised = _raise(items[0], session)
    assert raised[0].npc_type == 'skeleton'


def test_auto_targeting_only_offers_corpse_squares():
    from natural20.utils.action_builder import build_params

    session, battle_map, caster, guard = _setup()
    build_info = _spell(session, caster).build_map(SimpleNamespace(clone=lambda: SimpleNamespace()))
    assert build_params(session, caster, None, build_info, map=battle_map) in (None, [[]])

    guard.make_dead()
    assert build_params(session, caster, None, build_info, map=battle_map) == [[[3, 2]]]


def test_point_targeted_spell_action_serializes():
    session, _battle_map, caster, guard = _setup()
    action = SpellAction(session, caster, 'spell')
    action.target = [3, 2]
    assert action.to_dict()['target'] == [3, 2]
    action.target = [guard, (4, 5)]
    assert action.to_dict()['target'] == [guard.entity_uid, [4, 5]]


def test_one_minute_casting_time_is_blocked_in_combat():
    session, battle_map, _caster, guard = _setup()
    necromancer = session.npc('goblin', {'name': 'Necromancer'})
    necromancer.properties['spell_slots'] = {'3': 2}
    battle_map.add(necromancer, 5, 5, group='b')
    assert SpellAction.can_cast(necromancer, None, 'animate_dead')

    battle = Battle(session, battle_map)
    battle.add(necromancer, 'b', add_to_initiative=True)
    battle.add(guard, 'a', add_to_initiative=True)
    battle.start(combat_order=[necromancer, guard])
    assert not SpellAction.can_cast(necromancer, battle, 'animate_dead')


def _pc_corpse(session, battle_map):
    fallen = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    battle_map.add(fallen, 3, 3, group='a')
    fallen.make_dead()
    return fallen


def test_dead_player_character_can_be_animated_without_losing_the_pc():
    session, battle_map, caster, _guard = _setup()
    fallen = _pc_corpse(session, battle_map)
    spell = _spell(session, caster)
    assert spell.validate(battle_map, [3, 3])

    items = spell.resolve(caster, None, SimpleNamespace(target=[3, 3], at_level=3), battle_map)
    zombie = _raise(items[0], session)[0]

    assert battle_map.entity_at(3, 3) is zombie
    assert fallen in battle_map.entities
    assert session.entity_by_uid(fallen.entity_uid) is fallen
    assert fallen.attributes['body_moved_to'] == zombie.entity_uid
    assert zombie.properties['animated_remains_uid'] == fallen.entity_uid
    assert corpses_at(battle_map, 3, 3, humanoid=True) == []

    # Webapp respawn paths call place(); the body must stay tokenless.
    battle_map.place((3, 3), fallen)
    assert battle_map.entity_at(3, 3) is zombie


def test_destroying_the_zombie_returns_the_pc_corpse():
    session, battle_map, caster, _guard = _setup()
    session.register_map('battle_sim', battle_map)
    fallen = _pc_corpse(session, battle_map)
    items = _spell(session, caster).resolve(caster, None, SimpleNamespace(target=[3, 3], at_level=3), battle_map)
    zombie = _raise(items[0], session)[0]
    battle_map.move_to(zombie, 4, 4)
    assert battle_map.entity_at(3, 3) is None

    zombie.take_damage(zombie.max_hp() * 3, damage_type='radiant')
    assert zombie.dead()
    assert battle_map.entity_at(4, 4) is fallen
    assert list(battle_map.position_of(fallen)) == [4, 4]
    assert 'body_moved_to' not in fallen.attributes
    assert fallen.dead()
    assert corpses_at(battle_map, 4, 4, humanoid=True) == [fallen]


def test_map_remove_keeps_other_occupants_token():
    session, battle_map, _caster, guard = _setup()
    other = session.npc('human_guard', {'name': 'Other'})
    battle_map.add(other, 5, 5, group='b')
    battle_map.entities[guard] = [5, 5]
    battle_map.remove(guard)
    assert battle_map.entity_at(5, 5) is other

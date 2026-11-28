"""Minotaur Charge: YAML-driven charge riders on NPC attacks
(``natural20.utils.monster_traits.charge_config``) — extra gore damage plus a
Strength save or the target is pushed and knocked prone, gated on the
movement the creature actually made this turn."""
from natural20.actions.attack_action import AttackAction
from natural20.actions.move_action import MoveAction
from natural20.npc import Npc
from natural20.utils.monster_traits import charge_config, charge_met
from tests.ranger_spell_helpers import Arena, forced_save


def _minotaur(tmp_path):
    arena = Arena(tmp_path, caster='ranger')
    minotaur = Npc(arena.session, 'minotaur', {})
    arena.session.register_entity(minotaur)
    arena.map.add(minotaur, 10, 2, 'b')
    arena.battle.add(minotaur, 'b', add_to_initiative=True)
    minotaur.reset_turn(arena.battle)
    return arena, minotaur


def test_stat_block_yaml():
    from natural20.yaml_loader import load_yaml, templates_root
    details = load_yaml(templates_root() / 'npcs' / 'minotaur.yml')
    assert details['max_hp'] == 76 and details['default_ac'] == 14
    assert details['speed'] == 40 and details['reckless'] is True
    gore = next(a for a in details['actions'] if a['name'] == 'Gore')
    charge = charge_config(gore)
    assert charge['distance_ft'] == 10
    assert charge['damage_die'] == '2d8'
    assert charge['save_dc'] == 'strength:14'
    assert charge['push_ft'] == 10 and charge['prone'] is True


def test_move_tracking_and_charge_met(tmp_path):
    arena, minotaur = _minotaur(tmp_path)
    state = arena.battle.entity_state_for(minotaur)
    assert state['movement_used_ft'] == 0
    move = MoveAction(arena.session, minotaur, 'move',
                      {'move_path': [[10, 2], [9, 2], [8, 2], [7, 2]]})
    move.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(move)
    state = arena.battle.entity_state_for(minotaur)
    assert state['movement_used_ft'] == 15
    cfg = charge_config(next(a for a in minotaur.npc_actions if a['name'] == 'Gore'))
    assert charge_met(arena.battle, minotaur, arena.goblin, cfg)


def test_no_charge_without_movement(tmp_path):
    arena, minotaur = _minotaur(tmp_path)
    arena.map.move_to(minotaur, 7, 2, arena.battle)  # teleport-style: no tracking
    cfg = charge_config(next(a for a in minotaur.npc_actions if a['name'] == 'Gore'))
    assert not charge_met(arena.battle, minotaur, arena.goblin, cfg)


def test_charge_rider_damage_save_push_prone(tmp_path):
    arena, minotaur = _minotaur(tmp_path)
    move = MoveAction(arena.session, minotaur, 'move',
                      {'move_path': [[10, 2], [9, 2], [8, 2], [7, 2]]})
    move.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(move)
    gore = next(a for a in minotaur.npc_actions if a['name'] == 'Gore')

    action = AttackAction(arena.session, minotaur, 'attack', {'npc_action': gore})
    action.hit_result = {}
    riders = action._on_hit_riders(arena.battle, arena.goblin, gore, 'Gore', False)
    damage = [r for r in riders if r['type'] == 'additional_damage']
    charge = [r for r in riders if r['type'] == 'charge_rider']
    assert len(damage) == 1 and 'd8' in str(damage[0]['damage'])
    assert damage[0]['damage_type'] == 'piercing'
    assert len(charge) == 1

    arena.goblin.attributes['hp'] = 60
    AttackAction.apply(arena.battle, damage[0], arena.session)
    assert arena.goblin.hp() < 60  # the 2d8 charge damage landed
    with forced_save(arena.goblin, 1):
        AttackAction.apply(arena.battle, charge[0], arena.session)
    assert 'prone' in arena.goblin.statuses
    # pushed away from the minotaur (at 7,2): goblin started at (6,2)
    gx, gy = arena.map.position_of(arena.goblin)
    assert gx <= 4 and gy == 2
    # the save/push/prone line deals no damage itself
    assert arena.goblin.hp() >= 49


def test_charge_rider_save_success(tmp_path):
    arena, minotaur = _minotaur(tmp_path)
    move = MoveAction(arena.session, minotaur, 'move',
                      {'move_path': [[10, 2], [9, 2], [8, 2], [7, 2]]})
    move.resolve(arena.session, arena.map, {'battle': arena.battle})
    arena.battle.commit(move)
    gore = next(a for a in minotaur.npc_actions if a['name'] == 'Gore')
    action = AttackAction(arena.session, minotaur, 'attack', {'npc_action': gore})
    action.hit_result = {}
    riders = action._on_hit_riders(arena.battle, arena.goblin, gore, 'Gore', False)
    charge = [r for r in riders if r['type'] == 'charge_rider'][0]
    position = arena.map.position_of(arena.goblin)
    with forced_save(arena.goblin, 30):
        AttackAction.apply(arena.battle, charge, arena.session)
    assert 'prone' not in arena.goblin.statuses
    assert arena.map.position_of(arena.goblin) == position

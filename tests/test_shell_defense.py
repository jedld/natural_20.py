"""Tests for Tortle Shell Defense racial trait."""

from natural20.actions.shell_defense_action import ShellDefenseAction, EmergenceAction
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.session import Session


def _load_oogway():
    session = Session(root_path='user_levels/death_house')
    return session, PlayerCharacter.load(session, 'characters/Oogway.yml')


def test_tortle_has_shell_defense_feature():
    _session, pc = _load_oogway()
    assert pc.class_feature('shell_defense')
    assert pc.class_feature('natural_armor')


def test_shell_defense_available_out_of_combat():
    session, pc = _load_oogway()
    assert ShellDefenseAction.can(pc, None) is True
    actions = pc.available_actions(session, None, auto_target=False)
    assert any(isinstance(a, ShellDefenseAction) for a in actions)


def test_shell_defense_enter_and_emerge():
    session, pc = _load_oogway()
    battle_map = next(iter(session.maps.values()))
    battle = Battle(session, battle_map)
    battle.add(pc, group='a')
    battle.start()
    pc.reset_turn(battle)

    assert ShellDefenseAction.can(pc, battle) is True
    action = ShellDefenseAction(session, pc, 'shell_defense')
    action.resolve(session, battle_map, {'battle': battle})
    for item in action.result:
        ShellDefenseAction.apply(battle, item, session=session)

    assert pc._in_shell is True
    assert pc.prone() is True
    assert pc.speed() == 0
    assert pc.has_reaction(battle) is False
    assert pc.armor_class() >= 21  # 17 natural + 4 shell (+ shield if equipped)
    assert EmergenceAction.can(pc, battle) is True
    assert ShellDefenseAction.can(pc, battle) is False

    # MotM: only emerge is available while in shell
    actions = pc.available_actions(session, battle, auto_target=False)
    assert actions
    assert all(isinstance(a, EmergenceAction) for a in actions)

    emerge = EmergenceAction(session, pc, 'shell_emerge')
    emerge.resolve(session, battle_map, {'battle': battle})
    for item in emerge.result:
        EmergenceAction.apply(battle, item, session=session)

    assert pc._in_shell is False
    assert pc.prone() is False
    assert pc.speed() > 0


def test_zero_speed_blocks_move_out_of_combat():
    from natural20.actions.move_action import MoveAction

    session, pc = _load_oogway()
    assert MoveAction.can(pc, None) is True

    action = ShellDefenseAction(session, pc, 'shell_defense')
    action.resolve(session, None, {'battle': None})
    for item in action.result:
        ShellDefenseAction.apply(None, item, session=session)

    assert pc.speed() == 0
    assert MoveAction.can(pc, None) is False
    assert not any(
        isinstance(a, MoveAction)
        for a in pc.available_actions(session, None, auto_target=False)
    )


def test_shell_defense_save_modifiers():
    _session, pc = _load_oogway()
    pc._in_shell = True
    save = pc.save_throw('strength')
    assert getattr(save, 'advantage', False) is True

    dex = pc.save_throw('dexterity')
    assert getattr(dex, 'disadvantage', False) is True

"""5e "Unseen Attackers and Targets": guessing squares, hearing, blind attacks."""
from unittest.mock import patch

import pytest

from natural20.actions.attack_action import AttackAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import unseen_targets


@pytest.fixture
def setup():
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
    session.maps['test'] = battle_map
    battle = Battle(session, battle_map)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin', {"name": "Gruk"})
    battle.add(fighter, 'a', position=(1, 1), token='F')
    battle.add(goblin, 'b', position=(2, 1), token='g')
    for e in (fighter, goblin):
        e.reset_turn(battle)
    battle.start()
    battle.set_current_turn(fighter)
    goblin.statuses.append('invisible')
    return session, battle, battle_map, fighter, goblin


def _melee_attack(session, fighter):
    for item in fighter.properties.get('equipped', []):
        weapon = session.load_weapon(item)
        if weapon and weapon.get('type') == 'melee_attack':
            action = AttackAction(session, fighter, 'attack')
            action.using = item
            return action
    action = AttackAction(session, fighter, 'attack')
    action.using = 'unarmed_attack'
    return action


def _record_events(session):
    events = []
    original = session.event_manager.received_event

    def record(event):
        events.append(event)
        return original(event)
    return events, patch.object(session.event_manager, 'received_event', side_effect=record)


def test_invisible_unhidden_creature_is_heard(setup):
    session, battle, battle_map, fighter, goblin = setup
    assert not battle.can_see(fighter, goblin)
    sensed = unseen_targets.sensed_creatures(battle, fighter)
    assert [(s['uid'], s['pos'], s['kind']) for s in sensed] == [
        (goblin.entity_uid, (2, 1), unseen_targets.KIND_HEARD)]


def test_hidden_creature_only_leaves_last_known_position(setup):
    session, battle, battle_map, fighter, goblin = setup
    unseen_targets.sensed_creatures(battle, fighter)
    goblin.do_hide(30)
    sensed = unseen_targets.sensed_creatures(battle, fighter)
    assert [s['kind'] for s in sensed] == [unseen_targets.KIND_LAST_KNOWN]
    battle.round += 5
    assert unseen_targets.sensed_creatures(battle, fighter) == []


def test_markers_do_not_name_the_creature(setup):
    session, battle, battle_map, fighter, goblin = setup
    markers = unseen_targets.markers_for(battle, [fighter])
    assert set(markers) == {(2, 1)}
    assert 'Gruk' not in str(markers) and goblin.entity_uid not in str(markers)


def test_renderer_attaches_marker_without_revealing_the_token(setup):
    from natural20.web.json_renderer import JsonRenderer
    session, battle, battle_map, fighter, goblin = setup
    tiles = {(t['x'], t['y']): t
             for row in JsonRenderer(battle_map, battle).render(entity_pov=fighter) for t in row}
    marked = tiles[(2, 1)]
    assert marked['unseen_presence']['kind'] == unseen_targets.KIND_HEARD
    assert marked.get('id') != goblin.entity_uid
    assert not any('unseen_presence' in t for pos, t in tiles.items() if pos != (2, 1))


def test_blind_attack_on_occupied_square_has_disadvantage(setup):
    session, battle, battle_map, fighter, goblin = setup
    action = _melee_attack(session, fighter)
    action.target_square = (2, 1)
    with patch.object(Battle, 'can_see', lambda self, a, b, *x, **k: not (a is fighter and b is goblin)):
        action.resolve(session, battle_map, {'battle': battle})
    assert action.blind_attack
    assert action.advantage_mod < 0
    kinds = {item['type'] for item in action.result}
    assert kinds & {'damage', 'miss'}
    miss = next((i for i in action.result if i['type'] == 'miss'), None)
    if miss is not None:
        assert miss['blind_square'] == (2, 1)
        assert action.target is None, 'a miss must not reveal the occupant'
    else:
        assert action.target is goblin


def test_blind_miss_logs_the_same_for_empty_and_occupied_squares(setup):
    session, battle, battle_map, fighter, goblin = setup
    empty = _melee_attack(session, fighter)
    empty.target_square = (2, 2)
    empty.resolve(session, battle_map, {'battle': battle})
    assert [i['type'] for i in empty.result] == ['blind_miss']

    events, patcher = _record_events(session)
    with patcher:
        battle.commit(empty)
    blind = [e for e in events if e.get('event') == 'blind_miss']
    assert len(blind) == 1 and blind[0]['square'] == [2, 2]
    assert 'target' not in blind[0]
    assert not any(e.get('event') == 'miss' for e in events)
    assert battle.entity_state_for(fighter)['action'] == 0

    occupied = _melee_attack(session, fighter)
    occupied.target_square = (2, 1)
    occupied.attack_roll = None
    with patch.object(AttackAction, '_resolve_hit', autospec=True,
                      side_effect=lambda self, battle, target, *a, **k: self.result.append({
                          'type': 'miss', 'target': target, 'source': self.source, 'battle': battle,
                          'attack_name': 'x', 'thrown': False, 'advantage_mod': -1,
                          'adv_info': [[], []], 'as_reaction': False, 'as_legendary_action': False,
                          'attack_roll': self.attack_roll, 'weapon': self.using,
                          'second_hand': False, 'npc_action': None, 'multiattack_clear': None,
                      }) or self):
        occupied.resolve(session, battle_map, {'battle': battle})
    events, patcher = _record_events(session)
    fighter.reset_turn(battle)
    with patcher:
        battle.commit(occupied)
    assert [e['event'] for e in events if e.get('event') in ('miss', 'blind_miss')] == ['blind_miss']


def test_blind_attack_issue_rules(setup):
    session, battle, battle_map, fighter, goblin = setup
    action = _melee_attack(session, fighter)
    assert unseen_targets.blind_attack_issue(battle, fighter, action, (2, 1)) is None
    assert unseen_targets.blind_attack_issue(battle, fighter, action, (2, 2)) is None
    assert unseen_targets.blind_attack_issue(battle, fighter, action, (1, 1)) == 'validation.unseen.self'
    assert unseen_targets.blind_attack_issue(battle, fighter, action, (9, 9)) in (
        'validation.unseen.out_of_range', 'validation.unseen.out_of_bounds', 'validation.unseen.wall')


def test_attacking_reveals_location_to_observers(setup):
    session, battle, battle_map, fighter, goblin = setup
    goblin.do_hide(30)
    assert unseen_targets.sensed_creatures(battle, fighter) == []
    unseen_targets.note_noise(battle, goblin)
    sensed = unseen_targets.sensed_creatures(battle, fighter)
    assert [(s['pos'], s['kind']) for s in sensed] == [((2, 1), unseen_targets.KIND_LAST_KNOWN)]


def test_ai_gets_blind_attack_options(setup):
    session, battle, battle_map, fighter, goblin = setup
    attacks = [a for a in fighter.available_actions(session, battle)
               if isinstance(a, AttackAction)]
    blind = [a for a in attacks if a.target is None and a.target_square == (2, 1)]
    assert blind, 'sensed square offered to AI controllers'
    assert not any(a.target is goblin for a in attacks)
    assert all(0 < a.ai_value(battle) for a in blind)
    assert 'unseen square [2, 1]' in str(blind[0])


def test_jev_offers_blind_attack_leaf(setup):
    from natural20.utils.jev_decision import JevActionPlanner
    session, battle, battle_map, fighter, goblin = setup
    planner = JevActionPlanner(provider=None)
    planner._battle, planner._entity, planner._session = battle, fighter, session
    planner._map = battle_map
    planner._names = planner._display_names(battle, fighter)
    leaves = planner._collect_leaves(fighter.available_actions(session, battle))
    blind = [(a, d) for _, a, d in leaves if getattr(a, 'target_square', None) == (2, 1)]
    assert blind, [d for _, _, d in leaves]
    action, desc = blind[0]
    assert action.target is None
    assert 'unseen creature at square [2, 1]' in desc and 'Gruk' not in desc
    auto = planner._collect_leaves(None)
    assert any(getattr(a, 'target_square', None) == (2, 1) for _, a, _ in auto)


def test_invisible_ally_is_not_a_blind_attack_option(setup):
    session, battle, battle_map, fighter, goblin = setup
    with patch.object(Battle, 'allies', lambda self, a, b: True):
        attacks = [a for a in fighter.available_actions(session, battle)
                   if isinstance(a, AttackAction) and a.target_square is not None]
        assert attacks == []
        assert unseen_targets.markers_for(battle, [fighter]) == {}


def test_blind_attack_serialization_roundtrip(setup):
    session, battle, battle_map, fighter, goblin = setup
    action = _melee_attack(session, fighter)
    action.target_square = (2, 1)
    restored = AttackAction.from_dict(action.to_dict())
    assert restored.target_square == (2, 1)
    assert action.clone().target_square == (2, 1)


def test_feature_switch(setup):
    session, battle, battle_map, fighter, goblin = setup
    session.game_properties = {**(getattr(session, 'game_properties', None) or {}),
                               'unseen_targets': False}
    assert unseen_targets.sensed_creatures(battle, fighter) == []
    action = _melee_attack(session, fighter)
    assert unseen_targets.blind_attack_issue(battle, fighter, action, (2, 1)) == 'validation.unseen.disabled'

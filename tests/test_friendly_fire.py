"""AI combatants must not aim harmful actions at their own side."""
from unittest.mock import MagicMock, patch

import pytest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils import friendly_fire
from natural20.utils.jev_decision import JevActionPlanner, _spell_name


@pytest.fixture
def setup():
    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'tests/fixtures/battle_sim.yml')
    session.maps['test'] = battle_map
    battle = Battle(session, battle_map)
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    goblin = session.npc('goblin', {"name": "Gruk"})
    battle.add(mage, 'a', position=(1, 1), token='M')
    battle.add(fighter, 'a', position=(2, 1), token='F')
    battle.add(goblin, 'b', position=(5, 5), token='g')
    for e in (mage, fighter, goblin):
        e.reset_turn(battle)
    battle.start()
    battle.set_current_turn(mage)
    fighter.attributes['hp'] = 0
    fighter.statuses.append('unconscious')
    return session, battle, mage, fighter, goblin


def _leaves(session, battle, mage):
    planner = JevActionPlanner(provider=None)
    planner._battle, planner._entity, planner._session = battle, mage, session
    planner._map = battle.map_for(mage)
    planner._names = planner._display_names(battle, mage)
    return planner._collect_leaves(mage.available_actions(session, battle))


def _targets(action):
    t = getattr(action, 'target', None)
    return list(t) if isinstance(t, (list, tuple)) else [t]


def _hostile_on(leaves, entity):
    return [d for _, a, d in leaves
            if any(t is entity for t in _targets(a)) and friendly_fire.is_harmful(a)]


def test_unseen_enemy_leaves_no_magic_missile_on_downed_ally(setup):
    session, battle, mage, fighter, goblin = setup
    real = battle.can_see
    with patch.object(Battle, 'can_see',
                      lambda self, a, t, *x, **k: False if t is goblin else real(a, t, *x, **k)):
        leaves = _leaves(session, battle, mage)
    assert _hostile_on(leaves, fighter) == []
    assert not any('Magic Missile' in d or 'magic_missile' in d for _, _, d in leaves)
    assert any(_spell_name(a) == 'Mage Armor' and any(t is fighter for t in _targets(a))
               for _, a, _ in leaves), 'beneficial spells on allies stay available'


def test_visible_enemy_is_still_a_target(setup):
    session, battle, mage, fighter, goblin = setup
    leaves = _leaves(session, battle, mage)
    assert _hostile_on(leaves, fighter) == []
    assert _hostile_on(leaves, goblin), 'Magic Missile on the goblin remains'


def test_harm_classification(setup):
    session, battle, mage, fighter, goblin = setup
    by_spell = {}
    for action in mage.available_actions(session, battle):
        name = _spell_name(action)
        if name:
            by_spell[name] = action
    assert friendly_fire.is_harmful(by_spell['Magic Missile'])
    assert not friendly_fire.is_harmful(by_spell['Mage Armor'])
    assert friendly_fire._spell_is_harmful(session.load_spell('magic_missile'))
    assert not friendly_fire._spell_is_harmful(session.load_spell('bless'))
    assert not friendly_fire._spell_is_harmful({'damage_type': 'fire', 'hostile': False})
    assert friendly_fire._spell_is_harmful({'hostile': True})
    scroll = MagicMock(properties={'spell': 'magic_missile'})
    assert friendly_fire._item_is_harmful(session, scroll)
    assert not friendly_fire._item_is_harmful(session, MagicMock(properties={'spell': 'bless'}))


def test_jev_does_not_step_back_to_squares_visited_this_turn(setup):
    from natural20.actions.move_action import MoveAction
    session, battle, mage, fighter, goblin = setup

    def move_ends():
        planner = JevActionPlanner(provider=None)
        planner._battle, planner._entity, planner._session = battle, mage, session
        planner._map = battle.map_for(mage)
        planner._names = planner._display_names(battle, mage)
        return {tuple(a.move_path[-1]) for _, a, _ in planner._collect_leaves(None)
                if isinstance(a, MoveAction)}

    ends = move_ends()
    if not ends:
        pytest.skip('fixture offers no strategic move leaves')
    dest = sorted(ends)[0]
    battle.entity_state_for(mage)['positions_entered'] = {dest: 1}
    assert dest not in move_ends()


def test_llm_controller_drops_friendly_fire(setup):
    from natural20.llm_controller import LlmMcpController
    session, battle, mage, fighter, goblin = setup
    mm = next(a for a in mage.available_actions(session, battle) if _spell_name(a) == 'Magic Missile')
    mm.target = [fighter, fighter, fighter]
    ctrl = LlmMcpController(session, defer_provider=True)
    with patch.object(LlmMcpController, '_ask_llm_for_choice', return_value=0):
        assert ctrl.select_action(battle, mage, [mm]) is None

"""Tests for the JEV (TypeSafe "System One") recursive NPC battle AI.

Behavior under test (see natural20/utils/jev_decision.py):

* The action builder generates the possible choices for an entity based on
  its current state.
* The Jev model first recommends which *type* of action to take (attack,
  spell, move, help, dodge, ...) and then recursively formulates the full
  action tree:
      attack -> weapon -> target
      spell  -> spell name (and level) -> target
* Movement has special handling:
      move -> entity (melee range) | defensive square | hide | offensive square
* Any provider failure falls back to the generic heuristic controller.
"""
import random

import pytest

from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.action import Action
from natural20.actions.attack_action import AttackAction
from natural20.actions.move_action import MoveAction
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.help_action import HelpAction
from natural20.utils.jev_decision import jev_select_action

try:
    from webapp.llm_handler import JevProvider
except Exception:  # pragma: no cover - webapp optional in engine tests
    JevProvider = None

from natural20.llm_controller import LlmMcpController


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def build_battle(fighter_pos=None, npc_pos=None):
    """A 2-entity battle on the battle_sim fixture map with the NPC on its turn.

    The fighter defaults to the square adjacent to the goblin so that melee
    weapons (5 ft range) have a legal target and the attack subtree is
    materializable by the action builder.
    """
    random.seed(7000)  # deterministic rolls
    event_manager = EventManager()
    session = Session_for_test(event_manager)
    m = Map(session, 'battle_sim')
    battle = Battle(session, m)
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    npc = session.npc('goblin')
    battle.add(fighter, 'a', position=fighter_pos or [2, 5], token='G')
    battle.add(npc, 'b', position=npc_pos or [1, 5], token='g')
    battle.start()
    battle.set_current_turn(npc)
    npc.reset_turn(battle)
    fighter.reset_turn(battle)
    return session, battle, m, fighter, npc


def Session_for_test(event_manager):
    from natural20.session import Session
    return Session(root_path='tests/fixtures', event_manager=event_manager)


class FakeJev:
    """Scripted stand-in for JevProvider.decide_action.

    ``script`` entries are applied in order:
      - int: choose ``int % len(options)``
      - str: choose the index of the option *containing* the string
      - Exception: raise it (simulates a provider failure)
      - None: return None (provider unavailable at that step)
    """

    is_available = True

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def decide_action(self, state, options):
        self.calls.append(list(options))
        if not self.script:
            return None
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if item is None:
            return None
        if isinstance(item, str):
            for i, opt in enumerate(options):
                if item in opt:
                    return {'index': i, 'choice': opt}
            # no match: pick last so the test fails loudly via assertions
            return {'index': len(options) - 1, 'choice': options[-1]}
        idx = int(item) % len(options)
        return {'index': idx, 'choice': options[idx]}

    def decide_bool(self, state, instructions):
        # not used by the planner; must not break it
        return {'noul': 0.9, 'confidence': 0.9}

    @property
    def n_calls(self):
        return len(self.calls)


# --------------------------------------------------------------------------- #
# Action-type level: the model recommends which kind of action
# --------------------------------------------------------------------------- #

class TestActionTypeRecommendation:
    def test_attack_is_recommended_and_recursed(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['attack', 0, 0])
        action = jev_select_action(prov, battle, npc)

        assert isinstance(action, AttackAction)
        # Recursion: type -> weapon -> target
        assert len(prov.calls) == 3
        type_options = prov.calls[0]
        assert any(o.startswith('attack') for o in type_options)
        weapon_options = prov.calls[1]
        assert all(isinstance(o, str) and o for o in weapon_options)
        target_options = prov.calls[2]
        assert 'Gomerin' in ' '.join(target_options)
        # The final action is fully specified: weapon + target
        assert action.target is fighter
        weapon_name = action.using or (action.npc_action or {}).get('name')
        assert weapon_name in weapon_options

    def test_move_type_is_offered_with_special_intent_subtree(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['move', 'melee', 0])
        action = jev_select_action(prov, battle, npc)

        assert isinstance(action, MoveAction)
        # Level 2 must be the movement *intent* menu (special handling):
        # a small set of strategic intents, NOT the raw neighbour-square
        # enumeration. Each intent label is one of the four strategic
        # categories (melee / defensive / hide / offensive); only the
        # ones with currently-legal options are offered (an open map with
        # no cover offers no defensive/hide intents, which is correct).
        intent_options = prov.calls[1]
        assert intent_options
        assert all(
            any(k in o for k in ('melee', 'defensive', 'hide', 'offensive'))
            for o in intent_options
        )
        # the fighter is adjacent, so a melee-engagement intent must exist
        assert any('melee' in o for o in intent_options)
        # Level 3 is the concrete destination squares for the chosen intent.
        assert len(prov.calls) >= 3
        # The chosen destination is a valid square on the map
        dest = action.move_path[-1]
        assert m.placeable(npc, dest[0], dest[1])

    def test_dodge_is_offered_when_actions_remain(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['dodge'])
        action = jev_select_action(prov, battle, npc)
        assert isinstance(action, DodgeAction)
        # Dodge has no parameters: exactly one decision (the type level)
        assert len(prov.calls) == 1

    def test_help_recurses_to_allies(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['help', 'Gomerin'])
        action = jev_select_action(prov, battle, npc)
        assert isinstance(action, HelpAction)
        assert action.target is fighter
        assert len(prov.calls) == 2
        assert 'Gomerin' in ' '.join(prov.calls[1])


# --------------------------------------------------------------------------- #
# Spell recursion: spell -> name/level -> target
# --------------------------------------------------------------------------- #

def build_battle_with_wizard():
    """Battle with the spellcasting Test Wizard NPC (polymorph, haste) on its
    turn, using the same fixture setup as tests/test_npc_spellcaster.py."""
    random.seed(7000)
    event_manager = EventManager()
    session = Session_for_test(event_manager)
    m = Map(session, 'battle_sim')
    session.register_map('test_map', m)
    battle = Battle(session, m)
    wizard = session.npc('test_wizard', {'name': 'Noke'})
    fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
    m.add(wizard, 1, 1)
    m.add(fighter, 1, 2)
    battle.add(wizard, 'b', add_to_initiative=True)
    battle.add(fighter, 'a', add_to_initiative=True)
    battle.start(combat_order=[wizard, fighter])
    wizard.reset_turn(battle)
    fighter.reset_turn(battle)
    battle.set_current_turn(wizard)
    return session, battle, m, fighter, wizard


class TestSpellRecursion:
    def test_spell_name_level_then_target(self):
        from natural20.actions.spell_action import SpellAction
        session, battle, m, fighter, wizard = build_battle_with_wizard()
        assert wizard.has_spells()

        prov = FakeJev(['spell', 0, 0])
        action = jev_select_action(prov, battle, wizard)

        assert isinstance(action, SpellAction)
        # Recursion: type -> spell (name + level) -> target (or AoE)
        assert len(prov.calls) >= 3
        type_options = prov.calls[0]
        assert any(o.startswith('cast a spell') for o in type_options)
        # Level 2 is the spell menu: each option names the spell and level
        spell_options = prov.calls[1]
        assert spell_options
        assert all('level' in o or 'cantrip' in o for o in spell_options)


# --------------------------------------------------------------------------- #
# Fallbacks and robustness
# --------------------------------------------------------------------------- #

class TestFallbacks:
    def test_provider_failure_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev([RuntimeError('jev exploded')])
        # The planner gives up cleanly (returns None); the *controller* is
        # what routes that to the heuristic fallback.
        assert jev_select_action(prov, battle, npc) is None
        assert prov.n_calls == 1  # failed on the first (type-level) call

    def test_provider_none_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        assert jev_select_action(None, battle, npc) is None

    def test_unavailable_provider_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev([0])
        prov.is_available = False
        assert jev_select_action(prov, battle, npc) is None
        assert prov.n_calls == 0

    def test_no_actions_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        # An explicit empty action list yields no plan
        action = jev_select_action(FakeJev([0]), battle, npc, available_actions=[])
        assert action is None

    def test_type_key_groups_by_class(self):
        # DodgeAction.build() sets action_type='attack' (latent builder bug)
        # but must still group under 'dodge' via class identity.
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        acts = [a for a in npc.available_actions(session, battle) if a]
        pl = JevActionPlanner(FakeJev([]))
        pl._battle = battle
        pl._entity = npc
        pl._map = m
        pl._session = session
        groups = pl._collect_groups(acts)
        types = set(groups.keys())
        assert 'dodge' in types
        assert all(isinstance(g, str) for g in types)


# --------------------------------------------------------------------------- #
# Wiring through LlmMcpController
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(JevProvider is None, reason='webapp.llm_handler not importable')
class TestControllerWiring:
    class FakeJevProvider(JevProvider):
        """A JevProvider that never touches the network."""

        def __init__(self, script):
            super().__init__(opts={'api_key': 'test', 'timeout': 1})
            self.client = object()  # make is_available True
            self._script = list(script)
            self.calls = []

        def decide_action(self, state, options):
            self.calls.append(list(options))
            if not self._script:
                return None
            item = self._script.pop(0)
            if isinstance(item, str):
                for i, opt in enumerate(options):
                    if item in opt:
                        return {'index': i, 'choice': opt}
                return {'index': 0, 'choice': options[0]}
            idx = int(item) % len(options)
            return {'index': idx, 'choice': options[idx]}

        def decide_bool(self, state, instructions):
            return {'noul': 0.9, 'confidence': 0.9}

    def test_select_action_uses_jev_tree(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['attack', 0, 0])
        ctrl = LlmMcpController(session, llm_provider=prov)
        actions = [a for a in npc.available_actions(session, battle) if a]
        action = ctrl.select_action(battle, npc, actions)

        assert isinstance(action, AttackAction)
        assert action.target is fighter
        # The provider was actually consulted (not the flat prompt path)
        assert len(prov.calls) >= 2

    def test_move_for_plans_movement_intent(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['move', 'melee', 0])
        ctrl = LlmMcpController(session, llm_provider=prov)
        action = ctrl.move_for(npc, battle)

        assert isinstance(action, MoveAction)
        assert action.move_path and len(action.move_path) > 1
        # the second decision was the strategic intent menu, not raw squares
        assert prov.calls[1]
        assert all(
            any(k in o for k in ('melee', 'defensive', 'hide', 'offensive'))
            for o in prov.calls[1]
        )

    def test_select_action_falls_back_when_jev_unavailable(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider([])
        prov.client = None  # is_available -> False
        ctrl = LlmMcpController(session, llm_provider=prov)
        actions = [a for a in npc.available_actions(session, battle) if a]
        action = ctrl.select_action(battle, npc, actions)
        assert isinstance(action, Action)
        assert prov.calls == []  # never consulted


# --------------------------------------------------------------------------- #
def _in_melee_range(m, a, b):
    try:
        return m.distance(a, b) <= 5
    except Exception:
        return False

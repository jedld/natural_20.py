"""Tests for the JEV (TypeSafe "System One") NPC battle AI planner.

Behavior under test (see natural20/utils/jev_decision.py):

* The action space is flattened to fully-specified, *executable* leaf actions:
      attack -> weapon + target  (one leaf per weapon/target pair)
      spell  -> spell (name + level) + target  (one leaf per combination)
      move   -> strategic destination squares (engage / defensive / hide /
                offensive), each leaf a complete movement path
* Actions that cannot be completed in the current state (no weapon, no legal
  target, ...) are rejected before the model is ever consulted.
* A tree that prunes down to a single legal leaf is auto-selected with zero
  provider round-trips.
* Otherwise the decision model makes exactly ONE ``decide_action`` call over
  the flat leaf list.
* A ``pass (end turn)`` leaf is always offered (appended after capping); the
  controller maps a chosen pass to ``None`` so the battle loop ends the turn.
* Any provider failure falls back cleanly to ``None`` (the controller then
  uses the generic heuristic controller).
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
from natural20.actions.end_turn_action import EndTurnAction
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
    weapons (5 ft range) have a legal target and the attack leaves are
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

    The planner makes at most one call per ``select``; script entries:
      - str: choose the index of the option *containing* the string
      - int: choose ``int % len(options)``
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
# Flat leaf planning: one call over fully-specified actions
# --------------------------------------------------------------------------- #

class TestFlatLeafPlanning:
    def test_attack_leaf_is_fully_specified_in_one_call(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['attack '])
        action = jev_select_action(prov, battle, npc)

        assert isinstance(action, AttackAction)
        # Exactly one JEV round-trip over the flat leaf list.
        assert len(prov.calls) == 1
        flat_options = prov.calls[0]
        assert any(o.startswith('attack ') for o in flat_options)
        # Final action fully specified: weapon + target
        assert action.target is fighter
        weapon_name = action.using or (action.npc_action or {}).get('name')
        assert weapon_name
        assert any(f"with {weapon_name}" in o for o in flat_options)

    def test_move_leaves_offer_strategic_destinations(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['move: engage'])
        action = jev_select_action(prov, battle, npc)

        assert isinstance(action, MoveAction)
        assert len(prov.calls) == 1
        flat_options = prov.calls[0]
        # Movement leaves are strategic (intent-prefixed), not raw squares.
        move_opts = [o for o in flat_options if o.startswith('move:')]
        assert move_opts
        assert any('engage' in o for o in move_opts)
        # The chosen destination is a valid square on the map.
        dest = action.move_path[-1]
        assert m.placeable(npc, dest[0], dest[1])

    def test_dodge_leaf_is_offered(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['dodge'])
        action = jev_select_action(prov, battle, npc)
        assert isinstance(action, DodgeAction)
        # Dodge has no parameters: one flat call, one option for it.
        assert len(prov.calls) == 1
        assert prov.calls[0].count('dodge') == 1

    def test_help_leaf_names_the_ally(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['help '])
        action = jev_select_action(prov, battle, npc)
        assert isinstance(action, HelpAction)
        assert len(prov.calls) == 1
        assert 'Gomerin' in ' '.join(prov.calls[0])
        assert action.target is fighter

    def test_shove_leaf_names_the_foe(self):
        from natural20.actions.shove_action import ShoveAction
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['shove '])
        action = jev_select_action(prov, battle, npc)
        assert isinstance(action, ShoveAction)
        assert len(prov.calls) == 1
        assert action.target is fighter


# --------------------------------------------------------------------------- #
# Spell leaves: spell (name + level) + target in one flat list
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


class TestSpellLeaves:
    def test_spell_leaves_carry_name_level_and_target(self):
        from natural20.actions.spell_action import SpellAction
        session, battle, m, fighter, wizard = build_battle_with_wizard()
        assert wizard.has_spells()

        prov = FakeJev(['cast '])
        action = jev_select_action(prov, battle, wizard)

        assert isinstance(action, SpellAction)
        assert len(prov.calls) == 1
        spell_options = [o for o in prov.calls[0] if o.startswith('cast ')]
        assert spell_options
        # each spell leaf names the spell, its level, and a concrete target
        assert all('level' in o or 'cantrip' in o for o in spell_options)
        assert all('Gomerin' in o or 'Noke' in o or 'empty space' in o
                   for o in spell_options)


# --------------------------------------------------------------------------- #
# Executability: infeasible actions are rejected up front
# --------------------------------------------------------------------------- #

class TestExecutability:
    def test_weaponless_attack_leaf_is_rejected(self):
        """An attack with no weapon/npc_action cannot resolve its range, so it
        must never reach the decision model."""
        session, battle, m, fighter, npc = build_battle()
        bad_attack = AttackAction(session, npc, 'attack')  # no using / no npc_action
        assert getattr(bad_attack, 'using', None) is None
        assert getattr(bad_attack, 'npc_action', None) is None

        prov = FakeJev(['help'])
        action = jev_select_action(prov, battle, npc,
                                   available_actions=[bad_attack,
                                                       HelpAction(session, npc, 'help')])
        # The only executable leaf is the help action.
        assert isinstance(action, HelpAction)
        assert prov.n_calls == 1
        # The infeasible attack never reaches the decision model.
        assert not any(o.startswith('attack') for o in prov.calls[0])

    def test_out_of_range_attack_leaf_is_rejected(self):
        """A melee attack with no foe in range is infeasible and never reaches
        the decision model; the in-range ranged attack is the only executable
        leaf (alongside pass) and is chosen in a single round-trip."""
        # The fixture map is 6x7 and dark (visibility is light-based): the
        # goblin sits at [1,5]; the fighter at [5,5] is 20 ft away in the same
        # lit area - out of scimitar range (5 ft) but within shortbow range
        # (80 ft).
        session, battle, m, fighter, npc = build_battle(fighter_pos=[5, 5])
        melee_attack = AttackAction(session, npc, 'attack')
        melee_attack.using = 'scimitar'   # weapon id, 5 ft range
        bow_attack = AttackAction(session, npc, 'attack')
        bow_attack.using = 'shortbow'     # weapon id, 80 ft range

        # Sanity: the range split this test relies on.
        assert not battle.valid_targets_for(npc, melee_attack)
        assert fighter in battle.valid_targets_for(npc, bow_attack)

        prov = FakeJev(['shortbow'])
        action = jev_select_action(prov, battle, npc,
                                   available_actions=[melee_attack, bow_attack])
        assert isinstance(action, AttackAction)
        assert action.using == 'shortbow'
        assert action.target is fighter
        assert prov.n_calls == 1
        # The infeasible melee attack never reaches the decision model.
        assert not any('scimitar' in o for o in prov.calls[0])

    def test_only_infeasible_actions_yield_pass(self):
        session, battle, m, fighter, npc = build_battle()
        bad_attack = AttackAction(session, npc, 'attack')
        prov = FakeJev([0])
        action = jev_select_action(prov, battle, npc,
                                   available_actions=[bad_attack])
        # Nothing executable but the always-present pass leaf -> the single
        # leaf is auto-selected (the controller turns it into an end turn).
        assert isinstance(action, EndTurnAction)
        assert prov.n_calls == 0  # single leaf -> no question


# --------------------------------------------------------------------------- #
# Single-legal-leaf trees are auto-selected without a round-trip
# --------------------------------------------------------------------------- #

class TestPassLeaf:
    def test_pass_leaf_always_offered(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['attack '])
        jev_select_action(prov, battle, npc)
        assert prov.calls  # the flat list was asked
        assert 'pass (end turn)' in prov.calls[0]

    def test_pass_choice_returns_end_turn_action(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev(['pass'])
        action = jev_select_action(prov, battle, npc)
        assert isinstance(action, EndTurnAction)
        assert len(prov.calls) == 1

    def test_only_pass_is_single_leaf_auto_selected(self):
        # With an empty explicit list the only leaf is pass itself: the tree
        # prunes to one option, so it is auto-selected with zero round-trips.
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev([])  # would fail the test if ever consulted
        action = jev_select_action(prov, battle, npc, available_actions=[])
        assert isinstance(action, EndTurnAction)
        assert prov.n_calls == 0


class TestSingleExecutableAction:
    # Since pass is always offered, a single executable action is two
    # options (the action + pass), so the model is always consulted.

    def test_single_executable_action_asked_with_pass(self):
        session, battle, m, fighter, npc = build_battle()
        help_act = HelpAction(session, npc, 'help')
        prov = FakeJev(['help'])
        action = jev_select_action(prov, battle, npc,
                                   available_actions=[help_act])
        assert isinstance(action, HelpAction)
        assert action.target is fighter  # enriched to the only legal ally
        assert len(prov.calls) == 1
        assert 'pass (end turn)' in prov.calls[0]

    def test_mixed_list_executable_action_asked_with_pass(self):
        session, battle, m, fighter, npc = build_battle()
        bad_attack = AttackAction(session, npc, 'attack')  # rejected (no weapon)
        help_act = HelpAction(session, npc, 'help')        # the one executable leaf
        prov = FakeJev(['help'])
        action = jev_select_action(prov, battle, npc,
                                   available_actions=[bad_attack, help_act])
        assert isinstance(action, HelpAction)
        assert len(prov.calls) == 1
        assert 'pass (end turn)' in prov.calls[0]


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
        assert prov.n_calls == 1  # failed on the single (flat) call

    def test_provider_none_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        assert jev_select_action(None, battle, npc) is None

    def test_unavailable_provider_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        prov = FakeJev([0])
        prov.is_available = False
        assert jev_select_action(prov, battle, npc) is None
        assert prov.n_calls == 0

    def test_type_key_groups_by_class(self):
        # Defensive actions must group under their class-derived type key
        # even if a builder ever sets a misleading action_type.
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        acts = [a for a in npc.available_actions(session, battle) if a]
        pl = JevActionPlanner(FakeJev([]))
        pl._battle = battle
        pl._entity = npc
        pl._map = m
        pl._session = session
        keys = {pl._type_key(a) for a in acts}
        assert 'dodge' in keys
        assert all(isinstance(k, str) for k in keys)


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

    def test_select_action_uses_flat_jev_leaf(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['attack '])
        ctrl = LlmMcpController(session, llm_provider=prov)
        actions = [a for a in npc.available_actions(session, battle) if a]
        action = ctrl.select_action(battle, npc, actions)

        assert isinstance(action, AttackAction)
        assert action.target is fighter
        # The provider was consulted exactly once, over the flat leaf list
        assert len(prov.calls) == 1
        assert any(o.startswith('attack ') for o in prov.calls[0])

    def test_move_for_plans_movement_leaf(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['move:'])
        ctrl = LlmMcpController(session, llm_provider=prov)
        action = ctrl.move_for(npc, battle)

        assert isinstance(action, MoveAction)
        assert action.move_path and len(action.move_path) > 1
        # The single decision is the flat list; movement leaves carry the
        # strategic intent prefix, not raw squares.
        assert len(prov.calls) == 1
        move_opts = [o for o in prov.calls[0] if o.startswith('move:')]
        assert move_opts
        assert all(
            any(k in o for k in ('engage', 'defensive', 'hide', 'offensive'))
            for o in move_opts
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

    def test_move_for_returns_chosen_attack(self):
        """Regression: a non-movement JEV pick must be returned as-is for the
        turn loop to commit (not lost to the heuristic fallback, which the
        old bare ``action.move_path`` access crashed into)."""
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['attack '])
        ctrl = LlmMcpController(session, llm_provider=prov)
        action = ctrl.move_for(npc, battle)

        assert isinstance(action, AttackAction)
        assert action.target is fighter
        assert len(prov.calls) == 1

    def test_move_for_pass_ends_turn(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['pass'])
        ctrl = LlmMcpController(session, llm_provider=prov)
        assert ctrl.move_for(npc, battle) is None
        assert len(prov.calls) == 1

    def test_select_action_pass_returns_none(self):
        session, battle, m, fighter, npc = build_battle()
        prov = self.FakeJevProvider(['pass'])
        ctrl = LlmMcpController(session, llm_provider=prov)
        actions = [a for a in npc.available_actions(session, battle) if a]
        assert ctrl.select_action(battle, npc, actions) is None
        assert len(prov.calls) == 1

    def test_select_action_single_action_still_asked_when_jev_live(self):
        """With JEV live, a lone available action is weighed against pass
        instead of being auto-taken by the single-action shortcut."""
        session, battle, m, fighter, npc = build_battle()
        help_act = HelpAction(session, npc, 'help')
        prov = self.FakeJevProvider(['help'])
        ctrl = LlmMcpController(session, llm_provider=prov)
        action = ctrl.select_action(battle, npc, [help_act])
        assert isinstance(action, HelpAction)
        assert len(prov.calls) == 1
        assert 'pass (end turn)' in prov.calls[0]


class TestBuilderActionTypes:
    def test_defensive_builders_use_their_own_action_type(self):
        """Disengage/Dodge builders must not carry action_type='attack'
        (a copy-paste bug that misrouted commit-time events and the VTT
        animation to the attack branch)."""
        session, battle, m, fighter, npc = build_battle()
        from natural20.actions.disengage_action import (
            DisengageAction, DisengageBonusAction)
        from natural20.actions.dodge_action import DodgeAction

        dis = DisengageAction.build(session, npc)
        assert dis.action_type == 'disengage'

        dis_bonus = DisengageBonusAction.build(session, npc)
        assert isinstance(dis_bonus, DisengageBonusAction)
        assert dis_bonus.action_type == 'disengage_bonus'

        dod = DodgeAction.build(session, npc)
        assert dod.action_type == 'dodge'


# --------------------------------------------------------------------------- #
# State rendering: attributes, inventory, spell slots, name disambiguation
# --------------------------------------------------------------------------- #

def build_mage_battle():
    """A spellcasting PlayerCharacter (Crysania the wizard) vs a goblin,
    with the mage on her turn."""
    random.seed(7001)
    event_manager = EventManager()
    session = Session_for_test(event_manager)
    m = Map(session, 'battle_sim')
    battle = Battle(session, m)
    mage = PlayerCharacter.load(session, 'high_elf_mage.yml')
    goblin = session.npc('goblin')
    battle.add(mage, 'a', position=[2, 5], token='W')
    battle.add(goblin, 'b', position=[1, 5], token='g')
    battle.start()
    battle.set_current_turn(mage)
    mage.reset_turn(battle)
    goblin.reset_turn(battle)
    return session, battle, m, goblin, mage


def state_text(planner_cls, battle, entity):
    """Render the state text the planner would hand to the JEV provider."""
    planner = planner_cls(FakeJev([]))
    planner._battle = battle
    planner._entity = entity
    planner._map = battle.map_for(entity)
    planner._names = planner._display_names(battle, entity)
    return planner._render_state(battle, entity)


class TestStateRendering:
    def test_state_renders_ability_modifiers(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, goblin, mage = build_mage_battle()
        st = state_text(JevActionPlanner, battle, mage)
        # Crysania: str10 dex15 con14 int18 wis12 cha8 -> +0/+2/+2/+4/+1/-1
        assert 'mods: str+0 dex+2 con+2 int+4 wis+1 cha-1' in st

    def test_state_renders_usable_inventory(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, goblin, mage = build_mage_battle()
        st = state_text(JevActionPlanner, battle, mage)
        # The fixture Crysania carries one scroll of magic missile (usable).
        assert 'items:' in st
        assert 'scroll' in st.lower()

    def test_state_renders_spell_slots_for_pc(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, goblin, mage = build_mage_battle()
        assert mage.max_spell_slots(1) > 0
        st = state_text(JevActionPlanner, battle, mage)
        cur = mage.spell_slots_count(1)
        mx = mage.max_spell_slots(1)
        assert f"spell slots: L1 {cur}/{mx}" in st

    def test_state_renders_spell_slots_for_npc(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, wizard = build_battle_with_wizard()
        assert wizard.max_spell_slots(3) == 2
        assert wizard.max_spell_slots(4) == 1
        st = state_text(JevActionPlanner, battle, wizard)
        assert f"spell slots: L3 {wizard.spell_slots_count(3)}/2" in st
        assert f"L4 {wizard.spell_slots_count(4)}/1" in st

    def test_state_marks_unconscious_enemies(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        fighter.set_hp(0)
        fighter.update_state('unconscious')
        st = state_text(JevActionPlanner, battle, npc)
        # A 0-HP unconscious foe is still visible but must be flagged.
        assert 'Gomerin hp 0' in st
        assert '(unconscious)' in st

    def test_state_disambiguates_colliding_names(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        # Give the fighter the goblin's name: the visible-enemies line must
        # disambiguate by position so the model can tell them apart.
        goblin_name = npc.name
        fighter.name = goblin_name
        st = state_text(JevActionPlanner, battle, npc)
        enemies_line = [l for l in st.splitlines() if l.startswith('visible enemies')][0]
        assert '@[' in enemies_line
        # The acting entity keeps its plain name.
        assert f"Entity: {goblin_name};" in st

    def test_state_lists_allies(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, goblin, mage = build_mage_battle()
        # A second PC on the mage's side must appear in the allies line.
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle.add(fighter, 'a', position=[3, 5], token='F')
        fighter.reset_turn(battle)
        st = state_text(JevActionPlanner, battle, mage)
        allies_line = [l for l in st.splitlines() if l.startswith('allies:')][0]
        assert 'none' not in allies_line
        assert fighter.name in allies_line

    def test_state_shows_entity_own_conditions(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, goblin, mage = build_mage_battle()
        # Standing conditions live on ``entity.statuses`` (the same list every
        # condition check reads) - they must reach the state the model sees.
        mage.statuses.append('poisoned')
        st = state_text(JevActionPlanner, battle, mage)
        statuses_line = [l for l in st.splitlines() if l.startswith('statuses:')][0]
        assert 'poisoned' in statuses_line

    def test_state_merges_turn_action_markers_with_conditions(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, goblin, mage = build_mage_battle()
        # The per-turn dodge/disengage markers (battle state) and the entity's
        # own conditions (entity.statuses) are both rendered on one line.
        mage.statuses.append('prone')
        battle.entity_state_for(mage)['statuses'].add('dodge')
        st = state_text(JevActionPlanner, battle, mage)
        statuses_line = [l for l in st.splitlines() if l.startswith('statuses:')][0]
        assert 'prone' in statuses_line
        assert 'dodge' in statuses_line

    def test_state_shows_armor_class(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        assert fighter.armor_class() > 0 and npc.armor_class() > 0
        st = state_text(JevActionPlanner, battle, npc)
        # The acting entity's own AC is on the header line ...
        header = [l for l in st.splitlines() if l.startswith('Entity:')][0]
        assert f"AC {npc.armor_class()}" in header
        # ... and each visible enemy carries its AC on the enemy line, so the
        # model can weigh hit-chance, not just HP.
        enemies_line = [l for l in st.splitlines() if l.startswith('visible enemies')][0]
        assert f"ac {fighter.armor_class()}" in enemies_line

    def test_state_shows_active_buffs_and_boosted_ac(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, wizard = build_battle_with_wizard()
        base_ac = wizard.armor_class()
        # Haste (self-cast): +2 AC and an active, named effect.
        action = jev_select_action(FakeJev(['Haste']), battle, wizard)
        battle.action(action)
        battle.commit(action)
        assert wizard.armor_class() == base_ac + 2
        st = state_text(JevActionPlanner, battle, wizard)
        header = [l for l in st.splitlines() if l.startswith('Entity:')][0]
        assert f"AC {base_ac + 2}" in header
        # The effect is named (Haste, not its class) and deduplicated even
        # though Haste registers two mechanics (speed_override + ac_bonus).
        effects_lines = [l for l in st.splitlines() if l.startswith('effects:')]
        assert len(effects_lines) == 1
        assert 'Haste' in effects_lines[0]
        assert 'HasteSpell' not in effects_lines[0]


# --------------------------------------------------------------------------- #
# Spellcasting end-to-end (PlayerCharacter and NPC)
# --------------------------------------------------------------------------- #

class TestSpellcasterEndToEnd:
    def test_pc_wizard_casts_via_jev_and_spends_a_slot(self):
        """A wizard PC picks a leveled spell from the flat leaf list and the
        cast resolves: damage is dealt and a slot is consumed."""
        from natural20.actions.spell_action import SpellAction
        session, battle, m, goblin, mage = build_mage_battle()
        assert mage.has_spells()

        prov = FakeJev(['Burning Hands'])
        action = jev_select_action(prov, battle, mage)

        assert isinstance(action, SpellAction)
        assert len(prov.calls) == 1
        assert any('Burning Hands' in o for o in prov.calls[0])
        assert action.spell_action.properties.get('name') == 'Burning Hands'

        hp_before = goblin.hp()
        slots_before = mage.spell_slots_count(1)
        battle.action(action)
        battle.commit(action)
        assert goblin.hp() < hp_before  # 3d6 fire on the cone
        assert mage.spell_slots_count(1) == slots_before - 1

    def test_npc_wizard_casts_via_jev_and_applies_haste(self):
        """The Test Wizard NPC picks Haste from the flat leaf list; the cast
        resolves, the target is hasted, and a slot is consumed. (Haste's only
        legal target here is the wizard himself: the fighter is an enemy.)"""
        from natural20.actions.spell_action import SpellAction
        session, battle, m, fighter, wizard = build_battle_with_wizard()
        assert wizard.has_spells()

        prov = FakeJev(['Haste'])
        action = jev_select_action(prov, battle, wizard)

        assert isinstance(action, SpellAction)
        assert len(prov.calls) == 1
        assert any('Haste' in o for o in prov.calls[0])
        assert action.target is wizard

        slots_before = wizard.spell_slots_count(3)
        battle.action(action)
        battle.commit(action)
        assert 'hasted' in wizard.statuses
        assert wizard.spell_slots_count(3) == slots_before - 1


# --------------------------------------------------------------------------- #
# POV combat log: entries witnessed since the entity's last turn
# --------------------------------------------------------------------------- #

def _pov_lines(st):
    """The bullet lines under ``since last turn:`` in a rendered state."""
    out, in_block = [], False
    for line in st.splitlines():
        if line.startswith('since last turn:'):
            in_block = True
            continue
        if in_block:
            if line.startswith('- '):
                out.append(line)
            else:
                break
    return out


class _StubBattle:
    """Duck-typed battle exposing only ``can_see`` for POV unit tests."""

    def __init__(self, visible_pairs=()):
        self._visible = set(visible_pairs)

    def can_see(self, e1, e2):
        return (id(e1), id(e2)) in self._visible


def _stub_entity(uid):
    class E:
        pass
    e = E()
    e.entity_uid = uid
    e.name = uid
    return e


def _stub_action(source, target=None, action_type='attack', result=None):
    class A:
        pass
    a = A()
    a.source = source
    a.target = target
    a.action_type = action_type
    a.result = result or []
    return a


class TestPovCombatLog:
    def test_witnessed_attack_appears_in_state(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        # Goblin's turn (set by build_battle): it attacks the fighter.
        battle.start_turn()
        action = jev_select_action(FakeJev(['attack ']), battle, npc)
        battle.action(action)
        battle.commit(action)
        battle.end_turn()

        # Now the fighter's turn: the witnessed attack must be in its state.
        battle.set_current_turn(fighter)
        battle.start_turn()
        st = state_text(JevActionPlanner, battle, fighter)
        pov = _pov_lines(st)
        assert any(npc.name in l and 'attacked' in l for l in pov)

    def test_window_excludes_entries_before_last_turn(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, npc = build_battle()
        # Round 1: goblin attacks (log 0), fighter dodges (log 1).
        battle.start_turn()
        a1 = jev_select_action(FakeJev(['attack ']), battle, npc)
        battle.action(a1)
        battle.commit(a1)
        battle.end_turn()

        battle.set_current_turn(fighter)
        battle.start_turn()
        d1 = jev_select_action(FakeJev(['dodge']), battle, fighter)
        battle.action(d1)
        battle.commit(d1)
        battle.end_turn()

        # Round 2: goblin attacks again (log 2). On the fighter's next turn
        # the window starts at the fighter's first turn, so the goblin's
        # round-1 attack is outside it: only the dodge and the newest attack
        # may appear.
        battle.set_current_turn(npc)
        npc.reset_turn(battle)
        battle.start_turn()
        a2 = jev_select_action(FakeJev(['attack ']), battle, npc)
        battle.action(a2)
        battle.commit(a2)
        battle.end_turn()

        battle.set_current_turn(fighter)
        fighter.reset_turn(battle)
        battle.start_turn()
        st = state_text(JevActionPlanner, battle, fighter)
        pov = _pov_lines(st)
        assert len(pov) == 2
        assert any('dodged' in l for l in pov)
        assert sum(1 for l in pov if 'attacked' in l) == 1

    def test_spell_cast_line_names_the_spell(self):
        from natural20.utils.jev_decision import JevActionPlanner
        session, battle, m, fighter, wizard = build_battle_with_wizard()
        # Wizard's turn (set by the builder): Haste on himself, committed.
        battle.start_turn()
        action = jev_select_action(FakeJev(['Haste']), battle, wizard)
        battle.action(action)
        battle.commit(action)
        battle.end_turn()

        # Now the fighter's turn: the cast is witnessed and names the spell.
        battle.set_current_turn(fighter)
        battle.start_turn()
        st = state_text(JevActionPlanner, battle, fighter)
        pov = _pov_lines(st)
        assert any('cast' in l and 'Haste' in l for l in pov)

    def test_pov_log_is_capped(self):
        from natural20.utils.jev_decision import JevActionPlanner, MAX_JEV_POV_LOG
        session, battle, m, fighter, npc = build_battle()
        battle.start_turn()
        action = jev_select_action(FakeJev(['attack ']), battle, npc)
        battle.action(action)
        battle.commit(action)
        # Pad the log far past the cap with the same witnessed entry.
        for _ in range(20):
            battle.battle_log.append(action)
        planner = JevActionPlanner(None)
        planner._names = planner._display_names(battle, fighter)
        out = planner._pov_log(battle, fighter)
        assert len(out) == MAX_JEV_POV_LOG

    def test_pov_witnessed_rules(self):
        from natural20.utils.jev_decision import _pov_witnessed
        me, foe, ally = _stub_entity('me'), _stub_entity('foe'), _stub_entity('ally')

        # Own action: always witnessed.
        assert _pov_witnessed(_StubBattle(), me, _stub_action(me))
        # Being targeted: always witnessed.
        assert _pov_witnessed(_StubBattle(), me, _stub_action(foe, target=me))
        # Visible actor: witnessed.
        b = _StubBattle([(id(me), id(foe))])
        assert _pov_witnessed(b, me, _stub_action(foe))
        # Invisible actor but visible target: witnessed.
        b = _StubBattle([(id(me), id(ally))])
        assert _pov_witnessed(b, me, _stub_action(foe, target=ally))
        # Nothing visible: not witnessed.
        assert not _pov_witnessed(_StubBattle(), me, _stub_action(foe, target=ally))

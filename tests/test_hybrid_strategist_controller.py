"""Hybrid LLM-strategist + JEV executor battle controller.

At the start of each turn the generative strategist provider is fed the same
state text the JEV planner sees (plus the legal options) and writes
step-by-step orders. The orders are stored in battle entity state so every
JEV question for the rest of the turn - including reactions during other
creatures' turns - carries them, and each plan is logged DM-only via the
``strategist_plan`` event.
"""

import random
import unittest

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.llm_controller import HybridStrategistController, LlmMcpController
from natural20.map import Map
from natural20.session import Session
from natural20.utils.jev_decision import (
    JevActionPlanner,
    STRATEGIST_ORDERS_KEY,
    get_strategist_orders,
    set_strategist_orders,
)

try:
    from webapp.llm_handler import JevProvider
except Exception:  # pragma: no cover - webapp not installed in this env
    JevProvider = None

PLAN_TEXT = (
    "Focus the archer on the flank.\n"
    "1. move to the cover pillar\n"
    "2. Shortbow at Vrogzuk\n"
    "Reaction: opportunity attack if the elf closes in"
)


class FakeStrategist:
    """Generative stand-in: records prompts, returns a canned plan."""

    name = 'fake_strategist'

    def __init__(self, reply=PLAN_TEXT):
        self.reply = reply
        self.calls = []

    def send_message(self, messages):
        self.calls.append(messages)
        return self.reply


class RecordingJev:
    """Records every decide_action call (state + options) and picks an index."""

    name = 'jev_fake'

    def __init__(self, pick=0):
        self.pick = pick
        self.decisions = []  # (state, options)
        self.is_available = True

    def send_message(self, messages):
        raise AssertionError('JEV must never be asked to generate prose')

    def decide_action(self, state, options):
        self.decisions.append((state, list(options)))
        index = self.pick if 0 <= self.pick < len(options) else 0
        return {'index': index, 'choice': options[index], 'confidence': 0.9}


class CapturingOutputLogger:
    def __init__(self):
        self.entries = []  # (msg, visibility)

    def log(self, event_msg, event=None, visibility=None):
        self.entries.append((event_msg, visibility))


def _real_jev_provider(fake):
    """A JevProvider instance (for the isinstance gate) delegating to *fake*."""
    class _LiveJev(JevProvider):
        @property
        def is_available(self):
            return True

    live = _LiveJev()
    live.decide_action = fake.decide_action
    return live


class TestHybridStrategistController(unittest.TestCase):
    def setUp(self):
        random.seed(11)
        self.logger = CapturingOutputLogger()
        self.em = EventManager(output_logger=self.logger)
        self.em.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=self.em)
        self.map = Map(self.session, 'entryway')
        self.battle = Battle(self.session, self.map)
        self.pc = self.map.entity_by_uid('gomerin')
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.pc, 'a')
        self.battle.add(self.goblin, 'b')
        self.battle.start()
        self.jev = RecordingJev()
        self.jev_provider = _real_jev_provider(self.jev)
        self.strategist = FakeStrategist()
        self.controller = HybridStrategistController(
            self.session, llm_provider=self.jev_provider,
            strategist_provider=self.strategist)

    def _actions(self, entity):
        return list(entity.available_actions(self.session, self.battle))

    # ------------------------------------------------------------------ #
    def test_orders_generated_and_stored_in_battle_state(self):
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertEqual(len(self.strategist.calls), 1)
        stored = get_strategist_orders(self.battle, self.goblin)
        self.assertIsNotNone(stored)
        self.assertIn('opportunity attack', stored)

    def test_orders_regenerated_only_once_per_turn(self):
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertEqual(len(self.strategist.calls), 1)
        # a new turn marks them stale again
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertEqual(len(self.strategist.calls), 2)

    def test_orders_injected_into_every_jev_question(self):
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertTrue(self.jev.decisions, 'JEV was asked no questions')
        state = self.jev.decisions[0][0]
        self.assertIn("commander's orders", state)
        self.assertIn('Shortbow at Vrogzuk', state)

    def test_strategist_prompt_uses_jev_state_and_options(self):
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        messages = self.strategist.calls[0]
        user = messages[-1]['content']
        system = messages[0]['content']
        self.assertIn('Entity:', user)          # JEV state text
        self.assertIn('mods:', user)            # sheet block
        self.assertIn('legal options right now:', user)
        self.assertNotIn('Task:', user)         # JEV's own task line stripped
        self.assertIn('tactical advisor', system)
        # Movement is decided later by JEV — ground the MOVE: vocabulary.
        self.assertIn('MOVE:', system)
        self.assertIn('movement intents the executor understands', user)
        self.assertIn('MOVE: <tag>', user)

    def test_no_previous_turn_orders_leak_into_prompt(self):
        set_strategist_orders(self.battle, self.goblin, 'OLD PLAN: do the old thing')
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        user = self.strategist.calls[0][-1]['content']
        self.assertNotIn('OLD PLAN', user)
        # the new plan replaced it
        self.assertNotIn('OLD PLAN', get_strategist_orders(self.battle, self.goblin))

    def test_orders_persist_for_reactions_on_other_turns(self):
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        # another creature acts; the goblin reacts (e.g. an opportunity attack)
        from natural20.actions.end_turn_action import EndTurnAction
        valid = [EndTurnAction(self.session, self.goblin, 'end_turn')] + \
            list(self.goblin.available_actions(self.session, self.battle,
                                               opportunity_attack=True))
        # JEV index 0 == pass -> explicitly hold (no heuristic fallback)
        self.assertIsNone(self.controller.select_reaction(
            self.goblin, self.battle, self.map, valid, {'type': 'opportunity_attack'}))
        # and the reaction question carried the orders, with no new LLM call
        self.assertEqual(len(self.strategist.calls), 1)
        self.assertIn("commander's orders", self.jev.decisions[-1][0])

    def test_plan_logged_dm_only(self):
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        plan_lines = [entry for entry in self.logger.entries
                      if 'opportunity attack if the elf' in entry[0]
                      or 'plans this turn' in entry[0]]
        self.assertTrue(plan_lines, 'strategist plan was not logged')
        for _msg, visibility in plan_lines:
            self.assertEqual(visibility, 'dm')

    def test_clean_orders_preserves_move_and_reaction_tags(self):
        verbose = "\n".join(
            f"{i}. long reasoning about the map and options" for i in range(1, 30)
        ) + "\nMOVE: retreat\nReaction: hold"
        cleaned = self.controller._clean_orders(verbose)
        self.assertIsNotNone(cleaned)
        self.assertIn('MOVE: retreat', cleaned)
        self.assertIn('Reaction: hold', cleaned)
        self.assertLessEqual(len(cleaned.splitlines()), self.controller.MAX_ORDERS_LINES)

    def test_without_strategist_behaves_like_plain_jev(self):
        controller = HybridStrategistController(
            self.session, llm_provider=self.jev_provider)
        controller.begin_turn(self.goblin)
        controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        # still ran JEV, just with no orders block
        self.assertTrue(self.jev.decisions)
        self.assertNotIn("commander's orders", self.jev.decisions[0][0])

    def test_no_generation_when_executor_not_jev(self):
        generative = FakeStrategist()
        controller = HybridStrategistController(
            self.session, llm_provider=generative)
        controller.begin_turn(self.goblin)
        controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        # not a JEV executor: the strategist layer never runs
        self.assertIsNone(get_strategist_orders(self.battle, self.goblin))

    def test_orders_survive_battle_state_serialization(self):
        import yaml

        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        state = self.battle.entity_state_for(self.goblin)
        text = yaml.safe_dump({STRATEGIST_ORDERS_KEY: state[STRATEGIST_ORDERS_KEY]})
        restored = yaml.safe_load(text)
        self.assertIn('opportunity attack', restored[STRATEGIST_ORDERS_KEY])

    # ------------------------------------------------------------------ #
    # Rules oracle (hallucination guard)                                  #
    # ------------------------------------------------------------------ #

    def test_oracle_rules_reach_strategist_prompt(self):
        from natural20.actions.action_surge_action import ActionSurgeAction
        from natural20.actions.attack_action import AttackAction
        from natural20.actions.second_wind_action import SecondWindAction

        attack = AttackAction(self.session, self.pc, 'attack')
        attack.using = 'Rapier'
        actions = [SecondWindAction(self.session, self.pc, 'second_wind'),
                   ActionSurgeAction(self.session, self.pc, 'action_surge'),
                   attack]
        self.controller.begin_turn(self.pc)
        self.controller.select_action(self.battle, self.pc, actions)
        messages = self.strategist.calls[-1]
        user = messages[-1]['content']
        self.assertIn('rules for those options', user)
        self.assertIn('once per short rest', user)   # Second Wind rules
        self.assertIn('Action Surge', user)
        self.assertIn('one weapon attack', user)     # attack basics
        # the system prompt tells the strategist the oracle is authoritative
        self.assertIn('ORACLE', messages[0]['content'])

    def test_oracle_shows_seen_spells_and_traits(self):
        class FakeSpell:
            properties = {
                'name': 'Bless', 'label': 'Bless',
                'description': 'Attacks and saves gain a d4 bonus.',
                'casting_time': '1:action', 'concentration': True,
            }

        self.goblin.properties = dict(self.goblin.properties or {})
        self.goblin.properties['regeneration'] = {'hp': 5,
                                                  'suppressed_by': ['radiant']}
        self.goblin.properties['legendary_resistance'] = 2
        self.pc.register_effect('bless', None, effect=FakeSpell(),
                                source=self.pc)
        self.controller.begin_turn(self.pc)
        self.controller.select_action(self.battle, self.pc,
                                      self._actions(self.pc))
        user = self.strategist.calls[-1][-1]['content']
        self.assertIn('seen in this fight', user)
        self.assertIn('Bless', user)
        self.assertIn('Attacks and saves gain a d4 bonus.', user)
        self.assertIn('regenerates 5 hit points', user)
        self.assertIn('suppressed if it took radiant damage', user)
        self.assertIn('legendary resistance', user)

    def test_oracle_can_be_disabled_by_env(self):
        import os
        os.environ['N20_STRATEGIST_ORACLE'] = '0'
        try:
            self.controller.begin_turn(self.pc)
            self.controller.select_action(self.battle, self.pc,
                                          self._actions(self.pc))
            user = self.strategist.calls[-1][-1]['content']
            self.assertNotIn('rules for those options', user)
            self.assertNotIn('seen in this fight', user)
        finally:
            os.environ.pop('N20_STRATEGIST_ORACLE', None)

    def test_controller_to_dict_roundtrip(self):
        data = self.controller.to_dict()
        self.assertNotIn('llm_provider', data)
        clone = HybridStrategistController.from_dict(data)
        self.assertIsInstance(clone, HybridStrategistController)
        self.assertTrue(clone._provider_pending)
        self.assertTrue(clone._strategist_pending)

    # ------------------------------------------------------------------ #
    # Named agent bundles (.ai.yaml ``agents:``)                          #
    # ------------------------------------------------------------------ #

    def test_agent_directives_frame_strategist_prompt(self):
        self.controller.agent_name = 'brute'
        self.controller.agent_persona = 'Focus the archers.\nNever pursue.'
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        user = self.strategist.calls[0][-1]['content']
        self.assertIn('Standing orders for', user)
        self.assertIn('agent profile brute', user)
        self.assertIn('Focus the archers.', user)
        self.assertIn('Never pursue.', user)

    def test_agent_directives_reach_jev_state_context(self):
        self.controller.agent_name = 'brute'
        self.controller.agent_persona = 'Focus the archers.\nNever pursue.'
        self.battle.set_controller_for(self.goblin, self.controller)
        self.controller.begin_turn(self.goblin)
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        state = self.jev.decisions[0][0]
        self.assertIn('standing orders (brute agent profile):', state)
        self.assertIn('Never pursue.', state)

    def test_agent_identity_round_trips_through_save(self):
        self.controller.agent_name = 'brute'
        self.controller.agent_persona = 'Hold the corridor.'
        self.controller.agent_profile = 'jev_fast'
        self.controller.agent_strategist_profile = 'dm'
        data = self.controller.to_dict()
        clone = HybridStrategistController.from_dict(data)
        self.assertEqual(clone.agent_name, 'brute')
        self.assertEqual(clone.agent_persona, 'Hold the corridor.')
        self.assertEqual(clone.agent_profile, 'jev_fast')
        self.assertEqual(clone.agent_strategist_profile, 'dm')
        self.assertTrue(clone._provider_pending)
        self.assertTrue(clone._strategist_pending)

    def test_agent_profiles_rebound_after_load(self):
        executor = _real_jev_provider(RecordingJev())
        planner = FakeStrategist()

        def resolver(profile_name):
            return executor if profile_name == 'jev_x' else planner

        LlmMcpController.profile_resolver = staticmethod(resolver)
        try:
            self.controller.agent_profile = 'jev_x'
            self.controller.agent_strategist_profile = 'dm'
            self.controller._provider_pending = True
            self.controller._strategist_pending = True
            self.controller._last_entity = self.goblin
            self.controller._ensure_provider(self.goblin)
            self.assertIs(self.controller.llm_provider, executor)
            self.assertIs(self.controller.strategist_provider, planner)
        finally:
            LlmMcpController.profile_resolver = None

    def test_plain_llm_controller_gets_agent_prompt_block(self):
        self.map.place((2, 2), self.goblin)
        controller = LlmMcpController(self.session, llm_provider=self.strategist)
        controller.agent_name = 'skirmisher'
        controller.agent_persona = 'Hit and slide away. Never stand in melee.'
        prompt = controller._build_prompt(self.battle, self.goblin,
                                          self._actions(self.goblin))
        self.assertIn('Standing orders (skirmisher agent profile):', prompt)
        self.assertIn('Hit and slide away.', prompt)

    # ------------------------------------------------------------------ #
    # Order lifecycle without a while_active-style host loop              #
    # ------------------------------------------------------------------ #

    def test_orders_regenerate_next_round_without_begin_turn(self):
        # The webapp VTT runs its own turn loop and never calls the
        # controller's begin_turn; orders must re-arm on the battle round so
        # planning is once per creature *per round*, not once per battle.
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertEqual(len(self.strategist.calls), 1)
        # further decisions in the same round reuse the plan
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertEqual(len(self.strategist.calls), 1)
        # a new round re-arms even though begin_turn was never called
        self.battle.round += 1
        self.controller.select_action(self.battle, self.goblin, self._actions(self.goblin))
        self.assertEqual(len(self.strategist.calls), 2)
        stored = get_strategist_orders(self.battle, self.goblin)
        self.assertIn('opportunity attack', stored)

    def test_restored_controller_property_binds_resolver_not_env_default(self):
        clone = HybridStrategistController.from_dict(self.controller.to_dict())
        jev = _real_jev_provider(RecordingJev())
        calls = []

        def resolver(entity):
            calls.append(entity)
            return None if not calls or len(calls) == 1 else jev

        LlmMcpController.provider_resolver = staticmethod(resolver)
        try:
            # a resolver that cannot answer keeps the controller pending
            # instead of binding the env-default provider
            self.assertIsNone(clone.llm_provider)
            self.assertTrue(clone._provider_pending)
            # _ensure_provider(entity) still binds normally
            clone._ensure_provider(self.goblin)
            self.assertIs(clone.llm_provider, jev)
            self.assertFalse(clone._provider_pending)
            clone2 = HybridStrategistController.from_dict(self.controller.to_dict())
            self.assertIs(clone2.llm_provider, jev)  # plain property read resolves
        finally:
            LlmMcpController.provider_resolver = None


class TestOracleRules(unittest.TestCase):
    """Unit checks on the oracle's per-option rules text (utils/oracle)."""

    def test_spell_rules_carry_casting_time_and_description(self):
        from natural20.utils.oracle import spell_rules
        text = spell_rules({
            'name': 'Magic Missile',
            'casting_time': '1:action',
            'range': 120,
            'components': ['verbal', 'somatic'],
            'description': 'Three darts hit automatically, 1d4+1 force each.',
        })
        self.assertIn('casting time: Action', text)
        self.assertIn('range 120 ft', text)
        self.assertIn('components V,S', text)
        self.assertIn('Three darts hit automatically', text)

    def test_npc_attack_rules_synthesize_riders(self):
        from natural20.utils.oracle import npc_attack_rules
        text = npc_attack_rules({
            'name': 'Unarmed Strike',
            'attack': 9,
            'damage_die': '1d8+4',
            'damage_type': 'slashing',
            'additional_damage': [{'damage_die': '2d6+5',
                                   'damage_type': 'necrotic',
                                   'life_drain': True}],
        })
        self.assertIn('+9 to hit', text)
        self.assertIn('1d8+4 slashing damage', text)
        self.assertIn('2d6+5', text)
        self.assertIn('life drain', text)

    def test_second_wind_rules_use_the_engine_die(self):
        from natural20.actions.second_wind_action import SecondWindAction
        from natural20.utils.oracle import option_rules

        session = Session(root_path='tests/fixtures',
                          event_manager=EventManager())
        map_ = Map(session, 'entryway')
        battle = Battle(session, map_)
        pc = map_.entity_by_uid('gomerin')
        battle.add(pc, 'a')
        battle.start()
        text = option_rules(SecondWindAction(session, pc, 'second_wind'))
        self.assertIn('Second Wind (bonus action', text)
        self.assertIn('hit points', text)
        self.assertNotIn('advantage on attacks', text)


class TestStrategistOrdersRender(unittest.TestCase):
    """The planner state renderer includes the stored orders block."""

    def setUp(self):
        random.seed(4)
        self.session = Session(root_path='tests/fixtures',
                               event_manager=EventManager())
        self.map = Map(self.session, 'entryway')
        self.battle = Battle(self.session, self.map)
        self.goblin = self.session.npc('goblin')
        self.battle.add(self.goblin, 'b')
        self.battle.start()

    def test_block_present_when_orders_set(self):
        set_strategist_orders(self.battle, self.goblin, "1. attack\nReaction: hold")
        state = JevActionPlanner(None)._render_state(self.battle, self.goblin)
        self.assertIn("commander's orders", state)
        self.assertIn('Reaction: hold', state)

    def test_absent_without_orders(self):
        state = JevActionPlanner(None)._render_state(self.battle, self.goblin)
        self.assertNotIn("commander's orders", state)

    def test_capped(self):
        set_strategist_orders(self.battle, self.goblin, '\n'.join(
            f'{i}. step with {chr(97 + i % 26)}' * 8 for i in range(40)))
        state = JevActionPlanner(None)._render_state(self.battle, self.goblin)
        order_lines = [ln for ln in state.splitlines() if '. step' in ln]
        self.assertLessEqual(len(order_lines), 16)


if __name__ == '__main__':
    unittest.main()

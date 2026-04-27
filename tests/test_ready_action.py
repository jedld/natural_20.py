"""Tests for the engine-level Ready (Hold) action."""

import random
import unittest

from natural20.battle import Battle
from natural20.map import Map
from natural20.session import Session
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.actions.move_action import MoveAction
from natural20.actions.ready_action import ReadyAction
from natural20.ready_action import (
    ReadyActionState,
    normalize_trigger,
    normalize_action_spec,
    evaluate_trigger,
)


def _make_session():
    em = EventManager()
    em.standard_cli()
    return Session(root_path='tests/fixtures', event_manager=em)


class TestReadyActionStateHelpers(unittest.TestCase):
    def test_normalize_trigger_defaults(self):
        trig = normalize_trigger(None)
        self.assertEqual(trig['event'], 'movement')
        self.assertEqual(trig['condition'], 'always')
        self.assertEqual(trig['subject_filter'], 'enemies')
        self.assertEqual(trig['range_ft'], 5)

    def test_normalize_trigger_unknown_event_falls_back(self):
        trig = normalize_trigger({'event': 'nuclear_strike', 'subject_filter': 'space'})
        self.assertEqual(trig['event'], 'movement')
        self.assertEqual(trig['subject_filter'], 'enemies')

    def test_normalize_action_spec_attack(self):
        spec = normalize_action_spec({'kind': 'attack', 'weapon': 'longsword'})
        self.assertEqual(spec['kind'], 'attack')
        self.assertEqual(spec['weapon'], 'longsword')

    def test_normalize_action_spec_use_item(self):
        spec = normalize_action_spec({
            'kind': 'use_item',
            'item': 'healing_potion',
            'target': 'ally-uid-1',
        })
        self.assertEqual(spec['kind'], 'use_item')
        self.assertEqual(spec['item'], 'healing_potion')
        self.assertEqual(spec['target_uid'], 'ally-uid-1')

    def test_state_round_trip(self):
        state = ReadyActionState(
            entity_uid='u1', description='if goblin nears me, swing',
            trigger={'event': 'movement', 'condition': 'adjacent_to_self',
                     'subject_filter': 'enemies', 'subject_uids': [], 'range_ft': 5,
                     'description': ''},
            action_spec={'kind': 'attack', 'weapon': 'vicious_rapier',
                         'description': '', 'target_uid': None},
            declared_round=2,
        )
        restored = ReadyActionState.from_dict(state.to_dict())
        self.assertEqual(restored, state)


class TestReadyActionInBattle(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = _make_session()
        self.map = Map(self.session, 'tests/fixtures/battle_sim.yml')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin', {'name': 'g'})
        self.battle.add(self.fighter, 'a', position=(0, 0), token='F')
        self.battle.add(self.goblin, 'b', position=(0, 5), token='g')
        self.fighter.reset_turn(self.battle)
        self.goblin.reset_turn(self.battle)
        self.battle.start()

    def _declare_ready(self, trigger=None, action_spec=None,
                       description='if a goblin steps next to me, attack'):
        ready = ReadyAction(
            self.session, self.fighter, 'ready',
            opts={
                'description': description,
                'trigger': trigger or {
                    'event': 'movement', 'condition': 'adjacent_to_self',
                    'subject_filter': 'enemies',
                },
                'action_spec': action_spec or {
                    'kind': 'attack', 'weapon': 'vicious_rapier',
                },
            },
        )
        ready.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(ready)
        return ready

    def test_declare_consumes_action_and_registers_state(self):
        actions_before = self.fighter.total_actions(self.battle)
        self.assertGreater(actions_before, 0)
        self._declare_ready()
        self.assertEqual(self.fighter.total_actions(self.battle), actions_before - 1)
        state = self.battle.ready_action_for(self.fighter)
        self.assertIsNotNone(state)
        self.assertEqual(state.trigger['event'], 'movement')
        self.assertEqual(state.action_spec['kind'], 'attack')

    def test_can_requires_action_and_reaction(self):
        self.assertTrue(ReadyAction.can(self.fighter, self.battle))
        # Spend the reaction; can() should refuse.
        self.battle.consume(self.fighter, 'reaction')
        self.assertFalse(ReadyAction.can(self.fighter, self.battle))

    def test_movement_trigger_fires_attack_and_consumes_reaction(self):
        self._declare_ready()
        # Resolver replacement: don't actually run AttackAction; just record.
        fired = {}

        def resolver(state, event_name, payload, battle, owner):
            fired['state'] = state
            fired['event'] = event_name
            fired['source'] = payload.get('source')
            return None  # no-op fizzle so we don't depend on full attack pipeline

        self.battle.set_ready_action_resolver(resolver)

        # Move the goblin adjacent to the fighter.
        self.map.move_to(self.goblin, 1, 0, self.battle)
        # Trigger event uses the same path Battle.commit takes on a move.
        self.battle.trigger_event('movement', self.goblin, {'move_path': [(0, 5), (1, 0)]})

        self.assertIn('state', fired)
        self.assertIs(fired['source'], self.goblin)
        # State now expired and removed.
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_default_resolver_executes_attack_as_reaction(self):
        # Place goblin adjacent so the attack pipeline can resolve.
        self.map.move_to(self.goblin, 1, 0, self.battle)
        self._declare_ready()
        reactions_before = self.fighter.total_reactions(self.battle)
        self.assertGreaterEqual(reactions_before, 1)

        random.seed(1337)
        # Fire the trigger. The default resolver builds an AttackAction with
        # ``as_reaction=True`` against the goblin, which consumes the
        # fighter's reaction.
        self.battle.trigger_event('movement', self.goblin,
                                  {'move_path': [(1, 0)]})

        self.assertEqual(self.fighter.total_reactions(self.battle),
                         reactions_before - 1)
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_subject_filter_enemies_skips_allies(self):
        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(ally, 'a', position=(2, 2), token='M')
        ally.reset_turn(self.battle)
        self._declare_ready(trigger={
            'event': 'movement', 'condition': 'adjacent_to_self',
            'subject_filter': 'enemies',
        })
        called = []
        self.battle.set_ready_action_resolver(
            lambda *args, **kw: called.append(args) or None)

        # Ally moves adjacent — should NOT fire.
        self.map.move_to(ally, 1, 1, self.battle)
        self.battle.trigger_event('movement', ally,
                                  {'move_path': [(1, 1)]})
        self.assertEqual(called, [])
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))

    def test_start_of_owner_turn_clears_ready(self):
        self._declare_ready()
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))
        # Force the fighter to be the current turn and call start_turn.
        self.battle.current_turn_index = self.battle.combat_order.index(self.fighter)
        self.battle.start_turn()
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_serialization_round_trip_preserves_ready_state(self):
        self._declare_ready()
        data = self.battle.to_dict()
        restored = Battle.from_dict(data)
        state = restored.ready_action_for(self.fighter)
        self.assertIsNotNone(state)
        self.assertEqual(state.action_spec.get('kind'), 'attack')
        self.assertEqual(state.action_spec.get('weapon'), 'vicious_rapier')
        self.assertEqual(state.trigger.get('condition'), 'adjacent_to_self')

    def test_becomes_visible_fires_on_movement_into_view(self):
        # Ready an attack that triggers when an enemy enters line of sight.
        self._declare_ready(trigger={
            'event': 'becomes_visible',
            'subject_filter': 'enemies',
        })
        fired = {}

        def resolver(state, event_name, payload, battle, owner):
            fired['event'] = event_name
            fired['source'] = payload.get('source')
            return None

        self.battle.set_ready_action_resolver(resolver)

        # Patch can_see so the goblin is invisible at its prior position
        # (move_path[0]) but visible at its current position.
        original_can_see = self.map.can_see
        prior_pos = (0, 5)

        def fake_can_see(entity, entity2, *args, **kwargs):
            if entity is self.fighter and entity2 is self.goblin:
                if kwargs.get('entity_2_pos') == prior_pos:
                    return False
                return True
            return original_can_see(entity, entity2, *args, **kwargs)

        self.map.can_see = fake_can_see
        try:
            self.battle.trigger_event('movement', self.goblin,
                                      {'move_path': [prior_pos, (1, 4)]})
        finally:
            self.map.can_see = original_can_see

        self.assertEqual(fired.get('event'), 'becomes_visible')
        self.assertIs(fired.get('source'), self.goblin)
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_becomes_visible_does_not_fire_when_already_visible(self):
        self._declare_ready(trigger={
            'event': 'becomes_visible',
            'subject_filter': 'enemies',
        })
        called = []
        self.battle.set_ready_action_resolver(
            lambda *args, **kw: called.append(args) or None)
        # No can_see patch: open battle_sim has the goblin already visible at
        # both ends of the path, so the visibility transition condition is
        # False and the trigger should not fire.
        self.battle.trigger_event('movement', self.goblin,
                                  {'move_path': [(0, 5), (1, 4)]})
        self.assertEqual(called, [])
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))

    def test_goes_down_bridges_from_make_unconscious(self):
        # Add an ally so the fighter (acting as the readier) can react when
        # *someone else* drops to 0 HP. The trigger semantics are
        # subject_filter='allies'.
        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(ally, 'a', position=(1, 1), token='M')
        ally.reset_turn(self.battle)

        self._declare_ready(
            description='if my ally goes down, I use my healing potion on them',
            trigger={'event': 'goes_down', 'condition': 'always',
                     'subject_filter': 'allies'},
            action_spec={'kind': 'use_item', 'item': 'healing_potion'},
        )

        fired = {}

        def resolver(state, event_name, payload, battle, owner):
            fired['event'] = event_name
            fired['source'] = payload.get('source')
            fired['kind'] = state.action_spec.get('kind')
            fired['item'] = state.action_spec.get('item')
            return None  # fizzle so we don't depend on the full use_item pipeline

        self.battle.set_ready_action_resolver(resolver)

        # Ally drops to 0 HP -- ``make_unconscious`` emits the
        # event_manager 'unconscious' event, which the Battle bridge maps
        # into a 'goes_down' trigger.
        ally.make_unconscious()

        self.assertEqual(fired.get('event'), 'goes_down')
        self.assertIs(fired.get('source'), ally)
        self.assertEqual(fired.get('kind'), 'use_item')
        self.assertEqual(fired.get('item'), 'healing_potion')
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_goes_down_default_resolver_drinks_healing_potion(self):
        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        # Place adjacent so the 5 ft range check on the potion succeeds.
        self.battle.add(ally, 'a', position=(1, 1), token='M')
        ally.reset_turn(self.battle)

        self._declare_ready(
            description='if an ally drops, I feed them my healing potion',
            trigger={'event': 'goes_down', 'condition': 'always',
                     'subject_filter': 'allies'},
            action_spec={'kind': 'use_item', 'item': 'healing_potion'},
        )

        reactions_before = self.fighter.total_reactions(self.battle)
        # Ally takes lethal damage to register as 'unconscious'.
        random.seed(99)
        ally.make_unconscious()

        # Reaction was consumed (potion fired as a reaction, not an action).
        self.assertEqual(self.fighter.total_reactions(self.battle),
                         max(0, reactions_before - 1))
        # Readied state cleared after the reaction fires.
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_on_command_fires_with_phrase_match(self):
        self._declare_ready(
            description="when my master shouts 'now', I attack",
            trigger={'event': 'on_command', 'subject_filter': 'allies',
                     'command_phrase': 'now'},
        )
        fired = {}

        def resolver(state, event_name, payload, battle, owner):
            fired['event'] = event_name
            fired['message'] = (payload or {}).get('message')
            return None

        self.battle.set_ready_action_resolver(resolver)

        # An ally speaks the command word -- should fire.
        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(ally, 'a', position=(2, 2), token='M')
        ally.reset_turn(self.battle)
        self.battle.trigger_event('on_command', ally,
                                  {'target': ally, 'message': 'Strike NOW!'})

        self.assertEqual(fired.get('event'), 'on_command')
        self.assertEqual(fired.get('message'), 'Strike NOW!')
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_on_command_does_not_fire_without_phrase(self):
        self._declare_ready(
            description="on the word 'fireball'",
            trigger={'event': 'on_command', 'subject_filter': 'allies',
                     'command_phrase': 'fireball'},
        )
        called = []
        self.battle.set_ready_action_resolver(
            lambda *a, **k: called.append(a) or None)

        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(ally, 'a', position=(2, 2), token='M')
        ally.reset_turn(self.battle)
        self.battle.trigger_event('on_command', ally,
                                  {'target': ally, 'message': 'never mind'})

        self.assertEqual(called, [])
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))

    def test_object_interaction_bridges_door_open(self):
        self._declare_ready(
            description='shoot whoever opens that door',
            trigger={'event': 'object_interaction', 'subject_filter': 'any',
                     'object_action': 'open'},
        )
        fired = {}

        def resolver(state, event_name, payload, battle, owner):
            fired['event'] = event_name
            fired['sub_type'] = (payload or {}).get('sub_type')
            fired['source'] = (payload or {}).get('source')
            return None

        self.battle.set_ready_action_resolver(resolver)

        # Simulate the event_manager broadcast for a door being opened. The
        # Battle bridge should translate it into an 'object_interaction'
        # trigger event.
        self.session.event_manager.received_event({
            'source': self.goblin,
            'target': self.fighter,  # stand-in for the door object
            'event': 'object_interaction',
            'sub_type': 'open',
            'result': 'success',
            'reason': 'Door opened',
        })

        self.assertEqual(fired.get('event'), 'object_interaction')
        self.assertEqual(fired.get('sub_type'), 'open')
        self.assertIs(fired.get('source'), self.goblin)
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_object_interaction_filters_by_action(self):
        self._declare_ready(
            description='only when the door OPENS',
            trigger={'event': 'object_interaction', 'subject_filter': 'any',
                     'object_action': 'open'},
        )
        called = []
        self.battle.set_ready_action_resolver(
            lambda *a, **k: called.append(a) or None)

        # A 'close' event must not fire an 'open'-scoped readied action.
        self.session.event_manager.received_event({
            'source': self.goblin,
            'target': self.fighter,
            'event': 'object_interaction',
            'sub_type': 'close',
            'result': 'success',
        })

        self.assertEqual(called, [])
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))

    def test_ally_attacks_fires_when_ally_attacks_enemy(self):
        # Add a friendly ally on team 'a' to act as the attacker.
        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(ally, 'a', position=(1, 0), token='M')
        ally.reset_turn(self.battle)

        self._declare_ready(
            description='when my ally attacks the goblin, I attack it too',
            trigger={'event': 'ally_attacks', 'subject_filter': 'allies'},
        )
        fired = {}

        def resolver(state, event_name, payload, battle, owner):
            fired['event'] = event_name
            fired['source'] = (payload or {}).get('source')
            fired['target'] = (payload or {}).get('target')
            return None

        self.battle.set_ready_action_resolver(resolver)

        # Simulate ally attacking the goblin.
        self.battle.trigger_event('ally_attacks', ally,
                                  {'target': self.goblin,
                                   'attack_name': 'shortsword'})

        self.assertEqual(fired.get('event'), 'ally_attacks')
        self.assertIs(fired.get('source'), ally)
        self.assertIs(fired.get('target'), self.goblin)
        self.assertIsNone(self.battle.ready_action_for(self.fighter))

    def test_ally_attacks_does_not_fire_for_self(self):
        # The fighter itself attacking the goblin must not fire its own
        # ally_attacks readied action.
        self._declare_ready(
            description='piling on',
            trigger={'event': 'ally_attacks', 'subject_filter': 'allies'},
        )
        called = []
        self.battle.set_ready_action_resolver(
            lambda *a, **k: called.append(a) or None)

        self.battle.trigger_event('ally_attacks', self.fighter,
                                  {'target': self.goblin})
        self.assertEqual(called, [])
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))

    def test_ally_attacks_filters_by_attack_target_uid(self):
        ally = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.battle.add(ally, 'a', position=(1, 0), token='M')
        ally.reset_turn(self.battle)
        # Add a second goblin that is NOT the focus.
        other_goblin = self.session.npc('goblin', {'name': 'g2'})
        self.battle.add(other_goblin, 'b', position=(2, 5), token='G')
        other_goblin.reset_turn(self.battle)

        self._declare_ready(
            description='attack the goblin my ally focuses',
            trigger={'event': 'ally_attacks', 'subject_filter': 'allies',
                     'attack_target_uid': self.goblin.entity_uid},
        )
        called = []
        self.battle.set_ready_action_resolver(
            lambda *a, **k: called.append(a) or None)

        # Ally attacks the OTHER goblin -- should NOT fire.
        self.battle.trigger_event('ally_attacks', ally,
                                  {'target': other_goblin})
        self.assertEqual(called, [])
        self.assertIsNotNone(self.battle.ready_action_for(self.fighter))

        # Ally attacks the focused goblin -- should fire.
        self.battle.trigger_event('ally_attacks', ally,
                                  {'target': self.goblin})
        self.assertEqual(len(called), 1)
        self.assertIsNone(self.battle.ready_action_for(self.fighter))


class TestReadyHeldSpellRAW(unittest.TestCase):
    """Verify the readied-spell RAW gates per PHB p.193:

    * Slot is paid up-front when the spell is readied.
    * Concentration begins on a held-spell marker.
    * Only spells with casting_time '1:action' may be readied.
    * If concentration breaks, the held spell dissipates (slot stays spent).
    """

    def setUp(self):
        random.seed(7000)
        self.session = _make_session()
        self.map = Map(self.session, 'tests/fixtures/battle_sim.yml')
        self.battle = Battle(self.session, self.map)
        self.mage = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.goblin = self.session.npc('goblin', {'name': 'g'})
        self.battle.add(self.mage, 'a', position=(0, 0), token='M')
        self.battle.add(self.goblin, 'b', position=(0, 5), token='g')
        self.mage.reset_turn(self.battle)
        self.goblin.reset_turn(self.battle)
        self.battle.start()

    def _ready_spell(self, spell_slug, target=None, description=None):
        action_spec = {'kind': 'spell', 'spell': spell_slug}
        if target is not None:
            action_spec['target_uid'] = getattr(target, 'entity_uid', None)
        ready = ReadyAction(
            self.session, self.mage, 'ready',
            opts={
                'description': description or f"hold {spell_slug}",
                'trigger': {'event': 'movement',
                            'condition': 'adjacent_to_self',
                            'subject_filter': 'enemies'},
                'action_spec': action_spec,
            },
        )
        ready.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(ready)
        return ready

    def test_readying_spell_consumes_slot_at_ready_time(self):
        slots_before = self.mage.spell_slots_count(1, 'wizard')
        self.assertGreater(slots_before, 0)
        self._ready_spell('magic_missile', target=self.goblin)
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'),
                         slots_before - 1)
        state = self.battle.ready_action_for(self.mage)
        self.assertIsNotNone(state)
        self.assertTrue(state.action_spec.get('_slot_pre_consumed'))

    def test_readying_spell_starts_held_concentration(self):
        from natural20.ready_action import HeldSpellEffect
        self.assertIsNone(getattr(self.mage, 'concentration', None))
        self._ready_spell('magic_missile', target=self.goblin)
        held = getattr(self.mage, 'concentration', None)
        self.assertIsInstance(held, HeldSpellEffect)
        self.assertEqual(held.spell_slug, 'magic_missile')
        self.assertTrue(getattr(held, 'is_held_spell', False))

    def test_readying_non_action_spell_is_rejected(self):
        slots_before = self.mage.spell_slots_count(1, 'wizard')
        actions_before = self.mage.total_actions(self.battle)
        events = []
        self.session.event_manager.register_event_listener(
            ['ready_action_invalid'], lambda e: events.append(e))
        self._ready_spell('shield', target=self.mage)
        # Slot NOT consumed, action NOT consumed, no readied state.
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'),
                         slots_before)
        self.assertEqual(self.mage.total_actions(self.battle),
                         actions_before)
        self.assertIsNone(self.battle.ready_action_for(self.mage))
        # Concentration not started.
        self.assertIsNone(getattr(self.mage, 'concentration', None))
        # An invalid-ready event was emitted with a reason mentioning
        # casting time.
        self.assertTrue(any(
            'casting_time' in str(ev.get('reason', '')).lower()
            or '1-action' in str(ev.get('reason', '')).lower()
            for ev in events
        ))

    def test_readied_spell_dissipates_when_concentration_breaks(self):
        self._ready_spell('magic_missile', target=self.goblin)
        slots_after_ready = self.mage.spell_slots_count(1, 'wizard')
        self.assertIsNotNone(self.battle.ready_action_for(self.mage))

        dissipated = []
        self.session.event_manager.register_event_listener(
            ['ready_action_dissipated'], lambda e: dissipated.append(e))

        # Damage-induced concentration loss is modeled here as a direct
        # drop_concentration; the bridge listens to the 'concentration_end'
        # event regardless of cause.
        self.mage.drop_concentration()

        # The readied state was cleared.
        self.assertIsNone(self.battle.ready_action_for(self.mage))
        # The dissipation event fired.
        self.assertTrue(dissipated)
        # RAW: the slot is NOT refunded.
        self.assertEqual(self.mage.spell_slots_count(1, 'wizard'),
                         slots_after_ready)

    def test_readying_new_concentration_drops_prior_one(self):
        from natural20.ready_action import HeldSpellEffect

        class FakeEffect:
            is_held_spell = False
            label_text = 'Bless (fake)'

            def label(self):
                return self.label_text

        prior = FakeEffect()
        self.mage.concentration_on(prior)
        self.assertIs(self.mage.concentration, prior)

        self._ready_spell('magic_missile', target=self.goblin)
        # Prior concentration was replaced by the held-spell marker.
        self.assertIsInstance(self.mage.concentration, HeldSpellEffect)


class TestEvaluateTrigger(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        self.session = _make_session()
        self.map = Map(self.session, 'tests/fixtures/battle_sim.yml')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin', {'name': 'g'})
        self.battle.add(self.fighter, 'a', position=(0, 0))
        self.battle.add(self.goblin, 'b', position=(2, 2))
        self.fighter.reset_turn(self.battle)
        self.goblin.reset_turn(self.battle)

    def _state(self, **trigger):
        return ReadyActionState(
            entity_uid=str(self.fighter.entity_uid),
            trigger=normalize_trigger(trigger),
            action_spec=normalize_action_spec({'kind': 'attack'}),
        )

    def test_within_range_respects_distance(self):
        state = self._state(event='movement', condition='within_range',
                            subject_filter='enemies', range_ft=10)
        # Goblin at (2,2) → Chebyshev 2 squares × 5ft = 10ft, in range.
        self.assertTrue(evaluate_trigger(
            state, 'movement', {'source': self.goblin}, self.battle, self.fighter))
        # Move farther than 10ft.
        self.map.move_to(self.goblin, 5, 5, self.battle)
        self.assertFalse(evaluate_trigger(
            state, 'movement', {'source': self.goblin}, self.battle, self.fighter))

    def test_event_mismatch_is_false(self):
        state = self._state(event='movement', condition='always')
        self.assertFalse(evaluate_trigger(
            state, 'start_of_turn', {'source': self.goblin},
            self.battle, self.fighter))


if __name__ == '__main__':
    unittest.main()

import unittest
import random
from natural20.actions.move_action import MoveAction
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.item_library.pit_trap import PitTrap


class TestPitTrap(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.map = Map(self.session, 'traps')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='F')
        self.battle.start()
        self.fighter.reset_turn(self.battle)

    def _get_pit_trap(self):
        """Find the PitTrap object on the map."""
        for obj in self.map.objects_at(1, 3, reveal_concealed=True):
            if isinstance(obj, PitTrap):
                return obj
        return None

    def test_pit_trap_exists_on_map(self):
        trap = self._get_pit_trap()
        self.assertIsNotNone(trap)
        self.assertFalse(trap.activated)

    def test_pit_trap_is_concealed_before_activation(self):
        trap = self._get_pit_trap()
        self.assertTrue(trap.concealed())
        self.assertFalse(trap.jump_required())

    def test_pit_trap_is_passable(self):
        trap = self._get_pit_trap()
        self.assertTrue(trap.passable())

    def test_pit_trap_is_placeable_before_activation(self):
        trap = self._get_pit_trap()
        self.assertTrue(trap.placeable())

    def test_movement_onto_trap_activates_it(self):
        """Entity moving onto a concealed pit trap should trigger it."""
        trap = self._get_pit_trap()
        self.assertFalse(trap.activated)

        initial_hp = self.fighter.hp()

        # Build a move action to walk onto the pit trap at (1, 3)
        action = MoveAction(self.session, self.fighter, 'move')
        action.move_path = [[0, 3], [1, 3]]
        action.resolve(self.session, self.map, {'battle': self.battle})

        # Verify the result contains damage, state, and cancel_move types
        result_types = [r['type'] for r in action.result]
        self.assertIn('move', result_types)
        self.assertIn('damage', result_types)
        self.assertIn('state', result_types)
        self.assertIn('cancel_move', result_types)

        # Commit the action to apply effects
        self.battle.commit(action)

        # Trap should now be activated
        self.assertTrue(trap.activated)

        # Entity should have taken damage
        self.assertLess(self.fighter.hp(), initial_hp)

    def test_trap_visible_after_activation(self):
        """After activation, the trap is no longer concealed."""
        trap = self._get_pit_trap()

        # Trigger the trap
        action = MoveAction(self.session, self.fighter, 'move')
        action.move_path = [[0, 3], [1, 3]]
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)

        self.assertFalse(trap.concealed())
        self.assertTrue(trap.jump_required())
        self.assertFalse(trap.placeable())

    def test_movement_cancelled_after_trap(self):
        """Movement beyond the trap square should be cancelled."""
        trap = self._get_pit_trap()

        # Try to move through the trap to (2, 3)
        action = MoveAction(self.session, self.fighter, 'move')
        action.move_path = [[0, 3], [1, 3], [2, 3]]
        action.resolve(self.session, self.map, {'battle': self.battle})

        # The move results should only include movement up to the trap square
        move_results = [r for r in action.result if r['type'] == 'move']
        for move_result in move_results:
            last_pos = move_result['position']
            # Entity should not have reached (2, 3) — they stop at (1, 3)
            self.assertNotEqual(list(last_pos), [2, 3])

        self.battle.commit(action)
        self.assertTrue(trap.activated)

    def test_flying_entity_does_not_trigger_trap(self):
        """Flying entities should not trigger pit traps."""
        trap = self._get_pit_trap()

        # Make the fighter fly
        self.fighter.flying = True

        initial_hp = self.fighter.hp()

        action = MoveAction(self.session, self.fighter, 'move')
        action.move_path = [[0, 3], [1, 3]]
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)

        # Trap should NOT be activated
        self.assertFalse(trap.activated)
        # No damage taken
        self.assertEqual(self.fighter.hp(), initial_hp)

    def test_already_activated_trap_does_not_retrigger(self):
        """Walking over an already-activated trap should not deal damage again."""
        trap = self._get_pit_trap()

        # Activate the trap first
        action = MoveAction(self.session, self.fighter, 'move')
        action.move_path = [[0, 3], [1, 3]]
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertTrue(trap.activated)

        hp_after_first = self.fighter.hp()

        # Reset turn for more movement
        self.fighter.reset_turn(self.battle)

        # Move away then back
        action2 = MoveAction(self.session, self.fighter, 'move')
        action2.move_path = [list(self.map.position_of(self.fighter)), [0, 3]]
        action2.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action2)

        self.fighter.reset_turn(self.battle)

        action3 = MoveAction(self.session, self.fighter, 'move')
        action3.move_path = [[0, 3], [1, 3]]
        action3.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action3)

        # Should not take additional damage (trap already activated)
        self.assertEqual(self.fighter.hp(), hp_after_first)

    def test_area_trigger_handler_returns_correct_structure(self):
        """Direct test of PitTrap.area_trigger_handler return values."""
        trap = self._get_pit_trap()
        results = trap.area_trigger_handler(self.fighter, [1, 3], False)

        self.assertIsNotNone(results)
        self.assertGreaterEqual(len(results), 3)

        types = [r['type'] for r in results]
        self.assertIn('damage', types)
        self.assertIn('state', types)
        self.assertIn('cancel_move', types)

        # Damage result should have the right fields
        damage_result = next(r for r in results if r['type'] == 'damage')
        self.assertEqual(damage_result['source'], trap)
        self.assertEqual(damage_result['target'], self.fighter)
        self.assertIn('damage', damage_result)
        self.assertIn('damage_type', damage_result)

        # State result should set activated
        state_result = next(r for r in results if r['type'] == 'state')
        self.assertEqual(state_result['params'], {'activated': True})

    def test_area_trigger_handler_returns_none_for_wrong_position(self):
        """Trigger handler returns None if entity is not on the trap square."""
        trap = self._get_pit_trap()
        results = trap.area_trigger_handler(self.fighter, [0, 0], False)
        self.assertIsNone(results)

    def test_area_trigger_handler_returns_none_for_flying(self):
        """Trigger handler returns None for flying entities."""
        trap = self._get_pit_trap()
        results = trap.area_trigger_handler(self.fighter, [1, 3], True)
        self.assertIsNone(results)

    def test_jump_over_pit_trap_with_running_start(self):
        """Web UI jump (J key) over a pit trap with a running start should
        clear the trap without activating it.

        This mirrors how the Flask /action endpoint translates the
        ``manual_jump = [takeoff_index, landing_index]`` payload sent by
        the JS client into ``action.jump_index``: only the in-flight
        squares (takeoff+1 .. landing) should be marked as jump squares so
        the takeoff itself still counts as a walked square (granting the
        long-jump running-start budget).
        """
        trap = self._get_pit_trap()
        self.assertFalse(trap.activated)
        initial_hp = self.fighter.hp()

        # Reposition fighter to (3, 3) so they have running room toward the trap at (1, 3).
        self.map.move_to(self.fighter, 3, 3, self.battle)

        # Path: [3,3] (start) -> [2,3] (running step / takeoff) -> [1,3] (jump over trap) -> [0,3] (land)
        move_path = [[3, 3], [2, 3], [1, 3], [0, 3]]
        # JS sends [takeoff_idx, landing_idx]; server should produce
        # in-flight indices [2, 3] (excluding the takeoff at index 1).
        takeoff_idx, landing_idx = 1, 3

        action = MoveAction(self.session, self.fighter, 'move')
        action.move_path = move_path
        action.jump_index = list(range(takeoff_idx + 1, landing_idx + 1))
        action.resolve(self.session, self.map, {'battle': self.battle})
        self.battle.commit(action)

        # Trap must NOT activate and PC must NOT take damage.
        self.assertFalse(trap.activated, "pit trap should not activate when jumped over")
        self.assertEqual(self.fighter.hp(), initial_hp)
        # PC should have landed on the far side.
        self.assertEqual(list(self.map.position_of(self.fighter)), [0, 3])


class TestPitTrapDisarm(unittest.TestCase):
    """5e disarm-trap mechanics for the PitTrap object."""

    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.map = Map(self.session, 'traps')
        self.battle = Battle(self.session, self.map)
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        # Ensure the rogueish elf is carrying their tools so disarm is unlocked.
        self.fighter.add_item('thieves_tools', 1)
        self.battle.add(self.fighter, 'a', position='spawn_point_1', token='F')
        self.battle.start()
        self.fighter.reset_turn(self.battle)

    def _get_pit_trap(self):
        for obj in self.map.objects_at(1, 3, reveal_concealed=True):
            if isinstance(obj, PitTrap):
                return obj
        return None

    def test_disarm_interaction_exposed_when_adjacent(self):
        trap = self._get_pit_trap()
        # Per 5e: a creature must perceive the trap before they can
        # attempt to disarm it. Simulate the fighter spotting it.
        trap.mark_perceived_by(self.fighter)
        # Move the fighter adjacent to the trap (trap is at (1,3); fighter spawns at (0,3)).
        interactions = trap.available_interactions(self.fighter, self.battle)
        self.assertIn('disarm', interactions)
        self.assertFalse(interactions['disarm'].get('disabled'),
                         interactions['disarm'].get('disabled_text'))

    def test_disarm_hidden_until_trap_is_perceived(self):
        trap = self._get_pit_trap()
        # Without spotting the trap the disarm action must not surface,
        # even if the fighter has thieves' tools and is adjacent.
        self.assertFalse(trap.perceived_by_entity(self.fighter))
        interactions = trap.available_interactions(self.fighter, self.battle)
        self.assertNotIn('disarm', interactions)
        # Once revealed (e.g. via a successful Perception/Investigation
        # check) the action becomes available.
        trap.mark_perceived_by(self.fighter)
        interactions = trap.available_interactions(self.fighter, self.battle)
        self.assertIn('disarm', interactions)

    def test_disarm_disabled_without_thieves_tools(self):
        trap = self._get_pit_trap()
        trap.mark_perceived_by(self.fighter)
        # Strip the kit from the fighter.
        self.fighter.deduct_item('thieves_tools')
        interactions = trap.available_interactions(self.fighter, self.battle)
        self.assertTrue(interactions['disarm']['disabled'])
        self.assertEqual(interactions['disarm']['disabled_text'],
                         'object.pit_trap.tools_required')

    def test_successful_disarm_makes_trap_safe(self):
        trap = self._get_pit_trap()
        # Force a guaranteed-success roll: pick a low DC and patch the roll.
        trap.properties['disarm_dc'] = 1
        result = trap.resolve(self.fighter, 'disarm', None, {'battle': self.battle})
        self.assertEqual(result['action'], 'disarm_success')

        trap.use(self.fighter, result, session=self.session)
        self.assertTrue(trap.disarmed)
        self.assertFalse(trap.activated)
        self.assertFalse(trap.concealed())
        # Walking onto a disarmed trap is harmless.
        hp_before = self.fighter.hp()
        triggered = trap.area_trigger_handler(self.fighter, [1, 3], False)
        self.assertIsNone(triggered)
        self.assertEqual(self.fighter.hp(), hp_before)

    def test_failed_disarm_leaves_trap_intact(self):
        trap = self._get_pit_trap()
        # Set DC unreachable so the roll fails by less than the trigger margin.
        trap.properties['disarm_dc'] = 100
        # Patch the d20 to land exactly DC - 1, a normal failure.
        original_lockpick = self.fighter.lockpick

        class _StubRoll:
            def __init__(self, value):
                self._value = value
            def result(self):
                return self._value
            def __str__(self):
                return f"<stub {self._value}>"

        self.fighter.lockpick = lambda battle=None: _StubRoll(99)
        try:
            result = trap.resolve(self.fighter, 'disarm', None, {'battle': self.battle})
        finally:
            self.fighter.lockpick = original_lockpick

        self.assertEqual(result['action'], 'disarm_fail')
        trap.use(self.fighter, result, session=self.session)
        self.assertFalse(trap.disarmed)
        self.assertFalse(trap.activated)

    def test_critical_disarm_failure_triggers_trap(self):
        trap = self._get_pit_trap()
        trap.properties['disarm_dc'] = 100

        class _StubRoll:
            def __init__(self, value):
                self._value = value
            def result(self):
                return self._value
            def __str__(self):
                return f"<stub {self._value}>"

        original_lockpick = self.fighter.lockpick
        self.fighter.lockpick = lambda battle=None: _StubRoll(1)  # fail by 99.
        hp_before = self.fighter.hp()
        try:
            result = trap.resolve(self.fighter, 'disarm', None, {'battle': self.battle})
        finally:
            self.fighter.lockpick = original_lockpick

        self.assertEqual(result['action'], 'disarm_triggered')
        trap.use(self.fighter, result, session=self.session)
        self.assertTrue(trap.activated)
        self.assertFalse(trap.disarmed)
        self.assertLess(self.fighter.hp(), hp_before)

    def test_disarm_persists_through_serialization(self):
        trap = self._get_pit_trap()
        trap.disarmed = True
        data = trap.to_dict()
        data['session'] = self.session
        restored = PitTrap.from_dict(data)
        self.assertTrue(restored.disarmed)


if __name__ == '__main__':
    unittest.main()

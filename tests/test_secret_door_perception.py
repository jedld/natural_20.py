"""
Unit tests for secret door perception checks using the Death House 3rd floor map.

Tests cover:
- can_see returns correct values based on passive/active perception vs DC
- Look action reveals secret door when perception beats DC
- JsonRenderer shows/hides secret door based on perception and vision
"""
import unittest
import random
from unittest.mock import patch, MagicMock

from natural20.session import Session
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.web.json_renderer import JsonRenderer
from natural20.actions.look_action import LookAction
from natural20.utils.action_builder import autobuild
from natural20.die_roll import DieRoll


class CaptureOutputLogger:
    def __init__(self):
        self.entries = []

    def set_event_context(self, event):
        return None

    def clear_event_context(self):
        return None

    def log(self, event_msg, event=None, visibility=None):
        self.entries.append({
            'message': event_msg,
            'event': event,
            'visibility': visibility,
        })


class TestSecretDoorPerceptionDeathHouse(unittest.TestCase):
    """Test secret door perception on the Death House 3rd floor map."""

    def setUp(self):
        random.seed(7000)
        self.output_logger = CaptureOutputLogger()
        self.event_manager = EventManager(output_logger=self.output_logger)
        self.event_manager.standard_cli()
        self.session = Session(root_path='user_levels/death_house', event_manager=self.event_manager)
        self.map = self.session.maps['3rd_floor']

        # Find the secret door
        self.secret_door = None
        self.secret_door_pos = None
        for obj, pos in self.map.interactable_objects.items():
            if obj.secret() and obj.secret_perception_dc():
                self.secret_door = obj
                self.secret_door_pos = pos
                break

        self.assertIsNotNone(self.secret_door, "Secret door should exist on 3rd floor map")
        self.assertEqual(self.secret_door.name, 'attic_secret_door')
        self.assertEqual(self.secret_door_pos, [4, 8])
        self.assertEqual(self.secret_door.secret_perception_dc(), 15)
        self.assertTrue(self.secret_door.kind_of_door())

    def _load_character(self, char_file, uid, pos_x, pos_y):
        """Load a character and place on the map."""
        pc = PlayerCharacter.load(self.session, char_file, override={'entity_uid': uid})
        self.map.add(pc, pos_x, pos_y, group='a')
        return pc

    # --- can_see tests ---

    def test_can_see_fails_with_low_passive_perception(self):
        """Passive perception below DC should not see the secret door."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertLess(pc.passive_perception(), 15)
        self.assertFalse(self.map.can_see(pc, self.secret_door))

    def test_can_see_succeeds_with_high_passive_perception(self):
        """Passive perception >= DC should see the secret door."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        with patch.object(pc, 'passive_perception', return_value=15):
            self.assertTrue(self.map.can_see(pc, self.secret_door))

    def test_can_see_succeeds_with_active_perception_beating_dc(self):
        """Active perception >= DC should see the secret door."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(self.map.can_see(pc, self.secret_door, active_perception=16))

    def test_can_see_fails_with_active_perception_below_dc(self):
        """Active perception < DC (and passive < DC) should not see."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertFalse(self.map.can_see(pc, self.secret_door, active_perception=14))

    def test_can_see_uses_max_of_passive_and_active(self):
        """can_see uses max(passive, active) to check against DC."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        # passive=13, active=14 → max=14 < 15 → False
        self.assertFalse(self.map.can_see(pc, self.secret_door, active_perception=14))
        # passive=13, active=15 → max=15 >= 15 → True
        self.assertTrue(self.map.can_see(pc, self.secret_door, active_perception=15))

    def test_can_see_at_exact_dc_boundary(self):
        """Perception exactly at DC should succeed (>=, not >)."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        # Below DC first: revealing the door requires a successful check; if we
        # called can_see with PP>=DC first, perception_results would persist and
        # the low-PP case would still see the door as already revealed.
        with patch.object(pc, 'passive_perception', return_value=14):
            self.assertFalse(self.map.can_see(pc, self.secret_door))
        with patch.object(pc, 'passive_perception', return_value=15):
            self.assertTrue(self.map.can_see(pc, self.secret_door))

    # --- Renderer tests ---

    def test_renderer_hides_secret_door_low_perception_darkvision(self):
        """Darkvision character with low perception should NOT see secret door in render."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(pc.darkvision(30))
        self.assertLess(pc.passive_perception(), 15)

        renderer = JsonRenderer(self.map, None, padding=[0, 0])
        result = renderer.render(entity_pov=[pc])
        # y is inverted in renderer: index = height-1-y = 13-1-8 = 4
        tile = result[4][4]
        self.assertEqual(tile['x'], 4)
        self.assertEqual(tile['y'], 8)
        self.assertTrue(tile['line_of_sight'])
        self.assertEqual(tile.get('objects', []), [])

    def test_renderer_shows_secret_door_high_perception_darkvision(self):
        """Darkvision character with high perception should see secret door in render."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(pc.darkvision(30))

        with patch.object(pc, 'passive_perception', return_value=16):
            renderer = JsonRenderer(self.map, None, padding=[0, 0])
            result = renderer.render(entity_pov=[pc])
            tile = result[4][4]
            self.assertEqual(tile['x'], 4)
            self.assertEqual(tile['y'], 8)
            self.assertTrue(tile['line_of_sight'])
            objects = tile.get('objects', [])
            self.assertTrue(len(objects) > 0, "Secret door should be visible with high perception")
            self.assertEqual(objects[0]['name'], 'attic_secret_door')
            self.assertTrue(objects[0]['secret_door_marker'])
            self.assertFalse(objects[0]['secret_door_marker_opened'])
            self.assertEqual(
                objects[0]['secret_door_marker_edges'],
                {'top': True, 'right': False, 'bottom': True, 'left': False}
            )

    def test_renderer_does_not_mark_regular_corner_doors_as_secret(self):
        """Doors with secret_door type metadata but no actual secret state should not show the marker."""
        renderer = JsonRenderer(self.map, None, padding=[0, 0])
        result = renderer.render()
        tile = result[2][5]
        objects = tile.get('objects', [])
        self.assertTrue(len(objects) > 0)
        self.assertEqual(objects[0]['name'], 'corner_door_rt')
        self.assertFalse(objects[0]['secret_door_marker'])

    def test_renderer_shows_door_after_reveal(self):
        """After secret door is revealed (is_secret=False), it should always render."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(pc.darkvision(30))

        # Before reveal: not visible (perception 13 < DC 15)
        renderer = JsonRenderer(self.map, None, padding=[0, 0])
        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        self.assertEqual(tile.get('objects', []), [])

        # Reveal the door
        self.secret_door.is_secret = False

        # After reveal: visible regardless of perception
        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        objects = tile.get('objects', [])
        self.assertTrue(len(objects) > 0, "Revealed door should always be visible")
        self.assertEqual(objects[0]['name'], 'attic_secret_door')
        self.assertTrue(objects[0]['secret_door_marker'])

    def test_renderer_with_light_and_high_perception(self):
        """Non-darkvision character with light and high perception should see secret door."""
        pc = self._load_character('characters/halfling_rogue.yml', 'test_rogue', 3, 8)
        self.assertFalse(pc.darkvision(30))

        # Add light to the area
        self.map._light_map[3][8] = 1.0
        self.map._light_map[4][8] = 1.0

        with patch.object(pc, 'passive_perception', return_value=16):
            renderer = JsonRenderer(self.map, None, padding=[0, 0])
            result = renderer.render(entity_pov=[pc])
            tile = result[4][4]
            self.assertEqual(tile['x'], 4)
            self.assertEqual(tile['y'], 8)
            objects = tile.get('objects', [])
            self.assertTrue(len(objects) > 0, "Should see secret door with light + high perception")
            self.assertEqual(objects[0]['name'], 'attic_secret_door')

    def test_renderer_with_light_and_low_perception(self):
        """Non-darkvision character with light but low perception should NOT see secret door."""
        pc = self._load_character('characters/halfling_rogue.yml', 'test_rogue', 3, 8)
        self.assertFalse(pc.darkvision(30))
        self.assertLess(pc.passive_perception(), 15)

        # Add light to the area
        self.map._light_map[3][8] = 1.0
        self.map._light_map[4][8] = 1.0

        renderer = JsonRenderer(self.map, None, padding=[0, 0])
        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        self.assertEqual(tile['x'], 4)
        self.assertEqual(tile['y'], 8)
        self.assertEqual(tile.get('objects', []), [])

    def test_opened_secret_door_is_auto_discovered_when_seen(self):
        """Opened secret doors should become discovered for the viewer without a perception check."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(pc.darkvision(30))
        self.assertLess(pc.passive_perception(), 15)
        self.assertTrue(self.secret_door.is_secret)

        self.secret_door.open()

        self.assertTrue(self.map.can_see(pc, self.secret_door))
        self.assertIn(pc, self.secret_door.perception_results)
        self.assertTrue(self.secret_door.perception_results[pc]['revealed'])

        renderer = JsonRenderer(self.map, None, padding=[0, 0])
        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        objects = tile.get('objects', [])
        self.assertTrue(len(objects) > 0, "Opened secret door should render once seen")
        self.assertEqual(objects[0]['name'], 'attic_secret_door')
        self.assertTrue(objects[0]['secret_door_marker'])
        self.assertTrue(objects[0]['secret_door_marker_opened'])

    def test_first_secret_door_discovery_logs_custom_object_message_once(self):
        """First-time secret door discovery should add one viewer-scoped combat log entry."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)

        with patch.object(pc, 'passive_perception', return_value=16):
            self.assertTrue(self.map.can_see(pc, self.secret_door))
            renderer = JsonRenderer(self.map, None, padding=[0, 0])
            renderer.render(entity_pov=[pc])

        discovery_logs = [
            entry for entry in self.output_logger.entries
            if entry['message'] == 'You notice a secret door hidden in the wall.'
        ]
        self.assertEqual(len(discovery_logs), 1)
        self.assertEqual(discovery_logs[0]['visibility']['kind'], 'entity_only')
        self.assertEqual(discovery_logs[0]['visibility']['entity_uids'], [pc.entity_uid])

    def test_secret_door_discovery_uses_map_level_message_when_object_has_none(self):
        """Map-level metadata should provide the fallback discovery message."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.secret_door.properties.pop('secret_message', None)
        self.map.properties['map']['secret_message'] = '{viewer} spots a hidden passage near {door}.'

        with patch.object(pc, 'passive_perception', return_value=16):
            self.assertTrue(self.map.can_see(pc, self.secret_door))

        self.assertIn(
            f'{pc.label()} spots a hidden passage near {self.secret_door.label()}.',
            [entry['message'] for entry in self.output_logger.entries]
        )

    def test_renderer_keeps_secret_door_marker_after_discovery_out_of_current_los(self):
        """Once discovered, a secret door marker should keep rendering for that viewer even under fog."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)

        with patch.object(pc, 'passive_perception', return_value=16):
            renderer = JsonRenderer(self.map, None, padding=[0, 0])
            result = renderer.render(entity_pov=[pc])
            tile = result[4][4]
            objects = tile.get('objects', [])
            self.assertTrue(len(objects) > 0)
            self.assertTrue(self.secret_door.perception_results[pc]['revealed'])

        self.map.move_to(pc, 0, 0)
        self.assertFalse(self.map.can_see_square(pc, (4, 8)))

        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        objects = tile.get('objects', [])
        self.assertTrue(len(objects) > 0, "Discovered secret door marker should remain visible under fog")
        self.assertTrue(objects[0]['secret_door_marker'])

    # --- Look action tests ---

    def test_look_action_reveals_secret_door_on_high_roll(self):
        """Look action with perception roll >= DC should reveal the secret door."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        battle = Battle(self.session, self.map)
        battle.add(pc, 'a')
        pc.reset_turn(battle)

        self.assertTrue(self.secret_door.is_secret)

        # Mock the perception roll to return a high value (>= DC 15)
        with patch.object(pc, 'perception_check', return_value=DieRoll([20], 0, 20)):
            action = autobuild(self.session, LookAction, pc, battle)[0]
            battle.action(action)
            battle.commit(action)

        # The door should now be revealed
        self.assertFalse(self.secret_door.is_secret)
        # Perception result should be stored
        self.assertIn(pc, self.secret_door.perception_results)
        self.assertTrue(self.secret_door.perception_results[pc]['revealed'])

    def test_look_action_does_not_reveal_on_low_roll(self):
        """Look action with perception roll < DC should NOT reveal the secret door."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        battle = Battle(self.session, self.map)
        battle.add(pc, 'a')
        pc.reset_turn(battle)

        self.assertTrue(self.secret_door.is_secret)

        # Mock the perception roll to return a low value (< DC 15, also below passive 13)
        with patch.object(pc, 'perception_check', return_value=DieRoll([10], 0, 10)):
            action = autobuild(self.session, LookAction, pc, battle)[0]
            battle.action(action)
            battle.commit(action)

        # The door should still be secret
        self.assertTrue(self.secret_door.is_secret)

    def test_look_action_in_dark_with_darkvision_reveals_door(self):
        """Darkvision character in dark map can reveal secret door via Look action."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(pc.darkvision(30))
        self.assertEqual(self.map.light_at(4, 8), 0.0)  # Dark map

        battle = Battle(self.session, self.map)
        battle.add(pc, 'a')
        pc.reset_turn(battle)

        # Mock perception roll >= DC
        with patch.object(pc, 'perception_check', return_value=DieRoll([18], 0, 18)):
            action = autobuild(self.session, LookAction, pc, battle)[0]
            battle.action(action)
            battle.commit(action)

        # Door should be revealed
        self.assertFalse(self.secret_door.is_secret)

    def test_look_action_in_dark_without_darkvision_reveals_door(self):
        """Non-darkvision character in dark map can still reveal secret door via Look action.

        The can_see logic for secret doors bypasses LOS/illumination when
        perception beats DC, allowing detection by touch/sound even in darkness.
        """
        pc = self._load_character('characters/halfling_rogue.yml', 'test_rogue', 3, 8)
        self.assertFalse(pc.darkvision(30))
        self.assertEqual(self.map.light_at(4, 8), 0.0)  # Dark map

        battle = Battle(self.session, self.map)
        battle.add(pc, 'a')
        pc.reset_turn(battle)

        # Mock perception roll >= DC
        with patch.object(pc, 'perception_check', return_value=DieRoll([18], 0, 18)):
            action = autobuild(self.session, LookAction, pc, battle)[0]
            battle.action(action)
            battle.commit(action)

        # Door should be revealed even in darkness
        self.assertFalse(self.secret_door.is_secret)

    # --- Map properties verification ---

    def test_3rd_floor_map_is_dark(self):
        """The 3rd floor map should have illumination 0.0."""
        self.assertEqual(self.map.properties['map']['illumination'], 0.0)

    def test_secret_door_properties(self):
        """Verify secret door has correct properties."""
        self.assertTrue(self.secret_door.is_secret)
        self.assertEqual(self.secret_door.secret_perception_dc(), 15)
        self.assertTrue(self.secret_door.kind_of_door())
        self.assertFalse(self.secret_door.concealed())

    # --- battle.can_see forwarding active_perception ---

    def test_battle_can_see_forwards_active_perception(self):
        """battle.can_see should forward active_perception to map.can_see."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        battle = Battle(self.session, self.map)
        battle.add(pc, 'a')

        # Without active perception: passive 13 < DC 15 → can't see
        self.assertFalse(battle.can_see(pc, self.secret_door, active_perception=0))

        # With active perception >= DC: should see the secret door
        self.assertTrue(battle.can_see(pc, self.secret_door, active_perception=16))

    # --- Renderer with battle active perception ---

    def test_renderer_uses_battle_active_perception(self):
        """Renderer should use battle's active_perception when determining object visibility."""
        pc = self._load_character('characters/high_elf_fighter.yml', 'test_fighter', 3, 8)
        self.assertTrue(pc.darkvision(30))

        battle = Battle(self.session, self.map)
        battle.add(pc, 'a')
        pc.reset_turn(battle)

        # Without active perception: passive 13 < DC 15 → door not rendered
        renderer = JsonRenderer(self.map, battle, padding=[0, 0])
        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        self.assertEqual(tile.get('objects', []), [])

        # Set active perception in battle state (simulating post-Look)
        battle.entity_state_for(pc)['active_perception'] = 18

        # Now the renderer should show the door (active perception 18 >= DC 15)
        result = renderer.render(entity_pov=[pc])
        tile = result[4][4]
        objects = tile.get('objects', [])
        self.assertTrue(len(objects) > 0, "Secret door should be visible with active perception from battle")
        self.assertEqual(objects[0]['name'], 'attic_secret_door')

    # --- available_interactions / objects_near tests ---

    def test_available_interactions_hidden_before_perception(self):
        """A still-secret door must not expose any interactions to an entity that has not perceived it."""
        pc = self._load_character('characters/halfling_rogue.yml', 'test_rogue', 4, 7)
        self.assertTrue(self.secret_door.is_secret)
        self.assertNotIn(pc, self.secret_door.perception_results)
        self.assertEqual(self.secret_door.available_interactions(pc, battle=None), {})
        self.assertNotIn(self.secret_door, self.map.objects_near(pc, None))

    def test_available_interactions_open_after_perception_revealed(self):
        """Once perception_results marks the door revealed for this entity, 'open' must be available."""
        pc = self._load_character('characters/halfling_rogue.yml', 'test_rogue', 4, 7)
        # Simulate a successful perception reveal scoped to this entity (no global is_secret flip).
        self.secret_door.perception_results[pc] = {'perception_roll': 18, 'revealed': True}
        self.assertTrue(self.secret_door.is_secret)  # still secret globally

        actions = self.secret_door.available_interactions(pc, battle=None)
        self.assertIn('open', actions, f"Expected 'open' interaction after reveal, got {actions}")
        self.assertIn(self.secret_door, self.map.objects_near(pc, None))

    def test_other_entity_still_blocked_after_one_entity_reveals(self):
        """Per-entity reveal must not leak: other entities still see no interactions."""
        rose = self._load_character('characters/halfling_rogue.yml', 'rose', 4, 7)
        thorn = self._load_character('characters/halfling_rogue.yml', 'thorn', 4, 9)
        self.secret_door.perception_results[rose] = {'perception_roll': 18, 'revealed': True}

        self.assertIn('open', self.secret_door.available_interactions(rose, battle=None))
        self.assertEqual(self.secret_door.available_interactions(thorn, battle=None), {})

    def test_admin_always_sees_interactions(self):
        """admin=True bypasses both the secret gate and the range check."""
        pc = self._load_character('characters/halfling_rogue.yml', 'test_rogue', 0, 0)
        self.assertTrue(self.secret_door.is_secret)
        actions = self.secret_door.available_interactions(pc, battle=None, admin=True)
        self.assertIn('open', actions)


if __name__ == '__main__':
    unittest.main()

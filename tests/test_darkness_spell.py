import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.spell_action import SpellAction
from natural20.spell.darkness_spell import DarknessSpell, DarknessEffect
from natural20.spell.objects.darkness import Darkness


class TestDarknessSpell(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        np.random.seed(7000)
        random.seed(7000)
        self.warlock = PlayerCharacter.load(self.session, 'tiefling_warlock.yml')
        self.battle.add(self.warlock, 'a', position=[0, 5])
        self.battle.start()
        self.warlock.reset_turn(self.battle)

    # ---- metadata --------------------------------------------------
    def test_spell_loads(self):
        spell = self.session.load_spell('darkness')
        self.assertEqual(spell['level'], 2)
        self.assertEqual(spell['casting_time'], '1:action')
        self.assertEqual(spell['range'], 60)
        self.assertEqual(spell['radius'], 15)
        self.assertTrue(spell.get('concentration'))

    def test_warlock_has_darkness_prepared(self):
        self.assertIn('darkness', self.warlock.prepared_spells())

    # ---- placement & lighting --------------------------------------
    def test_casting_places_darkness_object(self):
        target = (0, 6)
        action = (
            SpellAction.build(self.session, self.warlock)
            ['next'](['darkness', 1])  # cast at level 2 needs slot index
            ['next'](target)
        )
        # at_level should be 2 (the spell's natural level)
        action.at_level = 2
        self.battle.action(action)
        self.battle.commit(action)

        darks = [e for e in self.battle_map.entities if isinstance(e, Darkness)]
        self.assertEqual(len(darks), 1)
        self.assertEqual(self.warlock.current_concentration().id, 'darkness')

    def test_light_zeroed_inside_radius(self):
        target = (3, 3)
        dark = Darkness(self.session, self.warlock, radius_feet=15)
        self.battle_map.place(target, dark)
        # 15 feet at 5 ft per square = 3 squares; chebyshev <= 3 inside.
        self.assertEqual(self.battle_map.light_at(3, 3), 0.0)
        self.assertEqual(self.battle_map.light_at(5, 5), 0.0)  # 2,2 away
        self.assertEqual(self.battle_map.light_at(6, 6), 0.0)  # 3,3 away (edge)
        self.assertGreater(self.battle_map.light_at(7, 7), 0.0)  # outside
        self.assertTrue(self.battle_map.magical_darkness_at(3, 3))
        self.assertFalse(self.battle_map.magical_darkness_at(7, 7))

    # ---- visibility blocks darkvision ------------------------------
    def test_darkvision_does_not_pierce_magical_darkness(self):
        # Place a darkvision-having tiefling viewer outside the darkness
        # and a target inside; viewer should not see target.
        viewer = self.warlock  # tieflings have darkvision 60
        # Move viewer far from the existing position, away from any darkness.
        self.battle_map.move_to(viewer, 6, 6)

        # Make the map's base illumination dark to test pure darkvision.
        # Use a dummy: monkeypatch base illumination off via a local map.
        dark_map = Map(self.session, 'battle_sim_objects')
        # Force base illumination to zero
        dark_map._light_map = np.zeros(dark_map.size)

        target_npc = self.session.npc('skeleton')
        dark_map.place([0, 5], viewer)
        dark_map.place([1, 5], target_npc)
        # Without any darkness placed, darkvision lets viewer see the target.
        self.assertTrue(dark_map.can_see(viewer, target_npc))

        # Now drop a Darkness object on top of the target.
        dark = Darkness(self.session, viewer, radius_feet=15)
        dark_map.place([1, 5], dark)
        self.assertFalse(dark_map.can_see(viewer, target_npc))

    # ---- concentration & dismissal ---------------------------------
    def test_dismissing_concentration_removes_darkness(self):
        target = (0, 6)
        dark = Darkness(self.session, self.warlock, radius_feet=15)
        self.battle_map.place(target, dark)
        effect = DarknessEffect(self.warlock, dark, self.battle_map)
        self.warlock.add_casted_effect({
            'target': target, 'effect': effect,
            'expiration': self.session.game_time + 600,
        })
        self.warlock.register_effect(
            'darkness', DarknessSpell, effect=effect, source=self.warlock,
            duration=600,
        )
        self.warlock.concentration_on(effect)

        self.assertIn(dark, self.battle_map.entities)
        self.warlock.drop_concentration()
        # drop_concentration only clears the marker; dismiss_effect runs the
        # cleanup. Trigger explicit dismissal via the established API.
        self.warlock.dismiss_effect(effect)
        self.assertNotIn(dark, self.battle_map.entities)


if __name__ == '__main__':
    unittest.main()

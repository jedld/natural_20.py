"""Daylight: point light source, carried light, and dispelling low-level Darkness."""
import random
import unittest

from natural20.actions.spell_action import SpellAction
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.daylight_spell import DaylightEffect
from natural20.spell.objects.darkness import Darkness
from natural20.spell.objects.daylight import DaylightSource
from natural20.utils.serialization import Serialization


class DaylightTest(unittest.TestCase):
    def setUp(self):
        random.seed(5)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.map = self.session.register_map('empty_map', Map(self.session, 'maps/empty_map'))
        self.cleric = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.wizard = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map.add(self.cleric, 1, 1)
        self.map.add(self.wizard, 4, 4)
        self.cleric.spell_slots.setdefault('cleric', {})[3] = 2
        self.cleric.properties.setdefault('prepared_spells', []).append('daylight')

    def cast(self, mode, point=None):
        step = SpellAction.build(self.session, self.cleric)['next'](['daylight', 3])['next'](mode)
        action = step['next'](point) if isinstance(step, dict) else step
        action.resolve(self.session, self.map, {})
        self._commit(action)
        return action

    def _commit(self, action):
        for item in action.result:
            SpellAction.apply(None, item, self.session)

    def daylight_objects(self):
        return [e for e in self.map.entities if isinstance(e, DaylightSource)]

    def test_point_places_light_source(self):
        self.cast('point', [2, 2])
        sources = self.daylight_objects()
        self.assertEqual(len(sources), 1)
        self.assertEqual(self.map.entity_or_object_pos(sources[0]), [2, 2])
        self.assertEqual(sources[0].light_properties(), {'bright': 60, 'dim': 60})
        self.assertEqual(self.cleric.spell_slots['cleric'][3], 1)
        self.assertTrue(any(isinstance(c['effect'], DaylightEffect) for c in self.cleric.casted_effects))

    def test_held_mode_lights_caster(self):
        self.cast('held')
        self.assertEqual(self.daylight_objects(), [])
        light = self.cleric.light_properties()
        self.assertGreaterEqual(light['bright'], 60)
        self.assertGreaterEqual(light['dim'], 60)

    def test_expires_after_an_hour(self):
        self.cast('point', [2, 2])
        self.session.game_time += 3601
        self.cleric._cleanup_effects()
        self.assertEqual(self.daylight_objects(), [])

    def test_dispels_overlapping_low_level_darkness(self):
        darkness = Darkness(self.session, self.wizard, radius_feet=15, spell_level=2)
        self.map.place([5, 5], darkness)
        strong = Darkness(self.session, self.wizard, radius_feet=15, spell_level=4)
        self.map.place([5, 6], strong)
        self.cast('point', [2, 2])
        remaining = [e for e in self.map.entities if isinstance(e, Darkness)]
        self.assertNotIn(darkness, remaining)
        self.assertIn(strong, remaining)

    def test_dispelling_darkness_ends_the_casters_spell(self):
        self.wizard.spell_slots.setdefault('wizard', {})[2] = 2
        self.wizard.properties.setdefault('prepared_spells', []).append('darkness')
        darkness_action = SpellAction.build(self.session, self.wizard)['next'](['darkness', 2])['next']([5, 6])
        darkness_action.resolve(self.session, self.map, {})
        self._commit(darkness_action)
        self.assertTrue(any(isinstance(e, Darkness) for e in self.map.entities))
        self.cast('point', [2, 2])
        self.assertFalse(any(isinstance(e, Darkness) for e in self.map.entities))
        self.assertIsNone(self.wizard.concentration)

    def test_save_load_round_trip(self):
        self.cast('point', [2, 2])
        darkness = Darkness(self.session, self.wizard, radius_feet=15, spell_level=4)
        self.map.place([5, 6], darkness)
        dump = Serialization().serialize(self.session, None, self.session.maps)
        session2, _battle, maps2 = Serialization().deserialize(dump)
        map2 = maps2['empty_map']
        sources = [e for e in map2.entities if isinstance(e, DaylightSource)]
        self.assertEqual(len(sources), 1)
        darks = [e for e in map2.entities if isinstance(e, Darkness)]
        self.assertEqual(darks[0].spell_level, 4)
        self.assertEqual(darks[0].owner.entity_uid, self.wizard.entity_uid)
        cleric2 = session2.entity_by_uid(self.cleric.entity_uid)
        effect = next(c['effect'] for c in cleric2.casted_effects if isinstance(c['effect'], DaylightEffect))
        cleric2.dismiss_effect(effect)
        self.assertEqual([e for e in map2.entities if isinstance(e, DaylightSource)], [])

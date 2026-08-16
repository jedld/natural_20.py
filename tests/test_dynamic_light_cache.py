"""Dynamic lighting must not scan every Ground tile on every light_at() call."""

import time
import unittest

from natural20.item_library.fireplace import Fireplace
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.web.json_renderer import JsonRenderer


def _open_map(width, height, illumination=0.0):
    rows = ['.' * width] * height
    properties = {
        'name': 'light_perf',
        'map': {
            'illumination': illumination,
            'size': [width, height],
            'base': rows,
        },
    }
    session = Session(root_path='tests/fixtures')
    return session, Map(session, None, name='light_perf', properties=properties)


class TestDynamicLightCache(unittest.TestCase):
    def test_light_at_skips_ground_tiles(self):
        session, battle_map = _open_map(40, 30, illumination=0.0)
        ground_count = sum(
            1 for obj in battle_map.interactable_objects
            if obj.__class__.__name__ == 'Ground'
        )
        self.assertGreater(ground_count, 500)

        props = session.load_object('fireplace')
        props['type'] = 'fireplace'
        props['lit'] = True
        fireplace = Fireplace(session, battle_map, props)
        battle_map.place_object(fireplace, 10, 10)

        lit = battle_map.light_at(10, 10)
        self.assertGreater(lit, 0.0)
        nearby = battle_map.light_at(11, 10)
        self.assertGreater(nearby, 0.0)

        emitters = battle_map._light_builder._emitters
        self.assertIsNotNone(emitters)
        self.assertLess(len(emitters), 20)
        self.assertTrue(any(entry[1] is fireplace for entry in emitters))

    def test_full_map_light_queries_stay_fast(self):
        _session, battle_map = _open_map(40, 30, illumination=0.55)
        width, height = battle_map.size
        t0 = time.perf_counter()
        for x in range(width):
            for y in range(height):
                battle_map.light_at(x, y)
        elapsed = time.perf_counter() - t0
        self.assertLess(
            elapsed, 1.0,
            f'light_at over {width * height} tiles took {elapsed:.2f}s',
        )

    def test_json_renderer_with_pov_stays_fast(self):
        session, battle_map = _open_map(40, 30, illumination=0.55)
        fighter = PlayerCharacter.load(session, 'high_elf_fighter.yml')
        battle_map.place((20, 15), fighter, 'G')
        renderer = JsonRenderer(battle_map)
        t0 = time.perf_counter()
        tiles = renderer.render(entity_pov=[fighter])
        elapsed = time.perf_counter() - t0
        self.assertEqual(len(tiles), 40)
        self.assertLess(
            elapsed, 2.0,
            f'JsonRenderer.render took {elapsed:.2f}s',
        )

    def test_lighting_fireplace_updates_without_respawn(self):
        session, battle_map = _open_map(12, 12, illumination=0.0)
        props = session.load_object('fireplace')
        props['type'] = 'fireplace'
        fireplace = Fireplace(session, battle_map, props)
        battle_map.place_object(fireplace, 4, 4)
        self.assertFalse(fireplace.is_lit())
        dark = battle_map.light_at(4, 4)
        fireplace.take_damage(5, damage_type='fire')
        self.assertTrue(fireplace.is_lit())
        lit = battle_map.light_at(4, 4)
        self.assertGreater(lit, dark)

    def test_tiny_hut_los_scan_skips_ground_tiles(self):
        from natural20.spell.objects.tiny_hut import force_dome_blocks_outside_vision

        _session, battle_map = _open_map(40, 30, illumination=0.55)
        t0 = time.perf_counter()
        for _ in range(2000):
            self.assertFalse(force_dome_blocks_outside_vision(battle_map, (1, 1), (2, 2)))
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.5, f'tiny hut LOS checks took {elapsed:.2f}s')

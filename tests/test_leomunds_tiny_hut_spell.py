"""Tests for Leomund's Tiny Hut."""
import random
import unittest

from natural20.actions.move_action import MoveAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.leomunds_tiny_hut_spell import LeomundsTinyHutSpell
from natural20.spell.objects.tiny_hut import (
    TinyHutDome,
    force_dome_blocks_spell,
    hut_cast_violation,
)


class TestLeomundsTinyHutSpell(unittest.TestCase):
    def setUp(self):
        random.seed(7200)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.wizard = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        prepared = list(self.wizard.properties.get('prepared_spells', []) or [])
        if 'leomunds_tiny_hut' not in prepared:
            prepared.append('leomunds_tiny_hut')
        self.wizard.properties['prepared_spells'] = prepared
        self.battle_map.add(self.wizard, 1, 1)
        self.battle.add(self.wizard, 'a', add_to_initiative=True)
        self.battle.start(combat_order=[self.wizard])
        self.wizard.reset_turn(self.battle)

    def _cast_hut(self):
        action = SpellAction.build(self.session, self.wizard)['next'](['leomunds_tiny_hut', 1])
        action.at_level = 3
        self.battle.action(action)
        self.battle.commit(action)
        return action

    def test_spell_loads(self):
        spell = self.session.load_spell('leomunds_tiny_hut')
        self.assertEqual(spell['radius'], 10)
        self.assertFalse(spell.get('concentration'))

    def test_cast_places_dome(self):
        self._cast_hut()
        domes = [o for o in self.battle_map.interactable_objects if isinstance(o, TinyHutDome)]
        self.assertEqual(len(domes), 1)
        self.assertGreater(len(domes[0].shell_squares), 0)
        self.assertTrue(domes[0].contains((1, 1)))

    def test_outsider_cannot_enter(self):
        self._cast_hut()
        outsider = self.session.npc('goblin', {'name': 'Guz'})
        self.battle_map.add(outsider, 4, 1)
        self.battle.add(outsider, 'b', add_to_initiative=True)
        move = MoveAction(self.session, outsider, 'move')
        move.target = (3, 1)
        move.move_path = [(4, 1), (3, 1)]
        self.battle.action(move)
        self.battle.commit(move)
        self.assertEqual(self.battle_map.entities[outsider], [4, 1])

    def test_occupant_can_exit_dome(self):
        ally = self.session.npc('goblin', {'name': 'Ally'})
        self.battle_map.add(ally, 2, 1)
        self.battle.add(ally, 'b', add_to_initiative=True)
        self._cast_hut()
        ally.reset_turn(self.battle)
        move_out = MoveAction(self.session, ally, 'move')
        move_out.target = (4, 1)
        move_out.move_path = [(2, 1), (3, 1), (4, 1)]
        self.battle.action(move_out)
        self.battle.commit(move_out)
        self.assertEqual(self.battle_map.entities[ally], [4, 1])

    def test_spell_line_blocked_across_dome(self):
        self._cast_hut()
        inside = (1, 1)
        outside = (4, 1)
        self.assertTrue(force_dome_blocks_spell(self.battle_map, inside, outside))

    def test_hut_ends_when_caster_leaves(self):
        self._cast_hut()
        move = MoveAction(self.session, self.wizard, 'move')
        move.target = (4, 1)
        move.move_path = [(1, 1), (2, 1), (3, 1), (4, 1)]
        self.battle.action(move)
        self.battle.commit(move)
        domes = [o for o in self.battle_map.interactable_objects if isinstance(o, TinyHutDome)]
        self.assertEqual(domes, [])

    def test_fails_with_large_creature(self):
        center = tuple(self.battle_map.entities[self.wizard])
        large = self.session.npc('goblin', {'name': 'Big'})
        large.properties['size'] = 'large'
        self.battle_map.add(large, 2, 1)
        self.assertEqual(hut_cast_violation(self.battle_map, center), 'creature_too_large')

    def test_interior_lighting_command(self):
        self._cast_hut()
        ok = LeomundsTinyHutSpell.set_interior_lighting(self.wizard, 'dim', self.session)
        self.assertTrue(ok)
        dome = next(o for o in self.battle_map.interactable_objects if isinstance(o, TinyHutDome))
        self.assertEqual(dome.interior_lighting, 'dim')
        self.assertEqual(float(self.battle_map.light_at(1, 1)), 0.5)

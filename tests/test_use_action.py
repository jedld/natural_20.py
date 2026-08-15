import unittest
from natural20.actions.use_item_action import UseItemAction
from natural20.session import Session
from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.map_renderer import MapRenderer
from natural20.utils.action_builder import autobuild
import random
import pdb

class TestUseItemAction(unittest.TestCase):
    def setUp(self):
        random.seed(7000)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.map)
        self.entity = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='G')
        self.entity.reset_turn(self.battle)
        action = UseItemAction.build(self.session, self.entity)
        self.action = action['next']('healing_potion')['next'](self.entity)

    def test_heal_thyself(self):
        usable = self.action.usable_items()
        self.assertEqual(len(usable), 1)
        self.assertEqual(usable[0]['name'], 'healing_potion')
        self.assertEqual(usable[0]['label'], 'Potion of Healing')
        self.assertEqual(usable[0]['qty'], 1)
        self.assertTrue(usable[0]['consumable'])
        self.assertEqual(usable[0]['item']['item_class'], 'HealingPotion')
        self.assertNotIn('container', usable[0])
        self.assertEqual(self.entity.item_count("healing_potion"), 1)
        self.action.resolve(self.session)
        self.entity.take_damage(53, session=self.session)
        self.assertEqual(self.entity.hp(), 14)
        UseItemAction.apply(self.battle, self.action.result[0])
        self.assertEqual(self.entity.hp(), 22)
        self.assertEqual(self.entity.item_count("healing_potion"), 0)

    def test_use_item_inside_container(self):
        self.entity.add_item('backpack', 1)
        ok, reason = self.entity.stow_item('backpack', 'healing_potion', 1, self.session)
        self.assertTrue(ok, reason)
        self.assertEqual(self.entity.item_count('healing_potion'), 1)
        self.assertNotIn('healing_potion', self.entity.inventory)
        usable = self.entity.usable_items()
        self.assertEqual(usable[0]['name'], 'healing_potion')
        self.assertEqual(usable[0]['container'], 'backpack')

        self.entity.take_damage(53, session=self.session)
        action = UseItemAction.build_self_use(
            self.session, self.entity, 'healing_potion', container_name='backpack'
        )
        action.resolve(self.session)
        UseItemAction.apply(self.battle, action.result[0])
        self.assertGreater(self.entity.hp(), 14)
        self.assertEqual(self.entity.item_count('healing_potion'), 0)
        self.assertEqual(self.entity.get_container_contents('backpack'), [])

    def test_spell_scroll(self):
        self.entity = PlayerCharacter.load(self.session, "high_elf_mage.yml")

        self.npc = self.session.npc('goblin')
        self.battle.add(self.entity, 'a', position='spawn_point_1', token='C')
        self.battle.add(self.npc, 'b', position=[1, 1], token='g')
        self.entity.reset_turn(self.battle)
        print(MapRenderer(self.map).render(self.battle))

        action = autobuild(self.session, UseItemAction, self.entity, self.battle, self.map, match=['scroll_of_magic_missile', self.npc])
        self.assertIsInstance(action[0], UseItemAction)
        self.battle.action(action[0])
        self.battle.commit(action[0])

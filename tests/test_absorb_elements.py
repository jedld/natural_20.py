import random
import unittest
from unittest.mock import MagicMock

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.controller import Controller
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.absorb_elements_spell import AbsorbElementsSpell


class _ReactionController(Controller):
    def __init__(self, session, accept=True):
        self.state = {}
        self.session = session
        self.battle_data = {}
        self.user = None
        self.accept = accept

    def select_reaction(self, entity, battle, map, valid_actions, event):
        if not self.accept or not valid_actions:
            return None
        return valid_actions[0]


class AbsorbElementsTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7101)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.wizard = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        prepared = list(self.wizard.properties.get('prepared_spells', []) or [])
        if 'absorb_elements' not in prepared:
            prepared.append('absorb_elements')
        self.wizard.properties['prepared_spells'] = prepared
        self.attacker = self.session.npc('goblin', {'name': 'Guz'})
        self.battle_map.add(self.wizard, 2, 2)
        self.battle_map.add(self.attacker, 4, 2)
        self.battle.add(self.wizard, 'a', add_to_initiative=True)
        self.battle.add(self.attacker, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.wizard, self.attacker])
        self.wizard.reset_turn(self.battle)

    def test_apply_ignores_unrelated_spell_damage(self):
        logged = []
        self.session.event_manager.register_event_listener(
            'spell_buf',
            lambda event: logged.append(event),
        )
        item = {
            'type': 'spell_damage',
            'source': self.wizard,
            'target': self.attacker,
            'attack_name': 'magic_missile',
            'damage_type': 'force',
            'damage': 3,
        }
        SpellAction.apply(self.battle, item, self.session)
        absorb_logs = [
            event for event in logged
            if 'Absorb' in str(event.get('spell', ''))
        ]
        self.assertEqual(absorb_logs, [])

    def test_does_not_trigger_on_force_damage(self):
        self.battle.set_controller_for(self.wizard, _ReactionController(self.session, accept=True))
        start_hp = self.wizard.hp()
        item = {'source': self.attacker, 'attack_name': 'magic_missile', 'damage_type': 'force'}
        self.wizard.take_damage(6, battle=self.battle, damage_type='force',
                                session=self.session, item=item)
        self.assertTrue(self.wizard.has_reaction(self.battle))
        self.assertEqual(self.wizard.hp(), start_hp - 6)

    def test_triggers_on_fire_damage_and_heals_triggering_hit(self):
        self.battle.set_controller_for(self.wizard, _ReactionController(self.session, accept=True))
        start_hp = self.wizard.hp()
        item = {'source': self.attacker, 'attack_name': 'firebolt', 'damage_type': 'fire'}
        self.wizard.take_damage(10, battle=self.battle, damage_type='fire',
                                session=self.session, item=item)
        self.assertFalse(self.wizard.has_reaction(self.battle))
        self.assertEqual(self.wizard.hp(), start_hp - 5)
        self.assertTrue(self.wizard.has_effect('resistance_override'))
        self.assertIn('absorb_elements', self.wizard.statuses)

    def test_resolve_targets_self(self):
        spell_props = self.session.load_spell('absorb_elements')
        spell = AbsorbElementsSpell(self.session, self.wizard, 'AbsorbElementsSpell', spell_props)
        action = SpellAction(self.session, self.wizard, 'spell')
        action.spell_action = spell
        action.at_level = 1
        action.trigger_damage_type = 'fire'
        action.trigger_heal_amount = 4
        results = spell.resolve(self.wizard, self.battle, action, self.battle_map)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['type'], 'absorb_elements')
        self.assertIs(results[0]['target'], self.wizard)
        self.assertEqual(results[0]['damage_type'], 'fire')
        self.assertEqual(results[0]['heal_amount'], 4)


if __name__ == '__main__':
    unittest.main()

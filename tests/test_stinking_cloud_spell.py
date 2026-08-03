import random
import unittest
from unittest.mock import patch

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.stinking_cloud_spell import StinkingCloudSpell
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented


class StinkingCloudSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7301)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.target = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.target, 3, 3)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.target, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.target])
        self.caster.reset_turn(self.battle)
        self.caster.properties.setdefault('spellbook', []).append('stinking_cloud')
        self.caster.properties.setdefault('prepared_spells', []).append('stinking_cloud')

    def test_yaml_and_loader(self):
        props = self.session.load_spell('stinking_cloud')
        self.assertEqual(props['level'], 3)
        self.assertEqual(props['radius'], 20)
        self.assertTrue(props.get('concentration'))
        self.assertTrue(spell_is_implemented('stinking_cloud', props))
        self.assertIsNotNone(load_spell_class('StinkingCloudSpell'))

    def test_build_map_uses_empty_space_targeting(self):
        spell_cls = load_spell_class('StinkingCloudSpell')
        spell = spell_cls(self.session, self.caster, 'StinkingCloudSpell', self.session.load_spell('stinking_cloud'))
        action = SpellAction.build(self.session, self.caster)['next'](['stinking_cloud', 1])
        build_map = spell.build_map(action)
        self.assertEqual(build_map['param'][0]['type'], 'select_empty_space')
        self.assertEqual(build_map['param'][0]['range'], 90)

    def test_cast_registers_zone_and_obscures_gas(self):
        action = SpellAction.build(self.session, self.caster)['next'](['stinking_cloud', 1])['next']([3, 3])
        action.at_level = 3
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertTrue(self.battle.active_zones)
        zone = self.battle.active_zones[0]
        self.assertIn((3, 3), zone.squares)
        self.assertTrue(self.battle_map._light_builder.obscuring_gas_at(3, 3))

    def test_failed_save_at_turn_start_loses_action(self):
        action = SpellAction.build(self.session, self.caster)['next'](['stinking_cloud', 1])['next']([3, 3])
        action.at_level = 3
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.target.reset_turn(self.battle)
        self.battle.entity_state_for(self.target)['action'] = 1
        original_save = self.target.save_throw

        def low_save(ability, battle=None, opts=None):
            roll = original_save(ability, battle, opts)
            roll.rolls = [1]
            return roll

        self.target.save_throw = low_save
        zone = self.battle.active_zones[0]
        zone.on_turn_start(self.target)
        self.assertEqual(self.battle.entity_state_for(self.target)['action'], 0)

    def test_poison_immune_auto_succeeds(self):
        action = SpellAction.build(self.session, self.caster)['next'](['stinking_cloud', 1])['next']([3, 3])
        action.at_level = 3
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.target.condition_immunities = ['poisoned']
        self.battle.entity_state_for(self.target)['action'] = 1
        zone = self.battle.active_zones[0]
        zone.on_turn_start(self.target)
        self.assertEqual(self.battle.entity_state_for(self.target)['action'], 1)

    def test_apply_without_battle_registers_environment_zone(self):
        spell_cls = load_spell_class('StinkingCloudSpell')
        spell = spell_cls(self.session, self.caster, 'StinkingCloudSpell', self.session.load_spell('stinking_cloud'))
        action = SpellAction.build(self.session, self.caster)['next'](['stinking_cloud', 1])['next']([3, 3])
        action.at_level = 3
        action.resolve(self.session, self.battle_map, {'battle': None})
        item = action.result[0]
        StinkingCloudSpell.apply(None, item, session=self.session)
        self.assertTrue(self.battle_map._light_builder.obscuring_gas_at(3, 3))
        self.assertEqual(len(getattr(self.battle_map, 'environment_zones', [])), 1)
        self.caster.remove_effect('stinking_cloud')

    def test_environment_tick_triggers_con_save_out_of_combat(self):
        from natural20.environment_zones import tick_environment_zones

        action = SpellAction.build(self.session, self.caster)['next'](['stinking_cloud', 1])['next']([3, 3])
        action.at_level = 3
        action.resolve(self.session, self.battle_map, {'battle': None})
        StinkingCloudSpell.apply(None, action.result[0], session=self.session)

        original_save = self.target.save_throw

        def low_save(ability, battle=None, opts=None):
            roll = original_save(ability, battle, opts)
            roll.rolls = [1]
            return roll

        self.target.save_throw = low_save
        saves = []
        real_received = self.session.event_manager.received_event

        def spy(event):
            if event.get('event') == 'stinking_cloud_save':
                saves.append(event)
            return real_received(event)

        with patch.object(self.session.event_manager, 'received_event', side_effect=spy):
            tick_environment_zones({'battle_sim': self.battle_map}, event_manager=self.session.event_manager)
        target_saves = [s for s in saves if s.get('target') is self.target]
        self.assertTrue(target_saves)
        self.assertFalse(target_saves[0]['success'])
        self.caster.remove_effect('stinking_cloud')


if __name__ == '__main__':
    unittest.main()

import unittest

from natural20.actions.attack_action import AttackAction
from natural20.actions.ready_action import ReadyAction
from natural20.actions.spell_action import SpellAction
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.action_bar import (
    TAB_COMMON,
    TAB_SPELLS,
    action_bar_tab_for,
    action_favorite_key,
    build_cast_options_for_spell,
    build_spell_tab_groups,
    partition_standard_actions,
    resolve_action_bar_config,
    spell_scales_with_slot,
)


class TestActionBarUtils(unittest.TestCase):
    def setUp(self):
        event_manager = EventManager()
        self.session = Session('tests/fixtures', event_manager=event_manager)
        self.entity = PlayerCharacter.load(self.session, 'high_elf_mage.yml')

    def test_action_favorite_key_for_attack(self):
        action = AttackAction(self.session, self.entity, 'attack', {'using': 'dagger'})
        action.using = 'dagger'
        self.assertEqual(action_favorite_key(action), 'attack:dagger')

    def test_partition_puts_attacks_on_common_tab(self):
        attack = AttackAction(self.session, self.entity, 'attack', {'using': 'dagger'})
        attack.using = 'dagger'
        ready = ReadyAction(self.session, self.entity, 'ready')
        common, other = partition_standard_actions([attack, ready])
        self.assertEqual(len(common), 1)
        self.assertEqual(common[0], attack)
        self.assertEqual(other, [ready])

    def test_spell_action_tab(self):
        spell = SpellAction(self.session, self.entity, 'spell')
        self.assertEqual(action_bar_tab_for(spell), TAB_SPELLS)

    def test_available_upcast_levels(self):
        groups = build_spell_tab_groups(self.entity, self.entity.castable_spells_by_level(None))
        leveled = [g for g in groups if g['level'] > 0]
        self.assertTrue(leveled)
        spell_with_upcast = next(
            s for g in leveled for s in g['spells'] if s['base_level'] == 1
        )
        self.assertGreaterEqual(len(spell_with_upcast['cast_options']), 1)

    def test_non_scaling_spell_hides_upcast_while_native_slots_remain(self):
        shield = self.entity.session.load_spell('shield')
        self.assertFalse(spell_scales_with_slot(shield, 'shield'))
        self.entity.spell_slots['wizard'][1] = 2
        self.entity.spell_slots['wizard'][2] = 2

        options = build_cast_options_for_spell(self.entity, shield)
        self.assertEqual([row['at_level'] for row in options], [1])

    def test_non_scaling_spell_offers_higher_slots_when_native_exhausted(self):
        shield = self.entity.session.load_spell('shield')
        self.entity.spell_slots['wizard'][1] = 0
        self.entity.spell_slots['wizard'][2] = 2

        options = build_cast_options_for_spell(self.entity, shield)
        self.assertEqual([row['at_level'] for row in options], [2])

    def test_scaling_spell_shows_all_available_slot_levels(self):
        magic_missile = self.entity.session.load_spell('magic_missile')
        self.assertTrue(spell_scales_with_slot(magic_missile, 'magic_missile'))
        self.entity.spell_slots['wizard'][1] = 2
        self.entity.spell_slots['wizard'][2] = 1

        options = build_cast_options_for_spell(self.entity, magic_missile, spell_name='magic_missile')
        self.assertEqual([row['at_level'] for row in options], [1, 2])

    def test_scorching_ray_detected_as_scaling_spell(self):
        scorching_ray = self.entity.session.load_spell('scorching_ray')
        self.assertTrue(scorching_ray.get('upcast'))
        self.assertTrue(spell_scales_with_slot(scorching_ray, 'scorching_ray'))
        self.assertTrue(spell_scales_with_slot(scorching_ray))
        self.entity.spell_slots['wizard'][2] = 2
        self.entity.spell_slots['wizard'][3] = 1

        options = build_cast_options_for_spell(self.entity, scorching_ray, spell_name='scorching_ray')
        self.assertEqual([row['at_level'] for row in options], [2, 3])

    def test_lightning_bolt_detected_as_scaling_spell(self):
        lightning_bolt = self.entity.session.load_spell('lightning_bolt')
        self.assertTrue(spell_scales_with_slot(lightning_bolt, 'lightning_bolt'))

    def test_sunbeam_is_not_treated_as_scaling_spell(self):
        sunbeam = self.entity.session.load_spell('sunbeam')
        self.assertFalse(spell_scales_with_slot(sunbeam, 'sunbeam'))
        self.entity.spell_slots['wizard'][6] = 0
        self.entity.spell_slots['wizard'][7] = 1

        options = build_cast_options_for_spell(self.entity, sunbeam, spell_name='sunbeam')
        self.assertEqual([row['at_level'] for row in options], [7])

    def test_resolve_action_bar_config_merges_character_favorites(self):
        self.entity.properties['action_bar'] = {'favorites': ['firebolt'], 'default_tab': 'spells'}
        config = resolve_action_bar_config(self.entity, {})
        self.assertEqual(config['favorites'], ['firebolt'])
        self.assertEqual(config['default_tab'], 'spells')
        self.assertIn('attack', config['common_action_types'])


if __name__ == '__main__':
    unittest.main()

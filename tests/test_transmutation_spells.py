import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.enlarge_reduce_spell import EnlargeReduceSpell
from natural20.spell.haste_spell import HasteSpell
from natural20.spell.polymorph_spell import PolymorphSpell
from natural20.spell.slow_spell import SlowSpell
from natural20.utils.action_builder import autobuild
from natural20.utils.spell_loader import load_spell_class


class TransmutationSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(9100)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.ally = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.enemy = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 0, 0)
        self.battle_map.add(self.ally, 1, 0)
        self.battle_map.add(self.enemy, 0, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.ally, 'a', add_to_initiative=True)
        self.battle.add(self.enemy, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.ally, self.enemy])
        self.caster.reset_turn(self.battle)
        self._prime_slots()

    def _prime_slots(self):
        for level in (2, 3, 4):
            while self.caster.spell_slots_count(level, 'wizard') < 2:
                self.caster.spell_slots['wizard'][level] = self.caster.spell_slots['wizard'].get(level, 0) + 1

    def _cast(self, spell_name, target, *, at_level=None, match=None):
        props = self.session.load_spell(spell_name)
        at_level = at_level or props['level']
        prepared = list(self.caster.properties.get('prepared_spells') or [])
        if spell_name not in prepared:
            prepared.append(spell_name)
            self.caster.properties['prepared_spells'] = prepared
        actions = autobuild(
            self.session,
            SpellAction,
            self.caster,
            self.battle,
            map=self.battle_map,
            match=match or {'select_spell': spell_name, 'select_target': target},
        )
        self.assertIsNotNone(actions, f'autobuild failed for {spell_name}')
        action = actions[0]
        action.at_level = at_level
        action.spellcasting_class = 'wizard'
        self.battle.action(action)
        self.battle.commit(action)
        return action

    def _mock_save(self, entity, total):
        roll = SimpleNamespace(result=lambda: total)
        entity.save_throw = lambda *args, **kwargs: roll
        return roll


class TestTransmutationSpellDefinitions(unittest.TestCase):
    def test_spell_classes_load(self):
        for name in ('EnlargeReduceSpell', 'HasteSpell', 'SlowSpell', 'PolymorphSpell'):
            self.assertIsNotNone(load_spell_class(name))

    def test_spell_yaml_definitions(self):
        session = Session(root_path='tests/fixtures')
        for key in ('enlarge_reduce', 'haste', 'slow', 'polymorph'):
            details = session.load_spell(key)
            self.assertIn('spell_class', details)
            self.assertTrue(details.get('concentration'))


class TestEnlargeReduceSpell(TransmutationSpellTestCase):
    def test_enlarge_applies_size_and_damage_modifier_on_ally(self):
        props = self.session.load_spell('enlarge_reduce')
        spell = EnlargeReduceSpell(self.session, self.caster, 'EnlargeReduceSpell', props)
        spell.mode = 'enlarge'
        EnlargeReduceSpell.apply(self.battle, {
            'type': 'enlarge_reduce',
            'source': self.caster,
            'target': self.ally,
            'effect': spell,
            'mode': 'enlarge',
        }, self.session)

        self.assertEqual(self.ally.size(), 'large')
        self.assertIn('enlarged', self.ally.statuses)
        mods = self.ally.collect_modifiers('damage_roll', {'weapon': {'type': 'melee_attack'}})
        self.assertTrue(any(m['value'] == '1d4' for m in mods))

    def test_enlarge_enemy_must_pass_constitution_save(self):
        props = self.session.load_spell('enlarge_reduce')
        spell = EnlargeReduceSpell(self.session, self.caster, 'EnlargeReduceSpell', props)
        spell.mode = 'enlarge'
        self._mock_save(self.enemy, 30)
        result = spell.resolve(self.caster, self.battle, SimpleNamespace(target=self.enemy, spell_action=spell), self.battle_map)
        self.assertEqual(result[0]['type'], 'spell_miss')

    def test_reduce_applies_small_size_and_penalty(self):
        props = self.session.load_spell('enlarge_reduce')
        spell = EnlargeReduceSpell(self.session, self.caster, 'EnlargeReduceSpell', props)
        spell.mode = 'reduce'
        EnlargeReduceSpell.apply(self.battle, {
            'type': 'enlarge_reduce',
            'source': self.caster,
            'target': self.enemy,
            'effect': spell,
            'mode': 'reduce',
        }, self.session)

        self.assertEqual(self.enemy.size(), 'small')
        self.assertIn('reduced', self.enemy.statuses)


class TestHasteSpell(TransmutationSpellTestCase):
    def test_haste_doubles_speed_and_adds_ac(self):
        props = self.session.load_spell('haste')
        spell = HasteSpell(self.session, self.caster, 'HasteSpell', props)
        base_speed = self.ally.speed()
        base_ac = self.ally.armor_class()
        HasteSpell.apply(self.battle, {
            'type': 'haste',
            'source': self.caster,
            'target': self.ally,
            'effect': spell,
        }, self.session)

        self.assertEqual(self.ally.speed(), base_speed * 2)
        self.assertEqual(self.ally.armor_class(), base_ac + 2)
        self.assertIn('hasted', self.ally.statuses)

    def test_haste_grants_extra_action_on_turn_start(self):
        props = self.session.load_spell('haste')
        spell = HasteSpell(self.session, self.caster, 'HasteSpell', props)
        HasteSpell.apply(self.battle, {
            'type': 'haste',
            'source': self.caster,
            'target': self.ally,
            'effect': spell,
        }, self.session)
        self.battle.set_current_turn(self.ally)
        self.ally.reset_turn(self.battle)
        state = self.battle.entity_state_for(self.ally)
        self.assertGreaterEqual(state.get('action', 0), 2)

    def test_haste_lethargy_after_dismiss(self):
        props = self.session.load_spell('haste')
        spell = HasteSpell(self.session, self.caster, 'HasteSpell', props)
        HasteSpell.apply(self.battle, {
            'type': 'haste',
            'source': self.caster,
            'target': self.ally,
            'effect': spell,
        }, self.session)
        spell.dismiss(self.ally, {'effect': spell}, {'battle': self.battle})
        self.assertIn('haste_lethargy', self.ally.statuses)

        self.battle.set_current_turn(self.ally)
        self.ally.reset_turn(self.battle)
        state = self.battle.entity_state_for(self.ally)
        self.assertEqual(state.get('action', 1), 0)
        self.assertEqual(state.get('movement', 1), 0)

        self.ally.resolve_trigger('end_of_turn', {'battle': self.battle})
        self.assertNotIn('haste_lethargy', self.ally.statuses)


class TestSlowSpell(TransmutationSpellTestCase):
    def test_slow_halves_speed_and_reduces_ac(self):
        props = self.session.load_spell('slow')
        spell = SlowSpell(self.session, self.caster, 'SlowSpell', props)
        base_speed = self.enemy.speed()
        base_ac = self.enemy.armor_class()
        SlowSpell.apply(self.battle, {
            'type': 'slow',
            'source': self.caster,
            'target': self.enemy,
            'effect': spell,
        }, self.session)

        self.assertEqual(self.enemy.speed(), base_speed // 2)
        self.assertEqual(self.enemy.armor_class(), base_ac - 2)
        self.assertFalse(self.enemy.has_reaction(self.battle))

    def test_slow_ends_on_successful_repeat_save(self):
        props = self.session.load_spell('slow')
        spell = SlowSpell(self.session, self.caster, 'SlowSpell', props)
        SlowSpell.apply(self.battle, {
            'type': 'slow',
            'source': self.caster,
            'target': self.enemy,
            'effect': spell,
        }, self.session)
        self._mock_save(self.enemy, 30)
        with patch.object(self.enemy, 'dismiss_effect', wraps=self.enemy.dismiss_effect) as dismiss:
            self.enemy.resolve_trigger('end_of_turn', {'battle': self.battle})
            dismiss.assert_called()

    def test_slow_resolve_targets_creatures_in_area(self):
        props = self.session.load_spell('slow')
        spell = SlowSpell(self.session, self.caster, 'SlowSpell', props)
        self._mock_save(self.enemy, 1)
        results = spell.resolve(
            self.caster,
            self.battle,
            SimpleNamespace(target=(0, 2)),
            self.battle_map,
        )
        applied = [r for r in results if r.get('type') == 'slow']
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]['target'], self.enemy)


class TestPolymorphSpell(TransmutationSpellTestCase):
    def test_polymorph_unwilling_target_uses_wisdom_save(self):
        props = self.session.load_spell('polymorph')
        spell = PolymorphSpell(self.session, self.caster, 'PolymorphSpell', props)
        self._mock_save(self.enemy, 30)
        result = spell.resolve(self.caster, self.battle, SimpleNamespace(target=self.enemy), self.battle_map)
        self.assertEqual(result[0]['type'], 'spell_miss')

    def test_polymorph_willing_ally_skips_save(self):
        props = self.session.load_spell('polymorph')
        spell = PolymorphSpell(self.session, self.caster, 'PolymorphSpell', props)
        result = spell.resolve(self.caster, self.battle, SimpleNamespace(target=self.ally), self.battle_map)
        self.assertEqual(result[0]['type'], 'polymorph')

    def test_polymorph_apply_sets_beast_transition(self):
        props = self.session.load_spell('polymorph')
        spell = PolymorphSpell(self.session, self.caster, 'PolymorphSpell', props)
        with patch.object(self.enemy, '_maybe_phase_transition', return_value=True) as transition:
            PolymorphSpell.apply(self.battle, {
                'type': 'polymorph',
                'source': self.caster,
                'target': self.enemy,
                'effect': spell,
            }, self.session)
            transition.assert_called_once()
        self.assertEqual(self.enemy.properties['phase_transition']['npc'], 'wolf')
        self.assertIn('polymorphed', self.enemy.statuses)


if __name__ == '__main__':
    unittest.main()

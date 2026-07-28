import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.hold_person_spell import HoldPersonSpell
from natural20.spell.extensions.save_check import SaveCheck
from natural20.utils.action_builder import acquire_targets, autobuild
from natural20.utils.spell_loader import load_spell_class
from natural20.weapons import target_advantage_condition


class _MockSaveRoll:
    def __init__(self, total):
        self._total = total

    def result(self):
        return self._total

    def __lt__(self, other):
        return self._total < other


class HoldPersonSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(9200)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'dwarf_cleric.yml')
        self.humanoid = self.session.npc('goblin', {'name': 'Goblin'})
        self.non_humanoid = self.session.npc('skeleton', {'name': 'Skeleton'})
        self.battle_map.add(self.caster, 0, 0)
        self.battle_map.add(self.humanoid, 0, 2)
        self.battle_map.add(self.non_humanoid, 1, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.humanoid, 'b', add_to_initiative=True)
        self.battle.add(self.non_humanoid, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.humanoid, self.non_humanoid])
        self.caster.reset_turn(self.battle)
        self._prime_slots()

    def _prime_slots(self):
        while self.caster.spell_slots_count(2, 'cleric') < 3:
            self.caster.spell_slots['cleric'][2] = self.caster.spell_slots['cleric'].get(2, 0) + 1
        while self.caster.spell_slots_count(3, 'cleric') < 2:
            self.caster.spell_slots['cleric'][3] = self.caster.spell_slots['cleric'].get(3, 0) + 1

    def _cast(self, target, *, at_level=None, match=None):
        props = self.session.load_spell('hold_person')
        at_level = at_level or props['level']
        prepared = list(self.caster.properties.get('prepared_spells') or [])
        if 'hold_person' not in prepared:
            prepared.append('hold_person')
            self.caster.properties['prepared_spells'] = prepared
        actions = autobuild(
            self.session,
            SpellAction,
            self.caster,
            self.battle,
            map=self.battle_map,
            match=match or {'select_spell': 'hold_person', 'select_target': target},
        )
        self.assertIsNotNone(actions, 'autobuild failed for hold_person')
        action = actions[0]
        action.at_level = at_level
        action.spellcasting_class = 'cleric'
        self.battle.action(action)
        self.battle.commit(action)
        return action

    def _mock_save(self, entity, total):
        roll = _MockSaveRoll(total)
        entity.save_throw = (lambda _roll: lambda *args, **kwargs: _roll)(roll)
        return roll

    def _mock_saves(self, mapping):
        for entity, total in mapping.items():
            self._mock_save(entity, total)


class TestHoldPersonSpellDefinition(unittest.TestCase):
    def test_spell_class_loads(self):
        self.assertIsNotNone(load_spell_class('HoldPersonSpell'))

    def test_yaml_definition(self):
        session = Session(root_path='tests/fixtures')
        props = session.load_spell('hold_person')
        self.assertEqual(props['level'], 2)
        self.assertTrue(props.get('concentration'))
        self.assertEqual(props.get('duration_seconds'), 60)
        self.assertIn('material', props.get('components', []))


class TestHoldPersonTargeting(HoldPersonSpellTestCase):
    def test_acquire_targets_filters_humanoids(self):
        param = {
            'range': 60,
            'target_types': ['enemies'],
            'require_humanoid': True,
        }
        targets = acquire_targets(param, self.caster, self.battle, self.battle_map)
        self.assertIn(self.humanoid, targets)
        self.assertNotIn(self.non_humanoid, targets)

    def test_resolve_rejects_non_humanoid(self):
        props = self.session.load_spell('hold_person')
        spell = HoldPersonSpell(self.session, self.caster, 'HoldPersonSpell', props)
        results = spell.resolve(
            self.caster,
            self.battle,
            SimpleNamespace(target=self.non_humanoid),
            self.battle_map,
        )
        self.assertEqual(results[0]['message'], 'not_humanoid')


class TestHoldPersonEffect(HoldPersonSpellTestCase):
    def test_failed_save_paralyzes_and_tracks_concentration(self):
        self._mock_save(self.humanoid, 1)
        self._cast(self.humanoid)

        self.assertTrue(self.humanoid.paralyzed())
        self.assertTrue(self.humanoid.incapacitated())
        self.assertEqual(self.caster.current_concentration(), self.caster.concentration)
        self.assertIsNotNone(self.caster.concentration)

    def test_successful_save_does_not_paralyze(self):
        self._mock_save(self.humanoid, 30)
        self._cast(self.humanoid)

        self.assertFalse(self.humanoid.paralyzed())
        self.assertIsNone(self.caster.concentration)

    def test_ends_on_successful_repeat_save(self):
        self._mock_save(self.humanoid, 1)
        self._cast(self.humanoid)
        self._mock_save(self.humanoid, 30)
        with patch.object(self.humanoid, 'dismiss_effect', wraps=self.humanoid.dismiss_effect) as dismiss:
            self.humanoid.resolve_trigger('end_of_turn', {'battle': self.battle})
            dismiss.assert_called()

    def test_upcast_targets_additional_humanoids(self):
        goblin_two = self.session.npc('goblin', {'name': 'Goblin 2'})
        self.battle_map.add(goblin_two, 0, 3)
        self.battle.add(goblin_two, 'b', add_to_initiative=True)

        props = self.session.load_spell('hold_person')
        spell = HoldPersonSpell(self.session, self.caster, 'HoldPersonSpell', props)
        build = spell.build_map(SimpleNamespace(at_level=3))
        self.assertEqual(build['param'][0]['num'], 2)

        self._mock_saves({self.humanoid: 1, goblin_two: 1})
        results = spell.resolve(
            self.caster,
            self.battle,
            SimpleNamespace(target=[self.humanoid, goblin_two], spellcasting_class='cleric'),
            self.battle_map,
        )
        for item in results:
            if item.get('type') == 'hold_person':
                HoldPersonSpell.apply(self.battle, item, self.session)

        self.assertTrue(self.humanoid.paralyzed())
        self.assertTrue(goblin_two.paralyzed())

    def test_upcast_rejects_targets_more_than_30_feet_apart(self):
        self.battle_map.move_to(self.humanoid, 0, 0, self.battle)
        goblin_far = self.session.npc('goblin', {'name': 'Goblin Far'})
        self.battle_map.add(goblin_far, 5, 6)
        self.battle.add(goblin_far, 'b', add_to_initiative=True)

        props = self.session.load_spell('hold_person')
        spell = HoldPersonSpell(self.session, self.caster, 'HoldPersonSpell', props)
        results = spell.resolve(
            self.caster,
            self.battle,
            SimpleNamespace(target=[self.humanoid, goblin_far]),
            self.battle_map,
        )
        self.assertEqual(results[0]['message'], 'targets_too_far_apart')


class TestParalyzedConditionRules(HoldPersonSpellTestCase):
    def test_paralyzed_auto_fails_strength_and_dexterity_saves(self):
        self.humanoid.statuses.append('paralyzed')
        str_save = self.humanoid.save_throw('strength', self.battle)
        dex_save = self.humanoid.save_throw('dexterity', self.battle)
        self.assertLess(str_save.result(), 8)
        self.assertLess(dex_save.result(), 8)

    def test_paralyzed_does_not_auto_fail_wisdom_saves(self):
        self.humanoid.statuses.append('paralyzed')
        self._mock_save(self.humanoid, 15)
        save = SaveCheck.make(self.humanoid, 'wisdom', 10, battle=self.battle)
        self.assertTrue(save.passed)

    def test_attacks_against_paralyzed_target_have_advantage(self):
        self.humanoid.statuses.append('paralyzed')
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle_map.add(fighter, 0, 1)
        self.battle.add(fighter, 'a', add_to_initiative=True)
        weapon = self.session.load_weapon(fighter.properties['equipped'][0])
        advantage_mod, adv_info = target_advantage_condition(
            self.session, fighter, self.humanoid, weapon, battle=self.battle,
        )
        self.assertGreater(advantage_mod, 0)
        self.assertIn('target_paralyzed', adv_info[0])

    def test_melee_hit_within_5_feet_is_critical_against_paralyzed_target(self):
        self._mock_save(self.humanoid, 1)
        self._cast(self.humanoid)

        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        fighter.can_sneak_attack = lambda *args, **kwargs: False
        self.battle_map.add(fighter, 0, 1)
        self.battle.add(fighter, 'a', add_to_initiative=True)
        fighter.reset_turn(self.battle)
        weapon_name = fighter.properties['equipped'][0]
        weapon = self.session.load_weapon(weapon_name)
        attack_roll = SimpleNamespace(
            nat_20=lambda: False,
            nat_1=lambda: False,
            result=lambda: 20,
        )
        attack = AttackAction(self.session, fighter, 'attack')
        attack.using = weapon_name
        attack.target = self.humanoid
        attack.source = fighter
        attack.thrown = False
        attack.advantage_mod = 0
        attack.attack_roll = attack_roll
        attack._resolve_hit(
            self.battle,
            self.humanoid,
            weapon,
            attack_roll,
            weapon['damage'],
            'attack',
            None,
            (['target_paralyzed'], []),
        )
        damage_roll = attack.hit_result['damage']
        self.assertGreaterEqual(len(damage_roll.rolls), 2)

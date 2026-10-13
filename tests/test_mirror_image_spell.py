import random
import unittest
from unittest.mock import patch

from natural20.actions.attack_action import AttackAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ruleset import get_ruleset
from natural20.session import Session
from natural20.spell.mirror_image_spell import MirrorImageSpell
from natural20.utils.spell_loader import load_spell_class, spell_is_implemented


class MirrorImageSpellTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(7202)
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.battle = Battle(self.session, self.battle_map)
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.attacker = self.session.npc('goblin', {'name': 'Goblin'})
        self.battle_map.add(self.caster, 2, 2)
        self.battle_map.add(self.attacker, 3, 2)
        self.battle.add(self.caster, 'a', add_to_initiative=True)
        self.battle.add(self.attacker, 'b', add_to_initiative=True)
        self.battle.start(combat_order=[self.caster, self.attacker])
        self.caster.reset_turn(self.battle)

    def test_yaml_and_loader(self):
        props = self.session.load_spell('mirror_image')
        self.assertEqual(props['level'], 2)
        self.assertTrue(spell_is_implemented('mirror_image', props))
        self.assertIsNotNone(load_spell_class('MirrorImageSpell'))

    def test_cast_applies_mirror_image_status(self):
        action = SpellAction.build(self.session, self.caster)['next'](['mirror_image', 1])['next'](self.caster)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertIn('mirror_image', self.caster.statuses)

    def test_mirror_image_does_not_require_concentration(self):
        action = SpellAction.build(self.session, self.caster)['next'](['mirror_image', 1])['next'](self.caster)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertIsNone(self.caster.current_concentration())

    def _cast(self):
        action = SpellAction.build(self.session, self.caster)['next'](['mirror_image', 1])['next'](self.caster)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)

    @staticmethod
    def _attack(total, natural=None):
        natural = natural if natural is not None else total - 5
        return DieRoll([natural], 5)

    @staticmethod
    def _fixed_roll(faces, sides):
        return lambda *a, **k: DieRoll(list(faces), 0, die_sides=sides)

    def test_2014_redirect_hits_duplicate_not_caster(self):
        self._cast()
        with patch.object(DieRoll, 'roll', self._fixed_roll([15], 20)):
            outcome = MirrorImageSpell.check_attack(self.attacker, self.caster, self._attack(20), True, self.battle)
        self.assertTrue(outcome['destroyed'])
        self.assertEqual(outcome['threshold'], 6)
        self.assertEqual(outcome['remaining'], 2)
        self.assertEqual(MirrorImageSpell._images_remaining(self.caster), 2)

    def test_2014_low_duplicate_roll_leaves_attack_alone(self):
        self._cast()
        with patch.object(DieRoll, 'roll', self._fixed_roll([5], 20)):
            outcome = MirrorImageSpell.check_attack(self.attacker, self.caster, self._attack(20), True, self.battle)
        self.assertIsNone(outcome)
        self.assertEqual(MirrorImageSpell._images_remaining(self.caster), 3)

    def test_2014_attack_below_duplicate_ac_misses_it(self):
        self._cast()
        duplicate_ac = 10 + self.caster.dex_mod()
        with patch.object(DieRoll, 'roll', self._fixed_roll([18], 20)):
            outcome = MirrorImageSpell.check_attack(
                self.attacker, self.caster, self._attack(duplicate_ac - 1), False, self.battle)
        self.assertFalse(outcome['destroyed'])
        self.assertEqual(outcome['duplicate_ac'], duplicate_ac)
        self.assertEqual(MirrorImageSpell._images_remaining(self.caster), 3)

    def test_2024_d6_on_hit(self):
        self.session.ruleset = get_ruleset('5e-2024')
        self._cast()
        with patch.object(DieRoll, 'roll', self._fixed_roll([1, 2, 1], 6)):
            self.assertIsNone(
                MirrorImageSpell.check_attack(self.attacker, self.caster, self._attack(20), True, self.battle))
        with patch.object(DieRoll, 'roll', self._fixed_roll([1, 4, 1], 6)):
            self.assertIsNone(
                MirrorImageSpell.check_attack(self.attacker, self.caster, self._attack(5), False, self.battle))
            outcome = MirrorImageSpell.check_attack(self.attacker, self.caster, self._attack(20), True, self.battle)
        self.assertEqual(outcome['model'], 'd6_on_hit')
        self.assertTrue(outcome['destroyed'])
        self.assertEqual(outcome['remaining'], 2)

    def test_truesight_and_blinded_attackers_are_unaffected(self):
        self._cast()
        self.attacker.properties['truesight'] = 120
        self.assertTrue(MirrorImageSpell.attacker_unaffected(self.attacker, self.caster, self.battle))
        self.attacker.properties.pop('truesight')
        self.assertFalse(MirrorImageSpell.attacker_unaffected(self.attacker, self.caster, self.battle))
        self.attacker.statuses.append('blinded')
        self.assertTrue(MirrorImageSpell.attacker_unaffected(self.attacker, self.caster, self.battle))

    def test_attack_against_duplicate_is_logged_and_misses_caster(self):
        self._cast()
        events = []
        self.session.event_manager.register_event_listener('mirror_image_duplicate', events.append)
        hp_before = self.caster.hp()
        self.attacker.reset_turn(self.battle)
        action = AttackAction(self.session, self.attacker, 'attack')
        action.target = self.caster
        action.npc_action = self.attacker.npc_actions[0]
        with patch.object(MirrorImageSpell, 'check_attack', return_value={
                'model': 'd20_redirect', 'images': 3, 'roll': DieRoll([12], 0), 'threshold': 6,
                'duplicate_ac': 12, 'destroyed': True, 'remaining': 2}):
            action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        self.assertEqual(self.caster.hp(), hp_before)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['destroyed'])
        self.assertEqual(events[0]['remaining'], 2)
        self.assertIs(events[0]['target'], self.caster)

    def test_multi_attack_spells_roll_each_attack_separately(self):
        from types import SimpleNamespace
        from natural20.utils.spell_attack_util import evaluate_spell_attack

        props = self.session.load_spell('scorching_ray')
        action = SimpleNamespace()
        rolls = [evaluate_spell_attack(self.session, self.caster, self.attacker, props, battle=self.battle,
                                       opts={'action': action, 'attack_index': i})[1] for i in range(3)]
        self.assertEqual(len({id(r) for r in rolls}), 3)
        again = evaluate_spell_attack(self.session, self.caster, self.attacker, props, battle=self.battle,
                                      opts={'action': action, 'attack_index': 1})[1]
        self.assertIs(again, rolls[1])

    def test_spell_attack_into_mirror_image_is_tagged(self):
        from types import SimpleNamespace
        from natural20.utils.spell_attack_util import evaluate_spell_attack, mirror_image_outcome_for

        self._cast()
        props = self.session.load_spell('scorching_ray')
        action = SimpleNamespace()
        outcome = {'model': 'd20_redirect', 'images': 3, 'destroyed': True, 'remaining': 2}
        with patch.object(MirrorImageSpell, 'check_attack', return_value=outcome):
            hit, roll, *_ = evaluate_spell_attack(self.session, self.attacker, self.caster, props,
                                                  battle=self.battle, opts={'action': action, 'attack_index': 0})
        self.assertFalse(hit)
        self.assertIs(mirror_image_outcome_for(action, roll, self.caster), outcome)

    def test_tile_reports_remaining_duplicates(self):
        self.assertEqual(MirrorImageSpell.images_remaining_for(self.caster), 0)
        self._cast()
        MirrorImageSpell._consume_image(self.caster)
        self.assertEqual(MirrorImageSpell.images_remaining_for(self.caster), 2)
        MirrorImageSpell._consume_image(self.caster)
        MirrorImageSpell._consume_image(self.caster)
        self.assertEqual(MirrorImageSpell.images_remaining_for(self.caster), 0)
        self.assertNotIn('mirror_image', self.caster.statuses)

    def test_active_effect_survives_save_load(self):
        from natural20.utils.serialization import Serialization

        action = SpellAction.build(self.session, self.caster)['next'](['mirror_image', 1])['next'](self.caster)
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        self.battle.commit(action)
        MirrorImageSpell._consume_image(self.caster)

        serializer = Serialization()
        yaml_str = serializer.serialize(self.session, self.battle, [self.battle_map])
        _session, _battle, maps = serializer.deserialize(yaml_str)

        caster = next(e for e in maps[0].entities if e.entity_uid == self.caster.entity_uid)
        effect = next(
            entry['effect']
            for entries in caster.effects.values()
            for entry in entries
            if isinstance(entry.get('effect'), MirrorImageSpell)
        )
        self.assertEqual(effect.images_remaining, 2)
        self.assertIs(effect.source, caster)
        self.assertEqual(MirrorImageSpell._images_remaining(caster), 2)


if __name__ == '__main__':
    unittest.main()

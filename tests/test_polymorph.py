import random
import unittest
from types import SimpleNamespace

from natural20.battle import Battle
from natural20.entity_class import wild_shape as ws
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.npc import Npc
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.polymorph_spell import PolymorphSpell
from natural20.utils import polymorph


class PolymorphTestCase(unittest.TestCase):
    def setUp(self):
        random.seed(4242)
        event_manager = EventManager()
        event_manager.standard_cli()
        self.session = Session(root_path='tests/fixtures', event_manager=event_manager)
        self.events = []
        original = event_manager.received_event

        def record(event):
            self.events.append(event)
            return original(event)

        event_manager.received_event = record

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
        self.spell = PolymorphSpell(self.session, self.caster, 'polymorph',
                                    self.session.load_spell('polymorph'))
        self.spell.source = self.caster

    def _resolve(self, target, save_total=None):
        if save_total is not None:
            roll = SimpleNamespace(result=lambda: save_total, prob=lambda dc: 0.5)
            target.save_throw = lambda *a, **k: roll
        action = SimpleNamespace(target=target)
        self.spell.action = action
        return self.spell.resolve(self.caster, self.battle, action, self.battle_map)

    def _cast(self, target, save_total=None):
        items = self._resolve(target, save_total)
        for item in items:
            PolymorphSpell.apply(self.battle, item, self.session)
        return items

    def _event_names(self):
        return [e.get('event') for e in self.events]


class TestPolymorphNpc(PolymorphTestCase):
    def test_failed_save_is_logged_and_transforms(self):
        hp_before = self.enemy.hp()
        items = self._cast(self.enemy, save_total=1)
        self.assertEqual(items[0]['type'], 'polymorph')
        self.assertEqual(items[0]['beast'], 'cat')
        self.assertIn('save_fail', self._event_names())
        self.assertIn('polymorph', self._event_names())
        self.assertTrue(polymorph.is_polymorphed(self.enemy))
        self.assertIn(polymorph.STATUS, self.enemy.statuses)
        self.assertEqual(self.enemy.max_hp(), 2)
        self.assertEqual(self.enemy.hp(), 2)
        self.assertEqual(self.enemy.ability_scores['int'], 3)
        self.assertEqual(self.caster.current_concentration(), self.spell)
        self.assertNotEqual(hp_before, self.enemy.hp())

    def test_successful_save_misses(self):
        items = self._cast(self.enemy, save_total=30)
        self.assertEqual(items[0]['type'], 'spell_miss')
        self.assertFalse(polymorph.is_polymorphed(self.enemy))

    def test_concentration_end_reverts(self):
        hp_before = self.enemy.hp()
        max_before = self.enemy.max_hp()
        self._cast(self.enemy, save_total=1)
        self.caster.dismiss_effect(self.spell)
        self.assertFalse(polymorph.is_polymorphed(self.enemy))
        self.assertNotIn(polymorph.STATUS, self.enemy.statuses)
        self.assertEqual(self.enemy.hp(), hp_before)
        self.assertEqual(self.enemy.max_hp(), max_before)
        self.assertIn('polymorph_end', self._event_names())

    def test_zero_hp_reverts_with_overflow_and_ends_spell(self):
        hp_before = self.enemy.hp()
        self._cast(self.enemy, save_total=1)
        self.enemy.take_damage(4, battle=self.battle, damage_type='slashing')
        self.assertFalse(polymorph.is_polymorphed(self.enemy))
        self.assertEqual(self.enemy.hp(), hp_before - 2)
        self.assertFalse(self.enemy.dead())
        self.assertIsNone(self.caster.current_concentration())
        self.assertEqual(
            [e for e in self.events if e.get('event') == 'polymorph_end'][-1]['reason'],
            'dropped_to_zero')

    def test_beast_form_has_no_spells_or_features(self):
        self._cast(self.enemy, save_total=1)
        types = {a.action_type for a in self.enemy.available_actions(self.session, self.battle)}
        self.assertTrue(types <= polymorph.ALLOWED_ACTION_TYPES, types)

    def test_shapechanger_is_unaffected(self):
        self.enemy.properties['race'] = ['humanoid', 'shapechanger']
        items = self._cast(self.enemy, save_total=1)
        self.assertEqual(items[0]['type'], 'polymorph_unaffected')
        self.assertEqual(items[0]['reason'], 'shapechanger')
        self.assertIn('polymorph_unaffected', self._event_names())
        self.assertFalse(polymorph.is_polymorphed(self.enemy))

    def test_save_load_round_trip(self):
        hp_before = self.enemy.hp()
        self._cast(self.enemy, save_total=1)
        restored = Npc.from_dict(self.enemy.to_dict())
        self.assertTrue(polymorph.is_polymorphed(restored))
        self.assertEqual(restored.ability_scores['int'], 3)
        polymorph.revert(restored, end_spell=False)
        self.assertEqual(restored.hp(), hp_before)


class TestPolymorphPlayerCharacter(PolymorphTestCase):
    def test_willing_ally_becomes_beast(self):
        int_before = self.ally.ability_scores['int']
        items = self._cast(self.ally)
        self.assertEqual(items[0]['type'], 'polymorph')
        self.assertEqual(items[0]['beast'], 'wolf')
        self.assertTrue(ws.is_wild_shaped(self.ally))
        self.assertEqual(ws.form_source(self.ally), 'polymorph')
        self.assertTrue(polymorph.is_polymorphed(self.ally))
        self.assertEqual(self.ally.hp(), 11)
        self.assertNotEqual(self.ally.ability_scores['int'], int_before)

    def test_polymorphed_pc_cannot_cast_or_revert_like_wild_shape(self):
        self._cast(self.ally)
        types = {a.action_type for a in self.ally.available_actions(self.session, self.battle)}
        self.assertNotIn('spell', types)
        self.assertNotIn('revert_wild_shape', types)
        self.assertTrue(types <= polymorph.ALLOWED_ACTION_TYPES, types)

    def test_concentration_end_restores_pc(self):
        hp_before = self.ally.hp()
        int_before = self.ally.ability_scores['int']
        self._cast(self.ally)
        self.caster.dismiss_effect(self.spell)
        self.assertFalse(ws.is_wild_shaped(self.ally))
        self.assertEqual(self.ally.hp(), hp_before)
        self.assertEqual(self.ally.ability_scores['int'], int_before)

    def test_big_hit_in_beast_form_is_not_massive_damage(self):
        hp_before = self.ally.hp()
        self._cast(self.ally)
        self.ally.take_damage(11 + 3, battle=self.battle, damage_type='slashing')
        self.assertFalse(ws.is_wild_shaped(self.ally))
        self.assertFalse(self.ally.dead())
        self.assertEqual(self.ally.hp(), hp_before - 3)

    def test_save_load_round_trip(self):
        self._cast(self.ally)
        restored = PlayerCharacter.from_dict(self.ally.to_dict())
        self.assertTrue(polymorph.is_polymorphed(restored))
        self.assertEqual(ws.form_source(restored), 'polymorph')


if __name__ == '__main__':
    unittest.main()

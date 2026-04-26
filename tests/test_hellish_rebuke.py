import random
import unittest
import numpy as np

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.battle import Battle
from natural20.map import Map
from natural20.actions.spell_action import SpellAction
from natural20.spell.hellish_rebuke_spell import HellishRebukeSpell
from natural20.die_roll import DieRoll
from natural20.controller import Controller


class _ReactionController(Controller):
    """Minimal controller that always accepts the first reaction option."""

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


class TestHellishRebuke(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        np.random.seed(7000)
        random.seed(7000)
        self.warlock = PlayerCharacter.load(self.session, 'tiefling_warlock.yml')
        self.battle.add(self.warlock, 'a', position=[0, 5])
        self.battle.start()
        self.warlock.reset_turn(self.battle)

    # --- spell metadata / loader ---

    def test_spell_loads(self):
        spell = self.session.load_spell('hellish_rebuke')
        self.assertIsNotNone(spell)
        self.assertEqual(spell['casting_time'], '1:reaction')
        self.assertEqual(spell['damage_type'], 'fire')
        self.assertEqual(spell['range'], 60)
        self.assertEqual(spell['level'], 1)
        self.assertTrue(spell.get('triggers_on_damage'))
        self.assertIn('Warlock', spell['spell_list_classes'])

    def test_warlock_has_spell_in_prepared_list(self):
        self.assertIn('hellish_rebuke', self.warlock.prepared_spells())

    # --- damage math ---

    def _add_target(self, position=(0, 6)):
        npc = self.session.npc('skeleton')
        self.battle.add(npc, 'b', position=list(position))
        npc.reset_turn(self.battle)
        return npc

    def test_full_damage_on_failed_save(self):
        npc = self._add_target()
        action = SpellAction.build(self.session, self.warlock)['next'](['hellish_rebuke', 0])['next'](npc)
        # Force the save to fail by patching DEX save below the DC.
        original_save = npc.save_throw

        def low_save(ability, battle=None, opts=None):
            roll = original_save(ability, battle, opts)
            roll.rolls = [1]
            return roll
        npc.save_throw = low_save
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        result = action.result[0]
        self.assertEqual(result['type'], 'spell_damage')
        self.assertEqual(result['damage_type'], 'fire')
        # Full damage equals damage_roll.result()
        self.assertEqual(result['damage'].result(), result['damage_roll'].result())

    def test_half_damage_on_successful_save(self):
        npc = self._add_target()
        action = SpellAction.build(self.session, self.warlock)['next'](['hellish_rebuke', 0])['next'](npc)
        original_save = npc.save_throw

        def high_save(ability, battle=None, opts=None):
            roll = original_save(ability, battle, opts)
            roll.rolls = [20]
            return roll
        npc.save_throw = high_save
        action.resolve(self.session, self.battle_map, {'battle': self.battle})
        result = action.result[0]
        self.assertEqual(result['type'], 'spell_damage')
        full = result['damage_roll'].result()
        half = result['damage']
        self.assertEqual(half, full // 2)

    def test_upcast_adds_die(self):
        npc = self._add_target()
        spell = self.session.load_spell('hellish_rebuke')
        action = SpellAction(self.session, self.warlock, 'spell')
        action.spell = spell
        action.level = 1
        action.at_level = 2
        action.spell_class = HellishRebukeSpell
        si = HellishRebukeSpell(self.session, self.warlock, 'HellishRebukeSpell', spell)
        si.action = action
        action.spell_action = si
        action.target = npc
        roll = si._damage(self.battle, opts={'at_level': 2})
        # 3d10 expected at upcast level 2
        self.assertEqual(len(roll.rolls), 3)
        # Base 2d10 at level 1
        roll1 = si._damage(self.battle, opts={'at_level': 1})
        self.assertEqual(len(roll1.rolls), 2)

    def test_resource_consumed(self):
        npc = self._add_target()
        self.assertTrue(self.warlock.has_reaction(self.battle))
        action = SpellAction.build(self.session, self.warlock)['next'](['hellish_rebuke', 0])['next'](npc)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertFalse(self.warlock.has_reaction(self.battle))

    def test_can_cast_blocked_when_no_reaction(self):
        # Drain the reaction.
        self.battle.consume(self.warlock, 'reaction')
        self.assertFalse(self.warlock.has_reaction(self.battle))
        self.assertFalse(SpellAction.can_cast(self.warlock, self.battle, 'hellish_rebuke'))

    # --- auto-trigger on damage taken ---

    def test_reaction_fires_when_damaged(self):
        attacker = self._add_target(position=(0, 6))
        # Wire controllers so the warlock will accept the reaction.
        self.battle.set_controller_for(self.warlock, _ReactionController(self.session, accept=True))
        # Make sure the warlock will fail damage (he's unarmored vs sword), and
        # force the skeleton's DEX save to fail so the spell deals damage.
        original_save = attacker.save_throw

        def low_save(ability, battle=None, opts=None):
            roll = original_save(ability, battle, opts)
            roll.rolls = [1]
            return roll
        attacker.save_throw = low_save

        attacker_start_hp = attacker.hp()
        # Apply damage to the warlock from the attacker.
        item = {'source': attacker, 'attack_name': 'unarmed_attack'}
        self.warlock.take_damage(3, battle=self.battle, damage_type='slashing',
                                 session=self.session, item=item)

        # The reaction should have consumed the warlock's reaction and dealt
        # fire damage to the attacker.
        self.assertFalse(self.warlock.has_reaction(self.battle))
        self.assertLess(attacker.hp(), attacker_start_hp)

    def test_reaction_skipped_when_controller_declines(self):
        attacker = self._add_target(position=(0, 6))
        self.battle.set_controller_for(self.warlock, _ReactionController(self.session, accept=False))
        attacker_start_hp = attacker.hp()
        item = {'source': attacker, 'attack_name': 'unarmed_attack'}
        self.warlock.take_damage(3, battle=self.battle, damage_type='slashing',
                                 session=self.session, item=item)
        self.assertTrue(self.warlock.has_reaction(self.battle))
        self.assertEqual(attacker.hp(), attacker_start_hp)


if __name__ == '__main__':
    unittest.main()

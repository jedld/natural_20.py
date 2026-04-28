# pyright: reportGeneralTypeIssues=false

import random
import unittest

from natural20.actions.attack_action import AttackAction
from natural20.action import AsyncReactionHandler
from natural20.controller import Controller
from natural20.die_roll import DieRoll
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class AlwaysSmiteController(Controller):
    def __init__(self, session):
        super().__init__(session)

    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        return valid_actions[0] if valid_actions else None


class AsyncSmiteController(Controller):
    def __init__(self, session):
        super().__init__(session)

    def select_reaction(self, entity, battle, map_obj, valid_actions, event):
        yield entity, event, valid_actions


class TestDivineSmite(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        random.seed(8128)
        self.session = self.make_session()
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)

    def _prepare_paladin(self, controller):
        paladin = PlayerCharacter.load(self.session, 'goliath_paladin.yml')
        self.battle.add(paladin, 'heroes', controller=controller, position=[0, 5])
        return paladin

    def _prepare_enemy(self, name, position):
        enemy = self.session.npc(name)
        self.battle.add(enemy, 'foes', position=position)
        return enemy

    def _execute_attack(self, attacker, target):
        attack = AttackAction(self.session, attacker, 'attack')
        attack.target = target
        attack.using = 'warhammer'
        DieRoll.fudge(18)
        self.battle.execute_action(attack)
        return attack

    def test_divine_smite_consumes_resources(self):
        controller = AlwaysSmiteController(self.session)
        paladin = self._prepare_paladin(controller)
        enemy = self._prepare_enemy('goblin', [1, 5])
        self.battle.start()
        paladin.reset_turn(self.battle)
        enemy.reset_turn(self.battle)

        initial_slots = paladin.spell_slots['paladin'][1]
        initial_bonus = self.battle.entity_state_for(paladin)['bonus_action']

        attack = self._execute_attack(paladin, enemy)

        smite = next((item for item in attack.result if isinstance(item, dict) and item.get('trigger') == 'divine_smite'), None)
        self.assertIsNotNone(smite, 'Divine Smite result not found in attack resolution')
        self.assertEqual(smite['damage_type'], 'radiant')
        self.assertEqual(len(smite['damage_roll'].rolls), 2)

        # Divine Smite costs no action — only the spell slot is consumed.
        self.assertEqual(paladin.spell_slots['paladin'][1], initial_slots - 1)
        self.assertEqual(self.battle.entity_state_for(paladin)['bonus_action'], initial_bonus)

        self.battle.commit(attack)
        self.assertLess(enemy.hp(), enemy.max_hp())

    def test_divine_smite_bonus_vs_undead(self):
        controller = AlwaysSmiteController(self.session)
        paladin = self._prepare_paladin(controller)
        undead = self._prepare_enemy('skeleton', [1, 5])
        self.battle.start()
        paladin.reset_turn(self.battle)
        undead.reset_turn(self.battle)

        attack = self._execute_attack(paladin, undead)

        smite = next((item for item in attack.result if isinstance(item, dict) and item.get('trigger') == 'divine_smite'), None)
        self.assertIsNotNone(smite, 'Divine Smite result not found in attack resolution')
        # Undead targets add an extra d8
        self.assertEqual(len(smite['damage_roll'].rolls), 3)
        self.battle.commit(attack)

    def test_divine_smite_async_flow(self):
        controller = AsyncSmiteController(self.session)
        paladin = self._prepare_paladin(controller)
        foe = self._prepare_enemy('goblin', [1, 5])
        self.battle.start()
        paladin.reset_turn(self.battle)
        foe.reset_turn(self.battle)

        attack = AttackAction(self.session, paladin, 'attack')
        attack.target = foe
        attack.using = 'warhammer'
        DieRoll.fudge(18)

        try:
            self.battle.action(attack)
        except AsyncReactionHandler as handler:
            self.assertEqual(handler.reaction_type, 'on_attack_hit')
            for _, _, actions in handler.resolve():
                handler.send(actions[0])
            attack = self.battle.action(attack)

        smite = next((item for item in attack.result if isinstance(item, dict) and item.get('trigger') == 'divine_smite'), None)
        self.assertIsNotNone(smite)
        self.battle.commit(attack)

    def test_divine_smite_dice_cap(self):
        """Per RAW Divine Smite caps at 5d8 (6d8 vs undead/fiend)."""
        from natural20.actions.divine_smite_action import DivineSmiteAction

        controller = AlwaysSmiteController(self.session)
        paladin = self._prepare_paladin(controller)
        goblin = self._prepare_enemy('goblin', [1, 5])
        skeleton = self._prepare_enemy('skeleton', [2, 5])
        spell_details = self.session.load_spell('divine_smite')

        # 1st-level slot: 2d8 base
        action = DivineSmiteAction(self.session, paladin, goblin, 1, spell_details, {})
        self.assertEqual(action._damage_dice_count(), 2)

        # 4th-level slot: capped at 5d8
        action = DivineSmiteAction(self.session, paladin, goblin, 4, spell_details, {})
        self.assertEqual(action._damage_dice_count(), 5)

        # 5th-level slot: still capped at 5d8 (no further increase)
        action = DivineSmiteAction(self.session, paladin, goblin, 5, spell_details, {})
        self.assertEqual(action._damage_dice_count(), 5)

        # 4th-level slot vs undead: 5d8 + 1d8 = 6d8
        action = DivineSmiteAction(self.session, paladin, skeleton, 4, spell_details, {})
        self.assertEqual(action._damage_dice_count(), 6)

        # 5th-level slot vs undead: still 6d8 (cap)
        action = DivineSmiteAction(self.session, paladin, skeleton, 5, spell_details, {})
        self.assertEqual(action._damage_dice_count(), 6)

    def test_divine_smite_doubles_dice_on_crit(self):
        """A critical hit doubles the Divine Smite damage dice."""
        controller = AlwaysSmiteController(self.session)
        paladin = self._prepare_paladin(controller)
        enemy = self._prepare_enemy('goblin', [1, 5])
        self.battle.start()
        paladin.reset_turn(self.battle)
        enemy.reset_turn(self.battle)

        attack = AttackAction(self.session, paladin, 'attack')
        attack.target = enemy
        attack.using = 'warhammer'
        # Force a natural 20 on the attack roll.
        DieRoll.fudge(20)
        self.battle.execute_action(attack)

        smite = next((item for item in attack.result if isinstance(item, dict) and item.get('trigger') == 'divine_smite'), None)
        self.assertIsNotNone(smite, 'Divine Smite result not found in attack resolution')
        # Base 2d8 doubled = 4d8 of radiant on a crit.
        self.assertEqual(len(smite['damage_roll'].rolls), 4)
        self.battle.commit(attack)


if __name__ == '__main__':
    unittest.main()

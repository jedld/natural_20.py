import pdb
import random
import unittest

from natural20.actions.attack_action import AttackAction, LinkedAttackAction
from natural20.actions.move_action import MoveAction
from natural20.actions.spell_action import SpellAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.map_renderer import MapRenderer
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.action_builder import autobuild
from natural20.weapons import target_advantage_condition
from natural20.die_roll import DieRoll

class TestClericSpellAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        return Session(root_path="tests/fixtures", event_manager=event_manager)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, "dwarf_cleric.yml")
        self.battle_map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.battle_map)
        self.npc = self.battle_map.entity_at(5, 5)
        self.battle.add(self.entity, "a", position=[0, 5])
        self.battle.add(self.npc, "b")
        self.entity.reset_turn(self.battle)


    def test_sacred_flame(self):
        random.seed(7003)
        self.assertEqual(self.npc.hp(), 9)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)["next"](
            ["sacred_flame", 0]
        )["next"](self.npc)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual([s["type"] for s in action.result], ["spell_damage"])
        self.battle.commit(action)
        self.assertEqual(self.npc.hp(), 1)

    def test_guiding_bolt(self):
        random.seed(7009)
        self.npc.attributes["hp"] = 21
        self.assertEqual(self.npc.hp(), 21)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)["next"](
            ["guiding_bolt", 0]
        )["next"](self.npc)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual(
            [s["type"] for s in action.result], ["spell_damage", "guiding_bolt"]
        )
        self.battle.commit(action)

        adv_mod, adv_info = target_advantage_condition(
            self.session, self.entity, self.npc, action.spell_action.properties, battle=self.battle
        )
        self.assertEqual(adv_info, [["guiding_bolt_advantage"], []])
        self.assertEqual(adv_mod, 1)
        self.assertEqual(self.npc.hp(), 1)
        self.entity.resolve_trigger("end_of_turn")
        adv_mod, adv_info = target_advantage_condition(
            self.session, self.entity, self.npc, action.spell_action.properties, battle=self.battle
        )
        self.assertEqual(adv_mod, 1)
        self.assertEqual(adv_info, [["guiding_bolt_advantage"], []])
        self.assertEqual(self.npc.light_properties(), {'dim': 1, 'bright': 0})
        self.entity.resolve_trigger("start_of_turn")
        self.entity.resolve_trigger("end_of_turn")
        adv_mod, adv_info = target_advantage_condition(
            self.session, self.entity, self.npc, action.spell_action.properties, battle=self.battle
        )
        self.assertEqual(adv_mod, 0)
        self.assertEqual(adv_info, [[], []])

    def test_guiding_bolt_with_next_attack_action(self):
        self.entity2 = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.assertTrue(self.entity2.darkvision(30))
        self.battle.add(self.entity2, "a", position=[3, 6], token='*')
        self.battle.start()
        self.entity2.reset_turn(self.battle)
        random.seed(7009)
        self.npc.attributes["hp"] = 21
        self.assertEqual(self.npc.hp(), 21)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)["next"](
            ["guiding_bolt", 0]
        )["next"](self.npc)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual(
            [s["type"] for s in action.result], ["spell_damage", "guiding_bolt"]
        )
        self.battle.commit(action)

        adv_mod, adv_info = target_advantage_condition(
            self.session, self.entity, self.npc, action.spell_action.properties, battle=self.battle
        )
        self.assertEqual(adv_info, [["guiding_bolt_advantage"], []])
        self.assertEqual(adv_mod, 1)
        self.assertEqual(self.npc.hp(), 1)

        action = autobuild(
            self.session,
            AttackAction,
            self.entity2,
            self.battle,
            self.battle_map,
            match=[self.npc, "longbow"],
            verbose=True
        )[0]

        self.assertIsNotNone(action)
        adv_mod, adv_info = target_advantage_condition(
            self.session, self.entity, self.npc, action.using, battle=self.battle
        )
        self.assertEqual(adv_info, [["guiding_bolt_advantage"], []])
        self.assertEqual(adv_mod, 1)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.battle.commit(action)


    def test_cure_wounds(self):
        random.seed(7003)
        self.entity.take_damage(4, session=self.session)
        self.assertEqual(self.entity.hp(), 4)
        print(MapRenderer(self.battle_map).render())
        action = SpellAction.build(self.session, self.entity)["next"](
            ["cure_wounds", 0]
        )["next"](self.entity)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual([s["type"] for s in action.result], ["spell_heal"])
        self.battle.commit(action)
        self.assertEqual(self.entity.hp(), 8)

    def test_bless(self):
        random.seed(7003)
        self.entity2 = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity2, "a", position=[0, 6], token="E")
        self.battle.start()
        self.entity2.reset_turn(self.battle)
        bless_action = SpellAction.build(self.session, self.entity)["next"](
            ["bless", 0]
        )["next"]([self.entity2])
        bless_action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual([s["type"] for s in bless_action.result], ["bless"])
        self.battle.commit(bless_action)

        self.assertEqual(str(self.entity.current_concentration()), "bless")
        self.assertTrue(self.entity2.has_effect("bless"))
        print(MapRenderer(self.battle_map).render())

        action = AttackAction.build(self.session, self.entity2)["next"]("dagger")[
            "next"
        ](self.npc)
        action = action.resolve(self.session, self.battle_map, {"battle": self.battle})
        result = action.result[0]
        self.assertEqual(str(result["attack_roll"]), "d20(9) + 8 + d4(4)")
        result = self.entity2.save_throw("wisdom", self.battle)
        self.assertEqual(str(result), "d20(5) + 1 + d4(2)")
        self.entity2.dismiss_effect(bless_action.spell_action)
        result = self.entity2.save_throw("wisdom", self.battle)
        self.assertEqual(str(result), "d20(11) + 1")

    def test_bless_multiple_targets(self):
        random.seed(7003)
        self.entity2 = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity2, "a", position=[0, 6], token="E")
        self.battle.start()
        self.entity2.reset_turn(self.battle)

        self.entity3 = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity3, "b", position=[0, 7], token="E")
        self.battle.start()
        self.entity3.reset_turn(self.battle)

        bless_action = SpellAction.build(self.session, self.entity)["next"](
            ["bless", 0]
        )["next"]([self.entity2, self.entity3])
        bless_action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual([s["type"] for s in bless_action.result], ["bless", "bless"])
        self.battle.commit(bless_action)

        self.assertTrue(self.entity2.has_effect("bless"))
        self.assertTrue(self.entity3.has_effect("bless"))
        self.entity3.make_dead()
        self.assertTrue(self.entity2.has_effect("bless"))
        self.assertTrue(self.entity.has_casted_effect('bless'))

    def test_protection_from_poison(self):
        random.seed(7003)
        self.entity2 = PlayerCharacter.load(self.session, "high_elf_fighter.yml")
        self.battle.add(self.entity2, "a", position=[0, 6], token="E")
        self.battle.start()
        print(MapRenderer(self.battle_map).render())
        action = autobuild(
            self.session,
            SpellAction,
            self.entity,
            self.battle,
            self.battle_map,
            match=["protection_from_poison", self.entity2],
        )[0]
        self.assertIsInstance(action, SpellAction)
        action.resolve(self.session, self.battle_map, {"battle": self.battle})
        self.assertEqual([s["type"] for s in action.result], ["protection_from_poison"])
        self.battle.commit(action)

    def test_spiritual_weapon(self):
        self.battle.add(self.entity, "a", position=[0, 1])
        self.battle.start()
        self.entity.reset_turn(self.battle)
        self.battle.set_current_turn(self.entity)
        print(MapRenderer(self.battle_map).render())
        action = autobuild(
            self.session,
            SpellAction,
            self.entity,
            self.battle,
            self.battle_map,
            match=["spiritual_weapon", [3, 6]],
            verbose=True
        )[0]
        self.assertIsInstance(action, SpellAction)
        self.battle.action(action)
        self.battle.commit(action)
        print(MapRenderer(self.battle_map).render())
        spiritual_weapon = self.battle_map.entity_at(3, 6)
        self.assertEqual(str(spiritual_weapon.damage), "1d8+3")
        self.entity.reset_turn(self.battle)
        available_spiritual_weapon_actions = spiritual_weapon.available_actions(
            self.session, self.battle
        )
        self.assertEqual(spiritual_weapon.hp(), None)
        self.assertEqual(
            [str(a) for a in available_spiritual_weapon_actions],
            ["move", "spiritual_weapon uses spiritual_weapon on None"],
        )
        self.battle.entity_state_for(self.entity)['action'] = 0
        available_spiritual_weapon_actions = spiritual_weapon.available_actions(
            self.session, self.battle
        )
        self.assertEqual(
            [str(a) for a in available_spiritual_weapon_actions],
            ["move", "spiritual_weapon uses spiritual_weapon on None"],
        )
        self.assertEqual(self.entity.has_casted_effect("spiritual_weapon"), True)

        # move weapon
        
        action = autobuild(
            self.session,
            MoveAction,
            spiritual_weapon,
            self.battle,
            self.battle_map,
            match=[[4, 6]]
        )[0]
        self.battle.action(action)
        self.battle.commit(action)
        print(MapRenderer(self.battle_map).render())

        entity_target = self.battle_map.entity_at(5, 5)
        self.battle.add(entity_target, "b")
        self.assertIsNotNone(entity_target)
        self.entity.reset_turn(self.battle)
        self.assertTrue(self.entity.has_bonus_action(self.battle))
        # attack with it
        action = autobuild(
            self.session,
            LinkedAttackAction,
            spiritual_weapon,
            self.battle,
            self.battle_map,
            match=[entity_target, "spiritual_weapon"],
            verbose=True
        )[0]
        action.as_bonus_action = True
        DieRoll.fudge(20)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertFalse(self.entity.has_bonus_action(self.battle))
        print(MapRenderer(self.battle_map).render())
        self.assertEqual(self.npc.hp(), 0)
        self.entity.reset_turn(self.battle)
        # player casts it again, should dismiss the previous ome
        action = autobuild(
            self.session,
            SpellAction,
            self.entity,
            self.battle,
            self.battle_map,
            match=["spiritual_weapon", [3, 6]],
        )[0]
        self.battle.action(action)
        self.battle.commit(action)
        print(MapRenderer(self.battle_map).render())
        spiritual_weapon = self.battle_map.entity_at(4, 6)
        self.assertEqual(spiritual_weapon, None)

    def test_compute_hit_probability(self):
        self.entity.ability_scores["wis"] = 20
        self.npc = self.session.npc("ogre")
        self.battle.add(self.npc, "b", position=[0, 6])

        self.npc.reset_turn(self.battle)
        self.assertEqual(self.entity.spell_save_dc("wisdom"), 15)

        action = SpellAction.build(self.session, self.entity)["next"](
            ["sacred_flame", 0]
        )["next"](self.npc)
        self.assertAlmostEqual(action.compute_hit_probability(self.battle), 0.75)
        self.assertAlmostEqual(action.avg_damage(self.battle), 4.5)

    def test_autobuild(self):
        self.npc = self.session.npc("skeleton")
        self.battle.add(self.npc, "b", position=[0, 6])
        auto_build_actions = autobuild(
            self.session, SpellAction, self.entity, self.battle
        )
        self.assertEqual(len(auto_build_actions), 13)
        actual_actions = sorted([str(a) for a in auto_build_actions])

        self.assertEqual(
           actual_actions,
            ['SpellAction: cure_wounds to Shor Valu',
             'SpellAction: guiding_bolt to Frenabs',
             'SpellAction: guiding_bolt to Skeleton',
             'SpellAction: protection_from_poison to Shor Valu',
             'SpellAction: sacred_flame to Frenabs',
             'SpellAction: sacred_flame to Skeleton',
             'SpellAction: spiritual_weapon to [2, 5]',
             'SpellAction: spiritual_weapon to [3, 5]',
             'SpellAction: spiritual_weapon to [3, 6]',
             'SpellAction: spiritual_weapon to [4, 5]',
             'SpellAction: spiritual_weapon to [4, 6]',
             'SpellAction: spiritual_weapon to [6, 5]',
             'SpellAction: spiritual_weapon to [7, 6]'
            ]
        )


if __name__ == "__main__":
    unittest.main()

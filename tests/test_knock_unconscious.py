import unittest

from natural20.actions.attack_action import AttackAction
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


class TestKnockUnconscious(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures', event_manager=EventManager())
        self.battle_map = Map(self.session, 'battle_sim')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin')
        self.battle_map.place((0, 0), self.fighter, 'G')
        self.battle_map.place((1, 0), self.goblin, 'g')

    def test_default_melee_damage_kills_npc_at_zero(self):
        self.goblin.take_damage(self.goblin.hp(), session=self.session)
        self.assertTrue(self.goblin.dead())
        self.assertFalse(self.goblin.unconscious())

    def test_knockout_leaves_npc_unconscious_and_stable(self):
        self.goblin.take_damage(
            self.goblin.hp(),
            session=self.session,
            item={'source': self.fighter, 'knock_unconscious': True},
        )
        self.assertFalse(self.goblin.dead())
        self.assertTrue(self.goblin.unconscious())
        self.assertTrue(self.goblin.stable())
        self.assertEqual(self.goblin.hp(), 0)

    def test_knockout_overrides_massive_damage(self):
        self.goblin.take_damage(
            self.goblin.max_hp() * 3,
            session=self.session,
            item={'source': self.fighter, 'knock_unconscious': True},
        )
        self.assertFalse(self.goblin.dead())
        self.assertTrue(self.goblin.unconscious())
        self.assertTrue(self.goblin.stable())

    def test_knockout_makes_pc_stable_at_zero(self):
        self.fighter.take_damage(
            self.fighter.hp(),
            session=self.session,
            item={'knock_unconscious': True},
        )
        self.assertFalse(self.fighter.dead())
        self.assertTrue(self.fighter.unconscious())
        self.assertTrue(self.fighter.stable())

    def test_pc_at_zero_without_knockout_is_unstable(self):
        self.fighter.take_damage(self.fighter.hp(), session=self.session)
        self.assertTrue(self.fighter.unconscious())
        self.assertFalse(self.fighter.stable())

    def test_follow_up_hit_on_knocked_out_npc_does_not_instant_kill(self):
        self.goblin.take_damage(
            self.goblin.hp(),
            session=self.session,
            item={'knock_unconscious': True},
        )
        self.goblin.take_damage(1, session=self.session)
        self.assertTrue(self.goblin.unconscious())
        self.assertFalse(self.goblin.dead())
        self.assertFalse(self.goblin.stable())

    def test_objects_ignore_knockout(self):
        from natural20.item_library.object import Object
        chest = Object(self.session, self.battle_map, {
            'name': 'crate',
            'max_hp': 5,
        })
        chest.take_damage(5, session=self.session, item={'knock_unconscious': True})
        self.assertTrue(chest.dead())
        self.assertFalse(chest.unconscious())

    def test_melee_attack_can_knock_unconscious(self):
        action = AttackAction(self.session, self.fighter, 'attack')
        action.using = 'rapier'
        self.assertTrue(action.can_knock_unconscious())

    def test_thrown_and_ranged_cannot_knock_unconscious(self):
        thrown = AttackAction(self.session, self.fighter, 'attack')
        thrown.using = 'rapier'
        thrown.thrown = True
        self.assertFalse(thrown.can_knock_unconscious())

        bow = AttackAction(self.session, self.fighter, 'attack')
        bow.using = 'longbow'
        self.assertFalse(bow.can_knock_unconscious())

    def test_resolve_gates_knockout_to_melee(self):
        action = AttackAction(self.session, self.fighter, 'attack')
        action.using = 'longbow'
        action.knock_unconscious = True
        action.target = self.goblin
        action.hit_result = {
            'source': self.fighter,
            'target': self.goblin,
            'type': 'damage',
            'thrown': False,
            'weapon': 'longbow',
            'battle': None,
            'damage': 1,
            'damage_type': 'piercing',
            'attack_name': 'longbow',
            'attack_roll': None,
            'knock_unconscious': bool(action.knock_unconscious) and action.can_knock_unconscious(),
        }
        self.assertFalse(action.hit_result['knock_unconscious'])

    def test_to_h_does_not_bake_in_knockout_mode(self):
        action = AttackAction(self.session, self.fighter, 'attack')
        action.using = 'rapier'
        payload = action.to_h()
        self.assertNotIn('knock_unconscious', payload)


if __name__ == '__main__':
    unittest.main()

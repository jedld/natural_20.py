import unittest
import random
from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.map import Map
from natural20.battle import Battle
from natural20.actions.spell_action import SpellAction


class TestThunderwaveSpell(unittest.TestCase):
    def make_session(self):
        em = EventManager()
        em.standard_cli()
        return Session(root_path='tests/fixtures', event_manager=em)

    def setUp(self):
        random.seed(7000)
        self.session = self.make_session()
        self.caster = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.map)
        # Place caster near an enemy so a centered 3x3 will include it
        self.battle.add(self.caster, 'a', position=[4, 5])
        # Nearby enemy at (5,5)
        self.enemy = self.map.entity_at(5, 5)
        self.battle.start()
        self.caster.reset_turn(self.battle)

    def test_thunderwave_push_and_damage(self):
        # Build thunderwave; no direction/target selection required
        action = SpellAction.build(self.session, self.caster)['next'](['thunderwave', 1])['next']()
        action.resolve(self.session, self.map, { 'battle': self.battle })
        # Expect at least one spell_damage for nearby enemy (5,5 is within 3 squares forward)
        types = [r['type'] for r in action.result]
        self.assertIn('spell_damage', types)
        # Commit to apply push effect
        self.battle.commit(action)
        # Ensure a thunderwave_push event was produced (movement may be blocked)
        push_events = [r for r in action.result if r.get('type') == 'thunderwave_push']
        self.assertGreaterEqual(len(push_events), 1)


if __name__ == '__main__':
    unittest.main()

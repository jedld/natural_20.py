import unittest

from natural20.battle import Battle
from natural20.llm_controller import LlmMcpController
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.spell.flaming_sphere_spell import FlamingSphereZone
from natural20.utils.hazard_context import hostile_hazard_lines
from natural20.utils.jev_decision import JevActionPlanner


def open_map(session, name='hazard_map'):
    return Map(
        session,
        None,
        name=name,
        properties={
            'name': name,
            'map': {
                'size': [6, 6],
                'base': ['......'] * 6,
            },
        },
    )


class HazardContextTests(unittest.TestCase):
    def setUp(self):
        self.session = Session('tests/fixtures')
        self.map = open_map(self.session)
        self.battle = Battle(self.session, self.map)
        self.hero = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.goblin = self.session.npc('goblin', {'name': 'Goblin'})
        self.map.place((0, 0), self.hero)
        self.map.place((2, 0), self.goblin)
        self.battle.add(self.hero, 'a')
        self.battle.add(self.goblin, 'b')
        self.battle.start(combat_order=[self.goblin, self.hero])
        self.spell = self.session.load_spell('flaming_sphere')

    def test_hostile_hazard_lines_lists_enemy_zone_not_ally_zone(self):
        hostile = FlamingSphereZone(self.goblin, self.battle, self.map, (3, 0), self.spell, dc=13, dice='2d6')
        friendly = FlamingSphereZone(self.hero, self.battle, self.map, (1, 0), self.spell, dc=13, dice='2d6')
        self.battle.active_zones.extend([hostile, friendly])

        lines = hostile_hazard_lines(self.battle, self.hero, self.map)

        self.assertEqual(len(lines), 1)
        self.assertIn('Flaming Sphere', lines[0])
        self.assertIn('(3, 0)', lines[0])
        self.assertIn('2d6 fire', lines[0])
        self.assertIn('DC13 dexterity save', lines[0])

    def test_jev_state_includes_hostile_hazards(self):
        zone = FlamingSphereZone(self.goblin, self.battle, self.map, (3, 0), self.spell, dc=13, dice='2d6')
        self.battle.active_zones.append(zone)

        state = JevActionPlanner(None)._render_state(self.battle, self.hero)

        self.assertIn('hostile hazards:', state)
        self.assertIn('Flaming Sphere', state)

    def test_llm_prompt_includes_hostile_hazards(self):
        zone = FlamingSphereZone(self.goblin, self.battle, self.map, (3, 0), self.spell, dc=13, dice='2d6')
        self.battle.active_zones.append(zone)

        controller = LlmMcpController(self.session)
        actions = self.hero.available_actions(self.session, self.battle)
        prompt = controller._build_prompt(self.battle, self.hero, actions)

        self.assertIn('Hostile hazards:', prompt)
        self.assertIn('Flaming Sphere', prompt)


class BlindsightVisionTests(unittest.TestCase):
    def setUp(self):
        self.session = Session('tests/fixtures')
        self.map = Map(
            self.session,
            None,
            name='blindsight_map',
            properties={
                'name': 'blindsight_map',
                'map': {
                    'size': [5, 5],
                    'base': ['.....'] * 5,
                },
            },
        )
        self.viewer = PlayerCharacter.load(self.session, 'high_elf_mage.yml')
        self.target = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.target_near = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.map.place((0, 0), self.viewer)
        self.map.place((1, 0), self.target_near)
        self.map.place((3, 0), self.target)
        self.viewer.properties['blindsight'] = 10

    def test_blindsight_does_not_suppress_normal_vision(self):
        self.map.light_at = lambda x, y: 1.0
        self.assertTrue(self.map.can_see(self.viewer, self.target))

    def test_blindsight_covers_darkness_within_range_only(self):
        self.map.light_at = lambda x, y: 0.0
        self.viewer.darkvision = lambda distance: False
        self.assertTrue(self.map.can_see(self.viewer, self.target_near))
        self.assertFalse(self.map.can_see(self.viewer, self.target))
        self.assertTrue(self.map.can_see_square(self.viewer, (1, 0)))
        self.assertFalse(self.map.can_see_square(self.viewer, (3, 0)))


if __name__ == '__main__':
    unittest.main()

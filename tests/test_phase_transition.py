import os
import random
import unittest
import yaml

from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session


PHASE2_NPC_FILENAME = 'phase2_dummy.yml'


class TestPhaseTransition(unittest.TestCase):
    def setUp(self):
        self.session = Session(
            root_path='tests/fixtures',
            event_manager=EventManager(),
        )
        self.map = Map(self.session, 'tests/fixtures/battle_sim.yml')
        self.session.register_map('test_map', self.map)
        random.seed(7003)

        # Author a minimal phase-2 fixture NPC on disk so Session.npc(...)
        # can locate it. Cleaned up in tearDown.
        self._phase2_path = os.path.join(
            self.session.root_path, 'npcs', PHASE2_NPC_FILENAME
        )
        with open(self._phase2_path, 'w') as f:
            yaml.safe_dump({
                'kind': 'phase2_dummy',
                'description': 'Phase 2 form for tests.',
                'size': 'medium',
                'race': ['humanoid'],
                'alignment': 'unaligned',
                'default_ac': 12,
                'max_hp': 20,
                'hp_die': '4d8 + 4',
                'speed': 30,
                'passive_perception': 10,
                'token': ['W'],
                'color': 'red',
                'ability': {'str': 14, 'dex': 10, 'con': 12, 'int': 5, 'wis': 10, 'cha': 5},
                'cr': 1,
                'xp': 200,
                'proficiency_bonus': 2,
                'attributes': [],
                'actions': [{
                    'name': 'slam',
                    'type': 'melee_attack',
                    'range': 5,
                    'targets': 1,
                    'attack': 4,
                    'damage': 5,
                    'damage_die': '1d6+2',
                    'damage_type': 'bludgeoning',
                }],
            }, f)

    def tearDown(self):
        try:
            os.remove(self._phase2_path)
        except OSError:
            pass

    def _build_phase1(self, *, transition=True):
        npc = self.session.npc('shamblingmound')
        if transition:
            npc.properties['phase_transition'] = {
                'npc': 'phase2_dummy',
                'label': 'Phase 2 Form',
                'narration': 'It rises again, twisted and reborn.',
            }
        return npc

    def test_phase_transition_swaps_entity_in_battle(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle = Battle(self.session, self.map)
        battle.add(fighter, 'a', position=[0, 1], token='G')
        npc = self._build_phase1()
        self.map.add(npc, 2, 2)
        battle.add(npc, 'b', add_to_initiative=True)
        original_uid = npc.entity_uid
        original_pos = self.map.position_of(npc)

        npc.make_dead(battle=battle)

        # The original entity should NOT actually be marked dead because the
        # phase transition fires instead.
        self.assertFalse(npc.dead(),
                         msg="phase transition should suppress normal death")

        # A new entity should now occupy the same square.
        new_entity = self.map.thing_at(*original_pos)[0]
        self.assertIsNotNone(new_entity)
        self.assertNotEqual(new_entity, npc)
        # UID is preserved by default.
        self.assertEqual(new_entity.entity_uid, original_uid)
        # New entity is wired into the battle. Because keep_uid is true by
        # default, both the old and the new python objects resolve to the
        # same UID-keyed slot; assert via the UID instead.
        self.assertIn(new_entity, battle.entities)
        self.assertIs(
            battle.entities.get_by_uid(str(original_uid))['controller'],
            battle.entities[new_entity]['controller'],
        )
        self.assertIn(new_entity, battle.combat_order)
        # Old entity object should not still occupy a separate slot in
        # combat order.
        self.assertEqual(
            battle.combat_order.count(new_entity), 1,
        )
        # Label override applied.
        self.assertEqual(new_entity.label(), 'Phase 2 Form')

    def test_phase_transition_only_fires_once(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle = Battle(self.session, self.map)
        battle.add(fighter, 'a', position=[0, 1], token='G')
        npc = self._build_phase1()
        self.map.add(npc, 2, 2)
        battle.add(npc, 'b', add_to_initiative=True)

        # First call: transitions silently.
        npc.make_dead(battle=battle)
        self.assertFalse(npc.dead())
        # Second call on the (now stale) old entity should fall through to a
        # real death rather than spawning yet another copy.
        npc.make_dead(battle=battle)
        self.assertTrue(npc.dead())

    def test_no_phase_transition_means_normal_death(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        battle = Battle(self.session, self.map)
        battle.add(fighter, 'a', position=[0, 1], token='G')
        npc = self._build_phase1(transition=False)
        self.map.add(npc, 2, 2)
        battle.add(npc, 'b', add_to_initiative=True)

        npc.make_dead(battle=battle)
        self.assertTrue(npc.dead())


if __name__ == '__main__':
    unittest.main()

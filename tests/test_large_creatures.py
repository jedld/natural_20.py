"""Regression tests for issue #6 (Large-creature follow-up, comment 7215852014).

Covers:
1. Ogre/Owlbear SRD 5.2.1 stat overlays (templates/rulesets/5e-2024/npcs/)
   and corrections to the 2014 base templates.
2. Squeezing: the status is actually SET on the mover, the map footprint and
   the melee ring follow the squeezed cell, MoveAction may end a move squeezed
   (matching the reachable-squares menu), and the squeeze attack modifiers are
   2014-only.
3. Cover: the GREATEST cover across every source-target square pair wins,
   independent of iteration order.
4. melee_squares: a Chebyshev ring around the creature's body squares
   (Medium 8 cells, Large 2x2 12 cells).
5. A Large grappler's dragged target may never end inside the footprint the
   grappler still occupies at the end of the move.
"""

import random
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

from natural20.actions.move_action import MoveAction
from natural20.battle import Battle
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.ruleset import get_ruleset
from natural20.session import Session
from natural20.utils.ac_utils import calculate_cover_ac
from natural20.weapons import compute_advantages_and_disadvantages

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TEMPLATES = HERE.parent / "templates"


def _sheet(path):
    with open(path, encoding='utf-8') as fh:
        return yaml.safe_load(fh)


def _action(actions, name):
    for a in actions:
        if a.get('name') == name:
            return a
    raise AssertionError(
        f"no action named {name!r} in {[a.get('name') for a in actions]}")


# ---------------------------------------------------------------------------
# Item 1: SRD 5.2.1 (2024) Ogre and Owlbear overlays + 2014 base corrections
# ---------------------------------------------------------------------------


class LargeCreatureTemplatesTest(unittest.TestCase):
    """The ruleset overlay root (templates/rulesets/<ruleset>/npcs/) shadows
    the base NPC sheets when the campaign declares that ruleset."""

    @classmethod
    def setUpClass(cls):
        # NB: the temp campaign is deliberately NOT deleted: Session registers
        # its locales/ directory with the process-global i18n loader, and a
        # removed directory breaks entity.label() in later tests.
        cls.tmp = tempfile.TemporaryDirectory()
        dest = Path(cls.tmp.name) / 'campaign'
        shutil.copytree(FIXTURES, dest,
                        ignore=shutil.ignore_patterns('tmp', '__pycache__', '*.pyc'))
        game_path = dest / 'game.yml'
        game = yaml.safe_load(game_path.read_text(encoding='utf-8')) or {}
        game['ruleset'] = '5e-2024'
        game_path.write_text(yaml.safe_dump(game), encoding='utf-8')
        # The fixture bundle ships campaign-local ogre/owlbear sheets, which
        # outrank the ruleset overlay; remove them so the 2024 overlays load.
        for stem in ('ogre.yml', 'owlbear.yml'):
            (dest / 'npcs' / stem).unlink(missing_ok=True)
        cls.base_campaign_dir = dest

    def setUp(self):
        self.session = Session(root_path=str(self.base_campaign_dir),
                               event_manager=EventManager())

    def test_ogre_2024_overlay(self):
        npc = self.session.npc('ogre')
        self.assertEqual(68, npc.max_hp())
        props = npc.properties
        self.assertEqual('8d10+24', props['hp_die'])
        self.assertEqual(450, props['xp'])
        self.assertEqual(8, npc.passive_perception())
        self.assertNotIn('stealth', props.get('skills') or {})
        greatclub = _action(props['actions'], 'Greatclub')
        self.assertEqual('bludgeoning', greatclub['damage_type'])
        self.assertEqual('2d8+4', greatclub['damage_die'])
        # The 2024 javelin works in melee too.
        melee_jav = _action(props['actions'], 'Javelin (melee)')
        self.assertEqual(5, melee_jav['range'])
        self.assertEqual('2d6+4', melee_jav['damage_die'])
        ranged_jav = _action(props['actions'], 'Javelin')
        self.assertEqual(120, ranged_jav['range_max'])
        self.assertEqual('piercing', ranged_jav['damage_type'])

    def test_owlbear_2024_overlay(self):
        npc = self.session.npc('owlbear')
        self.assertEqual(59, npc.max_hp())
        props = npc.properties
        self.assertEqual('11d8', props['hp_die'])
        self.assertEqual(40, props['speed'])
        self.assertEqual(40, props['speed_climb'])
        self.assertEqual(15, npc.passive_perception())
        self.assertEqual({'perception': 5, 'stealth': 2}, props['skills'])
        self.assertNotIn('keen_sight_and_smell', props.get('attributes') or [])
        self.assertEqual(['rend,rend'], props['multiattack'])
        rend = _action(props['actions'], 'rend')
        self.assertEqual(7, rend['attack'])
        self.assertEqual('2d8+5', rend['damage_die'])
        self.assertEqual('slashing', rend['damage_type'])
        self.assertEqual(700, props['xp'])

    def test_2014_base_templates_corrected(self):
        """The base sheets model the 2014 blocks and no longer carry typos."""
        ogre = _sheet(TEMPLATES / 'npcs' / 'ogre.yml')
        self.assertEqual('7d8+21', ogre['hp_die'])
        self.assertEqual(450, ogre['xp'])
        self.assertEqual({'stealth': -1}, ogre['skills'])
        self.assertEqual('bludgeoning', _action(ogre['actions'], 'Greatclub')['damage_type'])

        owl = _sheet(TEMPLATES / 'npcs' / 'owlbear.yml')
        self.assertEqual('11d8', owl['hp_die'])
        # 'perceiption' typo fixed; 2014 owlbear keeps Keen Sight and Smell.
        self.assertEqual({'perception': 3}, owl['skills'])
        self.assertIn('keen_sight_and_smell', owl['attributes'])
        claws = _action(owl['actions'], 'claws')
        self.assertEqual('2d6+4', claws['damage_die'])
        self.assertEqual('slashing', claws['damage_type'])

    def test_2014_base_used_without_ruleset_overlay(self):
        # The 5e-2024 overlay must NOT leak into a 2014 campaign: the bundled
        # base sheet (no campaign-local copy) still gives the 2014 numbers.
        import tempfile as _tf
        tmp = _tf.mkdtemp(prefix='n20-2014-')
        dest = Path(tmp) / 'campaign'
        shutil.copytree(FIXTURES, dest,
                        ignore=shutil.ignore_patterns('tmp', '__pycache__', '*.pyc'))
        for stem in ('ogre.yml', 'owlbear.yml'):
            (dest / 'npcs' / stem).unlink(missing_ok=True)
        session = Session(root_path=str(dest), event_manager=EventManager())
        npc = session.npc('ogre')
        self.assertEqual(59, npc.max_hp())
        self.assertEqual('7d8+21', npc.properties['hp_die'])
        self.assertEqual('bludgeoning',
                         _action(npc.properties['actions'], 'Greatclub')['damage_type'])


# ---------------------------------------------------------------------------
# Item 2: squeezing sets its status, and reach/footprint follow the squeeze
# ---------------------------------------------------------------------------


class SqueezeTest(unittest.TestCase):
    def setUp(self):
        random.seed(7001)
        self.session = Session(root_path=str(FIXTURES), event_manager=EventManager())
        self.map = Map(self.session, 'squeeze_arena')
        self.battle = Battle(self.session, self.map)
        self.ogre = self.session.npc('ogre')
        self.battle.add(self.ogre, 'b', position=[4, 4], token='O')
        self.ogre.reset_turn(self.battle)

    def test_squeeze_status_and_footprint(self):
        # The 1-wide gap at column 5 (rows 2-3) only fits the reduced
        # footprint: entering it must SET the squeezed status (it used to
        # call the never-setting getter) and shrink the occupied squares.
        self.assertEqual(4, len(self.map.entity_squares(self.ogre)))
        self.assertFalse(self.ogre.squeezed())
        self.map.move_to(self.ogre, 5, 3, self.battle)
        self.assertTrue(self.ogre.squeezed())
        self.assertEqual({(5, 3)}, {tuple(s) for s in self.map.entity_squares(self.ogre)})

        # Reach follows the squeezed cell: an 8-cell ring around (5,3), not
        # the old 2x2 body — a hero 10 ft away at (5,1) is not threatened.
        ring = {tuple(s) for s in self.ogre.melee_squares(self.map)}
        self.assertEqual(
            {(4, 2), (5, 2), (6, 2), (4, 3), (6, 3), (4, 4), (5, 4), (6, 4)}, ring)
        self.assertNotIn((5, 1), ring)

        # Leaving the gap unsqueezes and the full body is back.
        self.map.move_to(self.ogre, 4, 4, self.battle)
        self.assertFalse(self.ogre.squeezed())
        self.assertEqual(4, len(self.map.entity_squares(self.ogre)))

    def test_move_action_can_end_move_squeezed(self):
        # The reachable-squares menu already pathfinds through squeeze-only
        # gaps; the move COMMIT used to trim the path back until the end
        # square was placeable without squeezing, so the two disagreed.
        action = MoveAction(self.session, self.ogre, 'move',
                            {'move_path': [[4, 4], [5, 4], [5, 3]]})
        self.battle.action(action)
        self.battle.commit(action)
        self.assertEqual([5, 3], self.map.entity_or_object_pos(self.ogre))
        self.assertTrue(self.ogre.squeezed())

    def test_squeeze_attack_modifiers_are_2014_only(self):
        self.assertTrue(get_ruleset('5e-2014').squeeze_attack_modifiers())
        self.assertFalse(get_ruleset('5e-2024').squeeze_attack_modifiers())

        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        goblin = self.session.npc('goblin')
        self.map.place([2, 5], fighter, 'G')
        self.map.place([3, 5], goblin, 'g')

        fighter.do_squeeze()
        self.assertTrue(fighter.squeezed())
        _, disadvantage = compute_advantages_and_disadvantages(
            self.session, fighter, goblin, 'longsword')
        self.assertIn('squeezed', disadvantage)

        # 2024: squeezing is purely a movement constraint.
        self.session.ruleset = get_ruleset('5e-2024')
        _, disadvantage = compute_advantages_and_disadvantages(
            self.session, fighter, goblin, 'longsword')
        self.assertNotIn('squeezed', disadvantage)

        # Attacks AGAINST a squeezing creature used to gain advantage (2014).
        self.session.ruleset = get_ruleset('5e-2014')
        fighter.unsqueeze()
        goblin.do_squeeze()
        advantage, _ = compute_advantages_and_disadvantages(
            self.session, fighter, goblin, 'longsword')
        self.assertIn('squeezed', advantage)
        self.session.ruleset = get_ruleset('5e-2024')
        advantage, _ = compute_advantages_and_disadvantages(
            self.session, fighter, goblin, 'longsword')
        self.assertNotIn('squeezed', advantage)


# ---------------------------------------------------------------------------
# Item 3: cover takes the GREATEST cover over all source/target square pairs
# ---------------------------------------------------------------------------


class CoverGreatestPairTest(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path=str(FIXTURES), event_manager=EventManager())
        self.map = Map(self.session, 'open_arena')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.ogre = self.session.npc('ogre')
        self.map.place([1, 1], self.fighter, 'G')
        # Body squares (5,1),(6,1),(5,2),(6,2); a half-cover barrel sits on
        # the LAST scanned pair's square (6,2).

    def test_cover_from_later_pair_still_counts(self):
        # The old code returned as soon as the FIRST scanned source-target
        # pair produced no LOS cover, so the barrel (half cover) on the
        # LAST pair's square was ignored and the ogre got 0.
        self.map.place([5, 1], self.ogre, 'O')
        self.assertEqual(2, calculate_cover_ac(self.map, self.fighter, self.ogre))

    def test_no_cover_without_blocking_objects(self):
        self.map.place([1, 4], self.ogre, 'O')
        self.assertEqual(0, calculate_cover_ac(self.map, self.fighter, self.ogre))


# ---------------------------------------------------------------------------
# Item 4: melee_squares is a ring around the BODY squares
# ---------------------------------------------------------------------------


class MeleeRingTest(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path=str(FIXTURES), event_manager=EventManager())
        self.map = Map(self.session, 'open_arena')

    def test_large_body_threatens_twelve_cells(self):
        ogre = self.session.npc('ogre')
        self.map.place([3, 3], ogre, 'O')
        ring = {tuple(s) for s in ogre.melee_squares(self.map)}
        expected = {
            (2, 2), (3, 2), (4, 2), (5, 2),
            (2, 3), (5, 3),
            (2, 4), (5, 4),
            (2, 5), (3, 5), (4, 5), (5, 5),
        }
        self.assertEqual(expected, ring)
        self.assertEqual(12, len(ring))
        # The body squares are never threatened squares.
        body = {(3, 3), (4, 3), (3, 4), (4, 4)}
        self.assertFalse(body & ring)

    def test_medium_body_threatens_eight_cells(self):
        fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.map.place([4, 3], fighter, 'G')
        ring = {tuple(s) for s in fighter.melee_squares(self.map)}
        self.assertEqual(
            {(3, 2), (4, 2), (5, 2), (3, 3), (5, 3), (3, 4), (4, 4), (5, 4)}, ring)

    def test_adjacent_only_ring_matches_body_ring(self):
        ogre = self.session.npc('ogre')
        self.map.place([3, 3], ogre, 'O')
        ring = {tuple(s) for s in ogre.melee_squares(self.map, adjacent_only=True)}
        self.assertEqual(12, len(ring))


# ---------------------------------------------------------------------------
# Item 5: a Large grappler never drops its catch inside its own body
# ---------------------------------------------------------------------------


class LargeGrapplerDragTest(unittest.TestCase):
    def setUp(self):
        random.seed(7002)
        self.session = Session(root_path=str(FIXTURES), event_manager=EventManager())
        self.map = Map(self.session, 'open_arena')
        self.battle = Battle(self.session, self.map)
        self.ogre = self.session.npc('ogre')
        self.fighter = PlayerCharacter.load(self.session, 'high_elf_fighter.yml')
        self.battle.add(self.ogre, 'b', position=[3, 3], token='O')
        self.battle.add(self.fighter, 'a', position=[3, 2], token='G')
        self.ogre.reset_turn(self.battle)
        self.fighter.reset_turn(self.battle)

    def test_drag_never_ends_in_grappler_stay_squares(self):
        # Ogre body (3,3),(4,3),(3,4),(4,4); hero held on the north side at
        # (3,2). Stepping west moves the body to (2,3),(3,3),(2,4),(3,4):
        # the hero's lag trail would END at (3,3) — inside the ogre's own
        # body. The clamp must stop the trail before that square.
        self.fighter.do_grappled_by(self.ogre)
        self.assertTrue(self.ogre.is_grappling())
        action = MoveAction(self.session, self.ogre, 'move',
                            {'move_path': [[3, 3], [2, 3]]})
        self.battle.action(action)
        self.battle.commit(action)

        self.assertEqual([2, 3], self.map.entity_or_object_pos(self.ogre))
        hero_pos = tuple(self.map.entity_or_object_pos(self.fighter))
        stay_squares = {(2, 3), (3, 3), (2, 4), (3, 4)}
        self.assertNotIn(hero_pos, stay_squares)
        # Still grappled: the hero held at (3,2), adjacent to the new body.
        self.assertEqual((3, 2), hero_pos)
        self.assertTrue(self.ogre.is_grappling())


if __name__ == '__main__':
    unittest.main()

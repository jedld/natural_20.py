"""Death House Haunted One background tests."""

import os
import unittest

from natural20.session import Session
from natural20.event_manager import EventManager
from natural20.utils.background_validation import (
    apply_background_proficiencies,
    apply_background_starting_equipment,
    validate_background_language_selections,
    validate_background_skill_selections,
)
from natural20.utils.character_profile import (
    load_profile_tables,
    randomize_profile,
    roll_background_table,
)


def _death_house_restrictions(session):
    """Mirror campaign whitelist from death_house/game.yml for engine tests."""
    cfg = (session.game_properties or {}).get('character_builder') or {}
    allowed = {str(x).strip().lower() for x in (cfg.get('allowed_backgrounds') or []) if str(x).strip()}
    return allowed


class TestHauntedOneBackground(unittest.TestCase):
    def setUp(self):
        self.campaign_root = os.path.join(
            os.path.dirname(__file__), '..', 'user_levels', 'death_house'
        )
        self.session = Session(
            root_path=self.campaign_root,
            event_manager=EventManager(),
        )

    def test_haunted_one_loads_from_campaign(self):
        backgrounds = self.session.load_backgrounds()
        self.assertIn('haunted_one', backgrounds)
        bg = backgrounds['haunted_one']
        self.assertEqual(bg['label'], 'Haunted One')
        self.assertEqual(bg['skill_choice_count'], 2)
        self.assertIn('investigation', bg['skills_pool'])
        self.assertEqual(bg['language_choice_count'], 2)
        self.assertEqual(bg['exotic_language_min'], 1)
        self.assertEqual(bg['default_equipment_pack'], 'monster_hunters_pack')

    def test_campaign_whitelist_allows_only_haunted_one(self):
        allowed = _death_house_restrictions(self.session)
        backgrounds = self.session.load_backgrounds()
        filtered = {
            name: data for name, data in backgrounds.items()
            if not allowed or name in allowed
        }
        self.assertEqual(set(filtered.keys()), {'haunted_one'})
        self.assertIn('haunted_one', backgrounds)
        self.assertIn('acolyte', backgrounds)

    def test_monster_hunters_pack_merges_from_campaign(self):
        packs = self.session.load_equipment_packs()
        self.assertIn('monster_hunters_pack', packs)
        self.assertIn('wooden_stake', packs['monster_hunters_pack']['items'])

    def test_skill_and_language_validation(self):
        bg = self.session.load_backgrounds()['haunted_one']
        ok, err = validate_background_skill_selections(bg, ['arcana', 'religion'])
        self.assertTrue(ok, err)
        ok, err = validate_background_skill_selections(bg, ['arcana'])
        self.assertFalse(ok)

        ok, err = validate_background_language_selections(
            bg,
            ['elvish', 'infernal'],
            granted_languages=set(),
        )
        self.assertTrue(ok, err)
        ok, err = validate_background_language_selections(
            bg,
            ['elvish', 'dwarvish'],
            granted_languages=set(),
        )
        self.assertFalse(ok)

    def test_apply_background_to_pc(self):
        bg = self.session.load_backgrounds()['haunted_one']
        pc = {'skills': [], 'languages': [], 'inventory': []}
        apply_background_proficiencies(
            pc,
            bg,
            skill_selections=['investigation', 'survival'],
            language_selections=['common', 'abyssal'],
        )
        apply_background_starting_equipment(pc, bg)
        self.assertIn('investigation', pc['skills'])
        self.assertIn('abyssal', pc['languages'])
        self.assertTrue(any(row.get('item') == 'silver_piece' for row in pc['inventory']))

    def test_campaign_profile_tables(self):
        tables = load_profile_tables(campaign_root=self.campaign_root)
        haunted = tables['backgrounds']['haunted_one']
        self.assertEqual(len(haunted['harrowing_events']), 10)
        self.assertGreaterEqual(len(haunted['gothic_trinkets']), 50)
        rolled = roll_background_table(
            background='haunted_one',
            table_name='harrowing_events',
            campaign_root=self.campaign_root,
        )
        self.assertTrue(rolled)

    def test_randomize_profile_includes_campaign_tables(self):
        profile = randomize_profile(
            background='haunted_one',
            include_personality=True,
            include_physical=False,
            include_alignment=False,
            include_harrowing_event=True,
            include_background_trinket=True,
            campaign_root=self.campaign_root,
        )
        self.assertTrue(profile.get('personality_traits'))
        self.assertTrue(profile.get('harrowing_event'))
        self.assertTrue(profile.get('background_trinket'))

"""Tests for 5e 2014 Background support.

Verifies:
  - Background YAML loading via Session.load_backgrounds()
  - Background class construction and serialization
  - Skill/tool proficiency merging into PlayerCharacter properties
  - Language choice handling
  - Equipment item references
  - Feature data accessibility
"""

import os
import unittest
import yaml

from natural20.session import Session
from natural20.background import Background
from natural20.event_manager import EventManager


class TestBackgroundLoading(unittest.TestCase):
    """Verify Session.load_backgrounds loads all 12 SRD backgrounds."""

    def setUp(self):
        self.session = Session(root_path='templates')

    def test_loads_all_12_backgrounds(self):
        backgrounds = self.session.load_backgrounds()
        expected = {
            'acolyte', 'charlatan', 'criminal', 'entertainer',
            'folk_hero', 'guild_artisan', 'hermit', 'noble',
            'outlander', 'sage', 'sailor', 'soldier',
        }
        self.assertEqual(set(backgrounds.keys()), expected,
                         "All 12 SRD backgrounds should be loaded")

    def test_background_has_required_fields(self):
        backgrounds = self.session.load_backgrounds()
        for name, bg_data in backgrounds.items():
            with self.subTest(background=name):
                self.assertIn('name', bg_data, f"{name} missing 'name'")
                self.assertIn('skill_proficiencies', bg_data,
                              f"{name} missing 'skill_proficiencies'")
                self.assertIn('tool_proficiencies', bg_data,
                              f"{name} missing 'tool_proficiencies'")
                self.assertIn('feature', bg_data, f"{name} missing 'feature'")
                self.assertIn('equipment', bg_data, f"{name} missing 'equipment'")

    def test_background_yaml_is_valid(self):
        """Every background YAML file should parse without errors."""
        backgrounds_dir = os.path.join('templates', 'backgrounds')
        for filename in os.listdir(backgrounds_dir):
            if filename.endswith('.yml'):
                with self.subTest(file=filename):
                    filepath = os.path.join(backgrounds_dir, filename)
                    with open(filepath) as f:
                        data = yaml.safe_load(f)
                    self.assertIsInstance(data, dict)


class TestBackgroundClass(unittest.TestCase):
    """Verify Background class construction, accessors, and serialization."""

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()

    def test_construction_from_yaml(self):
        bg = Background(self.backgrounds['acolyte'])
        self.assertEqual(bg.name, 'Acolyte')
        self.assertEqual(bg.label, 'Acolyte')
        self.assertIn('religion', bg.skill_proficiencies)
        self.assertIn('insight', bg.skill_proficiencies)

    def test_feature_accessors(self):
        bg = Background(self.backgrounds['acolyte'])
        self.assertEqual(bg.get_feature_name(), 'Shelter of the Faithful')
        self.assertIn('healing', bg.get_feature_description().lower())

    def test_language_choice_detection(self):
        acolyte = Background(self.backgrounds['acolyte'])
        self.assertTrue(acolyte.has_language_choices())
        self.assertEqual(acolyte.language_choice_count, 2)
        self.assertGreater(len(acolyte.languages_pool), 0)

        criminal = Background(self.backgrounds['criminal'])
        self.assertFalse(criminal.has_language_choices())
        self.assertEqual(criminal.language_choice_count, 0)

    def test_to_dict_roundtrip(self):
        bg = Background(self.backgrounds['sage'])
        data = bg.to_dict()
        bg2 = Background.from_yaml(data)
        self.assertEqual(bg2.name, bg.name)
        self.assertEqual(bg2.skill_proficiencies, bg.skill_proficiencies)
        self.assertEqual(bg2.tool_proficiencies, bg.tool_proficiencies)
        self.assertEqual(bg2.language_choice_count, bg.language_choice_count)
        self.assertEqual(bg2.feature, bg.feature)

    def test_all_backgrounds_constructible(self):
        for name, bg_data in self.backgrounds.items():
            with self.subTest(background=name):
                bg = Background(bg_data)
                self.assertIsInstance(bg.name, str)
                self.assertGreater(len(bg.name), 0)
                self.assertIsInstance(bg.skill_proficiencies, list)
                self.assertEqual(len(bg.skill_proficiencies), 2,
                                 "SRD backgrounds grant exactly 2 skill proficiencies")

    def test_equipment_list_populated(self):
        for name, bg_data in self.backgrounds.items():
            with self.subTest(background=name):
                bg = Background(bg_data)
                self.assertIsInstance(bg.equipment, list)
                self.assertGreater(len(bg.equipment), 0,
                                   f"{name} should have starting equipment")


class TestBackgroundSkillProficiencies(unittest.TestCase):
    """Verify each background grants the correct skill proficiencies per SRD."""

    EXPECTED_SKILLS = {
        'acolyte': {'religion', 'insight'},
        'charlatan': {'deception', 'stealth'},
        'criminal': {'deception', 'stealth'},
        'entertainer': {'acrobatics', 'performance'},
        'folk_hero': {'animal_handling', 'survival'},
        'guild_artisan': {'insight', 'persuasion'},
        'hermit': {'medicine', 'religion'},
        'noble': {'history', 'persuasion'},
        'outlander': {'athletics', 'survival'},
        'sage': {'arcana', 'history'},
        'sailor': {'athletics', 'perception'},
        'soldier': {'athletics', 'intimidation'},
    }

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()

    def test_all_skill_proficiencies_match_srd(self):
        for bg_name, expected_skills in self.EXPECTED_SKILLS.items():
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                actual = set(bg.skill_proficiencies)
                self.assertEqual(actual, expected_skills,
                                 f"{bg_name} skills mismatch")


class TestBackgroundToolProficiencies(unittest.TestCase):
    """Verify tool proficiency counts and presence per SRD."""

    # Backgrounds that grant tool proficiencies
    TOOLS_EXPECTED = {
        'charlatan': 2,   # disguises kit, forgery kit
        'criminal': 2,    # one gaming set, thieves tools
        'entertainer': 1, # one musical instrument
        'folk_hero': 2,   # one kind of artisans tools, woodcarvers tools/herbalism kit
        'guild_artisan': 1,  # one type of artisans tools
        'noble': 1,       # one gaming set
        'sailor': 2,      # navigators tools, sailors kit
        'soldier': 2,     # one gaming set, one musical instrument
    }

    # Backgrounds with no tool proficiencies
    NO_TOOLS = {'acolyte', 'hermit', 'outlander', 'sage'}

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()

    def test_tool_proficiency_counts(self):
        for bg_name, expected_count in self.TOOLS_EXPECTED.items():
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                self.assertEqual(len(bg.tool_proficiencies), expected_count,
                                 f"{bg_name} should have {expected_count} tool proficiencies")

    def test_no_tool_backgrounds(self):
        for bg_name in self.NO_TOOLS:
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                self.assertEqual(len(bg.tool_proficiencies), 0,
                                 f"{bg_name} should have no tool proficiencies")


class TestBackgroundLanguages(unittest.TestCase):
    """Verify language choice counts per SRD."""

    LANGUAGE_CHOICES = {
        'acolyte': 2,
        'charlatan': 1,
        'criminal': 0,
        'entertainer': 0,
        'folk_hero': 0,
        'guild_artisan': 1,
        'hermit': 1,
        'noble': 1,
        'outlander': 1,
        'sage': 2,
        'sailor': 0,
        'soldier': 0,
    }

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()

    def test_language_choice_counts(self):
        for bg_name, expected in self.LANGUAGE_CHOICES.items():
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                self.assertEqual(bg.language_choice_count, expected,
                                 f"{bg_name} language_choice_count mismatch")

    def test_language_pool_present_when_choices_exist(self):
        for bg_name, choice_count in self.LANGUAGE_CHOICES.items():
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                if choice_count > 0:
                    self.assertGreater(len(bg.languages_pool), 0,
                                       f"{bg_name} needs a languages_pool")

    def test_no_fixed_languages_for_choice_backgrounds(self):
        """Backgrounds with language choices should have empty fixed languages."""
        for bg_name, choice_count in self.LANGUAGE_CHOICES.items():
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                if choice_count > 0:
                    self.assertEqual(len(bg.languages), 0,
                                     f"{bg_name} fixed languages should be empty when choices exist")


class TestBackgroundFeatures(unittest.TestCase):
    """Verify every background has a named feature with a description."""

    KNOWN_FEATURES = {
        'acolyte': 'Shelter of the Faithful',
        'charlatan': 'False Identity',
        'criminal': 'Criminal Contact',
        'entertainer': 'By Popular Demand',
        'folk_hero': 'Rustic Hospitality',
        'guild_artisan': 'Guild Membership',
        'hermit': 'Discovery',
        'noble': 'Position of Privilege',
        'outlander': 'Wanderer',
        'sage': 'Researcher',
        'sailor': "Ship's Passage",
        'soldier': 'Military Rank',
    }

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()

    def test_feature_names_match_srd(self):
        for bg_name, expected_name in self.KNOWN_FEATURES.items():
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                self.assertEqual(bg.get_feature_name(), expected_name,
                                 f"{bg_name} feature name mismatch")

    def test_feature_has_description(self):
        for bg_name in self.KNOWN_FEATURES:
            with self.subTest(background=bg_name):
                bg = Background(self.backgrounds[bg_name])
                desc = bg.get_feature_description()
                self.assertIsInstance(desc, str)
                self.assertGreater(len(desc), 20,
                                   f"{bg_name} feature description too short")


class TestBackgroundEquipmentReferences(unittest.TestCase):
    """Document which background equipment items exist in equipment.yml."""

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()
        with open('templates/items/equipment.yml') as f:
            self.equipment = yaml.safe_load(f)

    def test_core_equipment_items_exist(self):
        """Items that should definitely exist in the catalog."""
        must_exist = {
            'holy_symbol', 'staff', 'shield', 'costume',
        }
        for item in must_exist:
            with self.subTest(item=item):
                self.assertIn(item, self.equipment,
                              f"Core equipment '{item}' missing from equipment.yml")

    def test_all_equipment_references_documented(self):
        """Collect all equipment references and report missing ones."""
        all_refs = set()
        for bg_data in self.backgrounds.values():
            for item in bg_data.get('equipment', []):
                all_refs.add(item)

        missing = all_refs - set(self.equipment.keys())
        # This test documents the gap rather than failing, since background
        # equipment is starting gear that may be flavor-only.
        if missing:
            print(f"\nBackground equipment items not in equipment.yml: {sorted(missing)}")
        # Assert that at least some items are found
        found = all_refs & set(self.equipment.keys())
        self.assertGreaterEqual(len(found), 4,
                                "At least 4 background equipment items should exist in catalog")


class TestBackgroundToolProficiencyReferences(unittest.TestCase):
    """Document which tool proficiencies are referenced but missing from catalog."""

    def setUp(self):
        self.session = Session(root_path='templates')
        self.backgrounds = self.session.load_backgrounds()
        with open('templates/items/equipment.yml') as f:
            self.equipment = yaml.safe_load(f)

    def test_thieves_tools_exists(self):
        """thieves_tools is the only tool proficiency currently in equipment.yml."""
        self.assertIn('thieves_tools', self.equipment)

    def test_missing_tool_proficiencies_documented(self):
        """Collect missing tool proficiencies for documentation."""
        needed_tools = set()
        for bg_data in self.backgrounds.values():
            for tool in bg_data.get('tool_proficiencies', []):
                needed_tools.add(tool)

        existing_tools = {k for k, v in self.equipment.items()
                          if v.get('type') in ('tool', 'tools')}
        missing = needed_tools - existing_tools

        if missing:
            print(f"\nTool proficiencies not in equipment.yml: {sorted(missing)}")
        # Document that thieves_tools is the only match
        self.assertIn('thieves_tools', needed_tools)
        self.assertIn('thieves_tools', existing_tools)


if __name__ == '__main__':
    unittest.main()

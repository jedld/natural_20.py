import unittest
import yaml
from pathlib import Path
from unittest.mock import MagicMock, patch

from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.utils.char_class_spells import (
    clear_spell_availability_cache,
    collect_spell_list_slugs,
    missing_spell_yaml_slugs,
    spell_availability_map,
)


class CharClassSpellListsTestCase(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='templates', event_manager=EventManager())
        self.classes_dir = Path('templates/char_classes')

    def test_all_builder_spell_slugs_exist_in_spells_yaml(self):
        classes = {}
        for yml in self.classes_dir.glob('*.yml'):
            classes[yml.stem] = yaml.safe_load(yml.read_text()) or {}

        missing = list(missing_spell_yaml_slugs(self.session, classes))
        self.assertEqual(
            missing,
            [],
            f"Character builder lists spells missing from spells.yml: {missing}",
        )

    def test_no_invalid_slug_characters(self):
        classes = {}
        for yml in self.classes_dir.glob('*.yml'):
            classes[yml.stem] = yaml.safe_load(yml.read_text()) or {}

        for slug in collect_spell_list_slugs(classes):
            self.assertNotIn('/', slug, f"Invalid slug with '/': {slug}")
            self.assertNotIn(' ', slug, f"Invalid slug with space: {slug}")

    def test_spell_availability_map_uses_bulk_spell_load_and_cache(self):
        clear_spell_availability_cache()
        session = MagicMock()
        session.root_path = '/tmp/test-campaign'
        session.load_all_spells.return_value = {
            'firebolt': {'name': 'Fire Bolt'},
            'sleep': {'name': 'Sleep'},
        }
        classes = {'wizard': {'spell_list': {'cantrip': ['firebolt'], 'level_1': ['sleep']}}}

        with patch('natural20.utils.spell_loader.spell_is_implemented', side_effect=lambda slug, meta: slug == 'firebolt'):
            first = spell_availability_map(session, classes)
            second = spell_availability_map(session, classes)

        self.assertEqual(first, {'firebolt': True, 'sleep': False})
        self.assertIs(second, first)
        session.load_all_spells.assert_called_once()
        clear_spell_availability_cache()


if __name__ == '__main__':
    unittest.main()

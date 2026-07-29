import unittest
import yaml
from pathlib import Path

from natural20.event_manager import EventManager
from natural20.session import Session
from natural20.utils.char_class_spells import collect_spell_list_slugs, missing_spell_yaml_slugs


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


if __name__ == '__main__':
    unittest.main()

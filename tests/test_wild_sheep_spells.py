import unittest

from natural20.utils.spell_loader import load_spell_class
from natural20.session import Session


class WildSheepSpellsTest(unittest.TestCase):
    def test_spell_classes_load(self):
        self.assertIsNotNone(load_spell_class('EnlargeReduceSpell'))
        self.assertIsNotNone(load_spell_class('HasteSpell'))
        self.assertIsNotNone(load_spell_class('PolymorphSpell'))

    def test_spell_definitions_in_campaign(self):
        session = Session(root_path='user_levels/wild_sheep_chase')
        for key in ('enlarge_reduce', 'haste', 'polymorph'):
            details = session.load_spell(key)
            self.assertIn('spell_class', details)


if __name__ == '__main__':
    unittest.main()

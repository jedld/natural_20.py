import unittest
from pathlib import Path

from natural20.web.quick_interact_registry import (
    collect_quick_interact_icon_slugs,
    humanize_action_key,
    missing_quick_interact_icons,
    resolve_action_label,
)


class TestQuickInteractRegistry(unittest.TestCase):
    def test_humanize_action_key(self):
        self.assertEqual(humanize_action_key('servants_quarters'), 'Servants Quarters')

    def test_collect_quick_interact_icon_slugs_includes_switch_states(self):
        fixtures = Path('tests/fixtures/items/objects.yml')
        slugs = collect_quick_interact_icon_slugs(objects_yml_paths=[fixtures])
        actions = {ref['action'] for ref in slugs}
        self.assertIn('servants_quarters', actions)
        self.assertIn('master_bedroom', actions)

    def test_missing_quick_interact_icons_reports_entries(self):
        missing = missing_quick_interact_icons()
        self.assertIsInstance(missing, list)
        if missing:
            self.assertIn('slug', missing[0])
            self.assertIn('action', missing[0])

    def test_resolve_action_label_prefers_prompt(self):
        class Stub:
            buttons = {}

        label = resolve_action_label(Stub(), 'buzz', {'prompt': 'Ring for Room Service'})
        self.assertEqual(label, 'Ring for Room Service')


if __name__ == '__main__':
    unittest.main()

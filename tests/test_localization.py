import os
import unittest

from natural20.battle import Battle
from natural20.item_library.door_object import DoorObject
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.session import Session
from natural20.utils.localization import (
    is_locale_key,
    localize_quick_interact_actions,
    missing_locale_keys,
    resolve_locale_text,
    set_locale_value,
)
from natural20.web.object_quick_interactions import quick_interact_actions_for


class TestLocalizationUtils(unittest.TestCase):
    def test_is_locale_key(self):
        self.assertTrue(is_locale_key('object.door.key_required'))
        self.assertFalse(is_locale_key('Key required'))
        self.assertFalse(is_locale_key('(missing key)'))

    def test_resolve_locale_text_translates_key(self):
        session = Session(root_path='tests/fixtures')
        text = resolve_locale_text(session.t, 'object.door.key_required')
        self.assertEqual(text, 'Key required')

    def test_resolve_locale_text_passthrough_human_text(self):
        session = Session(root_path='tests/fixtures')
        text = resolve_locale_text(session.t, 'Already checked')
        self.assertEqual(text, 'Already checked')

    def test_missing_locale_keys_detects_absent_entries(self):
        tree = {}
        set_locale_value(tree, 'object.door.unlock', 'Door unlocked')
        missing = missing_locale_keys(['object.door.unlock', 'object.door.key_required'], tree)
        self.assertEqual(missing, ['object.door.key_required'])


class TestQuickInteractLocalization(unittest.TestCase):
    def setUp(self):
        self.session = Session(root_path='tests/fixtures')
        self.entity = PlayerCharacter.load(self.session, os.path.join('high_elf_fighter.yml'))
        self.battle_map = Map(self.session, 'battle_sim_objects')
        self.battle = Battle(self.session, self.battle_map)
        self.battle_map.place((1, 5), self.entity, 'G')
        self.door = self.battle_map.object_at(1, 4)
        self.door.locked = True
        self.battle.add(self.entity, group='a')
        self.battle.start()
        self.entity.reset_turn(self.battle)

    def test_locked_door_disabled_text_is_localized(self):
        actions = quick_interact_actions_for(self.door, self.entity, self.battle)
        localized = localize_quick_interact_actions(actions, self.session)
        unlock = next(a for a in localized if a['action'] == 'unlock')
        self.assertTrue(unlock['disabled'])
        self.assertEqual(unlock['disabled_text'], 'Key required')


if __name__ == '__main__':
    unittest.main()

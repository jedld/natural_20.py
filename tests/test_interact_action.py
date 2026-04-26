import os
from natural20.actions.interact_action import InteractAction
from natural20.session import Session
from natural20.player_character import PlayerCharacter
import unittest
from natural20.battle import Battle
from natural20.map import Map
from natural20.map_renderer import MapRenderer
from natural20.event_manager import EventManager
from natural20.utils.action_builder import autobuild
import random
import pdb


class ListLogger:
    def __init__(self):
        self.messages = []

    def log(self, event_msg):
        self.messages.append(event_msg)


class FakeRoll:
    def __init__(self, text, total):
        self.text = text
        self.total = total

    def result(self):
        return self.total

    def __str__(self):
        return self.text

# typed: false
class TestInteractAction(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def setUp(self):
        self.session = self.make_session()
        self.entity = PlayerCharacter.load(self.session, os.path.join("high_elf_fighter.yml"))
        self.battle_map = Map(self.session, "battle_sim_objects")
        self.battle = Battle(self.session, self.battle_map)
        self.battle_map.place((1, 5), self.entity, "G")
        self.door = self.battle_map.object_at(1, 4)
        self.chest = self.battle_map.object_at(1, 6)
        self.battle.add(self.entity, group='a')
        self.battle.start()
        self.entity.reset_turn(self.battle)

    def test_ability_checks(self):
        self.battle.add(self.entity, group='a')
        self.battle.start()
        self.entity.reset_turn(self.battle)
        print(MapRenderer(self.battle_map).render())
        action = autobuild(self.session, InteractAction, self.entity, self.battle, match=[self.door, "investigation_check"], verbose=True)[0]

        self.assertIsInstance(action, InteractAction)
        self.assertEqual(action.button_label(), 'Investigation Check')
        self.assertEqual(action.button_prompt(), 'Inspect Door')
        self.assertListEqual(self.door.investigate_details(self.entity), [])

        self.assertEqual(self.door.closed(), True)
        self.battle.action(action)
        self.battle.commit(action)
        self.assertEqual(self.door.closed(), False)
        print(MapRenderer(self.battle_map).render())
        _investigate_list = self.door.investigate_details(self.entity)
  
        self.assertListEqual(_investigate_list, ['(success) The door is not trapped'])

    def test_ability_check_string_outcome_emits_message_event(self):
        """When ability_checks.<ability>.success/failure is a plain string,
        Object.use should auto-broadcast it as a `message` event so the
        configured outcome text surfaces to the chat log (regression for
        the Death House nursery 'Part the shroud' bug).
        """
        from natural20.item_library.object import Object as N20Object

        captured = []
        self.session.event_manager.register_event_listener(
            'message', lambda evt: captured.append(evt)
        )

        properties = {
            'name': 'plinth',
            'type': 'note',
            'ability_checks': {
                'investigation': {
                    'prompt': 'Inspect plinth',
                    'dc': 1,
                    'success': 'You discover a hidden rune.',
                    'failure': 'You find nothing of note.',
                },
            },
        }
        plinth = N20Object(self.session, self.battle_map, properties)

        # Force success path
        result = {
            'action': 'investigation_check',
            'ability': 'investigation',
            'check_type': 'check',
            'roll': FakeRoll('d20(20)+0', 20),
            'dc': 1,
            'success': True,
        }
        plinth.use(self.entity, result, self.session)
        success_msgs = [e for e in captured if e['message'] == 'You discover a hidden rune.']
        self.assertEqual(len(success_msgs), 1)
        self.assertIs(success_msgs[0]['target'], plinth)

        # Force failure path on a fresh object so check_results don't disable it
        captured.clear()
        plinth2 = N20Object(self.session, self.battle_map, properties)
        result_fail = {
            'action': 'investigation_check',
            'ability': 'investigation',
            'check_type': 'check',
            'roll': FakeRoll('d20(1)+0', 1),
            'dc': 99,
            'success': False,
        }
        plinth2.use(self.entity, result_fail, self.session)
        failure_msgs = [e for e in captured if e['message'] == 'You find nothing of note.']
        self.assertEqual(len(failure_msgs), 1)

    def test_ability_check_dict_outcome_does_not_duplicate_message(self):
        """When success is a dict with `message` and `events`, the events
        list handles broadcast — Object.use must NOT also auto-broadcast
        the inspector-only `message` field."""
        captured = []
        self.session.event_manager.register_event_listener(
            'message', lambda evt: captured.append(evt)
        )

        # The fixture front_door uses dict-form success with
        # message='(success) The door is not trapped' and events broadcasting
        # 'You open the door'. Only the events-list message should appear,
        # NOT the inspector-only top-level message.
        action = autobuild(
            self.session, InteractAction, self.entity, self.battle,
            match=[self.door, 'investigation_check'], verbose=False
        )[0]
        self.battle.action(action)
        self.battle.commit(action)

        messages = [e['message'] for e in captured]
        # Inspector-only text must NOT be broadcast
        self.assertNotIn('(success) The door is not trapped', messages)

    def test_event_with_narration_emits_narration_event(self):
        """When an event entry includes a `narration` block, GenericEventHandler
        should emit a `narration` event (in addition to any `message`) so the
        webapp can surface it via the DM narration overlay."""
        from natural20.concern.generic_event_handler import GenericEventHandler

        captured_narration = []
        captured_messages = []
        self.session.event_manager.register_event_listener(
            'narration', lambda evt: captured_narration.append(evt)
        )
        self.session.event_manager.register_event_listener(
            'message', lambda evt: captured_messages.append(evt)
        )

        handler = GenericEventHandler(self.session, self.battle_map, {
            'event': 'investigation_check_success',
            'message': 'You uncover the hidden bundle.',
            'narration': {
                'title': 'Part the Shroud',
                'text': 'You steel yourself and draw aside the dusty black shroud.',
                'once': False,
            },
        })
        handler.handle(self.entity)

        self.assertEqual(len(captured_narration), 1)
        evt = captured_narration[0]
        self.assertEqual(evt['event'], 'narration')
        self.assertIn('on_enter', evt['narration'])
        self.assertEqual(evt['narration']['on_enter']['title'], 'Part the Shroud')
        self.assertEqual(
            evt['narration']['on_enter']['text'],
            'You steel yourself and draw aside the dusty black shroud.',
        )
        # The companion message event still fires
        self.assertTrue(any(m['message'] == 'You uncover the hidden bundle.' for m in captured_messages))

    def test_opening_and_closing_doors(self):
        print(MapRenderer(self.battle_map).render())
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        self.assertEqual(build['param'], [{'type': 'interact', 'target': self.door }])
        self.assertEqual(set(self.door.available_interactions(self.entity).keys()),set(['open','investigation_check']))

        self.assertFalse(self.door.opened())
        build = build['next']('open')
        self.assertIsInstance(build, InteractAction)
        build.resolve(self.session)
        InteractAction.apply(None, build.result[0], session=self.session)
        self.assertTrue(self.door.opened())
        self.assertIn(self.door, self.battle_map.objects_near(self.entity, None))
        print(MapRenderer(self.battle_map).render())
        door_close = self.build_door_close()
        door_close.resolve(self.session)
        InteractAction.apply(None, door_close.result[0], session=self.session)
        self.assertFalse(self.door.opened())
        print(MapRenderer(self.battle_map).render())

    def test_opening_and_closing_chests(self):
        print(MapRenderer(self.battle_map).render())
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.chest)
        self.assertEqual(build['param'], [{'type': 'interact', 'target': self.chest }])
        self.assertEqual(set(self.chest.available_interactions(self.entity).keys()),set(['open']))

        self.assertFalse(self.chest.opened())
        build = build['next']('open')
        self.assertIsInstance(build, InteractAction)
        build.resolve(self.session)
        InteractAction.apply(None, build.result[0], session=self.session)
        self.assertTrue(self.chest.opened())
        self.assertIn(self.chest, self.battle_map.objects_near(self.entity, None))
        print(MapRenderer(self.battle_map).render())
        chest_close = self.build_chest_close()
        chest_close.resolve(self.session)
        InteractAction.apply(None, chest_close.result[0], session=self.session)
        self.assertFalse(self.chest.opened())
        print(MapRenderer(self.battle_map).render())

    def test_player_item_transfer(self):
        self.entity2 = PlayerCharacter.load(self.session, os.path.join("dwarf_cleric.yml"))
        self.battle_map.place((0, 6), self.entity2, "G")
        self.assertListEqual([str(s) for s in self.battle_map.objects_near(self.entity, self.battle)], ['Shor Valu', 'front_door', 'chest','Ground'])
        print(MapRenderer(self.battle_map).render())
        self.assertListEqual([str(a) for a in self.entity.available_actions(self.session, self.battle)], ['Hide',
            'Dash',
            'Disengage',
            'Dodge',
            'move to [0, 5]',
            'move to [2, 5]',
            'Prone',
            'SecondWind',
            'Help',
            'Grapple',
            'Shove',
            'UseItem: healing_potion',
            'Interact(Shor Valu,give)',
            'Interact(front_door,investigation_check)',
            'Interact(front_door,open)',
            'Interact(chest,open)',
            'Interact(Ground,pickup_drop)',
            'Look',
            'Speak'])

    def test_looting_unconscious_player_character_transfers_items(self):
        self.entity2 = PlayerCharacter.load(self.session, os.path.join("dwarf_cleric.yml"))
        self.battle_map.place((0, 6), self.entity2, "G")
        self.entity2.make_unconscious()
        if self.entity.item_count('healing_potion'):
            self.entity.deduct_item('healing_potion', self.entity.item_count('healing_potion'))
        self.entity2.add_item('healing_potion', 1)
        source_potions_before = self.entity.item_count('healing_potion')
        target_potions_before = self.entity2.item_count('healing_potion')

        loot_items = {
            'from': {
                'items': ['healing_potion'],
                'qty': ['1']
            },
            'to': {
                'items': [],
                'qty': []
            }
        }

        action = InteractAction(self.session, self.entity, 'interact')
        action.target = self.entity2
        action.object_action = 'loot'
        action.other_params = loot_items
        action.resolve(self.session, self.battle_map, {'battle': self.battle})

        self.assertTrue(InteractAction.apply(self.battle, action.result[0], session=self.session))
        self.assertEqual(self.entity.item_count('healing_potion'), source_potions_before + 1)
        self.assertEqual(self.entity2.item_count('healing_potion'), target_potions_before - 1)


    def test_autobuild(self):
        self.assertTrue(self.door.closed())
        self.assertEqual(set(self.door.available_interactions(self.entity).keys()), set(['open', 'investigation_check']))
        action_list = autobuild(self.session, InteractAction, self.entity, self.battle)
        self.assertEqual([str(item) for item in action_list], ['Interact(front_door,investigation_check)',
            'Interact(front_door,open)',
            'Interact(chest,open)',
            'Interact(Ground,pickup_drop)'])

    def test_failed_lockpick_logs_roll_for_cabinet(self):
        logger = ListLogger()
        event_manager = EventManager(output_logger=logger)
        event_manager.standard_cli()
        session = Session(root_path='tests/fixtures', event_manager=event_manager)
        entity = PlayerCharacter.load(session, os.path.join('halfling_rogue.yml'))
        battle_map = Map(session, 'entryway')
        cabinet = battle_map.entity_by_name('cabinet')

        self.assertIsNotNone(cabinet)

        entity.lockpick = lambda battle=None: FakeRoll('d20(7) + 7', 14)

        action = InteractAction(session, entity, 'interact')
        action.target = cabinet
        action.object_action = 'lockpick'
        action.resolve(session, battle_map)
        toast_results = InteractAction.apply(None, action.result[0], session=session)

        matching_messages = [message for message in logger.messages if 'failed to lockpick cabinet' in message]
        self.assertEqual(len(matching_messages), 1)
        self.assertIn('d20(7) + 7 = 14', matching_messages[0])
        self.assertIn('Lockpicking failed', matching_messages[0])
        self.assertEqual(toast_results[0]['type'], 'message')
        self.assertEqual(toast_results[0]['position'], cabinet.position())
        self.assertIn('failed to lockpick cabinet', toast_results[0]['message'])

    def test_successful_lockpick_returns_toast_for_cabinet(self):
        session = self.make_session()
        entity = PlayerCharacter.load(session, os.path.join('halfling_rogue.yml'))
        battle_map = Map(session, 'entryway')
        cabinet = battle_map.entity_by_name('cabinet')

        self.assertIsNotNone(cabinet)

        entity.lockpick = lambda battle=None: FakeRoll('d20(15) + 7', 22)

        action = InteractAction(session, entity, 'interact')
        action.target = cabinet
        action.object_action = 'lockpick'
        action.resolve(session, battle_map)
        toast_results = InteractAction.apply(None, action.result[0], session=session)

        self.assertFalse(cabinet.is_locked)
        self.assertEqual(toast_results[0]['type'], 'message')
        self.assertEqual(toast_results[0]['position'], cabinet.position())
        self.assertIn('successfully lockpicked cabinet', toast_results[0]['message'])
        self.assertIn('d20(15) + 7 = 22', toast_results[0]['message'])

    def test_failed_lockpick_adds_message_toaster_to_battle_animation_log(self):
        session = self.make_session()
        entity = PlayerCharacter.load(session, os.path.join('halfling_rogue.yml'))
        battle_map = Map(session, 'entryway')
        cabinet = battle_map.entity_by_name('cabinet')
        battle = Battle(session, battle_map, animation_log_enabled=True)

        battle_map.place((1, 2), entity, 'G')
        battle.add(entity, group='a')
        battle.start()
        entity.reset_turn(battle)
        entity.lockpick = lambda battle=None: FakeRoll('d20(7) + 7', 14)

        action = InteractAction(session, entity, 'interact')
        action.target = cabinet
        action.object_action = 'lockpick'
        action.resolve(session, battle_map, {'battle': battle})
        battle.commit(action)

        toast_entries = [entry for entry in battle.get_animation_logs() if isinstance(entry, dict) and entry.get('type') == 'message_toaster']
        self.assertEqual(len(toast_entries), 1)
        self.assertEqual(toast_entries[0]['position'], cabinet.position())
        self.assertIn('failed to lockpick cabinet', toast_entries[0]['message'])

    def build_door_open(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        build = build['next']('open')
        return build

    def build_door_close(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.door)
        build = build['next']('close')
        return build
    
    def build_chest_open(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.chest)
        build = build['next']('open')
        return build
    
    def build_chest_close(self):
        build = InteractAction.build(self.session, self.entity)
        build = build['next'](self.chest)
        build = build['next']('close')
        return build


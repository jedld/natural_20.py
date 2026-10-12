import unittest
import random
from natural20.session import Session
from natural20.battle import Battle
from natural20.player_character import PlayerCharacter
from natural20.event_manager import EventManager
from natural20.map import Map
from natural20.actions.attack_action import AttackAction, TwoWeaponAttackAction
from natural20.map_renderer import MapRenderer
from natural20.utils.ac_utils import calculate_cover_ac
from pdb import set_trace
from natural20.web.json_renderer import JsonRenderer
from natural20.map_renderer import MapRenderer

from natural20.utils.serialization import Serialization
import uuid
import yaml
import os

class TestSerialization(unittest.TestCase):
    def make_session(self):
        event_manager = EventManager()
        event_manager.standard_cli()
        random.seed(7000)
        return Session(root_path='tests/fixtures', event_manager=event_manager)

    def test_savegame(self):
        session = self.make_session()
        battle_map = Map(session, 'entryway')
        battle = Battle(session, battle_map)
        character = battle_map.entity_by_uid('gomerin')
        battle.add(character, 'a', token='G')
        character.reset_turn(battle)


        # action = autobuild(session, AttackAction, character, battle, match=[npc, 'vicious_rapier'])[0]
        temp_directory = 'tests/fixtures/tmp'
        os.makedirs(temp_directory, exist_ok=True)
        random_filename = os.path.join(temp_directory, uuid.uuid4().hex)
        serializer = Serialization()
        yaml = serializer.serialize(session, battle, [battle_map], filename=random_filename)
        new_session, new_battle, new_maps = serializer.deserialize(yaml)
        print(MapRenderer(battle_map, battle).render())
        print(MapRenderer(new_maps[0], new_battle).render())

        json_render = JsonRenderer(new_maps[0], new_battle).render()
        json_render_2 = JsonRenderer(battle_map, battle).render()
        self.assertEqual(json_render, json_render_2)
        os.remove(random_filename)

    def test_mid_battle_save_with_combat_log_round_trips(self):
        from natural20.actions.move_action import MoveAction
        from natural20.generic_controller import GenericController

        session = self.make_session()
        battle_map = Map(session, 'entryway')
        battle = Battle(session, battle_map)
        character = battle_map.entity_by_uid('gomerin')
        controller = GenericController(session)
        battle.add(character, 'a', token='G', controller=controller)
        character.reset_turn(battle)
        # Controller memory keyed by live Battle/entity objects.
        controller._battle_data(battle, character)['visited_location'][(1, 2)] = True
        battle.entity_state_for(character)['positions_entered'] = {(1, 2): 1, (2, 2): 1}

        attack = AttackAction(session, character, 'attack')
        attack.target = character
        attack.using = 'dagger'
        attack.legendary_action = True
        move = MoveAction(session, character, 'move')
        move.move_path = [[1, 2], [2, 2]]
        battle.battle_log.extend([attack, move])

        serializer = Serialization()
        new_session, new_battle, _ = serializer.deserialize(
            serializer.serialize(session, battle, [battle_map]))

        restored_attack, restored_move = new_battle.battle_log
        restored_char = new_session.entity_by_uid('gomerin')
        self.assertIs(restored_attack.source, restored_char)
        self.assertIs(restored_attack.target, restored_char)
        self.assertTrue(restored_attack.legendary_action)
        self.assertIs(restored_move.source, restored_char)
        self.assertEqual(new_battle.entity_state_for(restored_char)['positions_entered'],
                         {(1, 2): 1, (2, 2): 1})

    def test_untagged_battle_log_actions_save_as_records(self):
        from natural20.actions.use_item_action import UseItemAction
        from natural20.actions.action_record import ActionRecord

        session = self.make_session()
        battle_map = Map(session, 'entryway')
        battle = Battle(session, battle_map)
        character = battle_map.entity_by_uid('gomerin')
        battle.add(character, 'a', token='G')
        character.reset_turn(battle)

        use_item = UseItemAction(session, character, 'use_item')
        use_item.target = character
        battle.battle_log.append(use_item)

        serializer = Serialization()
        new_session, new_battle, _ = serializer.deserialize(
            serializer.serialize(session, battle, [battle_map]))

        record = new_battle.battle_log[0]
        restored_char = new_session.entity_by_uid('gomerin')
        self.assertIsInstance(record, ActionRecord)
        self.assertEqual(record.action_type, 'use_item')
        self.assertIs(record.source, restored_char)
        self.assertIs(record.target, restored_char)
        self.assertEqual(str(record), str(use_item))

    def test_item_library_classes_with_from_dict_are_registered(self):
        # Unregistered map objects crash yaml.dump, so every autosave silently fails.
        import importlib
        import inspect
        import pkgutil
        import natural20.item_library as item_library
        from natural20.utils.serialization import CLASS_TAG_MAPPING

        missing = []
        for mod_info in pkgutil.iter_modules(item_library.__path__):
            module = importlib.import_module(f'natural20.item_library.{mod_info.name}')
            for _name, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ != module.__name__:
                    continue
                if 'from_dict' in cls.__dict__ and cls not in CLASS_TAG_MAPPING:
                    missing.append(cls.__name__)
        self.assertEqual(missing, [])

def test_spell_action_point_target_serializes():
    from types import SimpleNamespace
    from natural20.actions.spell_action import SpellAction

    assert SpellAction._serialize_target([29, 11]) == [29, 11]
    creature = SimpleNamespace(entity_uid='abc')
    assert SpellAction._serialize_target(creature) == 'abc'
    assert SpellAction._serialize_target([creature, [1, 2]]) == ['abc', [1, 2]]


def test_plain_effect_objects_round_trip():
    from natural20.spell.chill_touch_spell import ChillTouchSpellUndeadEffect

    session = Session(root_path='tests/fixtures', event_manager=EventManager())
    battle_map = Map(session, 'entryway')
    battle = Battle(session, battle_map)
    caster = battle_map.entity_by_uid('gomerin')
    battle.add(caster, 'a', token='G')
    skeleton = session.npc('skeleton')
    battle_map.add(skeleton, 1, 1)
    battle.add(skeleton, 'b')
    effect = ChillTouchSpellUndeadEffect(caster, skeleton)
    skeleton.register_effect('attack_advantage_modifier', ChillTouchSpellUndeadEffect,
                             effect=effect, source=caster)

    serializer = Serialization()
    data = serializer.serialize(session, battle, [battle_map])
    assert '!effect_object' in data
    new_session, _new_battle, new_maps = serializer.deserialize(data)

    restored_skeleton = new_maps[0].entity_by_uid(skeleton.entity_uid)
    restored = restored_skeleton.effects['attack_advantage_modifier'][0]['effect']
    assert isinstance(restored, ChillTouchSpellUndeadEffect)
    assert restored.source.entity_uid == caster.entity_uid
    assert restored.target is restored_skeleton or restored.target.entity_uid == skeleton.entity_uid
    assert not isinstance(restored.source, str)

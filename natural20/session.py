import yaml
import os
from collections import deque
from natural20.npc import Npc
from natural20.event_manager import EventManager
from natural20.player_character import PlayerCharacter
from natural20.map import Map
import i18n
from copy import deepcopy
import pdb

def represent_map(dumper, data):
    return dumper.represent_mapping('!map', data.to_dict())

def represent_battle(dumper, data):
    return dumper.represent_mapping('!battle', data.to_dict())



# typed: true
class Session:
    def __init__(self, root_path=None, event_manager=None, conversation_handlers=None):
        if not event_manager:
            event_manager = EventManager()
        self.root_path = root_path or '.'
        self.session_state = {}
        self.weapons = {}
        self.equipment = {}
        self.objects = {}
        self.thing = {}
        self.char_classes = {}
        self.spells = {}
        self.settings = {
            'manual_dice_roll': False
        }
        self.game_time = 0
        self.render_for_text = True
        self.event_log = deque(maxlen=100)
        self.default_locale = 'en'
        self.event_manager = event_manager
        self.conversation_handlers = conversation_handlers or {}
        i18n.load_path.append(os.path.join(self.root_path, 'locales'))
        i18n.set('filename_format', '{locale}.{format}')
        game_file = os.path.join(self.root_path, 'game.yml')
        if os.path.exists(game_file):
            with open(game_file, 'r') as f:
                self.game_properties = yaml.safe_load(f)
        else:
            raise Exception(f'Missing game {game_file} file')
        self._load_all_maps(self.game_properties)

    def register_conversation_handler(self, type, handler):
        print(f'Registering conversation handler {type} {handler}')
        self.conversation_handlers[type] = handler

    def conversation_controller(self, entity, handler, prompt):
        if handler not in self.conversation_handlers:
            raise Exception(f'Unknown conversation handler: {handler}')
        return self.conversation_handlers[handler](entity, prompt)

    def reset(self):
        self.game_time = 0
        self.session_state = {}
        self.event_log = deque(maxlen=100)

    def map_for(self, entity):
        return self.map_for_entity(entity)

    def map_for_entity(self, entity):
        for _, map_obj in self.maps.items():
            if isinstance(entity, str):
                _entity = map_obj.get_entity_by_uid(entity)
            else:
                _entity = entity

            if _entity in map_obj.entities:
                return map_obj

            if _entity in map_obj.interactable_objects.keys():
                return map_obj
        return None

    def entity_by_uid(self, entity_uid):
        for _, map_obj in self.maps.items():
            entity = map_obj.entity_by_uid(entity_uid)
            if entity:
                return entity
        return None        

    def _load_all_maps(self, game_file):
        self.maps = {}

        if 'maps' not in game_file:
            self.maps['index'] = Map(self, game_file.get('starting_map'), name = 'index')
            return self.maps

        map_with_key = game_file.get('maps', {})
        for name, map_file in map_with_key.items():
            self.maps[name] = Map(self, map_file, name=name)

        # add links to the other maps
        for _, map_obj in self.maps.items():
            for name, linked_map in self.maps.items():
                if map_obj!=linked_map:
                    map_obj.add_linked_map(name, linked_map)

        return self.maps

    def register_map(self, name, map_file):
        self.maps[name] = Map(self, map_file, name=name)
        return self.maps[name]

    def groups(self):
        return self.game_properties.get('groups', {})

    def opposing(self, group1, group2):

        group1_info = self.groups()[group1]
        group2_info = self.groups()[group2]

        if group2 in group1_info.get('enemies', []):
            return True
        if group1 in group2_info.get('enemies', []):
            return True
        return False


    @staticmethod
    def new_session(root_path=None):
        session = Session(root_path)
        return session

    @staticmethod
    def current_session():
        return Session.session

    @staticmethod
    def set_session(session):
        Session.session = session

    def clear_event_log(self):
        self.event_log.clear()

    def log_event(self, event):
        self.event_log.append(event)

    def update_settings(self, settings):
        valid_settings = ['manual_dice_roll']
        for k in settings.keys():
            if k not in valid_settings:
                raise Exception('Invalid settings')
        self.settings.update(settings)

    def setting(self, k):
        valid_settings = ['manual_dice_roll']
        if k not in valid_settings:
            raise Exception('Invalid settings')
        return self.settings[k]

    def increment_game_time(self, seconds=6):
        self.game_time += seconds

    def load_characters(self):
        files = os.listdir(os.path.join(self.root_path, 'characters'))
        characters = []
        for file in files:
            if file.endswith('.yml'):
                with open(os.path.join(self.root_path, 'characters', file), 'r') as f:
                    char_content = yaml.safe_load(f)
                    characters.append(PlayerCharacter(self, char_content))
        return characters

    def save_state(self, state_type, value=None):
        if value is None:
            value = {}
        self.session_state.setdefault(state_type, {})
        self.session_state[state_type].update(value)

    def load_state(self, state_type):
        return self.session_state.get(state_type, {})

    def has_save_game(self):
        return os.path.exists(os.path.join(self.root_path, 'savegame.yml'))

    def save_game(self, battle, maps, filename=None):
        from natural20.battle import Battle

        if maps and not isinstance(maps, list):
            maps = [maps]
        state = {'session': self, 'maps': battle.maps if battle else maps, 'battle': battle}
        yaml_str = yaml.safe_dump(state)
        if filename:
            with open(os.path.join(self.root_path, filename), 'w') as f:
                f.write(yaml_str)
        return yaml_str

    def save_character(self, name, data):
        with open(os.path.join(self.root_path, 'characters', f'{name}.yml'), 'w') as f:
            yaml.safe_dump(data, f)

    def load_save(self, yaml=None, filename=None):
        save_file = os.path.join(self.root_path, filename)
        if yaml:
            return yaml.safe_load(yaml)
        elif os.path.exists(save_file):
            with open(save_file, 'r') as f:
                return yaml.safe_load(f)
        return None

    def npc(self, npc_type, options=None):
        if options is None:
            options = {}
        return Npc(self, npc_type, options)

    def load_npcs(self):
        files = os.listdir(os.path.join(self.root_path, 'npcs'))
        npcs = []
        for file in files:
            if file.endswith('.yml'):
                npc_name = os.path.splitext(file)[0]
                npcs.append(Npc(self, npc_name, { "rand_life" : True}))
        return npcs
    

    def npc_info(self, familiar=False):
        files = os.listdir(os.path.join(self.root_path, 'npcs'))
        npc_info = {}
        for file in files:
            if file.endswith('.yml'):
                npc_name = os.path.splitext(file)[0]
                with open(os.path.join(self.root_path, 'npcs', file), 'r') as f:
                    npc_details = yaml.safe_load(f)
                    if familiar:
                        if not npc_details.get('familiar', False):
                            continue

                    npc_info[npc_name] = {**npc_details, 'id': npc_name, 'label': npc_details.get('label', npc_name)}
        return npc_info

    def load_races(self):
        files = os.listdir(os.path.join(self.root_path, 'races'))
        races = {}
        for file in files:
            if file.endswith('.yml'):
                race_name = os.path.splitext(file)[0]
                with open(os.path.join(self.root_path, 'races', file), 'r') as f:
                    races[race_name] = yaml.safe_load(f)
        return races

    def load_classes(self):
        files = os.listdir(os.path.join(self.root_path, 'char_classes'))
        classes = {}
        for file in files:
            if file.endswith('.yml'):
                class_name = os.path.splitext(file)[0]
                with open(os.path.join(self.root_path, 'char_classes', file), 'r') as f:
                    classes[class_name] = yaml.safe_load(f)
        return classes

    def load_spell(self, spell):
        if spell not in self.spells:
            spells = self.load_yaml_file('items', 'spells')
            spell_details = spells.get(spell)

            if not spell_details:
                raise Exception(f'Spell {spell} not found')

            self.spells[spell] = spell_details
            self.spells[spell]['id'] = spell
        return self.spells[spell]
    
    def load_all_spells(self):
        return self.load_yaml_file('items', 'spells')

    def load_class(self, klass):
        if klass not in self.char_classes:
            self.char_classes[klass] = self.load_yaml_file('char_classes', klass)
        return self.char_classes[klass]

    def load_weapon(self, weapon):
        if weapon not in self.weapons:
            weapons = self.load_yaml_file('items', 'weapons')
            self.weapons[weapon] = weapons.get(weapon)
            if self.weapons[weapon] is not None:
                self.weapons[weapon]['equippable'] = True
        return self.weapons[weapon]

    def load_weapons(self):
        return self.load_yaml_file('items', 'weapons')

    def load_thing(self, item):
        if item not in self.thing:
            self.thing[item] = self.load_weapon(item) or self.load_equipment(item) or self.load_object(item)
        return self.thing[item]

    def load_equipment(self, item):
        if item not in self.equipment:
            equipment = self.load_yaml_file('items', 'equipment')
            self.equipment[item] = equipment.get(item)
            if self.equipment[item] and 'equippable' not in self.equipment[item]:
                if self.equipment[item].get('type') in ['shield', 'armor']:
                    self.equipment[item]['equippable'] = True
                else:
                    self.equipment[item]['equippable'] = False
        return self.equipment[item]

    def load_all_equipments(self):
        return self.load_yaml_file('items', 'equipment')

    def load_object(self, object_name):
        if object_name not in self.objects:
            objects = self.load_yaml_file('items', 'objects')
            self.objects[object_name] = objects.get(object_name)
            assert self.objects[object_name], f'Object {object_name} not found'
        return deepcopy(self.objects[object_name])

    def t(self, token, options=None):
        if options is None:
            options = {}
        return i18n.t(token, **options)

    def load_yaml_file(self, category, resource):
        file_path = os.path.join(self.root_path, category, f'{resource}.yml')
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)

    def update_state(self, state):
        self.session_state.update(state)

    def to_dict(self):
        return {
            'game_time': self.game_time,
            'root_path': self.root_path,
            'session_state': self.session_state,
            'event_log': list(self.event_log),
            'settings': self.settings,
            'render_for_text': self.render_for_text
        }

    def from_dict(data):
        session = Session(data['root_path'])
        session.game_time = data['game_time']
        session.session_state = data['session_state']
        session.event_log = deque(data['event_log'])
        session.settings = data['settings']
        session.render_for_text = data['render_for_text']
        return session
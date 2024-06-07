import yaml
import os
from collections import defaultdict, deque
from natural20.npc import Npc
# typed: true
class Session:
    def __init__(self, root_path=None):
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
        self.event_log = deque(maxlen=100)
        self.load_path = []
        self.load_path.append(os.path.join(self.root_path, 'locales'))
        self.default_locale = 'en'

        game_file = os.path.join(self.root_path, 'game.yml')
        if os.path.exists(game_file):
            with open(game_file, 'r') as f:
                self.game_properties = yaml.safe_load(f)
        else:
            raise Exception(f'Missing game {game_file} file')

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

    def save_state(self, state_type, value={}):
        self.session_state.setdefault(state_type, {})
        self.session_state[state_type].update(value)

    def load_state(self, state_type):
        return self.session_state.get(state_type, {})

    def has_save_game(self):
        return os.path.exists(os.path.join(self.root_path, 'savegame.yml'))

    def save_game(self, battle, map):
        state = {'session': self, 'map': battle.map if battle else map, 'battle': battle}
        with open(os.path.join(self.root_path, 'savegame.yml'), 'w') as f:
            yaml.safe_dump(state, f)

    def save_character(self, name, data):
        with open(os.path.join(self.root_path, 'characters', f'{name}.yml'), 'w') as f:
            yaml.safe_dump(data, f)

    def load_save(self):
        save_file = os.path.join(self.root_path, 'savegame.yml')
        if os.path.exists(save_file):
            with open(save_file, 'r') as f:
                return yaml.safe_load(f)
        return None

    def npc(self, npc_type, options={}):
        return Npc(self, npc_type, options)

    def load_npcs(self):
        files = os.listdir(os.path.join(self.root_path, 'npcs'))
        npcs = []
        for file in files:
            if file.endswith('.yml'):
                npc_name = os.path.splitext(file)[0]
                npcs.append(Npc(self, npc_name, rand_life=True))
        return npcs

    def npc_info(self):
        files = os.listdir(os.path.join(self.root_path, 'npcs'))
        npc_info = {}
        for file in files:
            if file.endswith('.yml'):
                npc_name = os.path.splitext(file)[0]
                with open(os.path.join(self.root_path, 'npcs', file), 'r') as f:
                    npc_details = yaml.safe_load(f)
                    npc_info[npc_name] = {**npc_details, 'id': npc_name}
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
            self.spells[spell] = spells.get(spell)
        return self.spells[spell]

    def load_class(self, klass):
        if klass not in self.char_classes:
            self.char_classes[klass] = self.load_yaml_file('char_classes', klass)
        return self.char_classes[klass]

    def load_weapon(self, weapon):
        if weapon not in self.weapons:
            weapons = self.load_yaml_file('items', 'weapons')
            self.weapons[weapon] = weapons.get(weapon)
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
        return self.equipment[item]

    def load_object(self, object_name):
        if object_name not in self.objects:
            objects = self.load_yaml_file('items', 'objects')
            self.objects[object_name] = objects.get(object_name)
        return self.objects[object_name]

    def t(self, token, options={}):
        return token

    def load_yaml_file(self, category, resource):
        file_path = os.path.join(self.root_path, category, f'{resource}.yml')
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)
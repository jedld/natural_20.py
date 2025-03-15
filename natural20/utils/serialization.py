from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.item_library.object import Object
from natural20.item_library.common import Ground, StoneWall
from natural20.session import Session
from typing import Any
import yaml
from natural20.map import Map
from natural20.battle import Battle
import pdb
import uuid

def represent_map(dumper, data):
    return dumper.represent_mapping('!map', data.to_dict())

def represent_battle(dumper, data):
    return dumper.represent_mapping('!battle', data.to_dict())

def represent_player_character(dumper, data):
    return dumper.represent_mapping('!player_character', data.to_dict())

def represent_npc(dumper, data):
    return dumper.represent_mapping('!npc', data.to_dict())

def represent_session(dumper, data):
    return dumper.represent_mapping('!session', data.to_dict())

def represent_object(dumper, data):
    return dumper.represent_mapping('!object', data.to_dict())

def represent_ground(dumper, data):
    return dumper.represent_mapping('!ground', data.to_dict())

def represent_stone_wall(dumper, data):
    return dumper.represent_mapping('!stone_wall', data.to_dict())

def represent_uuid(dumper, data):
    # Store the UUID value in a scalar node
    return dumper.represent_scalar('!uuid', str(data))

# Attach representers to SafeDumper instead
yaml.SafeDumper.add_representer(Map, represent_map)
yaml.SafeDumper.add_representer(Battle, represent_battle)
yaml.SafeDumper.add_representer(PlayerCharacter, represent_player_character)
yaml.SafeDumper.add_representer(Npc, represent_npc)
yaml.SafeDumper.add_representer(Session, represent_session)
yaml.SafeDumper.add_representer(Object, represent_object)
yaml.SafeDumper.add_representer(Ground, represent_ground)
yaml.SafeDumper.add_representer(StoneWall, represent_stone_wall)

# Attach this representer to the SafeDumper
yaml.SafeDumper.add_representer(uuid.UUID, represent_uuid)

# Create a specialized loader with constructors
class SafeLoaderWithConstructors(yaml.FullLoader):
    pass

def construct_map(loader, node):
    print('constructing map')
    data = loader.construct_mapping(node, deep=True)  # use deep=True to load nested mappings
    return Map.from_dict(data)

def construct_battle(loader, node):
    print('constructing battle')
    data = loader.construct_mapping(node, deep=True)
    return Battle.from_dict(data)

def construct_player_character(loader, node):
    data = loader.construct_mapping(node, deep=True)
    return PlayerCharacter.from_dict(data)

def construct_npc(loader, node):
    data = loader.construct_mapping(node, deep=True)
    return Npc.from_dict(data)

def construct_session(loader, node):
    data = loader.construct_mapping(node, deep=True)
    return Session.from_dict(data)

def construct_object(loader, node):
    data = loader.construct_mapping(node, deep=True)
    return Object.from_dict(data)

def construct_ground(loader, node):
    data = loader.construct_mapping(node, deep=True)
    return Ground.from_dict(data)

def construct_stone_wall(loader, node):
    data = loader.construct_mapping(node, deep=True)
    return StoneWall.from_dict(data)

def construct_uuid(loader, node):
    return uuid.UUID(loader.construct_scalar(node))

SafeLoaderWithConstructors.add_constructor('!map', construct_map)
SafeLoaderWithConstructors.add_constructor('!battle', construct_battle)
SafeLoaderWithConstructors.add_constructor('!player_character', construct_player_character)
SafeLoaderWithConstructors.add_constructor('!npc', construct_npc)
SafeLoaderWithConstructors.add_constructor('!session', construct_session)
SafeLoaderWithConstructors.add_constructor('!object', construct_object)
SafeLoaderWithConstructors.add_constructor('!ground', construct_ground)
SafeLoaderWithConstructors.add_constructor('!stone_wall', construct_stone_wall)
SafeLoaderWithConstructors.add_constructor('!uuid', construct_uuid)


class Serialization:
    def __init__(self):
        pass

    def serialize(self, session: Session, battle: Battle, maps: Map, filename: str = None):
        state = {
            'session': session,
            'maps': maps,
            'battle': battle
        }

        yaml_str = yaml.dump(state, Dumper=yaml.SafeDumper)
        if filename:
            with open(filename, 'w') as f:
                f.write(yaml_str)
        return yaml_str

    def deserialize(self, yaml_data):
        # Disallow unknown Python tags
        def no_undefined_constructor(loader, node):
            raise yaml.constructor.ConstructorError(
                None, None, "Unknown tag encountered: %s" % node.tag, node.start_mark
            )
        SafeLoaderWithConstructors.add_constructor(None, no_undefined_constructor)

        state = yaml.load(yaml_data, Loader=SafeLoaderWithConstructors)
        return state['session'], state['battle'], state['maps']

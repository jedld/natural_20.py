from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.item_library.object import Object
from natural20.item_library.common import Ground, StoneWall, StoneWallDirectional
from natural20.item_library.fireplace import Fireplace
from natural20.item_library.door_object import DoorObjectWall, DoorObject
from natural20.item_library.chest import Chest
from natural20.item_library.teleporter import Teleporter
from natural20.item_library.trap_door import TrapDoor
from natural20.item_library.switch import Switch
from natural20.item_library.spell_scroll import SpellScroll
from natural20.item_library.healing_potion import HealingPotion
from natural20.session import Session
from typing import Any
import yaml
from natural20.map import Map
from natural20.battle import Battle
import pdb
import uuid
import numpy as np

def represent_uuid(dumper, data):
    # Store the UUID value in a scalar node
    return dumper.represent_scalar('!uuid', str(data))

def represent_ndarray(dumper, data):
    return dumper.represent_list(data.tolist())

# Create a specialized loader with constructors
class SafeLoaderWithConstructors(yaml.FullLoader):
    pass

# Global mapping: classes are associated with their YAML tag.
CLASS_TAG_MAPPING = {
    Map: '!map',
    Battle: '!battle',
    HealingPotion: '!healing_potion',
    SpellScroll: '!spell_scroll',
    PlayerCharacter: '!player_character',
    Npc: '!npc',
    Session: '!session',
    Object: '!object',
    Ground: '!ground',
    StoneWall: '!stone_wall',
    StoneWallDirectional: '!stone_wall_directional',
    Fireplace: '!fireplace',
    DoorObjectWall: '!door_object_wall',
    DoorObject: '!door_object',
    Chest: '!chest',
    Switch: '!switch',
    Teleporter: '!teleporter',
    TrapDoor: '!trap_door',
}

def generic_constructor(loader, node):
    # Handle UUID specially.
    if node.tag == '!uuid':
        return uuid.UUID(loader.construct_scalar(node))
    # Look up our mapping to find the class associated with this tag.
    for cls, tag in CLASS_TAG_MAPPING.items():
        if node.tag == tag:
            data = loader.construct_mapping(node, deep=True)
            return cls.from_dict(data)
    raise yaml.constructor.ConstructorError(
        None, None, "Unknown tag encountered: %s" % node.tag, node.start_mark
    )

def register_yaml_handlers():
    # Register representers with a lambda to capture the tag.
    for cls, tag in CLASS_TAG_MAPPING.items():
        yaml.SafeDumper.add_representer(
            cls, lambda dumper, data, tag=tag: dumper.represent_mapping(tag, data.to_dict())
        )
    yaml.SafeDumper.add_representer(uuid.UUID, represent_uuid)
    yaml.SafeDumper.add_representer(np.ndarray, represent_ndarray)
    
    # Register constructors for each tag in our mapping, plus the UUID.
    for tag in list(CLASS_TAG_MAPPING.values()) + ['!uuid']:
        SafeLoaderWithConstructors.add_constructor(tag, generic_constructor)

register_yaml_handlers()

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

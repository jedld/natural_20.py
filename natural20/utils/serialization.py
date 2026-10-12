from natural20.battle import Battle
from natural20.map import Map
from natural20.player_character import PlayerCharacter
from natural20.npc import Npc
from natural20.item_library.object import Object
from natural20.item_library.common import Ground, StoneWall, StoneWallDirectional
from natural20.item_library.fireplace import Fireplace
from natural20.item_library.door_object import DoorObjectWall, DoorObject
from natural20.item_library.window_object import WindowObjectWall
from natural20.item_library.chest import Chest
from natural20.item_library.teleporter import Teleporter
from natural20.item_library.chasm import Chasm
from natural20.item_library.trap_door import TrapDoor
from natural20.item_library.switch import Switch
from natural20.item_library.multi_switch import MultiSwitch
from natural20.item_library.spell_scroll import SpellScroll
from natural20.item_library.healing_potion import HealingPotion
from natural20.item_library.proximity_trigger import ProximityTrigger
from natural20.item_library.room_service_buzzer import RoomServiceBuzzer
from natural20.item_library.crypt_coffin import CryptCoffin
from natural20.spell.mage_armor_spell import MageArmorSpell
from natural20.actions.spell_action import SpellAction
from natural20.actions.move_action import MoveAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.action_record import ActionRecord
from natural20.action import Action
from natural20.spell.bless_spell import BlessSpell
from natural20.item_library.pit_trap import PitTrap
from natural20.generic_controller import GenericController
from natural20.web.web_controller import WebController
from natural20.session import Session
from natural20.die_roll import DieRollResult
from typing import Any
import yaml
from natural20.map import Map
from natural20.battle import Battle
import pdb
import uuid
import numpy as np
import importlib
import re

def represent_uuid(dumper, data):
    # Store the UUID value in a scalar node
    return dumper.represent_scalar('!uuid', str(data))

def represent_ndarray(dumper, data):
    return dumper.represent_list(data.tolist())

def represent_np_integer(dumper, data):
    return dumper.represent_int(int(data))

def represent_np_floating(dumper, data):
    return dumper.represent_float(float(data))

def represent_np_bool(dumper, data):
    return dumper.represent_bool(bool(data))

def represent_die_roll_result(dumper, data):
    return dumper.represent_int(int(data))

_SPELL_BASE_FIELDS = {
    'session', 'name', 'properties', 'action', 'source', 'target',
    'errors', 'validation_issues', 'attack_roll',
}
_SPELL_SCALAR_TYPES = (bool, int, float, str, type(None))


def _entity_ref(value):
    uid = getattr(value, 'entity_uid', None)
    if uid is not None:
        return uid
    return value if isinstance(value, str) else None


def represent_spell(dumper, data):
    """Fallback for Spell subclasses without a dedicated tag (e.g. persistent effects)."""
    state = {
        k: v for k, v in vars(data).items()
        if k not in _SPELL_BASE_FIELDS and not k.startswith('_')
        and isinstance(v, _SPELL_SCALAR_TYPES)
    }
    return dumper.represent_mapping('!spell', {
        'class': f"{type(data).__module__}.{type(data).__qualname__}",
        'name': data.name,
        'session': data.session,
        'properties': data.properties,
        'source': _entity_ref(data.source),
        'target': _entity_ref(data.target),
        'state': state,
    })


EFFECT_ENTITY_REFS_ATTR = '_n20_entity_refs'


def represent_effect_object(dumper, data):
    """Fallback for plain engine objects (effect markers such as Chill Touch's
    undead effect) that have no dedicated tag. Entities become UIDs relinked
    on load; session/battle/map handles are dropped and other values are
    represented normally."""
    from natural20.entity import Entity

    klass = type(data)
    if not klass.__module__.startswith('natural20.') or not hasattr(data, '__dict__'):
        raise yaml.representer.RepresenterError("cannot represent an object", data)
    state, entities = {}, {}
    for key, value in vars(data).items():
        if key == EFFECT_ENTITY_REFS_ATTR or isinstance(value, (Session, Battle, Map)):
            continue
        if isinstance(value, Entity):
            entities[key] = value.entity_uid
        else:
            state[key] = value
    return dumper.represent_mapping('!effect_object', {
        'class': f"{klass.__module__}.{klass.__qualname__}",
        'state': state,
        'entities': entities,
    })


def effect_object_constructor(loader, node):
    data = loader.construct_mapping(node, deep=True)
    module_name, class_name = data['class'].rsplit('.', 1)
    klass = getattr(importlib.import_module(module_name), class_name)
    obj = klass.__new__(klass)
    for key, value in (data.get('state') or {}).items():
        setattr(obj, key, value)
    entities = data.get('entities') or {}
    for key, uid in entities.items():
        setattr(obj, key, uid)
    if entities:
        setattr(obj, EFFECT_ENTITY_REFS_ATTR, list(entities))
    return obj


def spell_constructor(loader, node):
    data = loader.construct_mapping(node, deep=True)
    module_name, class_name = data['class'].rsplit('.', 1)
    klass = getattr(importlib.import_module(module_name), class_name)
    spell = klass(data.get('session'), data.get('source'), data.get('name'), data.get('properties') or {})
    spell.target = data.get('target')
    for key, value in (data.get('state') or {}).items():
        setattr(spell, key, value)
    return spell


def relink_spell_entities(session, maps=None, battle=None):
    """Swap entity_uid strings on restored spell effects (and summoner links) back to live entities."""
    from natural20.spell.spell import Spell

    def resolve(value):
        if isinstance(value, str):
            entity = session.entity_by_uid(value)
            return entity if entity is not None else value
        return value

    def fix(spell):
        if isinstance(spell, Spell):
            spell.source = resolve(spell.source)
            spell.target = resolve(spell.target)
        for attr in getattr(spell, EFFECT_ENTITY_REFS_ATTR, None) or []:
            setattr(spell, attr, resolve(getattr(spell, attr, None)))

    entities = set()
    for m in (maps.values() if isinstance(maps, dict) else (maps or [])):
        entities.update(getattr(m, 'entities', {}) or {})
    if battle is not None:
        entities.update(getattr(battle, 'entities', {}) or {})
    for entity in entities:
        summoner_uid = (getattr(entity, 'properties', None) or {}).get('summoner_uid')
        if summoner_uid and getattr(entity, 'owner', None) is None:
            entity.owner = session.entity_by_uid(summoner_uid)
        for descriptors in (getattr(entity, 'effects', None) or {}).values():
            for descriptor in descriptors or []:
                if isinstance(descriptor, dict):
                    fix(descriptor.get('effect'))
                    if 'source' in descriptor:
                        descriptor['source'] = resolve(descriptor['source'])
        for descriptor in getattr(entity, 'casted_effects', None) or []:
            if isinstance(descriptor, dict):
                fix(descriptor.get('effect'))
                if 'target' in descriptor:
                    descriptor['target'] = resolve(descriptor['target'])


def relink_battle_log(session, battle):
    """Swap entity_uid strings on restored ``battle.battle_log`` actions back to
    live entities and attach the session (older saves omitted both)."""
    if battle is None:
        return
    for action in getattr(battle, 'battle_log', None) or []:
        if getattr(action, 'session', None) is None and hasattr(action, 'session'):
            action.session = session
        for attr in ('source', 'target'):
            value = getattr(action, attr, None)
            if isinstance(value, str):
                entity = session.entity_by_uid(value)
                if entity is not None:
                    setattr(action, attr, entity)
            elif isinstance(action, ActionRecord) and isinstance(value, list):
                setattr(action, attr, [
                    (session.entity_by_uid(v) or v) if isinstance(v, str) else v for v in value
                ])

def represent_class(dumper, data):
    # Represent a class by its fully qualified name.
    class_path = data.__module__ + "." + data.__qualname__
    return dumper.represent_scalar('!class', class_path)

yaml.SafeDumper.add_representer(type, represent_class)

# Create a specialized loader with constructors
class SafeLoaderWithConstructors(yaml.FullLoader):
    def construct_mapping(self, node, deep=False):
        # SafeDumper writes tuple keys (e.g. battle state ``positions_entered``)
        # as sequences, which are unhashable; load them back as tuples.
        if isinstance(node, yaml.MappingNode):
            for key_node, _ in node.value:
                if isinstance(key_node, yaml.SequenceNode):
                    key_node.tag = 'tag:yaml.org,2002:python/tuple'
        return super().construct_mapping(node, deep=deep)

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
    WindowObjectWall: '!window_object_wall',
    DoorObject: '!door_object',
    Chest: '!chest',
    Switch: '!switch',
    Teleporter: '!teleporter',
    Chasm: '!chasm',
    TrapDoor: '!trap_door',
    ProximityTrigger: '!proximity_trigger',
    MageArmorSpell: '!mage_armor_spell',
    SpellAction: '!spell_action',
    BlessSpell: '!bless_spell',
    MoveAction: '!move_action',
    PitTrap: '!pit_trap',
    GenericController: '!generic_controller',
    WebController: '!web_controller',
    AttackAction: '!attack_action',
    ActionRecord: '!action_record',
    MultiSwitch: '!multi_switch',
    RoomServiceBuzzer: '!room_service_buzzer',
    CryptCoffin: '!crypt_coffin',
}
def snake_case(str):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', str)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

def object_type_to_klass(obj_type):
    # snake case and add the exclamation
    obj_type = f"!{snake_case(obj_type)}"

    for cls, tag in CLASS_TAG_MAPPING.items():
        if tag == obj_type:
            return cls
    raise ValueError(f"Unknown object type: {obj_type}")

def generic_constructor(loader, node):
    # Handle UUID specially.
    if node.tag == '!uuid':
        return uuid.UUID(loader.construct_scalar(node))
    # Look up our mapping to find the class associated with this tag.
    for cls, tag in CLASS_TAG_MAPPING.items():
        if node.tag == tag:
            if tag in ('!generic_controller', '!web_controller'):
                # Older saves stored controller ``battle_data`` keyed by the
                # Battle being loaded (a recursive alias); it's transient, drop it.
                node.value = [(k, v) for k, v in node.value
                              if getattr(k, 'value', None) != 'battle_data']
            data = loader.construct_mapping(node, deep=True)
            return cls.from_dict(data)
    raise yaml.constructor.ConstructorError(
        None, None, "Unknown tag encountered: %s" % node.tag, node.start_mark
    )

def class_constructor(loader, node):
    class_path = loader.construct_scalar(node)
    module_name, class_name = class_path.rsplit('.', 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)

SafeLoaderWithConstructors.add_constructor('!class', class_constructor)

def register_yaml_handlers():
    # Register representers with a lambda to capture the tag.
    for cls, tag in CLASS_TAG_MAPPING.items():
        yaml.SafeDumper.add_representer(
            cls, lambda dumper, data, tag=tag: dumper.represent_mapping(tag, dict(data.to_dict()))
        )
    yaml.SafeDumper.add_representer(uuid.UUID, represent_uuid)
    yaml.SafeDumper.add_representer(np.ndarray, represent_ndarray)
    yaml.SafeDumper.add_representer(DieRollResult, represent_die_roll_result)
    from natural20.spell.spell import Spell
    yaml.SafeDumper.add_multi_representer(Spell, represent_spell)
    SafeLoaderWithConstructors.add_constructor('!spell', spell_constructor)
    # Actions without their own tag (e.g. UseItemAction in battle_log) are
    # saved as ActionRecord; exact-class representers above take precedence.
    yaml.SafeDumper.add_multi_representer(
        Action,
        lambda dumper, data: dumper.represent_mapping('!action_record', ActionRecord.from_action(data).to_dict()),
    )
    # NumPy scalar types (np.int64, np.float32, np.bool_, etc.) are not handled
    # by PyYAML SafeDumper by default.
    yaml.SafeDumper.add_multi_representer(np.integer, represent_np_integer)
    yaml.SafeDumper.add_multi_representer(np.floating, represent_np_floating)
    yaml.SafeDumper.add_multi_representer(np.bool_, represent_np_bool)
    yaml.SafeDumper.add_multi_representer(object, represent_effect_object)
    SafeLoaderWithConstructors.add_constructor('!effect_object', effect_object_constructor)
    
    # Register constructors for each tag in our mapping, plus the UUID.
    for tag in list(CLASS_TAG_MAPPING.values()) + ['!uuid']:
        SafeLoaderWithConstructors.add_constructor(tag, generic_constructor)

register_yaml_handlers()

class Serialization:
    def __init__(self):
        self.dict_cache = {}

    def serialize(self, session: Session, battle: Battle, maps: Map, filename: str = None):
        state = {
            'session': session,
            'maps': maps,
            'battle': battle
        }

        session._entity_serialize_seen = set()
        try:
            yaml_str = yaml.dump(state, Dumper=yaml.SafeDumper)
        finally:
            session._entity_serialize_seen = None
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
        # Ensure registry is populated for the restored session
        try:
            session = state['session']
            battle = state.get('battle')
            maps = state.get('maps')
            session.rebuild_entity_registry(maps=maps, battle=battle)
            relink_spell_entities(session, maps=maps, battle=battle)
            relink_battle_log(session, battle)
        except Exception:
            pass
        return state['session'], state['battle'], state['maps']

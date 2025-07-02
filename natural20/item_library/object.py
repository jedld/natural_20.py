from typing import List
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from typing import Dict
from typing import Tuple
from typing import Any
from natural20.entity import Entity
from natural20.die_roll import DieRoll
from natural20.utils.action_builder import autobuild
from natural20.actions.interact_action import InteractAction
from natural20.concern.event_loader import EventLoader
from natural20.concern.container import Container
import uuid
import pdb


class InvalidInteractionAction(Exception):
    def __init__(self, action: str, valid_actions: List[str] = []) -> None:
        self.action = action
        self.valid_actions = valid_actions

    def message(self) -> str:
        return f"Invalid action specified {self.action}. should be in {','.join(self.valid_actions)}"


@dataclass
class Object(Entity, Container, EventLoader):
    def __init__(self, session, map: Any, properties: Dict[str, Any]) -> None:
        Entity.__init__(self, properties.get('name'), properties.get('description', ''), properties)
        self.entity_uid = properties.get('entity_uid', str(uuid.uuid4()))
        self._name = properties.get('name')
        self._description = properties.get('description', self.name)
        self.map = map
        self.session = session
        self.type = properties.get('type')
        self.concentration = None
        self.effects = {}
        self.inventory = None
        self._temp_hp = 0
        self.interact_distance = properties.get('interact_distance', 5)
        # fake attributes for dungeons and dragons objects
        self.attributes = properties.get('attributes', {
        })
        self.ability_scores = properties.get('ability_scores', {
            "str": 0,
            "dex": 0,
            "con": 0,
            "int": 0,
            "wis": 0,
            "cha": 0
        })

        self.statuses = []
        self.properties = properties
        self.resistances = properties.get('resistances', [])
        self.is_concealed = properties.get('concealed', False)
        self.perception_dc = properties.get('perception_dc', None)
        self.setup_other_attributes()
        if properties.get('hp_die', None):
            self.attributes["hp"] = DieRoll.roll(properties['hp_die']).result()
        else:
            self.attributes["hp"] = properties.get('max_hp', None)

        if properties.get('inventory'):
            self.inventory = {
                inventory['type']: {'qty': inventory['qty']} for inventory in properties['inventory']
            }

        if properties.get('buttons'):
            for button in properties['buttons']:
                self.buttons[button['action']] = button

        for ability, skills in self.SKILL_AND_ABILITY_MAP.items():
            for skill in skills:
                setattr(self, f"{skill}_mod", self.make_skill_mod_function(skill, ability))
                setattr(self, f"{skill}_check", self.make_skill_check_function(skill))

        self.events = self.register_event_handlers(session, map, properties)

    def __str__(self) -> str:
        if self.name:
            return self.name
        return self.__class__.__name__

    def __repr__(self):
        """
        Return the string representation of the object
        """
        if self.name:
            return self.name
        return self.__class__.__name__

    def __hash__(self) -> int:
        return id(self)

    def after_setup(self):
        pass

    def conceal_perception_dc(self) -> int:
        return self.perception_dc

    def reveal(self):
        self.is_concealed = False
        self.trigger_event('reveal', None, self.session, self.map, None)

    def name(self) -> str:
        return self._name

    def label(self) -> str:
        return self.properties.get('label', "")

    def position(self) -> Any:
        return self.map.position_of(self)

    def color(self) -> Optional[str]:
        return self.properties.get('color')

    def armor_class(self) -> Optional[int]:
        return self.properties.get('default_ac')

    def opaque(self, origin=None) -> Optional[bool]:
        return self.properties.get('opaque')

    def half_cover(self) -> Optional[bool]:
        return self.properties.get('cover') == 'half'

    def cover_ac(self) -> int:
        cover = self.properties.get('cover')
        if cover == 'half':
            return 2
        elif cover == 'three_quarter':
            return 5
        else:
            return 0

    def three_quarter_cover(self) -> Optional[bool]:
        return self.properties.get('cover') == 'three_quarter'

    def total_cover(self) -> Optional[bool]:
        return self.properties.get('cover') == 'total'

    def can_hide(self) -> bool:
        return self.properties.get('allow_hide', False)

    def interactable(self):
        if 'ability_check' in self.properties:
            if len(self.properties['ability_check'].items()) > 0:
                return True
        return False

    def swimmable(self) -> bool:
        return self.properties.get('swimmable', False)

    def immune_to_condition(self, condition):
        return True

    def damage_threshold(self) -> int:
        return self.properties.get('damage_threshold', 0)

    def swim_movement_cost(self) -> int:
        if not self.swimmable():
            return self.movement_cost()
        return self.properties.get('movement_cost_swim', self.properties.get('movement_cost', 1))

    def max_hp(self) -> int:
        return self.hp

    def placeable(self) -> bool:
        return self.properties.get('placeable', True)

    def movement_cost(self) -> int:
        return self.properties.get('movement_cost', 1)
    
    def swim_movement_cost(self) -> int:
        return self.properties.get('movement_cost_swim', self.properties.get('movement_cost', 1))

    def token(self) -> Optional[str]:
        return self.properties.get('token')
    
    def token_image(self):
        if self.properties.get('token_image'):
            return f"objects/{self.properties.get('token_image')}"
        return None
    
    def profile_image(self):
        if self.properties.get('profile_image'):
            return self.properties.get('profile_image') + ".png"
        if self.properties.get('token_image'):
            return self.properties.get('token_image') + ".png"
        return self.properties.get('name') + ".png"
        
    
    def token_image_transform(self):
        return None

    def size(self) -> str:
        return self.properties.get('size', 'medium')

    def available_interactions(self, entity, battle=None, admin=False):
        interactions = {}
        if self.inventory:
            interactions['loot'] = {
                "prompt": "Loot"
            }
        if 'ability_checks' in self.properties:
            ability_check_properties = self.properties.get('ability_checks')
            for ability, ability_check_properties in ability_check_properties.items():
                disabled = False
                if entity in self.check_results and f"{ability}_check" in self.check_results[entity]:
                    disabled = True
                interactions[f"{ability}_check"] = {
                    "prompt" : ability_check_properties['prompt'],
                    "disabled": disabled,
                    "disabled_text": "Already checked"
                }
        return interactions

    def investigate_details(self, entity):
        investigate_details = []

        if self.properties.get('ability_checks'):
            for investigation_type, details in self.properties.get('ability_checks').items():
                if self.check_results.get(entity) and self.check_results.get(entity).get(f"{investigation_type}_check"):

                    if self.check_results.get(entity).get(f"{investigation_type}_check") >= details.get('dc'):
                        success_details = details.get('success')
                        if success_details and isinstance(success_details, str):
                            investigate_details.append(success_details)
                        else:
                            investigate_details.append(success_details.get('message'))
                    else:
                        failure_details = details.get('failure')
                        if failure_details and isinstance(failure_details, str):
                            investigate_details.append(failure_details)
                        else:
                            investigate_details.append(failure_details.get('message'))

        return investigate_details

    def resolve(self, entity, action, other_params, opts=None):
        if opts is None:
            opts = {}
        if 'ability_checks' in self.properties:
            for ability, ability_checks in self.properties.get('ability_checks').items():
                if action == f"{ability}_check":
                    if hasattr(self, f"{ability}_check"):
                        check_type_roll = getattr(self, f"{ability}_check")(opts.get('battle'))
                        return {
                            'action': action,
                            'ability': ability,
                            'check_type': "check",
                            'roll': check_type_roll,
                            'dc': ability_checks.get('dc'),
                            'success': check_type_roll.result() >= ability_checks.get('dc')
                        }

        if action in ['loot', 'store']:
            return {
                'action': action,
                'items': other_params,
                'source': entity,
                'target': self,
                'battle': opts.get('battle')
            }
        return None

    def use(self, entity, result, session=None):
        action = result.get('action')
        if action == 'loot':
            self.transfer(result.get('battle'), result.get('source'), result.get('target'), result.get('items'))
            return True
        elif action.endswith('_check'):
            if entity not in self.check_results:
                self.check_results[entity] = {}
            self.check_results[entity][action] = result.get('roll')

            if result.get('success'):
                self.session.event_manager.received_event({
                    "event": f"ability_check",
                    "ability": result.get('ability'),
                    "roll": result.get('roll'),
                    "dc": result.get('dc'),
                    "success": True,
                    "source": entity,
                    "target": self
                })
                self.resolve_trigger(f"{result.get('ability')}_check_success")
            else:
                self.session.event_manager.received_event({
                    "event": f"ability_check",
                    "ability": result.get('ability'),
                    "roll": result.get('roll'),
                    "dc": result.get('dc'),
                    "success": False,
                    "source": entity,
                    "target": self
                })
                self.resolve_trigger(f"{result.get('ability')}_check_failure")
            return True
        return False

    def available_actions(self, session, battle, opportunity_attack=False, map=None, auto_target=True, **opts):
        if opts is None:
            opts = {}

        actions = []
        execpt_interact = opts.get('except_interact', False)

        if execpt_interact:
            return []

        admin_actions = opts.get('admin_actions', False)

        for k, details in self.available_interactions(self, battle, admin = admin_actions).items():
            action = InteractAction(session, self, 'interact')
            action.object_action = [k, details]
            actions.append(action)
        return actions

    def light_properties(self) -> Optional[Dict[str, Any]]:
        return self.properties.get('light', None)

    def jump_required(self) -> Optional[bool]:
        return self.properties.get('jump')

    def passable(self, origin=None) -> Optional[bool]:
        return self.properties.get('passable')

    def wall(self) -> Optional[bool]:
        return self.properties.get('wall')

    def concealed(self) -> bool:
        return self.is_concealed

    def describe_health(self) -> str:
        return ''

    def object(self) -> bool:
        return True

    def npc(self) -> bool:
        return False

    def pc(self) -> bool:
        return False

    def items_label(self) -> str:
        return f"object.{self.__class__.__name__}.item_label"
    
    def setup_other_attributes(self):
        pass

    def build_map(self, action, action_object):
        if action == 'loot':
            def next_action(items):
                action_object.other_params = items
                return action_object
            return {
                'action': action_object,
                'param': [{
                    'type': 'select_items',
                    'label': self.items_label(),
                    'items': self.inventory
                }],
                'next': next_action
            }
        return None
    
    def on_enter(self, entity, map, battle):
        pass

    def update_state(self, state):
        super().update_state(state)
        if state == 'activated':
            self.activated = True
        if state == 'deactivated':
            self.activated = False

    def to_dict(self):
        _inventory = None
        if self.inventory:
            _inventory = [
                {
                    'type': k,
                    'qty': v['qty']
                } for k, v in self.inventory.items()
            ]
        return {
            'session': self.session,
            'entity_uid': self.entity_uid,
            'type': self.type,
            'attributes': self.attributes,
            'ability_scores': self.ability_scores,
            'statuses': list(self.statuses),
            'resistances': self.resistances,
            'is_concealed': self.is_concealed,
            'perception_dc': self.perception_dc,
            'inventory': _inventory,
            'properties': self.properties
        }

    def from_dict(data):
        object =  Object(data['session'], None, data['properties'])
        object.entity_uid = data['entity_uid']
        object.type = data['type']
        object.is_concealed = data['is_concealed']
        return object

class ItemLibrary:
    class AreaTrigger:
        @staticmethod
        def area_trigger_handler(entity: Any, entity_pos: Any, is_flying: bool) -> None:
            pass
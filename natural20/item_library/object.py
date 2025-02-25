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
import uuid
import pdb


class InvalidInteractionAction(Exception):
    def __init__(self, action: str, valid_actions: List[str] = []) -> None:
        self.action = action
        self.valid_actions = valid_actions

    def message(self) -> str:
        return f"Invalid action specified {self.action}. should be in {','.join(self.valid_actions)}"


@dataclass
class Object(Entity):
    def __init__(self, session, map: Any, properties: Dict[str, Any]) -> None:
        Entity.__init__(self, properties.get('name'), properties.get('description', ''), properties)
        self.entity_uid = uuid.uuid4()
        self._name = properties.get('name')
        self._description = properties.get('description', self.name)
        self.map = map
        self.session = session
        self.type = properties.get('type')
        self.concentration = None
        self.effects = {}
        self.inventory = {}
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

        self.statuses = set()
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

    def interactable(self, entity=None) -> bool:
        return False
    
    def max_hp(self) -> int:
        return self.hp

    def placeable(self) -> bool:
        return self.properties.get('placeable', True)

    def movement_cost(self) -> int:
        return self.properties.get('movement_cost', 1)

    def token(self) -> Optional[str]:
        return self.properties.get('token')
    
    def token_image(self):
        return self.properties.get('token_image')
    
    def profile_image(self):
        if self.properties.get('profile_image'):
            return self.properties.get('profile_image') + ".png"
        if self.properties.get('token_image'):
            return self.properties.get('token_image') + ".png"
        return None
    
    def token_image_transform(self):
        return None

    def size(self) -> str:
        return self.properties.get('size', 'medium')

    def available_interactions(self, entity: Any, battle: Any, admin: bool =False) -> List[Any]:
        return {}

    def available_actions(self, session, battle, opportunity_attack=False, map=None, auto_target=True):
        actions = []
        for _interaction in self.available_interactions(self, battle).keys():
            action = InteractAction(session, self, 'interact')
            action.object_action = _interaction
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

    def build_map(self, selected_interaction, action):
        return None
    
    def on_enter(self, entity, map, battle):
        pass

    def update_state(self, state):
        raise NotImplementedError()



class ItemLibrary:
    class AreaTrigger:
        @staticmethod
        def area_trigger_handler(entity: Any, entity_pos: Any, is_flying: bool) -> None:
            pass
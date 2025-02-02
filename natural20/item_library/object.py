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
    def __init__(self, map: Any, properties: Dict[str, Any]) -> None:
        self.entity_uid = uuid.uuid4()
        self.name = properties.get('name')
        self._description = properties.get('description', self.name)
        self.map = map
        self.type = properties.get('type')
        self.concentration = None
        self.effects = {}
        self.inventory = {}
        self._temp_hp = 0
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

        if map:
            self.session = map.session
        self.statuses = set()
        self.properties = properties
        self.resistances = properties.get('resistances', [])
        self.setup_other_attributes()
        if properties.get('hp_die', None):
            self.attributes["hp"] = DieRoll.roll(properties['hp_die']).result()
        else:
            self.attributes["hp"] = properties.get('max_hp', None)

        if properties.get('inventory'):
            self.inventory = {
                inventory['type']: {'qty': inventory['qty']} for inventory in properties['inventory']
            }

        for ability, skills in self.SKILL_AND_ABILITY_MAP.items():
            for skill in skills:
                setattr(self, f"{skill}_mod", self.make_skill_mod_function(skill, ability))
                setattr(self, f"{skill}_check", self.make_skill_check_function(skill))



    def __str__(self) -> str:
        return self.name
    
    def __repr__(self):
        """
        Return the string representation of the object
        """
        return self.name

    def __hash__(self) -> int:
        return id(self)

    def name(self) -> str:
        return self.properties.get('label') or self.name

    def label(self) -> str:
        return self.properties.get('label') or self.name

    def position(self) -> Any:
        return self.map.position_of(self)

    def color(self) -> Optional[str]:
        return self.properties.get('color')

    def armor_class(self) -> Optional[int]:
        return self.properties.get('default_ac')

    def opaque(self) -> Optional[bool]:
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

    def interactable(self) -> bool:
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
        return self.properties.get('token_image') + ".png"
    
    def token_image_transform(self):
        return None

    def size(self) -> str:
        return self.properties.get('size', 'medium')

    def available_interactions(self, entity: Any, battle: Any) -> List[Any]:
        return {}

    def available_actions(self, session, battle, opportunity_attack=False, map=None, auto_target=True):
        actions = []
        for _interaction in self.available_interactions(None, battle).keys():
            action = InteractAction(session, self, 'interact')
            action.object_action = _interaction
            actions.append(action)
        return actions

    def light_properties(self) -> Optional[Dict[str, Any]]:
        return self.properties.get('light', None)

    def jump_required(self) -> Optional[bool]:
        return self.properties.get('jump')

    def passable(self) -> Optional[bool]:
        return self.properties.get('passable')

    def wall(self) -> Optional[bool]:
        return self.properties.get('wall')

    def concealed(self) -> bool:
        return False

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



class ItemLibrary:
    class AreaTrigger:
        @staticmethod
        def area_trigger_handler(entity: Any, entity_pos: Any, is_flying: bool) -> None:
            pass
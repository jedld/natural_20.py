import yaml
import uuid
import os
import random
from natural20.die_roll import DieRoll
from natural20.entity import Entity
from natural20.actions.dodge_action import DodgeAction
from natural20.actions.move_action import MoveAction
from natural20.actions.dash import DashAction, DashBonusAction
from natural20.actions.disengage_action import DisengageAction, DisengageBonusAction
from natural20.actions.stand_action import StandAction
from natural20.actions.attack_action import AttackAction
from natural20.actions.hide_action import HideAction, HideBonusAction
from natural20.actions.help_action import HelpAction
from natural20.actions.grapple_action import GrappleAction
from natural20.actions.escape_grapple_action import EscapeGrappleAction
from natural20.actions.use_item_action import UseItemAction
from natural20.actions.interact_action import InteractAction
from natural20.actions.ground_interact_action import GroundInteractAction
from natural20.actions.multiattack_action import MultiattackAction
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.look_action import LookAction
from natural20.actions.spell_action import SpellAction
from natural20.utils.action_builder import autobuild
from natural20.actions.shove_action import ShoveAction
from natural20.utils.multiattack import Multiattack
from natural20.utils.npc_random_name_generator import generate_goblinoid_name, generate_ogre_name
from natural20.concern.lootable import Lootable
import pdb


import copy

class Npc(Entity, Multiattack, Lootable):
    ACTION_LIST = [
        AttackAction, DashAction, DashBonusAction, DisengageAction,
        DisengageBonusAction, HideAction, HideBonusAction,
        DodgeAction, LookAction, MoveAction,
        StandAction, ShoveAction, HelpAction, UseItemAction, GroundInteractAction,
        SpellAction, InteractAction
    ]

    def __init__(self, session, type, opt=None):
        super().__init__(type, "npc", {})
        if opt is None:
            opt = {}
        if os.path.exists(os.path.join(session.root_path, "npcs", f"{type}.yml")):
            with open(os.path.join(session.root_path, "npcs", f"{type}.yml"), "r") as file:
                self.properties = copy.deepcopy(yaml.safe_load(file))
        else:
            with open(os.path.join("npcs", f"{type}.yml"), "r") as file:
                self.properties = copy.deepcopy(yaml.safe_load(file))

        self.properties.update(opt.get("overrides", {}))

        self.ability_scores = self.properties["ability"]
        self.color = self.properties["color"]
        self.session = session
        self.npc_type = type
        self.group = opt.get("group", "b")
        self.inventory = {}

        default_inventory = self.properties.get("default_inventory", [])
        for inventory in default_inventory:
            self.inventory[inventory["type"]] =  { "qty": inventory["qty"] }

        for inventory in self.properties.get("inventory", []):
            self.inventory[inventory["type"]] = { "qty": inventory["qty"]}

        self.npc_actions = self.properties["actions"]
        self.battle_defaults = self.properties.get("battle_defaults", None)
        self.hidden_stealth = self.properties.get("hidden_stealth", None)
        self.opt = opt
        self.resistances = self.properties.get("resistances", [])
        self.statuses = []
        _conversation_buffer = self.properties.get("conversation_buffer", [])
        for _conversion in _conversation_buffer:
            self.conversation_buffer.append({ 'source': self, 'message': _conversion['message'], 'target': _conversion.get('target','all') })
        self.is_passive = self.properties.get("passive", False)
        self.is_concealed = self.properties.get("concealed", False)
        self.dialogue = self.properties.get("dialogue", [])
        self.condition_immunities = self.properties.get("condition_immunities", [])
        self.damage_vulnerabilities = self.properties.get("damage_vulnerabilities", [])
        if self.properties.get("speed_fly"):
            self.flying = True

        for stat in self.properties.get("statuses", []):
            self.statuses.append(stat)

        auto_name = ""
        if 'goblinoid' in self.properties.get('race',[]):
            auto_name = generate_goblinoid_name()
        elif type == "ogre":
            auto_name = generate_ogre_name()
        else:
            auto_name = type.replace("_", " ").title()

        self.name = auto_name if opt.get("name") == "_auto_" else opt.get("name", auto_name)

        self.entity_uid = self.properties.get('entity_uid', opt.get('entity_uid', str(uuid.uuid4())))
        self.setup_attributes()

    @staticmethod
    def load(session, path, override=None):
        if override is None:
            override = {}

        if not path.endswith(".yml"):
            path = f"{path}.yml"

        with open(os.path.join(session.root_path, path), "r") as file:
            properties = yaml.safe_load(file)

        properties.update(override)

        return Npc(session, properties["kind"].lower(), properties)
    
    def conversable(self):
        languages_known = self.properties.get('languages', [])
        if len(languages_known) > 0:
            return True
        return False

    def class_and_level(self):
        return [(self.npc_type, None)]
    
    def spell_slots_count(self, level, character_class=None):
        if self.familiar():
            return self.owner.spell_slots_count(level, character_class)
        else:
            return 0
    
    def max_spell_slots(self, level, character_class=None):
        if self.familiar():
            return self.owner.max_spell_slots(level, character_class)
        return 0

    def level(self):
        # return CR level I guess
        return self.properties.get("cr", 1)


    def c_class(self):
        return self.properties.get("kind")

    def kind(self):
        return self.properties["kind"]

    def size(self):
        return self.properties["size"]

    def token(self):
        return self.properties["token"]

    def max_hp(self):
        return self._max_hp

    def name(self):
        return self._name

    def set_name(self, value):
        self._name = value

    def npc(self):
        return True

    def armor_class(self):
        return self.properties["default_ac"]

    def set_dialogue(self, dialogue, addressed_to=None):
        self.dialogue.append([addressed_to, dialogue])

    def available_actions(self, session, battle, opportunity_attack=False, map=None, auto_target=True, **opts):
        if opts is None:
            opts = {}

        interact_only = opts.get('interact_only', False)
        except_interact = opts.get('except_interact', False)

        if self.unconscious():
            return ["end"]

        actions = []

        if battle and battle.current_turn() != self and not opportunity_attack:
            if not self.familiar():
                return []
            elif battle and battle.current_turn() == self.owner:
                actions.append(SpellAction(session, self, "spell"))
                return actions

        if opportunity_attack and not self.familiar():
            actions = [s for s in self.generate_npc_attack_actions(battle, opportunity_attack=True, auto_target=auto_target) if s.action_type == "attack" and s.npc_action["type"] == "melee_attack"]
        else:
            if not interact_only and not self.familiar():
                actions.extend(self.generate_npc_attack_actions(battle, auto_target=auto_target))
            for action_class in self.ACTION_LIST:
                if interact_only and action_class != InteractAction:
                    continue
                if except_interact and action_class == InteractAction:
                    continue

                if action_class.can(self, battle):
                    if action_class == MoveAction:
                        if auto_target:
                            actions = actions + autobuild(session, MoveAction, self, battle, map=map)
                        else:
                            actions.append(MoveAction(session, self, "move"))
                    elif action_class == DodgeAction:
                        actions.append(DodgeAction(session, self, "dodge"))
                    elif action_class == DisengageAction:
                        actions.append(DisengageAction(session, self, "disengage"))
                    elif action_class == StandAction:
                        actions.append(StandAction(session, self, "stand"))
                    elif action_class == HelpAction:
                        actions.append(HelpAction(session, self, "help"))
                    elif action_class == HideAction:
                        actions.append(HideAction(session, self, "hide"))
                    elif action_class == DisengageBonusAction:
                        actions.append(DisengageBonusAction(session, self, "disengage_bonus"))
                    elif action_class == DashAction:
                        actions.append(DashAction(session, self, "dash"))
                    elif action_class == DashBonusAction:
                        actions.append(DashBonusAction(session, self, "dash_bonus"))
                    elif action_class == HideBonusAction:
                        actions.append(HideBonusAction(session, self, "hide_bonus"))
                    elif action_class == ShoveAction:
                        if not self.familiar():
                            actions.append(ShoveAction(session, self, "shove"))
                    elif action_class == LookAction:
                        actions.append(LookAction(session, self, "look"))
                    elif action_class == InteractAction:
                        if map:
                            for objects in map.objects_near(self, battle):
                                for interaction, details in objects.available_interactions(self).items():
                                    action = InteractAction(session, self, 'interact', { "target": objects,
                                                                                                "object_action": interaction })
                                    if details.get('disabled'):
                                        action.disabled = True
                                        action.disabled_reason = self.t(details['disabled_text'])
                                    else:
                                        actions.append(action)

        return actions

    def placeable(self):
        if not self.dead():
            return False
        return True

    def melee_distance(self):
        melee_attacks = [a["range"] for a in self.properties["actions"] if a["type"] == "melee_attack"]
        return max(melee_attacks) if melee_attacks else None
    
    def class_feature(self, feature):
        return feature in self.properties.get("attributes", [])
    
    def class_descriptor(self):
        return self.properties.get("kind")

    def any_class_feature(self, features):
        return any(self.class_feature(f) for f in features)

    def available_interactions(self, entity, battle, admin=False):
        return {}

    def proficient_with_equipped_armor(self):
        return True

    def prepared_spells(self):
        return self.properties.get("prepared_spells", [])

    def available_spells(self, battle, touch=False):
        if self.familiar():
            return self.owner.available_spells(battle, touch=True)
        else:
            spell_list = self.spell_list(battle)
            return [k for k, v in spell_list.items() if not v['disabled']]

    def after_death(self):
        # for npcs send them to the object layer when dead
        entity_map = self.session.map_for(self)

        if entity_map:
            move_to_object_layer = not self.familiar()
            entity_map.remove(self, move_to_object_layer=move_to_object_layer)

    def token_image_transform(self):
        if self.dead():
            return "transform: rotate(180deg) scale(0.5); filter: brightness(50%) sepia(100%) hue-rotate(180deg); opacity: 0.5; "
        return None

    def available_spells_per_level(self, battle):
        if self.familiar():
            return self.owner.available_spells_per_level(battle)
        
        spell_list = self.spell_list(battle)
        spell_per_level = [[],[],[],[],[],[],[],[],[]]
        for spell, details in spell_list.items():
            spell_per_level[details['level']].append((spell, details))

        return enumerate(spell_per_level)

    def attack_options(self, battle, opportunity_attack=False):
        actions = []
        for npc_action in self.npc_actions:
            if npc_action.get("ammo") and self.item_count(npc_action["ammo"]) <= 0:
                continue
            if npc_action.get("if") and not self.eval_if(npc_action["if"]):
                continue
            if not AttackAction.can(self, battle, { "npc_action" : npc_action, "opportunity_attack" : opportunity_attack}):
                continue
            actions.append(npc_action)
        return actions

    def generate_npc_attack_actions(self, battle, opportunity_attack=False, auto_target=True):
        if self.familiar():
            return []
        actions = []

        npc_actions = self.attack_options(battle, opportunity_attack=opportunity_attack)
        for npc_action in npc_actions:
            action = AttackAction(self.session, self, "attack")
            action.npc_action = npc_action
            actions.append(action)

        # assign possible attack targets
        if battle and auto_target:
            final_attack_list = []
            for action in actions:
                valid_targets = battle.valid_targets_for(self, action, target_types=["enemies"])
                for target in valid_targets:
                    targeted_action = copy.copy(action)
                    targeted_action.target = target
                    final_attack_list.append(targeted_action)
            return final_attack_list
        else:
            return actions
        

    def setup_attributes(self):
        hp_die_roll = DieRoll.roll(self.properties.get("hp_die", "1d6"))
        if self.opt.get("rand_life"):
            self._max_hp = hp_die_roll.result()
            print(f"Setting up attributes for {self.name} with max hp: {hp_die_roll}={self._max_hp}")
        else:
            self._max_hp = self.properties.get("max_hp", 0)

        self.attributes["hp"] = copy.deepcopy(min(self.properties.get("override_hp", self._max_hp), self._max_hp))
        hp_details = DieRoll.parse(self.properties.get("hp_die", "1d6"))
        self._max_hit_die = {self.npc_type: hp_details.die_count}
        self._current_hit_die = {int(hp_details.die_type): hp_details.die_count}

    def is_npc(self):
        return True

    def to_dict(self):
        base_dict = super().to_dict()
        base_dict['type'] = 'npc'
        base_dict["npc_type"] = self.npc_type
        base_dict["_max_hp"] = self.max_hp()
        base_dict["properties"] = self.properties
        base_dict["attributes"] = self.attributes
        base_dict["inventory"] = self.inventory
        base_dict["statuses"] = self.statuses
        base_dict["entity_uid"] = self.entity_uid
        base_dict["name"] = self.name
        base_dict["session"] = self.session
        base_dict["group"] = self.group
        return base_dict
    
    def from_dict(data):
        npc = Npc(data["session"], data["npc_type"], data)
        npc.properties = data["properties"]
        npc._max_hp = data["_max_hp"]
        npc.attributes = data["attributes"]
        npc.inventory = data["inventory"]
        npc.statuses = data["statuses"]
        npc.entity_uid = data["entity_uid"]
        npc.name = data["name"]
        npc.group = data.get("group", "b")
        return npc
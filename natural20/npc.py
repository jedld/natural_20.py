import yaml
import uuid
from enum import Enum
from collections import namedtuple
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
from natural20.actions.first_aid_action import FirstAidAction
from natural20.actions.look_action import LookAction


import copy

class Npc(Entity):
    def __init__(self, session, type, opt={}):
        super().__init__(type, "npc", {})
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
        self.properties["familiar"] = opt.get("familiar", False)
        self.inventory = {}
        
        default_inventory = self.properties.get("default_inventory", [])
        for inventory in default_inventory:
            self.inventory[inventory["type"]] =  { "qty": inventory["qty"] }
        
        for inventory in self.properties.get("inventory", []):
            self.inventory[inventory["type"]] = { "qty": inventory["qty"]}
        
        self.npc_actions = self.properties["actions"]
        self.battle_defaults = self.properties.get("battle_defaults", None)
        self.opt = opt
        self.resistances = []
        self.statuses = []
        
        for stat in self.properties.get("statuses", []):
            self.statuses.append(stat)
        
        auto_name = ""
        if type == "goblin":
            auto_name = random.choice(["Skritz", "Grib", "Nackle", "Wrick", "Lurtz", "Snub", "Vex", "Jinx", "Znag", "Flix"])
        elif type == "ogre":
            auto_name = random.choice(["Guzar", "Irth", "Grukurg", "Zoduk"])
        else:
            auto_name = type.replace("_", " ").title()
        
        self.name = auto_name if opt.get("name") == "_auto_" else opt.get("name", auto_name)

        self.entity_uid = str(uuid.uuid4())
        self.setup_attributes()
    
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
    
    def name(self, value):
        self._name = value
    
    def npc(self):
        return True
    
    def armor_class(self):
        return self.properties["default_ac"]
    
    def available_actions(self, session, battle, opportunity_attack=False):
        if self.unconscious():
            return ["end"]
        
        actions = []
        
        if opportunity_attack:
            actions = [s for s in self.generate_npc_attack_actions(battle, opportunity_attack=True) if s.action_type == "attack" and s.npc_action["type"] == "melee_attack"]
        else:
            actions = self.generate_npc_attack_actions(battle) + [
                DodgeAction(session, self, "dodge"),
                MoveAction(session, self, "move"),
                LookAction(session, self, "look"),
                DisengageAction(session, self, "disengage"),
                DisengageBonusAction(session, self, "disengage_bonus"),
                StandAction(session, self, "stand"),
                HideAction(session, self, "hide"),
                HideBonusAction(session, self, "hide_bonus"),
                DashAction(session, self, "dash"),
                DashBonusAction(session, self, "dash_bonus"),
                HelpAction(session, self, "help"),
                GrappleAction(session, self, "grapple"),
                EscapeGrappleAction(session, self, "escape_grapple"),
                UseItemAction(session, self, "use_item"),
                InteractAction(session, self, "interact"),
                GroundInteractAction(session, self, "ground_interact"),
                FirstAidAction(session, self, "first_aid")
            ]
        
        return actions
    
    def melee_distance(self):
        melee_attacks = [a["range"] for a in self.properties["actions"] if a["type"] == "melee_attack"]
        return max(melee_attacks) if melee_attacks else None
    
    def class_feature(self, feature):
        return feature in self.properties.get("attributes", [])
    
    def available_interactions(self, entity, battle):
        return []
    
    def proficient_with_equipped_armor(self):
        return True
    
    def prepared_spells(self):
        return self.properties.get("prepared_spells", [])
    
    def generate_npc_attack_actions(self, battle, opportunity_attack=False):
        if self.familiar():
            return []
        
        actions = []
        
        for npc_action in self.npc_actions:
            if npc_action.get("ammo") and self.item_count(npc_action["ammo"]) <= 0:
                continue
            if npc_action.get("if") and not self.eval_if(npc_action["if"]):
                continue
            if not AttackAction.can(self, battle, { "npc_action" : npc_action, "opportunity_attack" : opportunity_attack}):
                continue
            
            action = AttackAction(self.session, self, "attack")
            action.npc_action = npc_action
            actions.append(action)
        
        return actions
    
    def setup_attributes(self):
        self._max_hp = DieRoll.roll(self.properties.get("hp_die", "1d6")).result() if self.opt.get("rand_life") else self.properties.get("max_hp", 0)
        self.attributes["hp"] = copy.deepcopy(min(self.properties.get("override_hp", self._max_hp), self._max_hp))
        hp_details = DieRoll.parse(self.properties.get("hp_die", "1d6"))
        self._max_hit_die = {self.npc_type: hp_details.die_count}
        self._current_hit_die = {int(hp_details.die_type): hp_details.die_count}

    def is_npc(self):
        return True
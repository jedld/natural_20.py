from natural20.entity import Entity
from natural20.actions.move_action import MoveAction
from natural20.actions.attack_action import LinkedAttackAction
from natural20.session import Session
import uuid
import pdb


class SpiritualWeapon(Entity):
    def __init__(self, session: Session, owner: Entity, name, description, attributes, **kwargs):
        super().__init__(name, description, attributes)
        self.session = session
        self.owner = owner
        self.damage = kwargs.get('damage', '1d8')
        self.group = owner.group
        
        self.properties = {
            'spiritual': True,
            'speed': 20,
            'speed_fly': 20,
            'name' : f"{owner.name}'s Spiritual Weapon",
            'description': f"A floating, spectral weapon created by {owner.label()}'s spell",
        }
        spell = kwargs.get('spell', {})
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['cleric']

        attack_modifiers = [self.owner.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]

        spiritual_weapon_actions = [{
            "name": 'spiritual_weapon',
            "type": "melee_attack",
            "range": 5,
            "targets": 1,
            "attack": max(attack_modifiers),
            "damage": 5,
            "damage_die": self.damage,
            "damage_type": "force"
        }]

        self.properties['actions'] = spiritual_weapon_actions
        self.npc_actions = spiritual_weapon_actions
        self.entity_uid = str(uuid.uuid4())
        self.flying = True

    def size(self):
        return 'medium'

    def label(self):
        return self.properties['name']

    def hp(self):
        return None
    
    def max_hp(self):
        return None

    def npc(self):
        return True

    def token(self):
        return ["⚔"]
    
    def token_image(self):
        return 'token_spiritual_weapon.png'

    def placeable(self):
        return False

    def passable(self, origin=None):
        return True

    def opaque(self, origin=None):
        return False

    def reset_turn(self, battle):
        battle.entities[self] = {
                'movement': 20,
                'action': 0,
                'bonus_action': 0,
                'reaction': 0,
                'free_object_interaction': 0,
                'active_perception': 0,
                'active_perception_disadvantage': 0,
                'two_weapon': None,
                'action_surge': None,
                'casted_level_spells': [],
                'positions_entered': {},
                'group': self.group
            }

    def attack_options(self, battle, opportunity_attack=False):
        actions = []
        if opportunity_attack:
            return []

        for npc_action in self.npc_actions:
            if not LinkedAttackAction.can(self, battle,  options={ "npc_action" : npc_action, "as_bonus_action" : True}):
                continue

            actions.append(npc_action)
        return actions

    def available_actions(self, session, battle, opportunity_attack=False, map=None, auto_target=True, **opts):
        if opts is None:
            opts = {}

        actions = []

        if opportunity_attack:
            return []
        interact_only = opts.get('interact_only', False)

        if interact_only:
            return []

        if battle:
            if battle.current_turn() == self.owner:
                actions.append(MoveAction(session, self, 'move'))
                if LinkedAttackAction.can(self, battle, options={ "npc_action" : self.npc_actions[0], "as_bonus_action" : True}):
                    attack = LinkedAttackAction(session, self, 'attack')
                    attack.npc_action = self.npc_actions[0]
                    attack.as_bonus_action = True
                    actions.append(attack)
                return actions
        else:
            actions.append(MoveAction(session, self, 'move'))
            attack = LinkedAttackAction(session, self, 'attack')
            attack.npc_action = self.npc_actions[0]
            attack.as_bonus_action = True
            actions.append(attack)
            return actions
        return []
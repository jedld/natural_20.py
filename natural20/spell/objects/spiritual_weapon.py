from natural20.entity import Entity
from natural20.actions.move_action import MoveAction
from natural20.actions.attack_action import AttackAction
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
            'speed': 20,
            'speed_fly': 20,
            'name' : f"{owner.name}'s Spiritual Weapon",
            'description': f"A floating, spectral weapon created by {owner.label()}'s spell"
        }
        spell = kwargs.get('spell', {})
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['cleric']

        attack_modifiers = [self.owner.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]

        self.npc_action = {
            "name": 'Spiritual Weapon',
            "type": "melee_attack",
            "range": 5,
            "targets": 1,
            "attack": max(attack_modifiers),
            "damage": 5,
            "damage_die": self.damage,
            "damage_type": "force"
        }
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


    def available_actions(self, session, battle, opportunity_attack=False, map=None, auto_target=True):
        actions = []

        if opportunity_attack:
            return []

        if battle:
            if battle.current_turn() == self.owner:
                actions.append(MoveAction(session, self, 'move'))
                attack = LinkedAttackAction(session, self, 'attack')
                attack.npc_action = self.npc_action
                attack.as_bonus_action = True
                actions.append(attack)
                return actions
        else:
            actions.append(MoveAction(session, self, 'move'))
            attack = LinkedAttackAction(session, self, 'attack')
            attack.npc_action = self.npc_action
            attack.as_bonus_action = True
            actions.append(attack)
            return actions
        return []
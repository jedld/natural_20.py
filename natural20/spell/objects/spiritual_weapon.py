from natural20.entity import Entity
from natural20.actions.move_action import MoveAction
from natural20.actions.attack_action import AttackAction

class SpiritualWeapon(Entity):
    def __init__(self, owner, name, description, attributes, **kwargs):
        super().__init__(name, description, attributes)
        self.owner = owner
        self.damage = kwargs.get('damage', '1d8')
        self.group = owner.group
        self.properties({
            'speed': 20
        })
        spell = kwargs.get('spell', {})
        spell_classes = spell.get('spell_list_classes', [])
        class_types = spell_classes if spell_classes else ['wizard']
        attack_modifers = [self.spell_attack_modifier(class_type=class_type.lower()) for class_type in class_types]
        self.npc_action = {
            "name": 'Spiritual Weapon',
            "type": "melee_attack",
            "range": 5,
            "targets": 1,
            "attack": max(attack_modifers),
            "damage": 5,
            "damage_die": self.damage,
            "damage_type": "force"
        }

    def npc(self):
        return True

    def token(self):
        return ["⚔"]

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
                attack = AttackAction(session, self, 'attack')
                attack.npc_action = self.npc_action
                attack.as_bonus_action = True
                actions.append(attack)
                return actions
        return []
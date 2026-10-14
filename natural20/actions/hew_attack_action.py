"""Great Weapon Master bonus attack (2024 "Hew" / 2014 crit-or-kill attack).

Offered after ``note_hew_trigger`` marks ``hew_pending`` with the weapon used
for the triggering melee critical hit or kill this turn.
"""

from natural20.actions.attack_action import AttackAction


class HewAttackAction(AttackAction):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.as_bonus_action = True
        self.is_hew = True

    def second_hand(self):
        return False

    def label(self):
        return f"Bonus Action -> {super().label()} (Great Weapon Master)"

    def __repr__(self):
        return f"HewAttack({self.using})"

    def __str__(self):
        return "HewAttack"

    @staticmethod
    def pending_weapon(entity, battle):
        if battle is None:
            return None
        state = battle.entity_state_for(entity)
        return state.get('hew_pending') if state else None

    @staticmethod
    def can(entity, battle, options=None):
        if battle is None:
            return False
        if entity.total_bonus_actions(battle) <= 0:
            return False
        weapon = HewAttackAction.pending_weapon(entity, battle)
        return bool(weapon) and weapon in (entity.properties.get('equipped') or [])

    def build_map(self):
        if not self.using:
            self.using = getattr(self.source, '_hew_pending_weapon', None)
        weapon = self.using

        def set_target(target):
            cloned = self.clone()
            cloned.target = target
            return cloned

        weapon_details = self.session.load_weapon(weapon) if weapon else {}
        reach = (weapon_details or {}).get('range', 5)
        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': 1,
                'weapon': weapon,
                'range': reach,
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    def clone(self):
        action = HewAttackAction(self.session, self.source, self.action_type, self.opts)
        action.using = self.using
        action.target = self.target
        action.knock_unconscious = bool(self.knock_unconscious)
        action.advantage_mod = self.advantage_mod
        action.attack_roll = self.attack_roll
        return action

"""Bonus-action unarmed strike granted by the monk's Martial Arts feature.

Available after the monk takes the Attack action on this turn while wielding
only monk weapons or making an unarmed strike (PHB/SRD 2014).
"""

from natural20.actions.attack_action import AttackAction


class MartialArtsBonusAttackAction(AttackAction):
    """A bonus-action unarmed strike triggered by Martial Arts."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.using = 'unarmed_attack'
        self.as_bonus_action = True

    def second_hand(self):
        # Reuses bonus-action consumption hook in AttackAction.consume_resource
        # without applying the off-hand modifier penalty (handled separately).
        return False

    def label(self):
        base = super().label()
        return f"Bonus Action -> {base} (Martial Arts)"

    def __repr__(self):
        return "MartialArtsBonusAttack(unarmed_attack)"

    def __str__(self):
        return "MartialArtsBonusAttack"

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('martial_arts'):
            return False
        if entity.total_bonus_actions(battle) <= 0:
            return False
        state = battle.entity_state_for(entity)
        if not state:
            return False
        return bool(state.get('martial_arts_pending'))

    def build_map(self):
        # Pre-fill the weapon to be unarmed strike; only target is left to pick.
        def set_target(target):
            cloned = self.clone()
            cloned.target = target
            return cloned

        return {
            'action': self,
            'param': [
                {
                    'type': 'select_target',
                    'num': 1,
                    'weapon': 'unarmed_attack',
                    'target_types': ['enemies'],
                }
            ],
            'next': set_target,
        }

    def clone(self):
        action = MartialArtsBonusAttackAction(self.session, self.source, self.action_type, self.opts)
        action.using = self.using
        action.target = self.target
        action.as_bonus_action = True
        action.advantage_mod = self.advantage_mod
        action.attack_roll = self.attack_roll
        return action

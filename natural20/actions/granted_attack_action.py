"""A free weapon attack granted by another feature (e.g. an attack option's
``follow_up_attack``).

``grant_attack`` records the pending attack in the battle state; the attack
costs no action, uses the recorded weapon, and may only target the recorded
candidates. Unused grants lapse at the end of the turn.
"""

from natural20.actions.attack_action import AttackAction
from natural20.utils.class_feature_registry import register_class_feature

STATE_KEY = 'granted_attack'


def grant_attack(battle, entity, weapon, candidates, label=None):
    state = battle.entity_state_for(entity) if battle is not None else None
    if state is None or not weapon or not candidates:
        return False
    state[STATE_KEY] = {
        'weapon': weapon,
        'candidates': [c.entity_uid for c in candidates],
        'label': label,
    }
    return True


def pending_grant(entity, battle):
    if battle is None:
        return None
    state = battle.entity_state_for(entity)
    return state.get(STATE_KEY) if state else None


class GrantedAttackAction(AttackAction):
    def __init__(self, session, source, action_type='granted_attack', opts=None):
        super().__init__(session, source, action_type, opts)
        self.is_granted = True
        self.battle = None

    def second_hand(self):
        return False

    def _grant(self, battle=None):
        return pending_grant(self.source, battle or self.battle)

    def label(self):
        grant = self._grant() or {}
        return f"{grant.get('label') or 'Granted Attack'} -> {super().label()}"

    def __repr__(self):
        return f"GrantedAttack({self.using})"

    def __str__(self):
        return "GrantedAttack"

    def available(self, battle=None):
        grant = pending_grant(self.source, battle)
        if not grant or grant.get('weapon') not in (self.source.properties.get('equipped') or []):
            return False
        current = battle.current_turn() if callable(getattr(battle, 'current_turn', None)) else None
        if current is not None and current is not self.source:
            return False
        self.battle = battle
        self.using = grant.get('weapon')
        return True

    @staticmethod
    def build_all(session, entity, feature_id='granted_attack'):
        return [GrantedAttackAction(session, entity, 'attack')]

    def candidates(self, battle):
        grant = pending_grant(self.source, battle) or {}
        uids = set(grant.get('candidates') or [])
        if battle is None:
            return []
        return [e for e in battle.entities.keys() if e.entity_uid in uids and not e.dead()]

    def validate(self, battle_map=None, target=None, battle=None):
        super().validate(battle_map, target=target, battle=battle)
        target = target if target is not None else self.target
        if target is None or battle is None:
            return
        if target not in self.candidates(battle):
            self.add_validation_issue('validation.targeting.unavailable')

    def build_map(self):
        battle = self.battle
        grant = pending_grant(self.source, battle) or {}
        if not self.using:
            self.using = grant.get('weapon')
        weapon_details = self.session.load_weapon(self.using) if self.using else {}

        def set_target(target):
            cloned = self.clone()
            cloned.target = target
            return cloned

        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': 1,
                'weapon': self.using,
                'range': (weapon_details or {}).get('range_max') or (weapon_details or {}).get('range', 5),
                'target_types': ['enemies'],
                'candidates': self.candidates(battle),
            }],
            'next': set_target,
        }

    def resolve(self, session, map=None, opts=None):
        battle = (opts or {}).get('battle') or self.battle
        if not pending_grant(self.source, battle):
            self.result = []
            return self
        if self.target is not None and battle is not None and self.target not in self.candidates(battle):
            self.result = []
            return self
        super().resolve(session, map, opts)
        for item in self.result or []:
            if isinstance(item, dict):
                item['_free_attack'] = True
                item['_granted_attack'] = True
        return self

    def clone(self):
        action = GrantedAttackAction(self.session, self.source, self.action_type, self.opts)
        action.using = self.using
        action.target = self.target
        action.knock_unconscious = bool(self.knock_unconscious)
        action.advantage_mod = self.advantage_mod
        action.attack_roll = self.attack_roll
        action.battle = self.battle
        return action


register_class_feature(
    feature_id='granted_attack',
    action_class=GrantedAttackAction,
    provides=lambda entity: True,
    builder=GrantedAttackAction.build_all,
)

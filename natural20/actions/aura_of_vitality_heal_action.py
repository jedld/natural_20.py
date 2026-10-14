from natural20.action import Action
from natural20.spell.aura_of_vitality_spell import (
    AuraOfVitalityEffect,
    aura_heal_item,
    aura_turn_key,
)


class AuraOfVitalityHealAction(Action):
    """Bonus action: one creature in an active Aura of Vitality regains 2d6 HP."""

    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def clone(self):
        action = AuraOfVitalityHealAction(self.session, self.source, self.action_type, self.opts)
        action.target = self.target
        return action

    def name(self):
        return 'Aura of Vitality'

    def label(self):
        return 'Aura of Vitality: Heal'

    @staticmethod
    def active_aura(caster):
        aura = getattr(caster, 'concentration', None)
        return aura if isinstance(aura, AuraOfVitalityEffect) else None

    @staticmethod
    def can(entity, battle, options=None):
        if battle is None or not entity.has_bonus_action(battle):
            return False
        aura = AuraOfVitalityHealAction.active_aura(entity)
        if aura is None:
            return False
        return list(aura.last_pulse_turn or []) != aura_turn_key(battle)

    @staticmethod
    def build(session, source):
        return AuraOfVitalityHealAction(session, source, 'aura_of_vitality_heal').build_map()

    def build_map(self):
        aura = AuraOfVitalityHealAction.active_aura(self.source)

        def set_target(target):
            action = self.clone()
            action.target = target
            return action

        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': aura.radius_ft() if aura else 30,
                'auto_pick': 'most_wounded',
                'target_types': ['allies', 'self'],
            }],
            'next': set_target,
        }

    def validate(self, battle_map, target=None):
        self.errors = []
        target = target if target is not None else self.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else None
        aura = AuraOfVitalityHealAction.active_aura(self.source)
        if aura is None:
            self.errors.append('You are not concentrating on Aura of Vitality.')
            return
        if target is None or not hasattr(target, 'heal'):
            self.errors.append('Choose a creature in the aura.')
            return
        if battle_map is not None and target is not self.source:
            distance = battle_map.distance(self.source, target) * battle_map.feet_per_grid
            if distance > aura.radius_ft():
                self.errors.append('That creature is not in the aura.')

    def avg_damage(self, battle, opts=None):
        return -7

    def compute_hit_probability(self, battle, opts=None):
        return 1.0

    def resolve(self, session, map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        self.result = []
        aura = AuraOfVitalityHealAction.active_aura(self.source)
        target = self.target
        if isinstance(target, (list, tuple)):
            target = target[0] if target else None
        if aura is None or target is None:
            return self
        self.result.append(aura_heal_item(self.source, target, aura, battle))
        self.result.append({
            'type': 'aura_of_vitality_pulse',
            'source': self.source,
            'target': target,
            'aura': aura,
        })
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'aura_of_vitality_pulse':
            return
        if battle and session is None:
            session = battle.session
        source = item['source']
        aura = item.get('aura')
        if battle is not None:
            battle.consume(source, 'bonus_action')
            if aura is not None:
                aura.last_pulse_turn = aura_turn_key(battle)
        if session is not None:
            session.event_manager.received_event({
                'event': 'aura_of_vitality_pulse',
                'source': source,
                'target': item.get('target'),
            })

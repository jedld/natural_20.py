"""Bard - Bardic Inspiration (D&D 5e SRD 2014).

As a bonus action, the bard chooses one creature other than themselves
within 60 feet who can hear them.  That creature gains one Bardic
Inspiration die which can be rolled and added to one ability check,
attack roll, or saving throw made within the next 10 minutes.
"""

from natural20.action import Action
from natural20.effects.bardic_inspiration_effect import (
    BARDIC_INSPIRATION_DURATION_SECONDS,
    BardicInspirationEffect,
    remove_bardic_inspiration_die,
)
from natural20.utils.target_validation import (
    evaluate_bardic_inspiration_target,
    has_validation_failures,
    resolve_battle_for_validation,
)


class BardicInspirationAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    def label(self):
        die = getattr(self.source, 'bardic_inspiration_die', lambda: '1d6')()
        return f'Bardic Inspiration ({die})'

    def __repr__(self):
        return 'BardicInspiration'

    @staticmethod
    def evaluate_target(entity, target, battle):
        return evaluate_bardic_inspiration_target(entity, target, battle)

    @staticmethod
    def _can_target(entity, target, battle):
        return not evaluate_bardic_inspiration_target(entity, target, battle)

    @staticmethod
    def can(entity, battle, options=None):
        if not getattr(entity, 'class_feature', None):
            return False
        if not entity.class_feature('bardic_inspiration'):
            return False
        if not getattr(entity, 'has_bardic_inspiration', None):
            return False
        if not entity.has_bardic_inspiration(1):
            return False
        if battle is None:
            return True
        return entity.total_bonus_actions(battle) > 0

    def build_map(self):
        def set_target(target):
            self.target = target
            return self

        return {
            "action": self,
            "param": [
                {
                    "type": "select_target",
                    "range": 60,
                    "target_types": ["allies"],
                    "num": 1,
                }
            ],
            "next": set_target,
        }

    def validate(self, battle_map, target=None, battle=None):
        self.clear_validation_errors()
        chosen = target if target is not None else self.target
        battle = resolve_battle_for_validation(battle_map, self.source, battle)
        self.extend_validation_issues(
            self.evaluate_target(self.source, chosen, battle),
        )
        return not has_validation_failures(self)

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        if not self._can_target(self.source, self.target, battle):
            self.result = []
            return self
        die = getattr(self.source, 'bardic_inspiration_die', lambda: '1d6')()
        self.result = [{
            'type': 'bardic_inspiration',
            'source': self.source,
            'target': self.target,
            'die': die,
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'bardic_inspiration':
            return
        if session is None:
            session = battle.session if battle else None
        source = item['source']
        target = item.get('target')

        if hasattr(source, 'consume_bardic_inspiration'):
            source.consume_bardic_inspiration(1)
        if battle:
            battle.consume(source, 'bonus_action')

        if target is not None:
            # Only one inspiration die at a time on a creature.
            remove_bardic_inspiration_die(target)
            effect = BardicInspirationEffect(source, target, item.get('die', '1d6'))
            expiration = None
            if session is not None:
                expiration = session.game_time + BARDIC_INSPIRATION_DURATION_SECONDS
            target.add_casted_effect({
                'effect': effect,
                'source': source,
                'die': effect.die,
                'expiration': expiration,
            })

        if session:
            session.event_manager.received_event({
                'source': source,
                'target': target,
                'event': 'bardic_inspiration',
                'die': item.get('die', '1d6'),
            })

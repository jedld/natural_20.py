"""Monk Ki feature - Flurry of Blows.

Spend 1 ki point as a bonus action immediately after taking the Attack
action to make two unarmed strikes (D&D 5e SRD).

Implemented as an action that schedules two free unarmed strikes against a
single target picked when Flurry of Blows is committed. The strikes are
resolved immediately as part of `apply` so they appear together in the
combat log alongside the bonus-action expenditure.
"""

from natural20.action import Action
from natural20.actions.attack_action import AttackAction


class FlurryOfBlowsAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.second_target = None

    def label(self):
        return 'Flurry of Blows (1 ki)'

    def __repr__(self):
        return 'FlurryOfBlows'

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('flurry_of_blows'):
            return False
        if not getattr(entity, 'has_ki', None) or not entity.has_ki(1):
            return False
        if entity.total_bonus_actions(battle) <= 0:
            return False
        state = battle.entity_state_for(entity)
        if not state or not state.get('martial_arts_pending'):
            return False
        return True

    def build_map(self):
        def set_target(target):
            cloned = FlurryOfBlowsAction(self.session, self.source, self.action_type, self.opts)
            cloned.target = target
            cloned.second_target = target
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

    def resolve(self, session, _map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')

        # Mark as a "bookkeeping" payload; consume bonus action + ki happens in apply.
        results = [{
            'type': 'flurry_of_blows',
            'source': self.source,
            'target': self.target,
            'battle': battle,
        }]

        for target in (self.target, self.second_target):
            if target is None:
                continue
            attack = AttackAction(self.session, self.source, 'attack')
            attack.using = 'unarmed_attack'
            attack.target = target
            # These strikes are free attacks granted by the feature - mark
            # them so they don't consume the action / bonus action slot when
            # AttackAction.consume_resource runs.
            attack.as_bonus_action = False
            attack.as_reaction = False
            attack._free_attack = True  # flag respected below in apply
            attack.resolve(session, _map, {'battle': battle})
            for item in attack.result:
                if isinstance(item, dict):
                    item['_free_attack'] = True
                results.append(item)

        self.result = results
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if session is None:
            session = battle.session if battle else None

        if item.get('type') != 'flurry_of_blows':
            return

        source = item['source']
        if battle:
            battle.consume(source, 'bonus_action')
            state = battle.entity_state_for(source)
            if state:
                state['martial_arts_pending'] = False
        if hasattr(source, 'consume_ki'):
            source.consume_ki(1)
        if session:
            session.event_manager.received_event({
                'source': source,
                'target': item.get('target'),
                'event': 'flurry_of_blows',
            })

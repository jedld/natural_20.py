"""Monk Ki feature - Step of the Wind.

Spend 1 ki point to take the Disengage or Dash action as a bonus action;
jump distance is doubled for the turn (D&D 5e SRD).

This action exposes two flavors selectable via `opts['mode']` ('disengage'
or 'dash'). When constructed without an explicit mode, it defaults to
'disengage' which is the more commonly-used variant in tactical play.
"""

from natural20.action import Action


class StepOfTheWindAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.mode = (opts or {}).get('mode', 'disengage')

    def label(self):
        if self.mode == 'dash':
            return 'Step of the Wind (1 ki, Dash)'
        return 'Step of the Wind (1 ki, Disengage)'

    def __repr__(self):
        return f'StepOfTheWind({self.mode})'

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('step_of_the_wind'):
            return False
        if not getattr(entity, 'has_ki', None) or not entity.has_ki(1):
            return False
        return entity.total_bonus_actions(battle) > 0

    def build_map(self):
        return self

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        self.result = [{
            'type': 'step_of_the_wind',
            'mode': self.mode,
            'source': self.source,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'step_of_the_wind':
            return
        if session is None:
            session = battle.session if battle else None
        source = item['source']
        if hasattr(source, 'consume_ki'):
            source.consume_ki(1)
        if battle:
            battle.consume(source, 'bonus_action')
            mode = item.get('mode', 'disengage')
            if mode == 'dash':
                state = battle.entity_state_for(source)
                if state:
                    state['movement'] = state.get('movement', 0) + source.speed()
            else:
                source.do_disengage(battle)
        if session:
            session.event_manager.received_event({
                'source': source,
                'mode': item.get('mode', 'disengage'),
                'event': 'step_of_the_wind',
            })

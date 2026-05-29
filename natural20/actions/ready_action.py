"""Ready / Hold action.

Spending your action on your turn to declare a *trigger* and a *prepared
action*. When the trigger fires (during a different creature's turn) you
spend your reaction to take the prepared action.

The trigger and prepared action are JSON-friendly dicts; the webapp's LLM
adjudicator fills them in (see ``natural20.ready_action.normalize_trigger``
and ``normalize_action_spec``). Tests can pass them in directly via
``opts``.
"""

from natural20.action import Action
from natural20.ready_action import (
    ReadyActionState,
    normalize_trigger,
    normalize_action_spec,
    prepare_held_spell,
)


class ReadyAction(Action):
    def __init__(self, session, source, action_type='ready', opts=None):
        super().__init__(session, source, action_type, opts)
        opts = opts or {}
        self.description = str(opts.get('description') or '').strip()
        self.trigger = normalize_trigger(opts.get('trigger'))
        self.action_spec = normalize_action_spec(opts.get('action_spec'))
        self.concentration_required = bool(opts.get('concentration_required', False))

    def __repr__(self):
        desc = self.description or self.trigger.get('description', '') or 'a trigger'
        return f"ready ({desc})"

    def label(self):
        return 'Ready an Action'

    def button_image(self):
        return 'ready'

    @staticmethod
    def can(entity, battle):
        if not battle:
            return False
        if entity.total_actions(battle) <= 0:
            return False
        # Don't let a creature stack readied actions; it must consume the
        # current one (or wait for it to expire) first.
        if getattr(battle, 'ready_action_for', None) and battle.ready_action_for(entity):
            return False
        # Need a reaction available to actually pay for the trigger later.
        if not entity.has_reaction(battle):
            return False
        return True

    def build_map(self):
        return {
            'param': [
                {
                    'type': 'select_ready_action',
                    'description': 'Describe the trigger and the action you are readying.',
                },
            ],
            'next': lambda opts: self._with_opts(opts),
        }

    def _with_opts(self, opts):
        if isinstance(opts, dict):
            self.description = str(opts.get('description') or self.description)
            if 'trigger' in opts:
                self.trigger = normalize_trigger(opts.get('trigger'))
            if 'action_spec' in opts:
                self.action_spec = normalize_action_spec(opts.get('action_spec'))
            if 'concentration_required' in opts:
                self.concentration_required = bool(opts.get('concentration_required'))
        return self

    @staticmethod
    def build(session, source):
        action = ReadyAction(session, source, 'ready')
        return action.build_map()

    def resolve(self, session, _map, opts=None):
        opts = opts or {}
        battle = opts.get('battle')
        self.result = [{
            'source': self.source,
            'type': 'ready_action',
            'description': self.description,
            'trigger': self.trigger,
            'action_spec': self.action_spec,
            'concentration_required': self.concentration_required,
            'battle': battle,
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if not isinstance(item, dict) or item.get('type') != 'ready_action':
            return
        source = item.get('source')
        if source is None or battle is None:
            return
        action_spec = dict(item.get('action_spec') or {})
        concentration_required = bool(item.get('concentration_required', False))
        # Per RAW, readying a spell pays the slot up-front and starts
        # concentration on the held magic. Validate + commit those costs
        # before registering the readied state. If validation fails (wrong
        # casting time, no slot, etc.) we abort the ready action entirely:
        # the action is not consumed and the readier can choose another.
        if (action_spec.get('kind') or '').lower() == 'spell':
            effect, error = prepare_held_spell(battle, source, action_spec)
            if error is not None:
                try:
                    battle.session.event_manager.received_event({
                        'source': source,
                        'event': 'ready_action_invalid',
                        'reason': error,
                        'description': str(item.get('description') or ''),
                        'action_spec': action_spec,
                    })
                except Exception:
                    pass
                return
            # ``prepare_held_spell`` mutates the spec to mark slot as paid
            # and (possibly) refines at_level / casting class. Always treat
            # held-spell ready actions as concentration-required so a broken
            # concentration expires the readied state.
            concentration_required = True
        state = ReadyActionState(
            entity_uid=str(getattr(source, 'entity_uid', '')),
            description=str(item.get('description') or ''),
            trigger=dict(item.get('trigger') or {}),
            action_spec=action_spec,
            declared_round=int(getattr(battle, 'round', 0) or 0),
            concentration_required=concentration_required,
        )
        battle.register_ready_action(source, state)
        battle.consume(source, 'action')
        try:
            battle.session.event_manager.received_event({
                'source': source,
                'event': 'ready_action_declared',
                'description': state.description,
                'trigger': dict(state.trigger),
                'action_spec': dict(state.action_spec),
            })
        except Exception:
            pass

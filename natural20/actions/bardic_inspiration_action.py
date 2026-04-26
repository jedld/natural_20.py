"""Bard - Bardic Inspiration (D&D 5e SRD 2014).

As a bonus action, the bard chooses one creature other than themselves
within 60 feet who can hear them.  That creature gains one Bardic
Inspiration die (currently 1d6 at levels 1-4) which can be rolled and
added to one ability check, attack roll, or saving throw made within the
next 10 minutes.

This implementation tracks the bookkeeping (uses, target acquisition, and
applying an effect on the recipient).  Recipient-side dice consumption
is left to higher-level UX integrations.
"""

from natural20.action import Action


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

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        die = getattr(self.source, 'bardic_inspiration_die', lambda: '1d6')()
        self.result = [{
            'type': 'bardic_inspiration',
            'source': self.source,
            'target': self.target,
            'die': die,
            'battle': opts.get('battle'),
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

        # Stamp an effect on the target so they (or downstream UI) know they
        # carry a Bardic Inspiration die.  Duration is 10 minutes per SRD.
        if target is not None and hasattr(target, 'casted_effects'):
            target.casted_effects.append({
                'effect': 'bardic_inspiration',
                'source': source,
                'die': item.get('die', '1d6'),
                'duration': 100,  # 100 rounds = 10 minutes
            })

        if session:
            session.event_manager.received_event({
                'source': source,
                'target': target,
                'event': 'bardic_inspiration',
                'die': item.get('die', '1d6'),
            })

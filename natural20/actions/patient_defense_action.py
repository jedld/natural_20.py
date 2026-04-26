"""Monk Ki feature - Patient Defense.

Spend 1 ki point to take the Dodge action as a bonus action (D&D 5e SRD).
"""

from natural20.action import Action


class PatientDefenseAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)

    def label(self):
        return 'Patient Defense (1 ki, Dodge)'

    def __repr__(self):
        return 'PatientDefense'

    @staticmethod
    def can(entity, battle, options=None):
        if not battle:
            return False
        if not getattr(entity, 'class_feature', None) or not entity.class_feature('patient_defense'):
            return False
        if not getattr(entity, 'has_ki', None) or not entity.has_ki(1):
            return False
        return entity.total_bonus_actions(battle) > 0

    def build_map(self):
        return self

    def resolve(self, _session, _map, opts=None):
        opts = opts or {}
        self.result = [{
            'type': 'patient_defense',
            'source': self.source,
            'battle': opts.get('battle'),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'patient_defense':
            return
        if session is None:
            session = battle.session if battle else None
        source = item['source']
        if hasattr(source, 'consume_ki'):
            source.consume_ki(1)
        if battle:
            battle.consume(source, 'bonus_action')
            source.do_dodge(battle)
        if session:
            session.event_manager.received_event({
                'source': source, 'event': 'patient_defense'
            })
            session.event_manager.received_event({
                'source': source, 'event': 'dodge'
            })

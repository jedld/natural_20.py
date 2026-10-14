"""Abjure Foes (Paladin 9, SRD 5.2).

Magic action, one Channel Divinity use: up to CHA modifier (minimum 1)
creatures the paladin can see within 60 feet make a Wisdom save against the
paladin's spell save DC. On a failure a creature is Frightened of the paladin
for 1 minute or until it takes damage, and while frightened it can only move,
take an action, or take a bonus action on its turns (one of the three).
"""

from natural20.action import Action
from natural20.utils.class_feature_registry import register_class_feature
from natural20.utils.fear import apply_fear

ABJURE_FOES_RANGE = 60


class AbjureFoesAction(Action):
    def __init__(self, session, source, action_type, opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None

    @staticmethod
    def can(entity, battle):
        if not entity.class_feature('abjure_foes'):
            return False
        if not getattr(entity, 'has_channel_divinity', None) or not entity.has_channel_divinity():
            return False
        if battle is None:
            return True
        state = battle.entity_state_for(entity)
        return bool(state) and state.get('action', 0) > 0

    def max_targets(self):
        return max(1, int(self.source.cha_mod() or 0))

    def label(self):
        uses = getattr(self.source, 'channel_divinity_count', 0)
        return f"Channel Divinity: Abjure Foes ({uses})"

    def __str__(self):
        return "AbjureFoes"

    __repr__ = __str__

    def build_map(self):
        def set_target(target):
            self.target = target
            return self

        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': self.max_targets(),
                'range': ABJURE_FOES_RANGE,
                'unique_targets': True,
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    @staticmethod
    def build(session, source):
        return AbjureFoesAction(session, source, 'abjure_foes').build_map()

    def _targets(self):
        targets = self.target if isinstance(self.target, (list, tuple)) else [self.target]
        seen = []
        for target in targets:
            if target is not None and target is not self.source and target not in seen:
                seen.append(target)
        return seen[:self.max_targets()]

    def resolve(self, session, battle_map=None, opts=None):
        battle = (opts or {}).get('battle')
        if battle_map is None and battle is not None:
            battle_map = battle.map_for(self.source)
        dc = self.source.spell_save_dc('charisma')
        results = []
        for target in self._targets():
            if target.dead():
                continue
            if battle_map is not None:
                try:
                    in_range = battle_map.distance(self.source, target) * battle_map.feet_per_grid <= ABJURE_FOES_RANGE
                    if not in_range or not battle_map.can_see(self.source, target):
                        continue
                except Exception:
                    pass
            roll = target.save_throw('wisdom', battle, {'dc': dc, 'is_magical': True,
                                                       'condition': 'frightened'})
            results.append({
                'type': 'abjure_foes',
                'source': self.source,
                'target': target,
                'roll': roll,
                'dc': dc,
                'success': roll.result() >= dc,
                'battle': battle,
            })
        if not results:
            results.append({'type': 'abjure_foes', 'source': self.source, 'target': None, 'battle': battle})
        results[0]['_consume_resources'] = True
        self.result = results
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'abjure_foes':
            return
        if session is None and battle is not None:
            session = battle.session
        source, target = item['source'], item.get('target')
        frightened = False
        if target is not None and not item.get('success'):
            frightened = apply_fear(target, source, save_dc=f"wisdom:{item['dc']}", duration=60,
                                    ends_on_damage=True, action_limit=True, label='abjure_foes')
        if session is not None:
            session.event_manager.received_event({
                'event': 'abjure_foes',
                'source': source,
                'target': target,
                'roll': item.get('roll'),
                'dc': item.get('dc'),
                'success': item.get('success'),
                'frightened': frightened,
            })
        if item.get('_consume_resources'):
            if hasattr(source, 'channel_divinity'):
                source.channel_divinity()
            if battle is not None:
                battle.consume(source, 'action')


register_class_feature(
    feature_id='abjure_foes',
    action_class=AbjureFoesAction,
)

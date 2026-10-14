"""Taunt (race YAML ``taunt`` block, e.g. Kender).

Bonus action: one creature within range that can hear the taunter makes a
Wisdom save; on a failure it has disadvantage on attack rolls against anyone
but the taunter until the start of the taunter's next turn
(``natural20/utils/taunt.py``). Uses come from a race ``resource_pools`` entry.

    taunt:
      feature: taunt
      pool: taunt
      activation: bonus_action
      range: 60
      save:
        ability: wisdom
        dc_abilities: [int, wis, cha]   # 8 + PB + best of these modifiers
"""

from __future__ import annotations

from natural20.action import Action
from natural20.utils.class_feature_registry import register_class_feature
from natural20.utils import taunt as taunt_utils


def taunt_spec(entity):
    race_props = getattr(entity, 'race_properties', None) or {}
    spec = race_props.get('taunt')
    if not spec:
        spec = (getattr(entity, 'properties', None) or {}).get('taunt')
    return spec if isinstance(spec, dict) else None


class TauntAction(Action):
    def __init__(self, session, source, action_type='taunt', opts=None):
        super().__init__(session, source, action_type, opts)
        self.target = None
        self.as_bonus_action = (self.spec().get('activation', 'bonus_action') == 'bonus_action')

    def spec(self):
        return taunt_spec(self.source) or {}

    def uses_left(self):
        pool = self.spec().get('pool')
        res = self.source.get_resource(pool) if pool else None
        return res.current if res is not None else 0

    def label(self):
        return f"Taunt ({self.uses_left()} left)"

    def button_label(self):
        return self.label()

    def __str__(self):
        return 'Taunt'

    __repr__ = __str__

    @staticmethod
    def can(entity, battle, options=None):
        spec = taunt_spec(entity)
        if not spec:
            return False
        feature = spec.get('feature')
        if feature and not entity.class_feature(feature):
            return False
        pool = spec.get('pool')
        if pool and not entity.has_resource(pool):
            return False
        if battle is not None and battle.entity_state_for(entity) is not None:
            if spec.get('activation', 'bonus_action') == 'bonus_action':
                return entity.total_bonus_actions(battle) > 0
            return entity.total_actions(battle) > 0
        return battle is not None

    def build_map(self):
        def set_target(target):
            action = TauntAction(self.session, self.source, self.action_type, self.opts)
            action.target = target
            return action

        return {
            'action': self,
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': int(self.spec().get('range', 60)),
                'target_types': ['enemies'],
            }],
            'next': set_target,
        }

    @staticmethod
    def build(session, source):
        return TauntAction(session, source, 'taunt').build_map()

    def resolve(self, session, map=None, opts=None):
        battle = (opts or {}).get('battle')
        target = self.target[0] if isinstance(self.target, (list, tuple)) else self.target
        spec = self.spec()
        save = spec.get('save') or {}
        dc = taunt_utils.ability_dc(self.source, save.get('dc_abilities') or ['cha'])
        item = {
            'type': 'taunt', 'source': self.source, 'target': target, 'battle': battle,
            'dc': dc, 'pool': spec.get('pool'),
            'activation': spec.get('activation', 'bonus_action'),
        }
        if target is not None and hasattr(target, 'save_throw'):
            from natural20.utils.combat_comms import can_hear, speech_block_reason
            if speech_block_reason(self.source) or not can_hear(target):
                item['no_effect'] = 'cannot_hear'
            else:
                roll = target.save_throw(save.get('ability', 'wisdom'), battle, {'dc': dc})
                item['roll'] = roll
                item['success'] = roll.result() >= dc
        self.result = [item]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'taunt':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle else source.session
        if battle is not None and battle.entity_state_for(source) is not None:
            battle.consume(source, item.get('activation') or 'bonus_action')
        if item.get('pool'):
            source.consume_resource(item['pool'])
        target = item.get('target')
        taunted = False
        if target is not None and item.get('roll') is not None and not item.get('success'):
            taunted = taunt_utils.apply_taunt(target, source, label='taunt')
        session.event_manager.received_event({
            'event': 'taunt', 'source': source, 'target': target, 'roll': item.get('roll'),
            'dc': item.get('dc'), 'taunted': taunted, 'no_effect': item.get('no_effect'),
        })
        return item


register_class_feature(
    feature_id='taunt',
    action_class=TauntAction,
)

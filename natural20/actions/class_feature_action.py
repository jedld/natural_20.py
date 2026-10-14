"""Simple self-targeted class feature from class YAML ``feature_actions``.

One action is offered per entry; see ``natural20/utils/class_mechanics.py``
for the YAML shape.
"""

from __future__ import annotations

from natural20.action import Action
from natural20.die_roll import DieRoll
from natural20.utils import class_mechanics
from natural20.utils.class_feature_registry import register_class_feature


class ClassFeatureAction(Action):
    def __init__(self, session, source, action_type='class_feature_action', opts=None):
        super().__init__(session, source, action_type, opts)
        self.klass = None
        self.spec = {}

    def feature_id(self):
        return str(self.spec.get('id') or self.spec.get('feature') or 'class_feature')

    def label(self):
        return self.spec.get('label') or self.feature_id().replace('_', ' ').title()

    def button_label(self):
        return self.label()

    def button_image(self):
        return self.spec.get('icon') or self.feature_id()

    def __str__(self):
        return self.label()

    __repr__ = __str__

    def activation(self):
        return str(self.spec.get('activation') or 'action')

    def available(self, battle=None):
        pool = self.spec.get('pool')
        if pool and not self.source.has_resource(pool):
            return False
        if self.spec.get('restore_spell_slots') and not self._slots_to_restore():
            return False
        if self.activation() not in ('action', 'bonus_action'):
            # 1-minute rites and the like can't be performed mid-combat.
            return battle is None or not battle.ongoing()
        if battle is None or battle.entity_state_for(self.source) is None:
            return True
        if self.activation() == 'bonus_action':
            return self.source.total_bonus_actions(battle) > 0
        return self.source.total_actions(battle) > 0

    @staticmethod
    def can(entity, battle, options=None):
        return bool(class_mechanics.class_specs(entity, 'feature_actions'))

    @staticmethod
    def build_all(session, entity, feature_id='class_feature_action'):
        actions = []
        for klass, spec in class_mechanics.class_specs(entity, 'feature_actions'):
            action = ClassFeatureAction(session, entity, feature_id)
            action.klass = klass
            action.spec = spec
            actions.append(action)
        return actions

    def build_map(self):
        return self

    def _slots_to_restore(self):
        """``{level: count}`` regained by ``restore_spell_slots``::

            restore_spell_slots:
              class: warlock     # defaults to the feature's class
              fraction: 0.5      # of the maximum slots, rounded up
              full_with_feature: eldritch_master   # regain all instead
        """
        spec = self.spec.get('restore_spell_slots')
        if not spec:
            return {}
        if not isinstance(spec, dict):
            spec = {}
        klass = spec.get('class') or self.klass
        source = self.source
        slots = (getattr(source, 'spell_slots', None) or {}).get(klass) or {}
        budget_fraction = float(spec.get('fraction', 0.5))
        full_feature = spec.get('full_with_feature')
        if full_feature and source.class_feature(full_feature):
            budget_fraction = 1.0
        out = {}
        for level in sorted(int(l) for l in slots.keys()):
            if level <= 0:
                continue
            try:
                maximum = int(source.max_spell_slots(level, klass) or 0)
            except Exception:
                maximum = 0
            if maximum <= 0:
                continue
            import math
            cap = math.ceil(maximum * budget_fraction)
            missing = maximum - int(slots.get(level, 0) or 0)
            regain = min(cap, missing)
            if regain > 0:
                out[level] = regain
        return out

    def resolve(self, session, map, opts=None):
        battle = (opts or {}).get('battle')
        result = {
            'type': 'class_feature_action',
            'source': self.source,
            'battle': battle,
            'feature': self.feature_id(),
            'label': self.label(),
            'pool': self.spec.get('pool'),
            'activation': self.activation(),
        }
        temp_spec = self.spec.get('temp_hp')
        if temp_spec:
            if not isinstance(temp_spec, dict):
                temp_spec = {'dice': temp_spec}
            roll = DieRoll.roll(str(temp_spec.get('dice') or '0'), battle=battle, entity=self.source,
                                description=self.label())
            bonus = class_mechanics.spec_value(self.source, temp_spec, self.klass, key='bonus')
            result['temp_hp'] = max(0, roll.result() + bonus)
            result['roll'] = roll
        restore = self._slots_to_restore()
        if restore:
            result['restore_slots'] = restore
            result['slot_class'] = (self.spec.get('restore_spell_slots') or {}).get('class') \
                if isinstance(self.spec.get('restore_spell_slots'), dict) else None
            result['slot_class'] = result['slot_class'] or self.klass
        self.result = [result]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'class_feature_action':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle else source.session
        activation = item.get('activation') or 'action'
        if (battle is not None and battle.entity_state_for(source) is not None
                and activation in ('action', 'bonus_action')):
            battle.consume(source, activation)
        if item.get('pool'):
            source.consume_resource(item['pool'])
        if item.get('temp_hp'):
            source.grant_temp_hp(item['temp_hp'], source=item.get('feature'))
        restored = 0
        for level, count in (item.get('restore_slots') or {}).items():
            slots = source.spell_slots.setdefault(item.get('slot_class'), {})
            slots[level] = int(slots.get(level, 0) or 0) + int(count)
            restored += int(count)
        session.event_manager.received_event({
            'event': 'class_feature_action', 'source': source, 'feature': item.get('feature'),
            'label': item.get('label'), 'temp_hp': item.get('temp_hp'), 'roll': item.get('roll'),
            'restored_slots': restored,
        })
        return item


register_class_feature(
    feature_id='class_feature_action',
    action_class=ClassFeatureAction,
    provides=lambda entity: bool(class_mechanics.class_specs(entity, 'feature_actions')),
    builder=ClassFeatureAction.build_all,
)

"""Create an item by spending a spell slot (class YAML ``craft_options``).

One action is offered per craftable item; see ``natural20/utils/class_mechanics.py``
for the YAML shape.
"""

from __future__ import annotations

from natural20.action import Action
from natural20.utils import class_mechanics
from natural20.utils.class_feature_registry import register_class_feature


def _slot_level(entity, klass, min_slot):
    slots = (getattr(entity, 'spell_slots', None) or {}).get(klass) or {}
    for level in sorted(slots):
        if level >= min_slot and slots.get(level, 0) > 0:
            return level
    return None


def craft_options(entity):
    """``(klass, spec, item)`` for every item the entity can craft right now."""
    out = []
    for klass, spec in class_mechanics.class_specs(entity, 'craft_options'):
        if not class_mechanics._has_required_items(entity, spec):
            continue
        if spec.get('cost', 'spell_slot') == 'spell_slot' and \
                _slot_level(entity, klass, int(spec.get('min_slot', 1))) is None:
            continue
        for item in spec.get('items') or []:
            out.append((klass, spec, item))
    return out


class CraftItemAction(Action):
    ai_in_combat = False

    def __init__(self, session, source, action_type='craft_item', opts=None):
        super().__init__(session, source, action_type, opts)
        self.klass = None
        self.spec = {}
        self.item = None

    def _item_label(self):
        try:
            details = self.session.load_equipment(self.item) or {}
        except Exception:
            details = {}
        return details.get('name') or str(self.item).replace('_', ' ').title()

    def label(self):
        item_label = self._item_label()
        prefix = self.spec.get('label') or 'Craft'
        if prefix.lower() in item_label.lower():
            prefix = 'Craft'
        return f"{prefix}: {item_label}"

    def button_label(self):
        return self.label()

    def button_image(self):
        return self.spec.get('icon') or 'craft_item'

    def __str__(self):
        return self.label()

    __repr__ = __str__

    def activation(self):
        return str(self.spec.get('activation') or 'action')

    def available(self, battle=None):
        if battle is None or battle.entity_state_for(self.source) is None:
            return True
        if self.activation() == 'bonus_action':
            return self.source.total_bonus_actions(battle) > 0
        return self.source.total_actions(battle) > 0

    @staticmethod
    def can(entity, battle, options=None):
        return bool(craft_options(entity))

    @staticmethod
    def build_all(session, entity, feature_id='craft_item'):
        actions = []
        for klass, spec, item in craft_options(entity):
            action = CraftItemAction(session, entity, feature_id)
            action.klass = klass
            action.spec = spec
            action.item = item
            actions.append(action)
        return actions

    def build_map(self):
        return self

    def resolve(self, session, map, opts=None):
        battle = (opts or {}).get('battle')
        slot_level = None
        if self.spec.get('cost', 'spell_slot') == 'spell_slot':
            slot_level = _slot_level(self.source, self.klass, int(self.spec.get('min_slot', 1)))
            if slot_level is None:
                self.result = []
                return self
        self.result = [{
            'type': 'craft_item',
            'source': self.source,
            'battle': battle,
            'item': self.item,
            'klass': self.klass,
            'slot_level': slot_level,
            'ledger': self.spec.get('id') or self.spec.get('feature'),
            'activation': self.activation(),
        }]
        return self

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'craft_item':
            return None
        source = item['source']
        if session is None:
            session = battle.session if battle else source.session
        if battle is not None and battle.entity_state_for(source) is not None:
            battle.consume(source, item.get('activation') or 'action')
        if item.get('slot_level'):
            source.consume_spell_slot(item['slot_level'], character_class=item.get('klass'))
        class_mechanics.give_crafted_item(source, item['item'], item.get('ledger'))
        session.event_manager.received_event({
            'event': 'craft_item', 'source': source, 'item': item['item'],
            'slot_level': item.get('slot_level'),
        })
        return item


register_class_feature(
    feature_id='craft_item',
    action_class=CraftItemAction,
    provides=lambda entity: bool(class_mechanics.class_specs(entity, 'craft_options')),
    builder=CraftItemAction.build_all,
)

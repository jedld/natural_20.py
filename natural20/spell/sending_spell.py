"""Sending — a short telepathic message (25 words) to a familiar creature.

Only creatures on the same map can be picked, and the exchange is logged as a
``sending`` event (the message text comes from ``spell_action.message`` when
the caller sets it). Creatures with INT 0 or 1 understand only the sender's
identity, not the words.
"""

from __future__ import annotations

from natural20.spell.spell import Spell
from natural20.utils.target_validation import add_validation_issue


class SendingSpell(Spell):
    SPELL_ID = 'sending'
    TARGET_TYPES = ['allies', 'enemies']

    def build_map(self, orig_action):
        def set_target(target):
            action = orig_action.clone()
            action.target = target
            return action

        return {
            'param': [{
                'type': 'select_target',
                'num': 1,
                'range': self.properties.get('range', 5280),
                'target_types': self.properties.get('target_types') or self.TARGET_TYPES,
            }],
            'next': set_target,
        }

    def validate(self, battle_map, target=None, battle=None):
        super().validate(battle_map, target, battle=battle)
        if target is None:
            add_validation_issue(self, 'validation.targeting.required')
        elif target is self.source:
            add_validation_issue(self, 'validation.targeting.self')

    def resolve(self, entity, battle, spell_action, battle_map):
        target = spell_action.target
        if target is None or target is entity:
            return []
        return [{
            'type': 'sending',
            'source': entity,
            'target': target,
            'message': getattr(spell_action, 'message', None),
            'spell': self.properties,
        }]

    @staticmethod
    def apply(battle, item, session=None):
        if item.get('type') != 'sending':
            return None
        if session is None and battle is not None:
            session = battle.session
        target = item['target']
        understood = int(target.ability_scores.get('int', 10) or 0) > 1 if hasattr(target, 'ability_scores') else True
        if session is not None:
            session.event_manager.received_event({
                'event': 'sending',
                'source': item['source'],
                'target': target,
                'message': item.get('message'),
                'understood': understood,
            })
        return item['source']
